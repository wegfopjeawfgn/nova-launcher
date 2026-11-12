"""Server status check using the modern Minecraft Java "Server List Ping".

Protocol version sent in the handshake: -1 (the value vanilla clients use to
say "I only want the status"; servers answer with their own version info).
SRV records are not resolved.
"""
import ipaddress
import json
import re
import socket
import struct
import time

import servidores

DEFAULT_PORT = 25565
PROTOCOL_VERSION = -1
MAX_STATUS_BYTES = 128 * 1024
_COLOR_CODES = re.compile("§.")


class _ProtocolError(Exception):
    pass


def encode_varint(number):
    number &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = number & 0x7F
        number >>= 7
        if number:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(source):
    """Read a VarInt (max 5 bytes) from a socket-like object (recv) or a
    file-like object (read). Returns a signed 32-bit int."""
    getter = source.recv if hasattr(source, "recv") else source.read
    result = 0
    for index in range(5):
        chunk = getter(1)
        if not chunk:
            raise _ProtocolError("Conexión cerrada.")
        byte = chunk[0]
        result |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            if result & 0x80000000:
                result -= 1 << 32
            return result
    raise _ProtocolError("VarInt demasiado largo.")


def is_public_address(ip_str):
    try:
        ip = ipaddress.ip_address(str(ip_str).split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified):
        return False
    return ip.is_global


def _packet(packet_id, payload=b""):
    body = encode_varint(packet_id) + payload
    return encode_varint(len(body)) + body


def _read_exact(sock, size, deadline):
    data = bytearray()
    while len(data) < size:
        _arm(sock, deadline)
        chunk = sock.recv(min(4096, size - len(data)))
        if not chunk:
            raise _ProtocolError("Conexión cerrada.")
        data += chunk
    return bytes(data)


def _arm(sock, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise socket.timeout("timeout")
    sock.settimeout(remaining)


class _Reader:
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline

    def recv(self, size):
        _arm(self.sock, self.deadline)
        return self.sock.recv(size)


def _read_packet(sock, deadline, limit):
    length = read_varint(_Reader(sock, deadline))
    if length < 1 or length > limit:
        raise _ProtocolError("Tamaño de paquete inválido.")
    data = _read_exact(sock, length, deadline)
    reader = _Slice(data)
    return read_varint(reader), data[reader.pos:]


class _Slice:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, size):
        chunk = self.data[self.pos:self.pos + size]
        self.pos += len(chunk)
        return chunk


def _flatten_motd(description):
    parts = []

    def walk(node, depth=0):
        if depth > 32:
            return
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str):
                parts.append(text)
            for child in node.get("extra") or []:
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1)

    walk(description)
    return _COLOR_CODES.sub("", "".join(parts)).strip()


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _query(ip, port, host, timeout):
    deadline = time.monotonic() + timeout
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        host_bytes = host.encode("utf-8")
        handshake = (encode_varint(PROTOCOL_VERSION) + encode_varint(len(host_bytes))
                     + host_bytes + struct.pack(">H", port) + encode_varint(1))
        _arm(sock, deadline)
        sock.sendall(_packet(0x00, handshake) + _packet(0x00))
        started = time.monotonic()
        packet_id, payload = _read_packet(sock, deadline, MAX_STATUS_BYTES + 16)
        latency = int((time.monotonic() - started) * 1000)
        if packet_id != 0x00:
            raise _ProtocolError("Respuesta inesperada.")
        reader = _Slice(payload)
        size = read_varint(reader)
        raw = payload[reader.pos:]
        if size < 0 or size > MAX_STATUS_BYTES or len(raw) < size:
            raise _ProtocolError("Respuesta inválida.")
        try:
            status = json.loads(raw[:size].decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise _ProtocolError("Respuesta mal formada.")
        if not isinstance(status, dict):
            raise _ProtocolError("Respuesta mal formada.")
        try:
            token = int(time.monotonic() * 1000) & 0x7FFFFFFFFFFFFFFF
            ping_start = time.monotonic()
            sock.sendall(_packet(0x01, struct.pack(">q", token)))
            pong_id, pong = _read_packet(sock, deadline, 16)
            if pong_id == 0x01 and pong == struct.pack(">q", token):
                latency = int((time.monotonic() - ping_start) * 1000)
        except (OSError, _ProtocolError):
            pass
    return status, latency


def check_server(address, *, timeout=3.0, allow_private=False, resolver=None):
    try:
        host, port = servidores.address_parts(address)
    except ValueError:
        return {"state": "invalido", "reason": "La dirección no es válida."}
    port = int(port) if port else DEFAULT_PORT
    if host.startswith("["):
        host = host[1:-1]
    try:
        infos = (resolver or socket.getaddrinfo)(host, port, 0, socket.SOCK_STREAM)
        ips = [info[4][0] for info in infos]
    except (OSError, UnicodeError):
        return {"state": "sin_respuesta", "reason": "No se pudo resolver el nombre."}
    if not ips:
        return {"state": "sin_respuesta", "reason": "No se pudo resolver el nombre."}
    if not allow_private and not all(is_public_address(ip) for ip in ips):
        return {"state": "no_verificable",
                "reason": "La dirección apunta a una red privada o reservada."}
    ip = ips[0].split("%", 1)[0]
    try:
        status, latency = _query(ip, port, host, timeout)
    except socket.timeout:
        return {"state": "sin_respuesta", "reason": "Tiempo de espera agotado."}
    except _ProtocolError:
        return {"state": "sin_respuesta", "reason": "Respuesta inválida del servidor."}
    except OSError:
        return {"state": "sin_respuesta", "reason": "No se pudo conectar."}
    players = status.get("players") if isinstance(status.get("players"), dict) else {}
    version = status.get("version") if isinstance(status.get("version"), dict) else {}
    name = version.get("name")
    return {
        "state": "online",
        "latency_ms": latency,
        "players_online": _int(players.get("online")),
        "players_max": _int(players.get("max")),
        "version": name if isinstance(name, str) else "",
        "motd": _flatten_motd(status.get("description", "")),
        "protocol": _int(version.get("protocol")),
    }


def describe(result):
    """One line for the server list. It only states what the check actually found."""
    state = result.get("state")
    if state == "online":
        parts = ["En línea", f"{result.get('players_online', 0)}/{result.get('players_max', 0)} jugadores",
                 f"{result.get('latency_ms', 0)} ms"]
        if result.get("version"):
            parts.append(str(result["version"]))
        return " · ".join(parts)
    if state == "no_verificable":
        return "No se puede comprobar desde Nova (red local o privada)"
    if state == "invalido":
        return "Dirección inválida"
    return "Sin respuesta"

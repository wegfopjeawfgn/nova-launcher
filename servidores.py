"""Read Minecraft's server list and validate direct-connect addresses."""
import gzip
import io
import ipaddress
import re
import struct


def address_parts(address):
    address = address.strip()
    match = re.fullmatch(r"(\[[0-9a-fA-F:.]+\]|[a-zA-Z0-9_.-]+)(?::([0-9]{1,5}))?", address)
    if not match or len(address) > 260 or address.startswith("-"):
        raise ValueError("Ingresá una dirección como ejemplo.net o ejemplo.net:25565.")
    host, port = match.groups()
    if host.startswith("["):
        ipaddress.IPv6Address(host[1:-1])
    if port and not 1 <= int(port) <= 65535:
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    return host, port


def saved_servers(path):
    if not path.exists():
        return []
    limit = 16 * 1024**2
    with path.open("rb") as source:
        signature = source.read(2)
        source.seek(0)
        if signature == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=source) as compressed:
                data = compressed.read(limit + 1)
        else:
            data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("La lista de servidores supera los 16 MiB.")
    stream = io.BytesIO(data)

    def take(size):
        result = stream.read(size)
        if len(result) != size:
            raise ValueError("La lista de servidores está incompleta.")
        return result

    def number(code):
        return struct.unpack(">" + code, take(struct.calcsize(code)))[0]

    def string():
        return take(number("H")).decode("utf-8", errors="replace")

    def payload(kind, depth):
        if depth > 24:
            raise ValueError("La lista de servidores está demasiado anidada.")
        if kind == 8:
            return string()
        if kind == 10:
            fields = {}
            while tag := number("B"):
                name = string()
                fields[name] = payload(tag, depth + 1)
            return fields
        if kind == 9:
            tag, count = number("B"), number("i")
            if not 0 <= count <= 10000:
                raise ValueError("La lista de servidores contiene demasiadas entradas.")
            return [payload(tag, depth + 1) for _ in range(count)]
        widths = {1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}
        if kind in widths:
            take(widths[kind])
        elif kind in (7, 11, 12):
            count = number("i")
            if count < 0:
                raise ValueError("La lista de servidores tiene un tamaño inválido.")
            take(count * {7: 1, 11: 4, 12: 8}[kind])
        else:
            raise ValueError("La lista de servidores tiene un formato desconocido.")
        return None

    if number("B") != 10:
        raise ValueError("La lista de servidores de Minecraft no es válida.")
    string()
    entries = payload(10, 0).get("servers")
    return [(entry.get("name") or entry["ip"], entry["ip"])
            for entry in entries or () if isinstance(entry, dict)
            and isinstance(entry.get("ip"), str) and isinstance(entry.get("name", ""), str)]

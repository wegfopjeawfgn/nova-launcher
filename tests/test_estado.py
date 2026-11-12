from pathlib import Path
import io
import json
import socket
import struct
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import estado  # noqa: E402


def recv_packet(conn):
    length = estado.read_varint(conn)
    data = b""
    while len(data) < length:
        data += conn.recv(length - len(data))
    return data


def packet(packet_id, payload=b""):
    body = estado.encode_varint(packet_id) + payload
    return estado.encode_varint(len(body)) + body


def status_packet(obj):
    raw = json.dumps(obj).encode()
    return packet(0, estado.encode_varint(len(raw)) + raw)


class FakeServer:
    def __init__(self, handler):
        self.handler = handler
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        self.sock.settimeout(0.2)
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            try:
                self.handler(conn, self.stop)
            except OSError:
                pass
            finally:
                conn.close()

    def close(self):
        self.stop.set()
        self.thread.join(2)
        self.sock.close()


GOOD = {
    "version": {"name": "Paper 1.21", "protocol": 767},
    "players": {"online": 3, "max": 20},
    "description": {"text": "§aHola ", "extra": [{"text": "mundo", "extra": ["§l!"]}]},
}


def good_handler(conn, stop):
    recv_packet(conn)
    recv_packet(conn)
    conn.sendall(status_packet(GOOD))
    ping = recv_packet(conn)
    conn.sendall(packet(1, ping[1:]))


class CheckServerTests(unittest.TestCase):
    def serve(self, handler):
        server = FakeServer(handler)
        self.addCleanup(server.close)
        return f"127.0.0.1:{server.port}"

    def test_online(self):
        result = estado.check_server(self.serve(good_handler), allow_private=True)
        self.assertEqual(result["state"], "online")
        self.assertEqual(result["players_online"], 3)
        self.assertEqual(result["players_max"], 20)
        self.assertEqual(result["version"], "Paper 1.21")
        self.assertEqual(result["protocol"], 767)
        self.assertEqual(result["motd"], "Hola mundo!")
        self.assertIsInstance(result["latency_ms"], int)

    def test_online_without_pong_uses_status_time(self):
        def handler(conn, stop):
            recv_packet(conn)
            recv_packet(conn)
            conn.sendall(status_packet(GOOD))
        result = estado.check_server(self.serve(handler), allow_private=True)
        self.assertEqual(result["state"], "online")

    def test_garbage(self):
        def handler(conn, stop):
            recv_packet(conn)
            conn.sendall(b"\x05\x00\x03abc")
        result = estado.check_server(self.serve(handler), allow_private=True, timeout=1)
        self.assertEqual(result["state"], "sin_respuesta")

    def test_not_json(self):
        def handler(conn, stop):
            recv_packet(conn)
            conn.sendall(packet(0, estado.encode_varint(3) + b"abc"))
        result = estado.check_server(self.serve(handler), allow_private=True, timeout=1)
        self.assertEqual(result["state"], "sin_respuesta")

    def test_silent_server_times_out(self):
        def handler(conn, stop):
            stop.wait(1.5)
        result = estado.check_server(self.serve(handler), allow_private=True, timeout=0.3)
        self.assertEqual(result["state"], "sin_respuesta")

    def test_giant_packet_rejected(self):
        def handler(conn, stop):
            recv_packet(conn)
            conn.sendall(estado.encode_varint(50 * 1024 * 1024))
            stop.wait(1.5)
        result = estado.check_server(self.serve(handler), allow_private=True, timeout=1)
        self.assertEqual(result["state"], "sin_respuesta")

    def test_connection_refused(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        result = estado.check_server(f"127.0.0.1:{port}", allow_private=True, timeout=1)
        self.assertEqual(result["state"], "sin_respuesta")

    def test_invalid_address(self):
        for bad in ("", "-x", "host:99999", "a b"):
            self.assertEqual(estado.check_server(bad)["state"], "invalido")


class SsrfTests(unittest.TestCase):
    def fake_resolver(self, *ips):
        calls = []

        def resolver(host, port, *args):
            calls.append(host)
            return [(socket.AF_INET6 if ":" in ip else socket.AF_INET,
                     socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
        resolver.calls = calls
        return resolver

    def test_private_targets_never_connect(self):
        original = socket.create_connection

        def boom(*args, **kwargs):
            raise AssertionError("connection attempted")
        socket.create_connection = boom
        self.addCleanup(setattr, socket, "create_connection", original)
        for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.1.1", "::1",
                   "fe80::1", "0.0.0.0", "224.0.0.1", "::ffff:127.0.0.1"):
            result = estado.check_server("ejemplo.net", resolver=self.fake_resolver(ip))
            self.assertEqual(result["state"], "no_verificable", ip)
            self.assertIn("reason", result)

    def test_mixed_public_and_private_rejected(self):
        original = socket.create_connection
        socket.create_connection = lambda *a, **k: self.fail("connected")
        self.addCleanup(setattr, socket, "create_connection", original)
        result = estado.check_server("ejemplo.net", resolver=self.fake_resolver("93.184.216.34", "10.0.0.5"))
        self.assertEqual(result["state"], "no_verificable")

    def test_connects_to_validated_ip_without_resolving_again(self):
        server = FakeServer(good_handler)
        self.addCleanup(server.close)
        resolver = self.fake_resolver("127.0.0.1")
        result = estado.check_server(f"ejemplo.net:{server.port}", allow_private=True, resolver=resolver)
        self.assertEqual(result["state"], "online")
        self.assertEqual(resolver.calls, ["ejemplo.net"])

    def test_is_public_address(self):
        self.assertTrue(estado.is_public_address("93.184.216.34"))
        self.assertTrue(estado.is_public_address("2606:2800:220:1:248:1893:25c8:1946"))
        for ip in ("127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.0.1", "169.254.169.254",
                   "::1", "fe80::1", "fc00::1", "0.0.0.0", "100.64.0.1", "nope"):
            self.assertFalse(estado.is_public_address(ip), ip)


class HelperTests(unittest.TestCase):
    def test_varint_roundtrip(self):
        for number in (0, 1, 127, 128, 255, 25565, 2097151, 2**31 - 1, -1):
            data = estado.encode_varint(number)
            self.assertLessEqual(len(data), 5)
            self.assertEqual(estado.read_varint(io.BytesIO(data)), number)

    def test_varint_too_long(self):
        with self.assertRaises(Exception):
            estado.read_varint(io.BytesIO(b"\x80" * 6))

    def test_motd_flatten(self):
        motd = {"text": "§cA", "extra": [{"text": "B", "extra": [{"text": "§r C"}]}, "D"]}
        self.assertEqual(estado._flatten_motd(motd), "AB CD")
        self.assertEqual(estado._flatten_motd("§4Rojo"), "Rojo")



class DescribeTests(unittest.TestCase):
    def test_describe_states(self):
        online = {"state": "online", "players_online": 12, "players_max": 100, "latency_ms": 45, "version": "Paper 1.21"}
        self.assertEqual(estado.describe(online), "En línea · 12/100 jugadores · 45 ms · Paper 1.21")
        self.assertEqual(estado.describe({"state": "sin_respuesta"}), "Sin respuesta")
        self.assertIn("red local", estado.describe({"state": "no_verificable"}))
        self.assertEqual(estado.describe({"state": "invalido"}), "Dirección inválida")
        self.assertEqual(estado.describe({}), "Sin respuesta")


if __name__ == "__main__":
    unittest.main()

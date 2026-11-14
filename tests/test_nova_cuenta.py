from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import nova_cuenta  # noqa: E402

TOKEN = "a" * 64
USER = {"username": "Neo", "avatar_emoji": "😎", "avatar_color": "#7c3aed"}


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data
        self.ok = 200 <= status < 300

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())

    def tearDown(self):
        motor.ROOT = self.original

    def test_round_trip_keeps_only_public_profile_and_private_permissions(self):
        self.assertIsNone(nova_cuenta.load())
        nova_cuenta.save(TOKEN, {**USER, "email": "neo@example.com"})
        self.assertEqual(nova_cuenta.load(), {"token": TOKEN, "usuario": {"username": "Neo", "avatar_emoji": "😎"}})
        mode = stat.S_IMODE((motor.ROOT / "nova-cuenta.json").stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertNotIn("email", (motor.ROOT / "nova-cuenta.json").read_text(encoding="utf-8"))
        nova_cuenta.clear()
        self.assertIsNone(nova_cuenta.load())

    def test_rejects_bad_tokens_and_profiles(self):
        with self.assertRaises(nova_cuenta.CuentaError):
            nova_cuenta.save("short", USER)
        with self.assertRaises(nova_cuenta.CuentaError):
            nova_cuenta.save(TOKEN, {"username": ""})
        (motor.ROOT / "nova-cuenta.json").write_text('{"token": "x", "usuario": {}}', encoding="utf-8")
        self.assertIsNone(nova_cuenta.load())


class ServerTests(unittest.TestCase):
    def test_start_only_accepts_pages_on_the_nova_site(self):
        good = {"user_code": "BCDF-GHJK", "device_code": "d" * 64, "interval": 5, "expires_in": 600,
                "verification_uri_complete": nova_cuenta.API + "/conectar?codigo=BCDF-GHJK"}
        with mock.patch.object(nova_cuenta.requests, "post", return_value=Response(200, good)) as post:
            connection = nova_cuenta.start()
        self.assertEqual(connection["codigo"], "BCDF-GHJK")
        self.assertEqual(post.call_args.kwargs["json"], {"accion": "iniciar", "app": "launcher"})
        evil = {**good, "verification_uri_complete": "https://evil.example/conectar?codigo=BCDF-GHJK"}
        with mock.patch.object(nova_cuenta.requests, "post", return_value=Response(200, evil)):
            with self.assertRaises(nova_cuenta.CuentaError):
                nova_cuenta.start()

    def test_server_errors_become_readable_messages(self):
        with mock.patch.object(nova_cuenta.requests, "post", return_value=Response(400, {"error": "App desconocida."})):
            with self.assertRaisesRegex(nova_cuenta.CuentaError, "App desconocida"):
                nova_cuenta.start()
        with mock.patch.object(nova_cuenta.requests, "post", side_effect=nova_cuenta.requests.ConnectionError()):
            with self.assertRaisesRegex(nova_cuenta.CuentaError, "conexión"):
                nova_cuenta.start()

    def test_profile_returns_none_when_revoked(self):
        with mock.patch.object(nova_cuenta.requests, "get", return_value=Response(401, {"error": "venció"})):
            self.assertIsNone(nova_cuenta.profile(TOKEN))
        with mock.patch.object(nova_cuenta.requests, "get", return_value=Response(200, {"usuario": USER})) as get:
            self.assertEqual(nova_cuenta.profile(TOKEN), {"username": "Neo", "avatar_emoji": "😎"})
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer " + TOKEN)

    def test_revoke_never_raises(self):
        with mock.patch.object(nova_cuenta.requests, "post", side_effect=nova_cuenta.requests.Timeout()):
            nova_cuenta.revoke(TOKEN)


class WaitTests(unittest.TestCase):
    connection = {"device_code": "d" * 64, "intervalo": 1, "vence": 60}

    def run_wait(self, answers, cancelled=lambda: False):
        clock = [0.0]
        answers = iter(answers)

        def poll(_):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        def sleep(seconds):
            clock[0] += seconds

        return nova_cuenta.wait_for_approval(self.connection, cancelled, poll=poll, sleep=sleep, clock=lambda: clock[0])

    def test_waits_through_pending_and_network_errors_until_approved(self):
        result = self.run_wait([{"estado": "pendiente"}, nova_cuenta.CuentaError("red"), {"estado": "esperar"},
                                {"estado": "aprobado", "token": TOKEN, "usuario": USER}])
        self.assertEqual(result, ("aprobado", TOKEN, USER))

    def test_reports_denied_and_expired(self):
        self.assertEqual(self.run_wait([{"estado": "rechazado"}]), ("rechazado",))
        self.assertEqual(self.run_wait([{"estado": "expirado"}]), ("expirado",))
        self.assertEqual(self.run_wait([{"estado": "pendiente"}] * 1000), ("expirado",))

    def test_cancel_stops_without_polling(self):
        self.assertEqual(self.run_wait([], cancelled=lambda: True), ("cancelado",))


if __name__ == "__main__":
    unittest.main()

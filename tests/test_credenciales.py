import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import credenciales  # noqa: E402
import motor  # noqa: E402

SESSION = {"id": "abc", "name": "Alex", "access_token": "t", "refresh_token": "r"}


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())

    def tearDown(self):
        motor.ROOT = self.original

    def test_round_trip_and_clear(self):
        self.assertIsNone(credenciales.load_session())
        credenciales.save_session("client", SESSION)
        self.assertEqual(credenciales.load_session(), ("client", SESSION))
        credenciales.clear_session()
        self.assertIsNone(credenciales.load_session())

    @unittest.skipIf(os.name == "nt", "permisos POSIX")
    def test_private_permissions(self):
        credenciales.save_session("client", SESSION)
        mode = stat.S_IMODE((motor.ROOT / "microsoft.json").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_rejects_incomplete_or_damaged(self):
        (motor.ROOT).mkdir(parents=True, exist_ok=True)
        (motor.ROOT / "microsoft.json").write_text("{ nope")
        self.assertIsNone(credenciales.load_session())
        credenciales.save_session("client", {"id": "x"})
        self.assertIsNone(credenciales.load_session())


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        self._env = os.environ.pop("CURSEFORGE_API_KEY", None)

    def tearDown(self):
        motor.ROOT = self.original
        if self._env is not None:
            os.environ["CURSEFORGE_API_KEY"] = self._env

    def test_round_trip_and_clear(self):
        self.assertIsNone(credenciales.load_api_key())
        credenciales.save_api_key("k" * 32)
        self.assertEqual(credenciales.load_api_key(), "k" * 32)
        credenciales.clear_api_key()
        self.assertIsNone(credenciales.load_api_key())

    @unittest.skipIf(os.name == "nt", "permisos POSIX")
    def test_private_permissions(self):
        credenciales.save_api_key("k" * 32)
        self.assertEqual(stat.S_IMODE((motor.ROOT / "curseforge.json").stat().st_mode), 0o600)

    def test_environment_is_a_fallback_and_junk_is_ignored(self):
        os.environ["CURSEFORGE_API_KEY"] = "from-env-" + "x" * 20
        try:
            self.assertEqual(credenciales.load_api_key(), "from-env-" + "x" * 20)
            motor.ROOT.mkdir(parents=True, exist_ok=True)
            (motor.ROOT / "curseforge.json").write_text("{nope")
            self.assertEqual(credenciales.load_api_key(), "from-env-" + "x" * 20)
        finally:
            os.environ.pop("CURSEFORGE_API_KEY", None)
        self.assertIsNone(credenciales.load_api_key())


if __name__ == "__main__":
    unittest.main()

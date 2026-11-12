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


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import uso  # noqa: E402


class UsoTests(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())

    def tearDown(self):
        motor.ROOT = self.original

    def test_payload_has_only_id_version_and_os(self):
        ping = uso.due()
        self.assertEqual(set(ping), {"id", "version", "os"})
        self.assertRegex(ping["id"], r"^[a-f0-9]{32}$")

    def test_a_sent_ping_keeps_the_id_and_waits_a_day(self):
        start = 10 * uso.DAY
        ping = uso.due(now=start)
        with mock.patch("uso.requests.post", return_value=mock.Mock(ok=True)):
            self.assertTrue(uso.send(ping, now=start))
        self.assertIsNone(uso.due(now=start + uso.DAY - 1))
        again = uso.due(now=start + uso.DAY)
        self.assertEqual(again["id"], ping["id"])

    def test_a_failed_ping_is_retried_and_never_raises(self):
        ping = uso.due()
        with mock.patch("uso.requests.post", side_effect=uso.requests.ConnectionError):
            self.assertFalse(uso.send(ping))
        with mock.patch("uso.requests.post", return_value=mock.Mock(ok=False)):
            self.assertFalse(uso.send(ping))
        self.assertIsNotNone(uso.due())

    def test_forget_removes_the_id(self):
        with mock.patch("uso.requests.post", return_value=mock.Mock(ok=True)):
            uso.send(uso.due())
        uso.forget()
        self.assertFalse((motor.ROOT / "uso.json").exists())


if __name__ == "__main__":
    unittest.main()

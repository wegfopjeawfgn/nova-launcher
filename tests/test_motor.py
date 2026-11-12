import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402


class SaveReadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / "data.json"

    def test_round_trip_and_backup(self):
        motor.save(self.path, {"a": 1})
        motor.save(self.path, {"a": 2})
        self.assertEqual(motor.read(self.path, None), {"a": 2})
        self.assertEqual(json.loads((self.folder / "data.json.bak").read_text()), {"a": 1})
        self.assertEqual([p.name for p in self.folder.glob("*.tmp")], [])

    def test_missing_file_returns_default(self):
        self.assertEqual(motor.read(self.path, {"x": 0}), {"x": 0})

    def test_corrupt_file_restores_backup(self):
        motor.save(self.path, {"ok": True})
        motor.save(self.path, {"ok": "newer"})
        self.path.write_text("{ truncated")
        self.assertEqual(motor.read(self.path, {}), {"ok": True})
        self.assertTrue((self.folder / "data.json.corrupt").exists())
        self.assertEqual(json.loads(self.path.read_text()), {"ok": True})

    def test_corrupt_file_without_backup_returns_default(self):
        self.path.write_text("not json")
        self.assertEqual(motor.read(self.path, {"d": 1}), {"d": 1})


class JvmArgsTests(unittest.TestCase):
    def test_accepts_flags(self):
        self.assertEqual(motor.parse_jvm_args("-XX:+UseG1GC -Xms1G"), ["-XX:+UseG1GC", "-Xms1G"])
        self.assertEqual(motor.parse_jvm_args(""), [])

    def test_rejects_non_flags_and_dangerous_options(self):
        for bad in ("hello", "-Xmx8G", "-javaagent:/tmp/x.jar", '-Dx="unclosed'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                motor.parse_jvm_args(bad)


class RotateLogTests(unittest.TestCase):
    def test_keeps_previous_logs(self):
        folder = Path(tempfile.mkdtemp())
        log = folder / "minecraft.log"
        for number in range(5):
            log.write_text(str(number))
            motor.rotate_log(log)
        self.assertFalse(log.exists())
        self.assertEqual((folder / "minecraft.log.1").read_text(), "4")
        self.assertEqual((folder / "minecraft.log.3").read_text(), "2")
        self.assertFalse((folder / "minecraft.log.4").exists())


if __name__ == "__main__":
    unittest.main()

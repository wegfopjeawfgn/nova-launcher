import json
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


class HeapArgumentTests(unittest.TestCase):
    def test_maximum_only_by_default(self):
        self.assertEqual(motor.heap_arguments({"memory": 4}), ["-Xmx4G"])
        self.assertEqual(motor.heap_arguments({"memory": 4, "memory_min": 0}), ["-Xmx4G"])

    def test_valid_minimum_goes_first(self):
        self.assertEqual(motor.heap_arguments({"memory": 6, "memory_min": 2}), ["-Xms2G", "-Xmx6G"])
        self.assertEqual(motor.heap_arguments({"memory": 4, "memory_min": 4}), ["-Xms4G", "-Xmx4G"])

    def test_invalid_minimum_is_ignored(self):
        for bad in (8, -1, True, "2", 2.5, None):
            with self.subTest(bad=bad):
                self.assertEqual(motor.heap_arguments({"memory": 4, "memory_min": bad}), ["-Xmx4G"])

    def test_defaults_include_the_minimum(self):
        self.assertEqual(motor.DEFAULTS["memory_min"], 0)


if __name__ == "__main__":
    unittest.main()

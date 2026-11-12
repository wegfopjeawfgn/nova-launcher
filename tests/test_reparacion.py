import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reparacion  # noqa: E402

GOOD = {"name": "x", "version": "1.21.1", "loader": "vanilla", "memory": 4, "jvm_args": "", "java": ""}


class RepairTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.folder = self.root / "instance"
        (self.folder / "game" / "mods").mkdir(parents=True)
        self.shared = self.root / "minecraft"
        (self.folder / "instance.json").write_text(json.dumps(GOOD))

    def tearDown(self):
        self._tmp.cleanup()

    def install(self, jar=b"data"):
        version = self.shared / "versions" / "1.21.1"
        version.mkdir(parents=True)
        (version / "1.21.1.json").write_text("{}")
        if jar is not None:
            (version / "1.21.1.jar").write_bytes(jar)
        (self.shared / "libraries").mkdir(exist_ok=True)

    def diagnose(self, instance=None, java=(None, 21, 21), memory_mb=16384):
        return reparacion.diagnose(self.folder, {**GOOD, **(instance or {})}, shared=self.shared,
                                   java=lambda: java, memory_mb=memory_mb)

    def ids(self, *args, **kwargs):
        return [(f["id"], f["severity"]) for f in self.diagnose(*args, **kwargs)]

    def test_healthy_instance_only_says_not_installed_yet(self):
        self.assertEqual(self.ids(), [("install", "info")])
        self.install()
        self.assertEqual(self.ids(), [])

    def test_missing_jar_is_an_incomplete_install(self):
        self.install(jar=None)
        self.assertEqual(self.ids(), [("install", "error")])
        (self.shared / "versions" / "1.21.1" / "1.21.1.jar").write_bytes(b"")
        self.assertEqual(self.ids(), [("install", "error")])

    def test_missing_libraries(self):
        self.install()
        (self.shared / "libraries").rmdir()
        self.assertEqual(self.ids(), [("libraries", "error")])

    def test_old_java(self):
        self.install()
        self.assertEqual(self.ids(java=("java", 21, 17)), [("java", "error")])
        self.assertEqual(self.ids(java=("java", 21, 21)), [])

    def test_missing_custom_java(self):
        self.install()
        self.assertEqual(self.ids({"java": str(self.root / "nope")}), [("java", "error")])

    def test_java_check_failure_is_a_warning(self):
        self.install()

        def broken():
            raise OSError("boom")

        found = reparacion.diagnose(self.folder, GOOD, shared=self.shared, java=broken, memory_mb=16384)
        self.assertEqual([(f["id"], f["severity"]) for f in found], [("java", "warning")])

    def test_memory_warnings(self):
        self.install()
        self.assertEqual(self.ids({"memory": 16}, memory_mb=16384), [("memory", "warning")])
        self.assertEqual(self.ids({"memory": 8}, memory_mb=16384), [])
        self.assertEqual(self.ids({"memory": 1, "loader": "fabric"}), [("memory", "warning")])
        self.assertEqual(self.ids({"memory": 16}, memory_mb=0), [])  # unknown RAM: no warning

    def test_invalid_settings_are_repairable(self):
        self.install()
        found = self.diagnose({"memory": 999, "jvm_args": "no-guion"})
        self.assertEqual([(f["id"], f["action"]) for f in found], [("settings", "reset_settings")])
        self.assertIn("RAM", found[0]["meaning"])

    def test_invalid_loader_cannot_be_auto_repaired(self):
        self.install()
        found = self.diagnose({"loader": "magic"})
        self.assertEqual([(f["id"], f["action"]) for f in found], [("settings", None)])

    def test_apply_keeps_a_backup_and_changes_only_bad_fields(self):
        config = self.folder / "instance.json"
        config.write_text(json.dumps({**GOOD, "memory": 500, "jvm_args": "bad", "name": "Mi mundo"}))
        changes = reparacion.apply("reset_settings", self.folder)
        self.assertEqual(len(changes), 2)
        saved = json.loads(config.read_text())
        self.assertEqual((saved["memory"], saved["jvm_args"], saved["name"]), (4, "", "Mi mundo"))
        backups = list(self.folder.glob("instance.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text())["memory"], 500)

    def test_apply_does_nothing_when_settings_are_fine(self):
        self.assertEqual(reparacion.apply("reset_settings", self.folder), [])
        self.assertEqual(list(self.folder.glob("instance.json.bak-*")), [])

    def test_unknown_action(self):
        with self.assertRaises(ValueError):
            reparacion.apply("format_disk", self.folder)

    def test_partial_downloads_are_reported_not_deleted(self):
        self.install()
        partial = self.folder / "game" / "mods" / "big.jar.part"
        partial.write_bytes(b"x")
        found = self.diagnose()
        self.assertEqual([f["id"] for f in found], ["partial"])
        self.assertTrue(partial.exists())

    def test_physical_memory_is_a_positive_number_or_none(self):
        value = reparacion.physical_memory_mb()
        self.assertTrue(value is None or value > 0)


if __name__ == "__main__":
    unittest.main()

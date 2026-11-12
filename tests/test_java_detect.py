import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import java_detect  # noqa: E402
import motor  # noqa: E402


def fake_java(path, version="21.0.2", vendor="Temurin", ok=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (f'#!/bin/sh\necho \'openjdk version "{version}" 2024-01-16\' >&2\n'
            f'echo \'OpenJDK Runtime Environment {vendor}-{version}\' >&2\n') if ok else "#!/bin/sh\nexit 3\n"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@unittest.skipIf(os.name == "nt", "usa scripts de shell")
class JavaDetectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(motor, "ROOT", self.root / "data")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_inspect_reads_major_and_vendor(self):
        info = java_detect.inspect(fake_java(self.root / "a" / "bin" / "java"))
        self.assertEqual((info["major"], info["vendor"]), (21, "Temurin"))

    def test_old_style_version_numbers(self):
        info = java_detect.inspect(fake_java(self.root / "b" / "bin" / "java", version="1.8.0_402"))
        self.assertEqual(info["major"], 8)

    def test_broken_or_missing_java_is_ignored(self):
        self.assertIsNone(java_detect.inspect(fake_java(self.root / "c" / "bin" / "java", ok=False)))
        self.assertIsNone(java_detect.inspect(self.root / "nope"))
        text = self.root / "d" / "bin" / "java"
        text.parent.mkdir(parents=True)
        text.write_text("#!/bin/sh\necho hello\n")
        text.chmod(0o755)
        self.assertIsNone(java_detect.inspect(text))

    def test_find_java_sorts_newest_first(self):
        paths = [fake_java(self.root / "j8" / "bin" / "java", "1.8.0_1"),
                 fake_java(self.root / "j21" / "bin" / "java", "21.0.1"),
                 fake_java(self.root / "j17" / "bin" / "java", "17.0.9")]
        self.assertEqual([i["major"] for i in java_detect.find_java(paths=paths)], [21, 17, 8])

    def test_candidates_come_from_known_places_and_have_no_duplicates(self):
        home = self.root / "home"
        fake_java(home / ".jdks" / "temurin-21" / "bin" / "java")
        fake_java(motor.ROOT / "minecraft" / "runtime" / "java-runtime-delta" / "linux" / "java-runtime-delta" / "bin" / "java")
        java_home = fake_java(self.root / "jh" / "bin" / "java")
        with mock.patch.object(java_detect.shutil, "which", return_value=str(java_home)):
            found = java_detect.candidate_paths(home=home, environ={"JAVA_HOME": str(self.root / "jh")}, system_roots=[])
        names = [str(p) for p in found]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn(str(java_home), names)
        self.assertTrue(any(".jdks" in n for n in names))
        self.assertTrue(any("java-runtime-delta" in n for n in names))

    def test_non_executable_files_are_skipped(self):
        home = self.root / "home"
        path = fake_java(home / ".jdks" / "x" / "bin" / "java")
        path.chmod(0o644)
        with mock.patch.object(java_detect.shutil, "which", return_value=None):
            self.assertEqual(java_detect.candidate_paths(home=home, environ={}, system_roots=[]), [])

    def test_label_marks_old_versions(self):
        info = {"path": "/x/java", "major": 8, "vendor": "Zulu"}
        self.assertIn("demasiado antiguo", java_detect.label(info, required=21))
        self.assertNotIn("demasiado antiguo", java_detect.label(info, required=8))
        self.assertTrue(java_detect.label({"path": "/y", "major": 21, "vendor": ""}).startswith("Java 21 ·"))


if __name__ == "__main__":
    unittest.main()

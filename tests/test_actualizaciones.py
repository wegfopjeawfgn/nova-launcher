from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actualizaciones  # noqa: E402
from nova_version import NOVA_VERSION  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_numeric_version(self):
        self.assertEqual(actualizaciones.numeric_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(actualizaciones.numeric_version("1.2"), (1, 2, 0))
        self.assertIsNone(actualizaciones.numeric_version("v1.2.3-beta"))
        self.assertIsNone(actualizaciones.numeric_version("latest"))

    def test_single_version_source(self):
        self.assertEqual(actualizaciones.VERSION, NOVA_VERSION)
        spec = (Path(__file__).resolve().parent.parent / "nova-launcher.spec").read_text()
        self.assertIn(f"Version:        {NOVA_VERSION}", spec)


class RepositoryTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(actualizaciones.repository("https://github.com/a/b/"), "a/b")
        self.assertEqual(actualizaciones.repository(""), "")

    def test_invalid(self):
        for bad in ("a", "a/..", "-a/b", "a/b/c", "a b/c"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                actualizaciones.repository(bad)


if __name__ == "__main__":
    unittest.main()

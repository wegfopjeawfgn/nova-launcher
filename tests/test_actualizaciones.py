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


class ChannelTests(unittest.TestCase):
    releases = [
        {"tag_name": "v9.0.0", "prerelease": True},
        {"tag_name": "v8.0.0", "draft": True},
        {"tag_name": "v7.1.0"},
        {"tag_name": "nightly"},
    ]

    def test_stable_skips_prereleases_and_drafts(self):
        self.assertEqual(actualizaciones.newest(self.releases, False)[0], (7, 1, 0))

    def test_beta_includes_prereleases(self):
        self.assertEqual(actualizaciones.newest(self.releases, True)[0], (9, 0, 0))

    def test_none_when_empty(self):
        self.assertEqual(actualizaciones.newest([], True), (None, None))


if __name__ == "__main__":
    unittest.main()

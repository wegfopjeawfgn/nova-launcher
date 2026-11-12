from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class LicenseTests(unittest.TestCase):
    def test_license_is_the_gpl_v3_text(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", text)
        self.assertIn("Version 3, 29 June 2007", text)
        self.assertGreater(len(text), 30000)

    def test_spec_declares_the_license_and_ships_the_files(self):
        spec = (ROOT / "nova-launcher.spec").read_text(encoding="utf-8")
        self.assertIn("License:        GPL-3.0-or-later AND BSD-2-Clause", spec)
        self.assertIn("%license LICENSE THIRD_PARTY_LICENSES.md", spec)

    def test_third_party_notice_keeps_the_bsd_copyright(self):
        text = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("minecraft-launcher-lib", text)
        self.assertIn("Copyright (c)", text)
        self.assertIn("Redistributions in binary form must reproduce", text)

    def test_installers_carry_the_license(self):
        windows = (ROOT / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
        self.assertIn("cp LICENSE THIRD_PARTY_LICENSES.md", windows)
        flatpak = (ROOT / "packaging" / "flatpak" / "io.nova.launcher.yml").read_text(encoding="utf-8")
        self.assertIn("LICENSE THIRD_PARTY_LICENSES.md", flatpak)

    def test_docs_mention_the_license_and_windows_checks(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("GPL-3.0-or-later", readme)
        self.assertIn("Get-FileHash", readme)
        self.assertTrue((ROOT / "packaging" / "windows" / "FIRMA.md").is_file())


if __name__ == "__main__":
    unittest.main()

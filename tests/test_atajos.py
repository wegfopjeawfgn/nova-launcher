import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import atajos  # noqa: E402

IDENT = "0123456789abcdef0123456789abcdef"


class ShortcutTests(unittest.TestCase):
    def test_valid_ids(self):
        self.assertTrue(atajos.valid_instance_id(IDENT))
        for bad in ("", "../x", IDENT + "0", IDENT.upper(), None, "g" * 32):
            with self.subTest(bad=bad):
                self.assertFalse(atajos.valid_instance_id(bad))

    def test_entry_is_single_line_fields_and_quoted(self):
        text = atajos.desktop_entry(IDENT, 'Mi "mundo"\nExec=evil $HOME %f', Path("/opt/Nova App/nova"))
        lines = text.splitlines()
        self.assertEqual(sum(line.startswith("Exec=") for line in lines), 1)
        exec_line = next(line for line in lines if line.startswith("Exec="))
        self.assertEqual(exec_line, f'Exec="/opt/Nova App/nova" --jugar {IDENT}')
        self.assertNotIn("evil\n", text)
        self.assertEqual(lines[0], "[Desktop Entry]")

    def test_quote_escapes_specials(self):
        self.assertEqual(atajos._quote('a"b$c`d\\e%f'), '"a\\"b\\$c\\`d\\\\e%%f"')

    def test_rejects_bad_id(self):
        with self.assertRaises(ValueError):
            atajos.desktop_entry("../../etc", "x", Path("/x"))

    @unittest.skipIf(os.name == "nt", "solo Linux")
    def test_create_and_remove(self):
        home = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = home
        try:
            folder = Path(home) / "instances" / IDENT
            path = atajos.create(folder, "Survival", Path("/usr/bin/nova-launcher"))
            self.assertTrue(path.is_file())
            self.assertIn("--jugar " + IDENT, path.read_text())
            self.assertTrue(os.access(path, os.X_OK))
            atajos.remove(folder)
            self.assertFalse(path.exists())
        finally:
            del os.environ["XDG_DATA_HOME"]


if __name__ == "__main__":
    unittest.main()

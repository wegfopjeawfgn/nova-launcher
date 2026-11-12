import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import i18n  # noqa: E402


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("es")

    def test_spanish_is_the_source_language(self):
        self.assertEqual(i18n.set_language("es"), "es")
        self.assertEqual(i18n.tr("Instancias"), "Instancias")

    def test_english_catalog_translates_known_texts_and_keeps_the_rest(self):
        self.assertIn("en", i18n.available())
        self.assertEqual(i18n.set_language("en"), "en")
        self.assertEqual(i18n.tr("Instancias"), "Instances")
        self.assertEqual(i18n.tr("Un texto sin traducir"), "Un texto sin traducir")

    def test_unknown_language_falls_back(self):
        i18n.set_language("en")
        self.assertEqual(i18n.set_language("xx"), "es")
        self.assertEqual(i18n.tr("Instancias"), "Instancias")

    def test_damaged_or_hostile_catalogs_never_raise(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "fr.json").write_text("{no json")
            (Path(folder) / "de.json").write_text(json.dumps({"a": "b", "c": 5, "d": "", 7: "x"}))
            (Path(folder) / "../x.json" if False else Path(folder) / "pt.json").write_text("[]")
            with mock.patch.object(i18n, "LOCALES", Path(folder)):
                self.assertEqual(i18n.set_language("fr"), "es")
                self.assertEqual(i18n.set_language("pt"), "es")
                self.assertEqual(i18n.set_language("de"), "de")
                self.assertEqual((i18n.tr("a"), i18n.tr("c"), i18n.tr("d")), ("b", "c", "d"))

    def test_language_code_cannot_escape_the_locales_folder(self):
        self.assertEqual(i18n.set_language("../README"), "es")

    def test_every_english_key_is_a_real_spanish_string_used_in_the_app(self):
        data = json.loads((i18n.LOCALES / "en.json").read_text(encoding="utf-8"))
        source = "".join(p.read_text(encoding="utf-8") for p in i18n.HERE.glob("*.py"))
        missing = [key for key in data if key not in source]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()

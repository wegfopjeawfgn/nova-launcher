from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tiempo  # noqa: E402


class PlaytimeTests(unittest.TestCase):
    def test_add_accumulates_and_ignores_empty_sessions(self):
        library = {}
        tiempo.add(library, "a", 90)
        tiempo.add(library, "a", 30)
        tiempo.add(library, "b", 0)
        tiempo.add(library, "b", -5)
        self.assertEqual(tiempo.of(library, "a"), 120)
        self.assertEqual(tiempo.of(library, "b"), 0)
        self.assertEqual(tiempo.total(library), 120)

    def test_short_formats(self):
        self.assertEqual(tiempo.short(0), "Sin jugar")
        self.assertEqual(tiempo.short(30), "Menos de 1 min")
        self.assertEqual(tiempo.short(45 * 60), "45 min")
        self.assertEqual(tiempo.short(3600 * 12 + 60 * 5), "12 h 05 min")

    def test_ignores_damaged_library(self):
        self.assertEqual(tiempo.total({"playtime": {"a": 10, "b": "20"}}), 30)


if __name__ == "__main__":
    unittest.main()

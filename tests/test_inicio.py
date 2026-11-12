from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inicio  # noqa: E402

NOW = 1_800_000_000


def cards(**kwargs):
    base = dict(recent={}, names={}, now=NOW, downloading=False, queued=0, account=None, update=None)
    return {c["key"]: c["text"] for c in inicio.summary(**{**base, **kwargs})}


class HomeTests(unittest.TestCase):
    def test_ago(self):
        self.assertEqual(inicio.ago(5), "hace un momento")
        self.assertEqual(inicio.ago(90), "hace 1 min")
        self.assertEqual(inicio.ago(3 * 3600), "hace 3 h")
        self.assertEqual(inicio.ago(86400), "hace 1 día")
        self.assertEqual(inicio.ago(3 * 86400), "hace 3 días")
        self.assertEqual(inicio.ago(-50), "hace un momento")

    def test_last_game_is_the_most_recent_known_instance(self):
        text = cards(recent={"a": NOW - 7200, "b": NOW - 60, "gone": NOW - 1}, names={"a": "Uno", "b": "Dos"})
        self.assertEqual(text["last"], "Dos · hace 1 min")

    def test_no_games_or_bad_data(self):
        self.assertEqual(cards()["last"], "Todavía no jugaste")
        self.assertEqual(cards(recent={"a": "x", "b": True}, names={"a": "A", "b": "B"})["last"], "Todavía no jugaste")

    def test_downloads(self):
        self.assertEqual(cards()["downloads"], "Sin descargas")
        self.assertEqual(cards(downloading=True)["downloads"], "1 en curso")
        self.assertEqual(cards(downloading=True, queued=2)["downloads"], "1 en curso · 2 en cola")
        self.assertEqual(cards(queued=1)["downloads"], "1 en cola")

    def test_account_and_update(self):
        self.assertEqual(cards(account=("microsoft", "Alex"))["account"], "Microsoft · Alex")
        self.assertEqual(cards(account=("offline", "Alex"))["account"], "Sin conexión · Alex")
        self.assertEqual(cards()["account"], "Sin cuenta: elegí un nombre")
        self.assertEqual(cards()["nova"], "Al día")
        self.assertEqual(cards(update="v9.9.9")["nova"], "Hay una versión nueva: v9.9.9")


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import historial  # noqa: E402


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "history.json"

    def test_start_finish_and_persist(self):
        history = historial.History(self.path)
        first = history.start("import", "Pack A")
        self.assertEqual(history.recent()[0]["state"], "running")
        self.assertTrue(history.finish(first, "error", "sin red"))
        again = historial.History(self.path)
        self.assertEqual(again.recent()[0]["message"], "sin red")
        self.assertEqual(again.recent()[0]["state"], "error")

    def test_running_entries_become_interrupted(self):
        history = historial.History(self.path)
        history.start("update", "Nova 1.1")
        reopened = historial.History(self.path)
        self.assertEqual(reopened.recent()[0]["state"], "interrupted")

    def test_limit_and_order(self):
        history = historial.History(self.path, limit=3)
        for number in range(5):
            history.finish(history.start("import", f"Pack {number}"), "ok", "")
        titles = [entry["title"] for entry in history.recent()]
        self.assertEqual(titles, ["Pack 4", "Pack 3", "Pack 2"])

    def test_clear_keeps_running_and_rejects_bad_state(self):
        history = historial.History(self.path)
        history.finish(history.start("import", "done"), "ok", "")
        running = history.start("import", "busy")
        history.clear_finished()
        self.assertEqual([entry["id"] for entry in history.recent()], [running])
        with self.assertRaises(ValueError):
            history.finish(running, "bogus", "")

    def test_damaged_file_is_ignored(self):
        self.path.write_text("{ nope")
        self.assertEqual(historial.History(self.path).recent(), [])


if __name__ == "__main__":
    unittest.main()

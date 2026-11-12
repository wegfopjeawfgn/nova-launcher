from pathlib import Path
from unittest import mock
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import errores  # noqa: E402
import estadisticas  # noqa: E402
import motor  # noqa: E402


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(motor, "ROOT", self.folder / "root")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = motor.ROOT / "insights.json"

    def add(self, instance="a", seconds=60, **extra):
        return estadisticas.record_session(instance, started_at=1_700_000_000.0, seconds=seconds, **extra)

    def test_accumulates_and_writes_in_root(self):
        self.assertTrue(self.add("a", 30, launch_seconds=2.5))
        self.add("b", 10, ok=False)
        self.assertTrue(self.path.is_file())
        self.assertEqual([p.name for p in motor.ROOT.iterdir() if p.suffix == ".tmp"], [])
        data = motor.read(self.path, [])
        self.assertEqual([s["instance"] for s in data], ["a", "b"])
        self.assertEqual(data[0]["launch"], 2.5)
        self.assertIsNone(data[1]["launch"])
        self.assertFalse(data[1]["ok"])
        self.assertRegex(data[0]["start"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

    def test_save_is_atomic_helper(self):
        with mock.patch.object(motor, "save", wraps=motor.save) as save:
            self.add()
        save.assert_called_once()
        self.assertEqual(save.call_args[0][0], self.path)

    def test_limit_keeps_last(self):
        for number in range(5):
            self.add(f"i{number}", 10, limit=3)
        self.assertEqual([s["instance"] for s in motor.read(self.path, [])], ["i2", "i3", "i4"])

    def test_ignores_short_and_invalid_input(self):
        self.assertFalse(self.add("a", 0.5))
        self.assertFalse(self.add("a/b", 10))
        self.assertFalse(self.add("..\\x", 10))
        self.assertFalse(self.add(5, 10))
        self.assertFalse(self.add("a", float("nan")))
        self.assertFalse(estadisticas.record_session("a", started_at=float("inf"), seconds=5))
        self.assertFalse(self.path.exists())
        self.add("a", 10, launch_seconds=float("nan"))
        self.assertIsNone(motor.read(self.path, [])[0]["launch"])

    def test_damaged_files_never_raise(self):
        self.path.parent.mkdir(parents=True)
        for text in ("{ nope", '{"a": 1}', "42", "null"):
            self.path.write_text(text)
            self.assertEqual(estadisticas.summary()["sessions"], 0)
            self.assertTrue(self.add("a", 5))
            self.assertEqual(estadisticas.summary()["sessions"], 1)
            estadisticas.clear()

    def test_weird_entries_are_skipped(self):
        good = {"instance": "a", "start": "2026-01-01T00:00:00+00:00", "seconds": 5, "launch": None, "ok": True}
        junk = [1, None, "x", {}, {**good, "seconds": "9"}, {**good, "seconds": -1},
                {**good, "instance": "a/b"}, {**good, "launch": "x"}, {**good, "ok": 1},
                {**good, "seconds": True}, {**good, "start": 3}, good]
        motor.save(self.path, junk)
        result = estadisticas.summary()
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(result["total_seconds"], 5)

    def test_summary_per_instance_and_order(self):
        self.add("a", 10)
        self.add("b", 100)
        self.add("a", 20, ok=False)
        result = estadisticas.summary({"b": "Mundo B"})
        self.assertEqual(result["sessions"], 3)
        self.assertEqual(result["total_seconds"], 130)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["per_instance"], [
            {"instance": "b", "name": "Mundo B", "sessions": 1, "seconds": 100},
            {"instance": "a", "name": "a", "sessions": 2, "seconds": 30}])

    def test_average_launch_ignores_none(self):
        self.add("a", 10, launch_seconds=2)
        self.add("a", 10)
        self.add("a", 10, launch_seconds=4)
        self.assertEqual(estadisticas.summary()["average_launch"], 3)
        estadisticas.clear()
        self.add("a", 10)
        self.assertIsNone(estadisticas.summary()["average_launch"])

    def test_recent_is_ten_newest_first(self):
        for number in range(12):
            self.add(f"i{number}", 10)
        recent = estadisticas.summary()["recent"]
        self.assertEqual([s["instance"] for s in recent], [f"i{n}" for n in range(11, 1, -1)])

    def test_empty_summary(self):
        self.assertEqual(estadisticas.summary(), {"sessions": 0, "total_seconds": 0, "average_launch": None,
                                                  "failed": 0, "per_instance": [], "recent": []})

    def test_clear(self):
        self.assertFalse(estadisticas.clear())
        self.add()
        self.assertTrue(estadisticas.clear())
        self.assertFalse(self.path.exists())
        self.assertFalse(estadisticas.clear())

    def test_describe_is_spanish_and_explicit(self):
        text = estadisticas.describe()
        for part in ("fecha y hora de inicio", "duración", "tiempo de arranque",
                     "si terminó bien", "identificador de la instancia", "Nada sale de tu computadora"):
            self.assertIn(part, text)

    def test_recent_errors(self):
        self.assertEqual(estadisticas.recent_errors(), [])
        motor.ROOT.mkdir(parents=True)
        errores.log_path().write_text(
            "[2026-01-01 10:00:00] iniciar\nTraceback (most recent call last):\n"
            '  File "/home/x/a.py", line 1, in f\nValueError: x\n\n'
            "[2026-01-02 11:00:00] descargar\nTraceback\n\n"
            "[2026-01-03 12:00:00] guardar\nOSError\n", encoding="utf-8")
        self.assertEqual(estadisticas.recent_errors(2),
                         ["[2026-01-02 11:00:00] descargar", "[2026-01-03 12:00:00] guardar"])
        self.assertEqual(len(estadisticas.recent_errors()), 3)
        self.assertEqual(estadisticas.recent_errors(0), [])

    def test_system_memory(self):
        result = estadisticas.system_memory_mb()
        self.assertEqual(set(result), {"total", "available"})
        for value in result.values():
            self.assertTrue(value is None or (isinstance(value, int) and value > 0))

    def test_system_memory_never_raises(self):
        with mock.patch("builtins.open", side_effect=OSError), mock.patch.object(estadisticas.sys, "platform", "linux"):
            self.assertEqual(estadisticas.system_memory_mb(), {"total": None, "available": None})


if __name__ == "__main__":
    unittest.main()

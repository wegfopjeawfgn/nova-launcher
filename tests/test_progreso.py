from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import progreso  # noqa: E402


class ProgressTests(unittest.TestCase):
    def test_sizes_and_durations(self):
        self.assertEqual(progreso.size_text(500), "500 B")
        self.assertEqual(progreso.size_text(2048), "2,0 KB")
        self.assertEqual(progreso.size_text(5 * 1024**2), "5,0 MB")
        self.assertEqual(progreso.size_text(3 * 1024**3), "3,0 GB")
        self.assertEqual(progreso.duration_text(9), "9 s")
        self.assertEqual(progreso.duration_text(125), "2 min 05 s")
        self.assertEqual(progreso.duration_text(3725), "1 h 02 min")

    def test_describe_with_speed_and_eta(self):
        text = progreso.describe(10 * 1024**2, 40 * 1024**2, 10)
        self.assertEqual(text, "10,0 MB de 40,0 MB · 1,0 MB/s · 30 s restantes")

    def test_no_eta_without_total_or_time(self):
        self.assertEqual(progreso.describe(1024, None, 0.2), "1,0 KB")
        self.assertNotIn("restantes", progreso.describe(2048, None, 5))

    def test_resumed_bytes_do_not_inflate_the_speed(self):
        text = progreso.describe(10 * 1024**2, 20 * 1024**2, 5, resumed_from=5 * 1024**2)
        self.assertIn("1,0 MB/s", text)
        self.assertIn("10 s restantes", text)


if __name__ == "__main__":
    unittest.main()

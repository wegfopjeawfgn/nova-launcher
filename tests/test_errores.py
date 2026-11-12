from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import errores  # noqa: E402
import motor  # noqa: E402


class ErrorLogTests(unittest.TestCase):
    def test_record_and_report_hide_home(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(motor, "ROOT", Path(folder)):
            try:
                raise ValueError(f"falló {Path.home()}/mundo")
            except ValueError as error:
                errores.record(error, "prueba")
            text = errores.report()
        self.assertIn("prueba", text)
        self.assertIn("ValueError", text)
        self.assertNotIn(str(Path.home()), text)

    def test_report_hides_tokens(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(motor, "ROOT", Path(folder)):
            try:
                raise ValueError("token " + "a" * 50)
            except ValueError as error:
                errores.record(error, "prueba")
            self.assertNotIn("a" * 50, errores.report())

    def test_report_without_log(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(motor, "ROOT", Path(folder)):
            self.assertIn("Sin errores registrados.", errores.report())


if __name__ == "__main__":
    unittest.main()

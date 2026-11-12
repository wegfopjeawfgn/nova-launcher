from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import consola
except ImportError:  # GTK bindings are not installed
    consola = None


@unittest.skipIf(consola is None, "PyGObject/GTK no está instalado")
class DiagnoseTests(unittest.TestCase):
    def test_known_errors(self):
        cases = {
            "java.lang.UnsupportedClassVersionError: x": "Java más reciente",
            "java.lang.OutOfMemoryError: Java heap space": "sin memoria",
            "Could not reserve enough space for object heap": "reservar tanta memoria",
            "GLFW error 65542: WGL: The driver does not appear to support OpenGL": "ventana gráfica",
            "net.fabricmc: Mod resolution encountered an incompatible mod set": "dependencias",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, consola.diagnose(text))

    def test_unknown_is_empty(self):
        self.assertEqual(consola.diagnose("all fine"), "")

    def test_report_contains_tail_and_hint(self):
        text = "\n".join(f"line {n}" for n in range(200)) + "\nOutOfMemoryError"
        report = consola.report(text)
        self.assertIn("Nova Launcher", report)
        self.assertIn("sin memoria", report)
        self.assertNotIn("line 0\n", report)
        self.assertIn("OutOfMemoryError", report)


if __name__ == "__main__":
    unittest.main()

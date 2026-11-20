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


@unittest.skipIf(consola is None, "PyGObject/GTK no está instalado")
class AnalyzeTests(unittest.TestCase):
    def test_java_version_error_offers_the_java_fix(self):
        result = consola.analyze("java.lang.UnsupportedClassVersionError: x")
        self.assertEqual(result["action"], "use_nova_java")
        self.assertIn("Java", result["advice"])

    def test_crash_report_names_the_suspected_mod(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            game = Path(tmp)
            (game / "crash-reports").mkdir()
            (game / "crash-reports" / "crash-2026-11-20_10.00.00-client.txt").write_text(
                "---- Minecraft Crash Report ----\nDescription: Ticking entity\n\nSuspected Mods: \n\tCreate (create)\n")
            result = consola.analyze("nothing known", game)
        self.assertIn("Ticking entity", result["advice"])
        self.assertEqual(result["mod"], "Create (create)")

    def test_no_report_and_no_pattern_is_empty(self):
        self.assertEqual(consola.analyze("all fine"), {"advice": "", "mod": "", "action": None})

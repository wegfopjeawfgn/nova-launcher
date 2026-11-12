import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import modanalisis  # noqa: E402


def fabric(mod_id, version="1.0.0", depends=None, **extra):
    return {"schemaVersion": 1, "id": mod_id, "name": mod_id.title(), "version": version,
            "depends": depends or {}, **extra}


def forge_toml(mod_id, version="1.0.0", deps=()):
    text = f'modLoader="javafml"\nloaderVersion="[1,)"\n[[mods]]\nmodId="{mod_id}"\nversion="{version}"\n'
    for dep, mandatory, rng in deps:
        text += (f'[[dependencies.{mod_id}]]\nmodId="{dep}"\nmandatory={"true" if mandatory else "false"}\n'
                 f'versionRange="{rng}"\n')
    return text


def jar(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content if isinstance(content, (bytes, str)) else json.dumps(content))


class RangeTests(unittest.TestCase):
    def test_fabric_ranges(self):
        cases = [("1.21.1", ">=1.21 <1.22", True), ("1.20.4", ">=1.21", False), ("1.21.1", "1.21.x", True),
                 ("1.20.1", "1.21.x", False), ("1.21.1", "~1.21.1", True), ("1.22.0", "~1.21.1", False),
                 ("1.21.1", "^1.20", True), ("2.0", "^1.20", False), ("1.21.1", "*", True),
                 ("1.20.1", ">=1.21 || 1.20.1", True), ("1.19", ">=1.21 || 1.20.1", False)]
        for version, requirement, expected in cases:
            with self.subTest(version=version, requirement=requirement):
                self.assertIs(modanalisis.satisfies(version, requirement), expected)

    def test_maven_ranges(self):
        self.assertIs(modanalisis.satisfies("1.21.1", "[1.21,1.22)"), True)
        self.assertIs(modanalisis.satisfies("1.22", "[1.21,1.22)"), False)
        self.assertIs(modanalisis.satisfies("1.20", "[1.21,)"), False)
        self.assertIs(modanalisis.satisfies("1.21", "[1.21]"), True)

    def test_unknown_is_not_a_failure(self):
        self.assertIsNone(modanalisis.satisfies("snapshot", ">=1.21"))
        self.assertIsNone(modanalisis.satisfies("1.21", "???"))
        self.assertIs(modanalisis.satisfies("1.21", None), True)
        self.assertIs(modanalisis.satisfies("1.21", ["1.20.x", "1.21.x"]), True)

    def test_version_with_build_metadata(self):
        self.assertEqual(modanalisis.parse_version("0.92.0+1.20.1"), (0, 92, 0))
        self.assertIsNone(modanalisis.parse_version("dev"))


class AnalyzeTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.mods = Path(self._folder.name)
        self.instance = {"loader": "fabric", "version": "1.21.1"}

    def tearDown(self):
        self._folder.cleanup()

    def titles(self, **kwargs):
        return [(i["title"], i["severity"]) for i in modanalisis.analyze(self.mods, {**self.instance, **kwargs})]

    def test_clean_setup_has_no_issues(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"minecraft": "~1.21", "b": "*"})})
        jar(self.mods / "b.jar", {"fabric.mod.json": fabric("b")})
        self.assertEqual(self.titles(), [])

    def test_missing_dependency_is_confirmed(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"b": "*", "fabricloader": ">=0.15"})})
        issues = modanalisis.analyze(self.mods, self.instance)
        self.assertEqual([(i["title"], i["severity"]) for i in issues], [("Falta una dependencia", "confirmado")])
        self.assertIn("«b»", issues[0]["reason"])

    def test_dependency_in_a_disabled_jar_suggests_enabling(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"b": "*"})})
        jar(self.mods / "b.jar.disabled", {"fabric.mod.json": fabric("b")})
        issues = modanalisis.analyze(self.mods, self.instance)
        self.assertIn("Activá", issues[0]["fix"])

    def test_dependency_nested_in_another_jar_counts(self):
        inner = io.BytesIO()
        jar(inner, {"fabric.mod.json": fabric("fabric-resource-loader-v0")})
        jar(self.mods / "fabric-api.jar", {"fabric.mod.json": fabric("fabric-api"),
                                           "META-INF/jars/inner.jar": inner.getvalue()})
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"fabric-resource-loader-v0": "*"})})
        self.assertEqual(self.titles(), [])

    def test_provides_counts(self):
        jar(self.mods / "p.jar", {"fabric.mod.json": fabric("p", provides=["alias"])})
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"alias": "*"})})
        self.assertEqual(self.titles(), [])

    def test_wrong_loader_and_vanilla(self):
        jar(self.mods / "f.jar", {"META-INF/mods.toml": forge_toml("f")})
        self.assertEqual(self.titles(), [("Cargador incorrecto", "confirmado")])
        self.assertEqual(self.titles(loader="forge"), [])
        self.assertEqual(self.titles(loader="vanilla"), [("Cargador incorrecto", "confirmado")])

    def test_fabric_mod_is_fine_on_quilt_but_not_the_reverse(self):
        jar(self.mods / "f.jar", {"fabric.mod.json": fabric("f")})
        self.assertEqual(self.titles(loader="quilt"), [])
        self.assertEqual(self.titles(loader="neoforge"), [("Cargador incorrecto", "confirmado")])

    def test_minecraft_version(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"minecraft": ">=1.21.5"})})
        self.assertEqual(self.titles(), [("Versión de Minecraft incompatible", "confirmado")])
        self.assertEqual(self.titles(version="1.21.6"), [])

    def test_dependency_version(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"b": ">=2.0"})})
        jar(self.mods / "b.jar", {"fabric.mod.json": fabric("b", version="1.5.0")})
        self.assertEqual(self.titles(), [("Versión de dependencia incompatible", "confirmado")])

    def test_duplicates_offer_disabling_the_older(self):
        jar(self.mods / "x-1.0.jar", {"fabric.mod.json": fabric("x", version="1.0.0")})
        jar(self.mods / "x-2.0.jar", {"fabric.mod.json": fabric("x", version="2.0.0")})
        issues = modanalisis.analyze(self.mods, self.instance)
        self.assertEqual(issues[0]["title"], "Mod duplicado")
        self.assertEqual(issues[0]["file"], "x-1.0.jar")
        self.assertEqual(issues[0]["action"], "disable")

    def test_breaks_and_conflicts_come_from_metadata_only(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", breaks={"b": "<2.0"}, conflicts={"c": "*"})})
        jar(self.mods / "b.jar", {"fabric.mod.json": fabric("b", version="1.0")})
        jar(self.mods / "c.jar", {"fabric.mod.json": fabric("c")})
        self.assertEqual(self.titles(), [("Incompatibilidad declarada", "confirmado"),
                                         ("Posible conflicto declarado", "posible")])

    def test_breaks_ignored_when_version_is_outside_the_range(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", breaks={"b": "<2.0"})})
        jar(self.mods / "b.jar", {"fabric.mod.json": fabric("b", version="3.0")})
        self.assertEqual(self.titles(), [])

    def test_installed_together_alone_is_never_a_problem(self):
        for name in "abcd":
            jar(self.mods / f"{name}.jar", {"fabric.mod.json": fabric(name)})
        self.assertEqual(self.titles(), [])

    def test_corrupt_and_unknown_files(self):
        (self.mods / "broken.jar").write_bytes(b"not a zip")
        jar(self.mods / "lib.jar", {"readme.txt": "x"})
        jar(self.mods / "bad.jar", {"fabric.mod.json": "{not json"})
        self.assertEqual(self.titles(), [("Archivo dañado", "confirmado"), ("Archivo dañado", "confirmado"),
                                         ("Sin información de mod", "aviso")])

    def test_forge_optional_dependency_is_not_required(self):
        jar(self.mods / "f.jar", {"META-INF/mods.toml": forge_toml("f", deps=[("jei", False, "[1,)")])})
        self.assertEqual(self.titles(loader="forge"), [])
        jar(self.mods / "g.jar", {"META-INF/mods.toml": forge_toml("g", deps=[("jei", True, "[1,)")])})
        self.assertEqual(self.titles(loader="forge"), [("Falta una dependencia", "confirmado")])

    def test_forge_builtin_dependencies_are_ignored(self):
        jar(self.mods / "f.jar", {"META-INF/mods.toml": forge_toml(
            "f", deps=[("minecraft", True, "[1.21,1.22)"), ("forge", True, "[50,)")])})
        self.assertEqual(self.titles(loader="forge"), [])

    def test_quilt_metadata(self):
        data = {"schema_version": 1, "quilt_loader": {"id": "q", "version": "1.0", "depends": [
            "needed", {"id": "opt", "optional": True}, {"id": "minecraft", "versions": ">=1.21"}]}}
        jar(self.mods / "q.jar", {"quilt.mod.json": data})
        issues = modanalisis.analyze(self.mods, {"loader": "quilt", "version": "1.21.1"})
        self.assertEqual([i["title"] for i in issues], ["Falta una dependencia"])

    def test_analysis_never_touches_files(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a", depends={"b": "*"})})
        before = sorted((p.name, p.stat().st_mtime_ns) for p in self.mods.iterdir())
        modanalisis.analyze(self.mods, self.instance)
        self.assertEqual(before, sorted((p.name, p.stat().st_mtime_ns) for p in self.mods.iterdir()))

    def test_disable_renames_and_refuses_overwrite(self):
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a")})
        target = modanalisis.disable(self.mods / "a.jar")
        self.assertTrue(target.exists() and not (self.mods / "a.jar").exists())
        jar(self.mods / "a.jar", {"fabric.mod.json": fabric("a")})
        with self.assertRaises(FileExistsError):
            modanalisis.disable(self.mods / "a.jar")
        with self.assertRaises(ValueError):
            modanalisis.disable(self.mods / "a.txt")

    def test_missing_folder_is_empty(self):
        self.assertEqual(modanalisis.analyze(self.mods / "nope", self.instance), [])


if __name__ == "__main__":
    unittest.main()

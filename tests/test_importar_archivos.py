from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import importar_archivos as importar  # noqa: E402
import motor  # noqa: E402


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, (str, bytes)) else json.dumps(data))
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "instance"
        (self.folder / "game").mkdir(parents=True)

    def zip(self, name, files):
        return make_zip(self.root / name, files)


class InspectTests(Base):
    def test_fabric_jar_is_a_mod_with_its_declared_name(self):
        path = self.zip("sodium.jar", {"fabric.mod.json": {"id": "sodium", "name": "Sodium", "version": "0.6.1"}})
        item = importar.inspect(path)
        self.assertTrue(item.ok)
        self.assertEqual((item.kind, item.title, item.loaders), ("mod", "Sodium", ("fabric",)))
        self.assertIn("0.6.1", item.detail)

    def test_forge_and_neoforge_jars_are_recognised(self):
        toml = 'modLoader="javafml"\n[[mods]]\nmodId="create"\nversion="6.0.1"\ndisplayName="Create"\n'
        forge = importar.inspect(self.zip("create.jar", {"META-INF/mods.toml": toml}))
        self.assertEqual((forge.kind, forge.title, forge.loaders), ("mod", "Create", ("forge",)))
        neo = importar.inspect(self.zip("neo.jar", {"META-INF/neoforge.mods.toml": toml}))
        self.assertEqual(neo.loaders, ("neoforge",))

    def test_jar_without_mod_metadata_is_refused_with_a_reason(self):
        item = importar.inspect(self.zip("lib.jar", {"com/example/A.class": b"x"}))
        self.assertFalse(item.ok)
        self.assertIn("No parece un mod", item.problem)

    def test_corrupt_or_empty_files_are_refused(self):
        broken = self.root / "broken.jar"
        broken.write_bytes(b"not a zip")
        self.assertIn("dañado", importar.inspect(broken).problem)
        empty = self.root / "empty.zip"
        empty.write_bytes(b"")
        self.assertIn("vacío", importar.inspect(empty).problem)

    def test_resource_pack_data_pack_and_shader_pack_are_told_apart(self):
        resource = importar.inspect(self.zip("faithful.zip", {
            "pack.mcmeta": {"pack": {"pack_format": 34, "description": "Faithful 64x"}}, "assets/minecraft/a.png": b"x"}))
        self.assertEqual((resource.kind, resource.detail), ("resourcepack", "Faithful 64x"))
        data = importar.inspect(self.zip("rules.zip", {"pack.mcmeta": {"pack": {}}, "data/minecraft/recipes/a.json": "{}"}))
        self.assertEqual(data.kind, "datapack")
        shader = importar.inspect(self.zip("bsl.zip", {"shaders/final.fsh": "x", "shaders/final.vsh": "x"}))
        self.assertEqual(shader.kind, "shader")

    def test_packs_nested_inside_a_folder_are_explained_not_installed(self):
        shader = importar.inspect(self.zip("nested.zip", {"BSL/shaders/final.fsh": "x"}))
        self.assertFalse(shader.ok)
        self.assertIn("dentro de una carpeta", shader.problem)
        resource = importar.inspect(self.zip("nested2.zip", {"Pack/pack.mcmeta": "{}", "Pack/assets/a": "x"}))
        self.assertIn("dentro de una carpeta", resource.problem)

    def test_unknown_zip_extension_and_directories_are_refused(self):
        self.assertIn("No reconozco", importar.inspect(self.zip("misc.zip", {"readme.txt": "hi"})).problem)
        text = self.root / "notes.txt"
        text.write_text("hi")
        self.assertIn("Formato no admitido", importar.inspect(text).problem)
        self.assertIn("carpetas", importar.inspect(self.root).problem)
        self.assertIn("carpetas", importar.inspect(self.root / "missing.zip").problem)

    def test_modpacks_are_recognised_by_their_index(self):
        index = {"formatVersion": 1, "game": "minecraft", "name": "Mi pack", "files": [],
                 "dependencies": {"minecraft": "1.21.1", "fabric-loader": "0.16.0"}}
        item = importar.inspect(self.zip("pack.mrpack", {"modrinth.index.json": index}))
        self.assertEqual((item.kind, item.title), ("modpack", "Mi pack"))
        self.assertTrue(item.ok)
        self.assertIn("1.21.1", item.detail)
        broken = importar.inspect(self.zip("bad.zip", {"modrinth.index.json": "{"}))
        self.assertEqual(broken.kind, "modpack")
        self.assertIn("No se pudo leer", broken.problem)

    def test_a_manifest_json_that_is_not_a_curseforge_pack_does_not_make_a_modpack(self):
        item = importar.inspect(self.zip("other.zip", {"manifest.json": {"hello": 1}, "pack.mcmeta": {"pack": {}},
                                                       "assets/a": "x"}))
        self.assertEqual(item.kind, "resourcepack")

    def test_size_limits_apply_per_kind(self):
        path = self.zip("big.jar", {"fabric.mod.json": "{}"})
        original = dict(importar.MAX_BYTES)
        self.addCleanup(importar.MAX_BYTES.update, original)
        importar.MAX_BYTES["mod"] = 10
        self.assertIn("máximo", importar.inspect(path).problem)

    def test_duplicate_paths_are_inspected_once(self):
        path = self.zip("a.jar", {"fabric.mod.json": "{}"})
        self.assertEqual(len(importar.inspect_many([path, path, str(path)])), 1)


class WarningTests(Base):
    def mod(self, *loaders):
        return importar.Item(path=Path("x.jar"), kind="mod", loaders=loaders)

    def test_loader_mismatch_and_vanilla_are_warned(self):
        self.assertIn("Vanilla", importar.warning(self.mod("fabric"), {"loader": "vanilla"}))
        self.assertIn("Fabric", importar.warning(self.mod("fabric"), {"loader": "forge"}))
        self.assertEqual(importar.warning(self.mod("fabric"), {"loader": "fabric"}), "")
        self.assertEqual(importar.warning(self.mod("fabric"), {"loader": "quilt"}), "")
        self.assertEqual(importar.warning(self.mod("forge", "neoforge"), {"loader": "neoforge"}), "")

    def test_shaders_need_a_mod_loader(self):
        shader = importar.Item(path=Path("x.zip"), kind="shader")
        self.assertIn("Iris", importar.warning(shader, {"loader": "vanilla"}))
        self.assertEqual(importar.warning(shader, {"loader": "fabric"}), "")


class InstallTests(Base):
    def item(self, name, files):
        item = importar.inspect(self.zip(name, files))
        self.assertTrue(item.ok, item.problem)
        return item

    def test_each_kind_goes_to_its_own_folder(self):
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        shader = self.item("bsl.zip", {"shaders/a.fsh": "x"})
        textures = self.item("tex.zip", {"pack.mcmeta": {"pack": {}}, "assets/a": "x"})
        target, message = importar.install(self.folder, mod)
        self.assertEqual(target, self.folder / "game" / "mods" / "sodium.jar")
        self.assertIn("instalado", message)
        self.assertEqual(importar.install(self.folder, shader)[0], self.folder / "game" / "shaderpacks" / "bsl.zip")
        self.assertEqual(importar.install(self.folder, textures)[0], self.folder / "game" / "resourcepacks" / "tex.zip")
        self.assertEqual(target.read_bytes(), mod.path.read_bytes())

    def test_identical_file_is_skipped_and_different_one_is_numbered(self):
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        importar.install(self.folder, mod)
        target, message = importar.install(self.folder, mod)
        self.assertIsNone(target)
        self.assertIn("ya estaba instalado", message)
        other = self.root / "other"
        other.mkdir()
        different = importar.inspect(make_zip(other / "sodium.jar", {"fabric.mod.json": {"id": "sodium", "version": "2"}}))
        target, _ = importar.install(self.folder, different)
        self.assertEqual(target.name, "sodium (2).jar")
        self.assertEqual(len(list((self.folder / "game" / "mods").iterdir())), 2)

    def test_importing_again_after_a_numbered_copy_does_not_make_another(self):
        mods = self.folder / "game" / "mods"
        mods.mkdir(parents=True)
        (mods / "sodium.jar").write_bytes(b"something else entirely")
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        first, _ = importar.install(self.folder, mod)
        self.assertEqual(first.name, "sodium (2).jar")
        again, message = importar.install(self.folder, mod)
        self.assertIsNone(again)
        self.assertIn("sodium (2).jar ya estaba instalado", message)
        self.assertEqual(len(list(mods.iterdir())), 2)

    def test_a_disabled_copy_counts_as_taken(self):
        mods = self.folder / "game" / "mods"
        mods.mkdir(parents=True)
        (mods / "sodium.jar.disabled").write_bytes(b"old")
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        target, _ = importar.install(self.folder, mod)
        self.assertEqual(target.name, "sodium (2).jar")

    def test_data_packs_need_an_existing_world(self):
        pack = self.item("rules.zip", {"pack.mcmeta": {"pack": {}}, "data/a/b.json": "{}"})
        with self.assertRaisesRegex(ValueError, "Elegí el mundo"):
            importar.install(self.folder, pack)
        with self.assertRaisesRegex(ValueError, "no existe"):
            importar.install(self.folder, pack, world="Nope")
        world = self.folder / "game" / "saves" / "Mi mundo"
        world.mkdir(parents=True)
        (world / "level.dat").write_bytes(b"x")
        self.assertEqual(importar.worlds(self.folder), ["Mi mundo"])
        target, _ = importar.install(self.folder, pack, world="Mi mundo")
        self.assertEqual(target, world / "datapacks" / "rules.zip")

    def test_world_name_cannot_escape_the_instance(self):
        pack = self.item("rules.zip", {"pack.mcmeta": {"pack": {}}, "data/a/b.json": "{}"})
        with self.assertRaises(ValueError):
            importar.install(self.folder, pack, world="../../outside")

    def test_unsafe_file_names_are_cleaned(self):
        self.assertEqual(importar.safe_name(Path('a:b*c?.JAR')), "a_b_c_.jar")
        self.assertEqual(importar.safe_name(Path("..hidden.zip")), "hidden.zip")
        self.assertTrue(importar.safe_name(Path("x" * 300 + ".zip")).endswith(".zip"))
        self.assertLessEqual(len(importar.safe_name(Path("x" * 300 + ".zip"))), 124)

    def test_failed_copy_leaves_nothing_behind(self):
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        mod.size += 1  # the file "changed" while copying
        with self.assertRaises(OSError):
            importar.install(self.folder, mod)
        self.assertEqual(list((self.folder / "game" / "mods").iterdir()), [])

    def test_modpacks_and_refused_items_are_not_installed_as_loose_content(self):
        index = {"formatVersion": 1, "game": "minecraft", "name": "Pack", "files": [],
                 "dependencies": {"minecraft": "1.21.1"}}
        pack = importar.inspect(self.zip("p.mrpack", {"modrinth.index.json": index}))
        with self.assertRaises(ValueError):
            importar.install(self.folder, pack)
        bad = importar.inspect(self.zip("misc.zip", {"x.txt": "x"}))
        with self.assertRaisesRegex(ValueError, "No reconozco"):
            importar.install(self.folder, bad)

    def test_progress_reports_bytes_and_a_busy_instance_is_refused(self):
        mod = self.item("sodium.jar", {"fabric.mod.json": {"id": "sodium"}})
        calls = []
        importar.install(self.folder, mod, progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls[-1], (mod.size, mod.size))
        other = self.root / "again.jar"
        other.write_bytes(mod.path.read_bytes() + b"\0")
        busy = importar.Item(path=other, kind="mod", size=other.stat().st_size)
        with motor.instance_lock(self.folder):
            with self.assertRaises(RuntimeError):
                importar.install(self.folder, busy)


if __name__ == "__main__":
    unittest.main()

import json
import os
from pathlib import Path
import sys
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import respaldos  # noqa: E402


class RespaldosCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(motor, "ROOT", self.folder / "root")
        patcher.start()
        self.addCleanup(patcher.stop)
        no_net = mock.patch("catalogo.requests.post", side_effect=AssertionError("red"))
        no_net.start()
        self.addCleanup(no_net.stop)

    def make_instance(self, name="Mi mundo", **settings):
        source = self.folder / "src"
        (source / "game" / "mods").mkdir(parents=True, exist_ok=True)
        motor.save(source / "instance.json", {**motor.DEFAULTS, "name": name, **settings})
        return source

    def add_world(self, source, name="W"):
        world = source / "game" / "saves" / name
        world.mkdir(parents=True)
        (world / "level.dat").write_bytes(b"lvl")
        (world / "session.lock").write_bytes(b"lock")
        return world


class CopyInstanceTests(RespaldosCase):
    def test_backup_and_restore_modes(self):
        source = self.make_instance()
        (source / "minecraft.log").write_text("log")
        (source / "session.lock").write_text("x")
        backup = respaldos.copy_instance(source, "backup")
        self.assertEqual(backup.parent, motor.ROOT / "backups")
        self.assertTrue((backup / "backup.json").is_file())
        self.assertFalse((backup / "minecraft.log").exists())
        self.assertFalse((backup / "session.lock").exists())
        self.assertFalse((backup / ".nova.lock").exists())
        restored = respaldos.copy_instance(backup, "restore")
        self.assertEqual(restored.parent, motor.ROOT / "instances")
        self.assertEqual(motor.read(restored / "instance.json", {})["name"], "Mi mundo (restaurada)")
        self.assertFalse((restored / "backup.json").exists())
        clone = respaldos.copy_instance(source, "clone")
        self.assertEqual(motor.read(clone / "instance.json", {})["name"], "Mi mundo (copia)")

    def test_long_name_is_truncated(self):
        source = self.make_instance("N" * 40)
        clone = respaldos.copy_instance(source, "clone")
        name = motor.read(clone / "instance.json", {})["name"]
        self.assertEqual(len(name), 40)
        self.assertTrue(name.endswith(" (copia)"))

    def test_symlink_and_invalid_source(self):
        source = self.make_instance()
        os.symlink("/etc/hostname", source / "game" / "link")
        with self.assertRaises(ValueError):
            respaldos.copy_instance(source, "clone")
        self.assertEqual(list((motor.ROOT / "instances").iterdir()), [])
        empty = self.folder / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            respaldos.copy_instance(empty, "clone")


class ExportTests(RespaldosCase):
    def read_zip(self, path):
        with zipfile.ZipFile(path) as archive:
            return archive.namelist(), archive

    def test_extension_is_validated(self):
        source = self.make_instance()
        with self.assertRaises(ValueError):
            respaldos.export_instance(source, self.folder / "out.tar", False)

    def test_export_zip_with_and_without_worlds(self):
        source = self.make_instance(loader="fabric", loader_version="0.16.9")
        self.add_world(source)
        plain = self.folder / "a.zip"
        respaldos.export_instance(source, plain, False)
        with zipfile.ZipFile(plain) as archive:
            self.assertEqual(archive.namelist(), ["nova-pack.json"])
            manifest = json.loads(archive.read("nova-pack.json"))
        self.assertEqual(manifest["dependencies"], {"minecraft": motor.VERSION, "fabric-loader": "0.16.9"})
        full = self.folder / "b.zip"
        respaldos.export_instance(source, full, True)
        with zipfile.ZipFile(full) as archive:
            self.assertEqual(sorted(archive.namelist()),
                             ["nova-pack.json", "overrides/saves/W/level.dat"])
        self.assertEqual([p.name for p in self.folder.glob("tmp*")], [])

    def test_vanilla_and_auto_loader(self):
        source = self.make_instance()
        out = self.folder / "v.zip"
        respaldos.export_instance(source, out, False)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(json.loads(archive.read("nova-pack.json"))["dependencies"],
                             {"minecraft": motor.VERSION})
        forge = self.make_instance(loader="forge", loader_version="")
        respaldos.export_instance(forge, out, False)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(json.loads(archive.read("nova-pack.json"))["dependencies"]["forge"], "auto")

    def test_mrpack_requires_loader_version(self):
        source = self.make_instance(loader="neoforge", loader_version="")
        with self.assertRaises(ValueError):
            respaldos.export_instance(source, self.folder / "x.mrpack", False)
        self.assertFalse((self.folder / "x.mrpack").exists())

    def test_mrpack_references_only_verified_cdn_files(self):
        source = self.make_instance(loader="fabric", loader_version="0.16.9")
        mods = source / "game" / "mods"
        (mods / "known.jar").write_bytes(b"known")
        (mods / "unknown.jar").write_bytes(b"unknown")
        os.symlink(mods / "known.jar", mods / "link.jar")
        import hashlib
        known = hashlib.sha512(b"known").hexdigest()
        hashes = {"sha512": known, "sha1": "1" * 40}
        remote = {known: {"files": [
            {"hashes": {"sha512": known}, "url": "https://evil.example/k.jar"},
            {"hashes": hashes, "url": "https://cdn.modrinth.com/k.jar"}]}}
        with mock.patch("catalogo.versions_by_hash", return_value=remote) as lookup:
            out = self.folder / "p.mrpack"
            respaldos.export_instance(source, out, False)
        self.assertEqual(sorted(lookup.call_args.args[0].values().__iter__().__next__()),
                         [mods / "known.jar"])
        with zipfile.ZipFile(out) as archive:
            index = json.loads(archive.read("modrinth.index.json"))
        self.assertEqual(index["game"], "minecraft")
        self.assertEqual(index["dependencies"]["fabric-loader"], "0.16.9")
        self.assertEqual(index["files"], [{"path": "mods/known.jar", "hashes": hashes,
                                           "downloads": ["https://cdn.modrinth.com/k.jar"],
                                           "fileSize": 5}])

    def test_worlds_with_symlinks_are_refused(self):
        source = self.make_instance()
        world = self.add_world(source)
        os.symlink("/etc/hostname", world / "leak")
        out = self.folder / "s.zip"
        with self.assertRaises(ValueError):
            respaldos.export_instance(source, out, True)
        self.assertFalse(out.exists())
        link = self.folder / "link"
        (link / "game").mkdir(parents=True)
        motor.save(link / "instance.json", {**motor.DEFAULTS, "name": "L"})
        outside = self.folder / "outside"
        outside.mkdir()
        os.symlink(outside, link / "game" / "saves")
        with self.assertRaises(ValueError):
            respaldos.export_instance(link, out, True)

    def test_export_round_trip_through_import_pack(self):
        import catalogo
        source = self.make_instance("Ida y vuelta", loader="fabric", loader_version="0.16.9")
        self.add_world(source, "Mundo")
        out = self.folder / "rt.zip"
        respaldos.export_instance(source, out, True)
        imported = catalogo.import_pack(out, 2048)
        self.assertEqual(motor.read(imported / "instance.json", {})["loader_version"], "0.16.9")
        self.assertTrue((imported / "game" / "saves" / "Mundo" / "level.dat").is_file())
        self.assertFalse((imported / "game" / "saves" / "Mundo" / "session.lock").exists())


class WorldTests(RespaldosCase):
    def test_worlds_listing(self):
        source = self.make_instance()
        self.add_world(source, "b")
        self.add_world(source, "A")
        (source / "game" / "saves" / "nolevel").mkdir()
        os.symlink(source / "game" / "saves" / "A", source / "game" / "saves" / "ln")
        self.assertEqual([p.name for p in respaldos.worlds(source)], ["A", "b"])
        self.assertEqual(respaldos.worlds(source, backups=True), [])

    def test_copy_world_backup_restore_and_unique_names(self):
        source = self.make_instance()
        world = self.add_world(source)
        first = respaldos.copy_world(source, world)
        second = respaldos.copy_world(source, world)
        self.assertEqual((first.name, second.name), ("W", "W 2"))
        self.assertFalse((first / "session.lock").exists())
        self.assertTrue((first / "level.dat").is_file())
        restored = respaldos.copy_world(source, first, restore=True)
        self.assertEqual(restored.name, "W (copia)")
        self.assertEqual(restored.parent, source / "game" / "saves")

    def test_copy_world_rejects_unknown_and_symlinks(self):
        source = self.make_instance()
        world = self.add_world(source)
        with self.assertRaises(ValueError):
            respaldos.copy_world(source, self.folder / "otro")
        os.symlink("/etc/hostname", world / "leak")
        with self.assertRaises(ValueError):
            respaldos.copy_world(source, world)
        self.assertEqual([p for p in (source / "world-backups").iterdir()], [])


class PrismTests(RespaldosCase):
    def prism(self, components, *, cfg="name=Mi Prism\n", game=".minecraft"):
        source = self.folder / "prism"
        (source / game).mkdir(parents=True)
        (source / game / "options.txt").write_text("o")
        (source / "mmc-pack.json").write_text(json.dumps({"components": components}))
        if cfg is not None:
            (source / "instance.cfg").write_text(cfg)
        return source

    def test_details_and_import(self):
        source = self.prism([{"uid": "net.minecraft", "version": "1.20.1"},
                             {"uid": "net.fabricmc.fabric-loader", "version": "0.15.0"},
                             {"uid": "org.lwjgl3", "version": "3.3.1"}])
        (source / ".minecraft" / "logs").mkdir()
        (source / ".minecraft" / "logs" / "latest.log").write_text("x")
        name, version, loader, loader_version, game = respaldos.prism_details(source)
        self.assertEqual((name, version, loader, loader_version), ("Mi Prism", "1.20.1", "fabric", "0.15.0"))
        result = respaldos.import_prism(source, 3000)
        settings = motor.read(result / "instance.json", {})
        self.assertEqual((settings["name"], settings["memory"], settings["loader"]),
                         ("Mi Prism", 3000, "fabric"))
        self.assertTrue((result / "game" / "options.txt").is_file())
        self.assertFalse((result / "game" / "logs").exists())

    def test_vanilla_and_fallback_name(self):
        source = self.prism([{"uid": "net.minecraft", "version": "1.21"}], cfg=None, game="minecraft")
        name, version, loader, loader_version, _ = respaldos.prism_details(source)
        self.assertEqual((name, version, loader, loader_version), ("prism", "1.21", "vanilla", ""))

    def test_incompatible_instances(self):
        cases = {
            "sin minecraft": [{"uid": "net.fabricmc.fabric-loader", "version": "1"}],
            "dos loaders": [{"uid": "net.minecraft", "version": "1.20"},
                            {"uid": "net.minecraftforge", "version": "1"},
                            {"uid": "net.neoforged", "version": "2"}],
            "version peligrosa": [{"uid": "net.minecraft", "version": "../x"}],
            "version punto": [{"uid": "net.minecraft", "version": ".."}],
            "loader raro": [{"uid": "net.minecraft", "version": "1.20"},
                            {"uid": "net.neoforged", "version": "1 2"}],
        }
        for label, components in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                respaldos.prism_details(self.prism(components))
            shutil.rmtree(self.folder / "prism")

    def test_missing_game_folder_and_symlink_content(self):
        source = self.prism([{"uid": "net.minecraft", "version": "1.20"}])
        os.symlink("/etc/hostname", source / ".minecraft" / "leak")
        with self.assertRaises(ValueError):
            respaldos.import_prism(source, 2048)
        self.assertEqual(list((motor.ROOT / "instances").iterdir()), [])
        (source / ".minecraft" / "leak").unlink()
        (source / ".minecraft" / "options.txt").unlink()
        (source / ".minecraft").rmdir()
        with self.assertRaises(ValueError):
            respaldos.prism_details(source)


if __name__ == "__main__":
    unittest.main()

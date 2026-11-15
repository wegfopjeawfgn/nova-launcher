import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import servidor_gestion as sg  # noqa: E402
import servidor_importar as si  # noqa: E402
import servidor_local as sl  # noqa: E402

JAVA = {"component": "java-runtime-delta", "major": 21, "server": None}


def make_jar(path, version=None):
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("META-INF/MANIFEST.MF", "x")
        if version:
            package.writestr("version.json", json.dumps({"id": version}))


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        self.source = Path(tempfile.mkdtemp(prefix="servidor-")) / "Mi Server Viejo"
        self.source.mkdir()
        sl.RUNNERS.clear()

    def tearDown(self):
        motor.ROOT = self.original


class DetectTests(Base):
    def test_vanilla_is_recognised_from_the_version_inside_its_jar(self):
        make_jar(self.source / "server.jar", "1.21.1")
        (self.source / "server.properties").write_text("server-port=25570\n")
        (self.source / "eula.txt").write_text("eula=true\n")
        found = si.detect(self.source)
        self.assertEqual((found["kind"], found["version"], found["jar"], found["port"], found["eula"]), ("vanilla", "1.21.1", "server.jar", 25570, True))
        self.assertEqual(found["name"], "Mi Server Viejo")

    def test_paper_by_its_history_and_by_its_jar_name(self):
        make_jar(self.source / "paper-1.21.10-130.jar")
        (self.source / "version_history.json").write_text('{"currentVersion": "git-Paper-130 (MC: 1.21.10)"}')
        found = si.detect(self.source)
        self.assertEqual((found["kind"], found["version"], found["build"], found["jar"]), ("paper", "1.21.10", "130", "paper-1.21.10-130.jar"))
        other = Path(tempfile.mkdtemp())
        make_jar(other / "server.jar")
        (other / "version_history.json").write_text('{"currentVersion": "git-Purpur-2400 (MC: 1.21.4)"}')
        found = si.detect(other)
        self.assertEqual((found["kind"], found["version"], found["build"]), ("paper", "1.21.4", "2400"))
        self.assertTrue(any("Purpur" in note for note in found["notes"]))

    def test_fabric_and_forge_layouts(self):
        make_jar(self.source / "fabric-server-launch.jar")
        (self.source / "libraries" / "net" / "fabricmc" / "intermediary" / "1.21.1").mkdir(parents=True)
        found = si.detect(self.source)
        self.assertEqual((found["kind"], found["version"], found["jar"]), ("fabric", "1.21.1", "fabric-server-launch.jar"))
        modern = Path(tempfile.mkdtemp())
        args = modern / "libraries" / "net" / "minecraftforge" / "forge" / "1.21.1-52.1.20"
        args.mkdir(parents=True)
        (args / "unix_args.txt").write_text("x")
        (modern / "user_jvm_args.txt").write_text("-Xmx6G\n")
        found = si.detect(modern)
        self.assertEqual((found["kind"], found["version"], found["forge_build"], found["memory"]), ("forge", "1.21.1", "52.1.20", 6))
        legacy = Path(tempfile.mkdtemp())
        make_jar(legacy / "forge-1.12.2-14.23.5.2860.jar")
        make_jar(legacy / "forge-1.12.2-14.23.5.2860-installer.jar")
        found = si.detect(legacy)
        self.assertEqual((found["kind"], found["version"], found["forge_build"], found["jar"]), ("forge", "1.12.2", "14.23.5.2860", "forge-1.12.2-14.23.5.2860.jar"))

    def test_unknown_and_odd_folders_never_raise(self):
        self.assertTrue(si.detect(self.source)["notes"])
        make_jar(self.source / "otro.jar")
        found = si.detect(self.source)
        self.assertIsNone(found["kind"])
        (self.source / "logs").mkdir()
        (self.source / "logs" / "latest.log").write_text("[10:00:00] [Server thread/INFO]: Starting minecraft server version 1.20.4\n")
        (self.source / "server.properties").write_text("server-port=abc\n")
        found = si.detect(self.source)
        self.assertEqual((found["version"], found["port"]), ("1.20.4", 25565))
        with self.assertRaises(ValueError):
            si.detect(self.source / "no-existe")
        (self.source / "start.sh").write_text("java -Xmx2048M -jar x.jar")
        self.assertEqual(si.detect(self.source)["memory"], 2)


class ImportTests(Base):
    def args(self, **extra):
        return {"name": "Importado", "kind": "paper", "version": "1.21.10", "memory": 4, "port": 25600, "jar": "paper-1.21.10-130.jar", "build": "130", **extra}

    def prepare(self):
        make_jar(self.source / "paper-1.21.10-130.jar")
        (self.source / "world").mkdir()
        (self.source / "world" / "level.dat").write_text("mundo")
        (self.source / "plugins").mkdir()
        (self.source / "plugins" / "A.jar").write_text("p")
        (self.source / "server.properties").write_text("server-port=25565\nmotd=Hola\n")
        (self.source / "nova-server.json").write_text("{}")

    def test_import_copies_registers_and_leaves_the_original_alone(self):
        self.prepare()
        notes = []
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            meta = si.import_server(self.source, progress=lambda d, t: notes.append((d, t)), **self.args())
        target = sl.folder(meta["id"])
        self.assertEqual((target / "world" / "level.dat").read_text(), "mundo")
        self.assertEqual((meta["jar"], meta["build"], meta["java_major"], meta["imported"]), ("paper-1.21.10-130.jar", "130", 21, True))
        self.assertNotEqual((target / "nova-server.json").read_text(), "{}")        # Nova's own record replaced the foreign one
        self.assertEqual(sl.read_properties(target)["server-port"], "25600")
        self.assertEqual(sl.read_properties(target)["motd"], "Hola")
        self.assertTrue((self.source / "world" / "level.dat").exists())
        self.assertEqual((self.source / "nova-server.json").read_text(), "{}")
        self.assertEqual(notes[-1][0], notes[-1][1])
        self.assertFalse(meta["eula"])
        self.assertEqual(sl.launch_command(meta, target, "java")[-3:], ["-jar", "paper-1.21.10-130.jar", "nogui"])

    def test_the_eula_is_only_written_when_the_person_accepts(self):
        self.prepare()
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            no = si.import_server(self.source, **self.args(name="Uno", port=25601))
            yes = si.import_server(self.source, accept_eula=True, **self.args(name="Dos", port=25602))
        self.assertFalse(sl.eula_accepted(sl.folder(no["id"])))
        self.assertTrue(sl.eula_accepted(sl.folder(yes["id"])))
        self.assertTrue(yes["eula"])

    def test_refusals_leave_nothing_behind(self):
        self.prepare()
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            for extra in ({"jar": "../x.jar"}, {"jar": "falta.jar"}, {"kind": "forge"}, {"port": 80}, {"name": ""}, {"kind": "otro"}):
                with self.assertRaises(ValueError, msg=extra):
                    si.import_server(self.source, **self.args(**extra))
            with self.assertRaises(ValueError):
                si.import_server(sl.root(), **self.args())              # Nova's own data
            sl.root().mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ValueError):
                si.import_server(motor.ROOT, **self.args())
            with mock.patch.object(si.shutil, "copytree", side_effect=OSError("disco lleno")):
                with self.assertRaises(OSError):
                    si.import_server(self.source, **self.args())
        self.assertEqual(sl.all_servers(), [])
        self.assertEqual(list(sl.root().iterdir()), [])

    def test_a_port_used_by_another_nova_server_is_refused(self):
        self.prepare()
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            si.import_server(self.source, **self.args())
            with self.assertRaises(ValueError):
                si.import_server(self.source, **self.args(name="Otro"))

    def test_forge_needs_its_build_and_vanilla_updates_rename_the_jar(self):
        modern = self.source / "libraries" / "net" / "minecraftforge" / "forge" / "1.21.1-52.1.20"
        modern.mkdir(parents=True)
        (modern / "unix_args.txt").write_text("x")
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            with self.assertRaises(ValueError):
                si.import_server(self.source, **self.args(kind="forge", version="1.21.1", jar=None, build=None))
            forge = si.import_server(self.source, **self.args(kind="forge", version="1.21.1", jar=None, forge_build="52.1.20", port=25603))
        self.assertEqual(forge["forge_build"], "52.1.20")
        self.assertNotIn("jar", forge)
        self.prepare()
        with mock.patch.object(sl, "mojang_info", return_value=JAVA):
            meta = si.import_server(self.source, **self.args(port=25604))
        info = {"url": "https://x", "size": None, "algo": None, "digest": None, "component": "c", "major": 21, "build": "131"}
        with mock.patch.object(sl, "resolve", return_value=info), mock.patch.object(sl, "ensure_java", return_value="java"), \
                mock.patch.object(sl, "download", lambda url, target, **k: target.write_bytes(b"n" * 2000)):
            sg.update_server(meta["id"])
        self.assertEqual(sl.load(meta["id"])["jar"], "server.jar")
        self.assertEqual(sl.launch_command(sl.load(meta["id"]), sl.folder(meta["id"]), "java")[-2], "server.jar")


if __name__ == "__main__":
    unittest.main()

import hashlib
from pathlib import Path
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import servidor_local as sl  # noqa: E402

FAKE = textwrap.dedent("""
    import sys
    print("Starting minecraft server", flush=True)
    print("[12:00:00] [Server thread/INFO]: Done (0.1s)! For help, type \\"help\\"", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if line == "stop":
            print("Stopping server", flush=True)
            sys.exit(0)
        print("echo " + line, flush=True)
""")


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        sl.RUNNERS.clear()

    def tearDown(self):
        sl.stop_all(wait=2)
        motor.ROOT = self.original

    def make(self, **extra):
        sid = "0123456789ab"
        path = sl.folder(sid)
        path.mkdir(parents=True)
        meta = {"id": sid, "name": "Mundo", "kind": "paper", "version": "1.21.1", "memory": 2, "port": 25590,
                "java_component": "x", "java_major": 21, "created": 1, **extra}
        sl.save(meta)
        return sid, path


class FilesTests(Base):
    def test_paths_cannot_leave_the_server_folder(self):
        sid, path = self.make()
        for bad in ("..", "../x", "a/../../x", "/etc/passwd/.."):
            with self.assertRaises(ValueError):
                sl.safe_path(path, bad)
        outside = Path(tempfile.mkdtemp())
        (path / "enlace").symlink_to(outside)
        with self.assertRaises(ValueError):
            sl.safe_path(path, "enlace/dentro")

    def test_add_rename_remove_and_never_overwrite(self):
        sid, path = self.make()
        (path / "plugins").mkdir()
        source = Path(tempfile.mkdtemp()) / "Plugin.jar"
        source.write_bytes(b"jar")
        self.assertEqual(sl.add_files(path, "plugins", [source]), ["Plugin.jar"])
        self.assertEqual(sl.add_files(path, "plugins", [source]), ["Plugin (2).jar"])
        sl.rename(path, "plugins/Plugin.jar", "Otro.jar")
        self.assertEqual(sorted(e["name"] for e in sl.list_dir(path, "plugins")), ["Otro.jar", "Plugin (2).jar"])
        sl.remove(path, "plugins/Otro.jar")
        self.assertFalse((path / "plugins" / "Otro.jar").exists())
        with self.assertRaises(ValueError):
            sl.remove(path, "")
        with self.assertRaises(ValueError):
            sl.rename(path, "plugins/Plugin (2).jar", "../fuera.jar")

    def test_removing_a_link_keeps_what_it_points_to(self):
        sid, path = self.make()
        outside = Path(tempfile.mkdtemp())
        (outside / "importante.txt").write_text("hola")
        (path / "enlace").symlink_to(outside)
        sl.remove(path, "enlace")
        self.assertTrue((outside / "importante.txt").exists())

    def test_text_editing_is_limited_to_text_files_and_size(self):
        sid, path = self.make()
        (path / "a.yml").write_text("x: 1\n")
        self.assertEqual(sl.read_text(path, "a.yml"), "x: 1\n")
        sl.write_text(path, "a.yml", "x: 2\n")
        self.assertEqual((path / "a.yml").read_text(), "x: 2\n")
        (path / "server.jar").write_bytes(b"x")
        with self.assertRaises(ValueError):
            sl.read_text(path, "server.jar")
        with self.assertRaises(ValueError):
            sl.write_text(path, "a.yml", "x" * (sl.MAX_TEXT + 1))


class FilesExtraTests(Base):
    def test_disable_and_enable_a_plugin(self):
        sid, path = self.make()
        (path / "plugins").mkdir()
        (path / "plugins" / "A.jar").write_bytes(b"x")
        self.assertEqual(sl.set_enabled(path, "plugins/A.jar", False), "A.jar.disabled")
        self.assertEqual(sl.set_enabled(path, "plugins/A.jar.disabled", True), "A.jar")
        with self.assertRaises(ValueError):
            sl.set_enabled(path, "plugins/A.jar", True)
        (path / "plugins" / "b.txt").write_text("x")
        with self.assertRaises(ValueError):
            sl.set_enabled(path, "plugins/b.txt", False)

    def test_export_copies_without_overwriting(self):
        sid, path = self.make()
        (path / "a.txt").write_text("hola")
        out = Path(tempfile.mkdtemp())
        self.assertEqual(sl.export(path, "a.txt", out).name, "a.txt")
        self.assertEqual(sl.export(path, "a.txt", out).name, "a (2).txt")

    def test_backup_world_zips_the_world_and_skips_the_lock(self):
        import zipfile
        sid, path = self.make()
        with self.assertRaises(ValueError):
            sl.backup_world(path)
        (path / "world" / "region").mkdir(parents=True)
        (path / "world" / "level.dat").write_bytes(b"d")
        (path / "world" / "session.lock").write_bytes(b"l")
        (path / "plugins").mkdir()
        zipped = sl.backup_world(path)
        names = zipfile.ZipFile(zipped).namelist()
        self.assertIn("world/level.dat", names)
        self.assertNotIn("world/session.lock", names)
        self.assertEqual(zipped.parent.name, "backups")


class PropertiesTests(Base):
    def test_only_the_changed_keys_move_and_comments_stay(self):
        sid, path = self.make()
        (path / "server.properties").write_text("#Minecraft\nmotd=Hola\ngamemode=survival\n")
        sl.write_properties(path, {"gamemode": "creative", "pvp": "false"})
        self.assertEqual((path / "server.properties").read_text(),
                         "#Minecraft\nmotd=Hola\ngamemode=creative\npvp=false\n")
        self.assertEqual(sl.read_properties(path)["motd"], "Hola")
        with self.assertRaises(ValueError):
            sl.write_properties(path, {"motd": "a\nop=true"})

    def test_eula_is_only_true_when_written_by_the_person(self):
        sid, path = self.make()
        self.assertFalse(sl.eula_accepted(path))
        (path / "eula.txt").write_text("eula=false\n")
        self.assertFalse(sl.eula_accepted(path))
        sl.write_eula(path)
        self.assertTrue(sl.eula_accepted(path))


class CreateTests(Base):
    def info(self):
        return {"url": "https://x/server.jar", "size": None, "algo": None, "digest": None, "component": "c", "major": 21}

    def fake_download(self, url, target, **kwargs):
        target.write_bytes(b"jar" * 500)

    def test_create_writes_a_ready_server_and_the_eula_only_when_accepted(self):
        with mock.patch.object(sl, "resolve", return_value=self.info()), mock.patch.object(sl, "download", self.fake_download), \
                mock.patch.object(sl, "ensure_java", return_value="java"):
            yes = sl.create("Amigos", "fabric", "1.21.1", 4, 25570, eula=True)
            no = sl.create("Otro", "paper", "1.21.1", 2, 25571, eula=False)
        self.assertTrue(sl.eula_accepted(sl.folder(yes["id"])))
        self.assertFalse(sl.eula_accepted(sl.folder(no["id"])))
        self.assertEqual(sl.read_properties(sl.folder(yes["id"]))["server-port"], "25570")
        self.assertEqual([m["name"] for m in sl.all_servers()], ["Amigos", "Otro"])

    def test_a_failed_download_leaves_no_folder(self):
        def boom(*a, **k):
            raise ValueError("falló")
        with mock.patch.object(sl, "resolve", return_value=self.info()), mock.patch.object(sl, "download", boom):
            with self.assertRaises(ValueError):
                sl.create("Roto", "paper", "1.21.1", 2, 25572, eula=True)
        self.assertEqual(sl.all_servers(), [])
        self.assertEqual(list(sl.root().iterdir()), [])

    def test_validation_of_name_port_and_duplicates(self):
        sid, path = self.make()
        for args in (("", "paper", "1.21", 2, 25565), ("x", "otro", "1.21", 2, 25565), ("x", "paper", "../1", 2, 25565),
                     ("x", "paper", "1.21", 0, 25565), ("x", "paper", "1.21", 2, 80), ("x", "paper", "1.21", 2, 25590)):
            with self.assertRaises(ValueError, msg=args):
                sl.check_new(*args)

    def test_download_checks_hash_and_size(self):
        class Response:
            def __init__(self, data):
                self.data = data
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def raise_for_status(self): pass
            def iter_content(self, n): yield self.data
        data = b"x" * 2000
        target = Path(tempfile.mkdtemp()) / "server.jar"
        with mock.patch("servidor_local.requests.get", return_value=Response(data)):
            sl.download("https://x", target, size=2000, algo="sha256", digest=hashlib.sha256(data).hexdigest())
            self.assertEqual(target.read_bytes(), data)
            target.unlink()
            with self.assertRaises(ValueError):
                sl.download("https://x", target, size=2000, algo="sha256", digest="0" * 64)
            with self.assertRaises(ValueError):
                sl.download("https://x", target, size=1999)
        self.assertEqual([p.name for p in target.parent.iterdir()], [])


class ResolveTests(Base):
    def test_each_kind_builds_the_right_download(self):
        manifest = {"versions": [{"id": "1.21.1", "type": "release", "url": "https://piston-meta.mojang.com/v.json"}]}
        version = {"javaVersion": {"component": "java-runtime-delta", "majorVersion": 21},
                   "downloads": {"server": {"url": "https://piston-data.mojang.com/s.jar", "size": 5, "sha1": "ab"}}}
        paper = [{"channel": "BETA"}, {"channel": "STABLE", "downloads": {"server:default": {
            "url": "https://fill-data.papermc.io/p.jar", "size": 9, "checksums": {"sha256": "cd"}}}}]
        fabric_loaders = [{"loader": {"version": "0.9", "stable": False}}, {"loader": {"version": "0.8", "stable": True}}]
        fabric_installers = [{"version": "1.1", "stable": True}]

        def get(url, **kwargs):
            data = (manifest if url == sl.MANIFEST else version if url.endswith("v.json") else
                    paper if "fill.papermc.io" in url else fabric_loaders if "versions/loader" in url else fabric_installers)
            return mock.Mock(json=lambda: data)
        with mock.patch.object(sl, "_get", get):
            vanilla = sl.resolve("vanilla", "1.21.1")
            self.assertEqual((vanilla["algo"], vanilla["digest"], vanilla["major"]), ("sha1", "ab", 21))
            self.assertEqual(sl.resolve("paper", "1.21.1")["digest"], "cd")
            self.assertTrue(sl.resolve("fabric", "1.21.1")["url"].endswith("/1.21.1/0.8/1.1/server/jar"))
            with self.assertRaises(ValueError):
                sl.resolve("paper", "9.9")


class RunnerTests(Base):
    def setUp(self):
        super().setUp()
        self.script = motor.ROOT / "falso.py"
        self.script.write_text(FAKE)
        self.patches = [mock.patch.object(sl, "ensure_java", return_value=sys.executable),
                        mock.patch.object(sl, "launch_command", lambda meta, path, java: [sys.executable, "-u", str(self.script)]),
                        mock.patch.object(sl, "free_port", return_value=True)]
        for patch in self.patches:
            patch.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])

    def wait(self, runner, state, seconds=8):
        end = time.monotonic() + seconds
        while runner.state != state and time.monotonic() < end:
            time.sleep(0.05)
        self.assertEqual(runner.state, state)

    def test_cannot_start_without_the_eula(self):
        sid, path = self.make()
        with self.assertRaises(sl.EulaError):
            sl.runner(sid).start()

    def test_start_command_stop_and_delete(self):
        sid, path = self.make()
        sl.write_eula(path)
        runner = sl.runner(sid)
        runner.start()
        self.wait(runner, "running")
        runner.send("/say hola")
        end = time.monotonic() + 5
        while not any("echo say hola" in line for line in runner.lines) and time.monotonic() < end:
            time.sleep(0.05)
        self.assertTrue(any("echo say hola" in line for line in runner.lines))
        with self.assertRaises(RuntimeError):
            sl.delete(sid)
        runner.stop()
        self.wait(runner, "stopped")
        with self.assertRaises(RuntimeError):
            runner.send("list")
        sl.delete(sid)
        self.assertFalse(path.exists())

    def test_restart_comes_back_up(self):
        sid, path = self.make()
        sl.write_eula(path)
        runner = sl.runner(sid)
        runner.start()
        self.wait(runner, "running")
        first = runner.process
        runner.restart()
        end = time.monotonic() + 10
        while (runner.process is first or runner.state != "running") and time.monotonic() < end:
            time.sleep(0.05)
        self.assertEqual(runner.state, "running")
        self.assertIsNot(runner.process, first)

    def test_a_busy_port_is_refused_before_anything_starts(self):
        sid, path = self.make()
        sl.write_eula(path)
        with mock.patch.object(sl, "free_port", return_value=False):
            with self.assertRaises(RuntimeError):
                sl.runner(sid).start()
        self.assertEqual(sl.runner(sid).state, "stopped")


if __name__ == "__main__":
    unittest.main()

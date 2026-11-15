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


class ForgeTests(Base):
    PROMOS = {"promos": {"1.21.1-latest": "52.1.21", "1.21.1-recommended": "52.1.20", "1.20.1-latest": "47.4.0", "1.16.5-latest": "36.2.42"}}

    def test_builds_prefer_recommended_and_versions_follow_forge_support(self):
        manifest = {"versions": [{"id": v, "type": "release", "url": "u"} for v in ("26.3", "1.21.1", "1.20.1")]}
        with mock.patch.object(sl, "_get", lambda url, **k: mock.Mock(json=lambda: self.PROMOS if "promotions" in url else manifest)):
            self.assertEqual(sl.forge_builds()["1.21.1"], "52.1.20")
            self.assertEqual(sl.forge_builds()["1.20.1"], "47.4.0")
            self.assertEqual(sl.release_versions("forge"), ["1.21.1", "1.20.1"])
            self.assertEqual(sl.release_versions(), ["26.3", "1.21.1", "1.20.1"])

    def test_resolve_builds_the_maven_url_and_checks_the_sidecar_hash(self):
        manifest = {"versions": [{"id": "1.21.1", "type": "release", "url": "https://piston-meta.mojang.com/v.json"}]}
        version = {"javaVersion": {"component": "java-runtime-delta", "majorVersion": 21}, "downloads": {}}
        digest = "ab" * 32

        def get(url, **kwargs):
            if url.endswith(".sha256"):
                return mock.Mock(text=digest + "  forge.jar\n")
            return mock.Mock(json=lambda: self.PROMOS if "promotions" in url else manifest if url == sl.MANIFEST else version)
        with mock.patch.object(sl, "_get", get):
            info = sl.resolve("forge", "1.21.1")
            self.assertEqual(info["url"], "https://maven.minecraftforge.net/net/minecraftforge/forge/1.21.1-52.1.20/forge-1.21.1-52.1.20-installer.jar")
            self.assertEqual((info["algo"], info["digest"], info["forge_build"]), ("sha256", digest, "52.1.20"))
            with self.assertRaises(ValueError):
                sl.resolve("forge", "1.2.3")

    def test_launch_command_modern_legacy_and_missing(self):
        sid, path = self.make(kind="forge", memory=3)
        with self.assertRaises(RuntimeError):
            sl.launch_command(sl.load(sid), path, "java")
        (path / "forge-1.16.5-36.2.42.jar").write_bytes(b"x")
        (path / "forge-installer.jar").write_bytes(b"x")
        legacy = sl.launch_command(sl.load(sid), path, "java")
        self.assertEqual(legacy, ["java", "-Xmx3G", "-Xms2G", "-jar", "forge-1.16.5-36.2.42.jar", "nogui"])
        args = path / "libraries/net/minecraftforge/forge/1.21.1-52.1.20"
        args.mkdir(parents=True)
        (args / "unix_args.txt").write_text("x")
        (args / "win_args.txt").write_text("x")
        modern = sl.launch_command(sl.load(sid), path, "java")
        self.assertEqual(modern[:2], ["java", "@user_jvm_args.txt"])
        self.assertTrue(modern[2].startswith("@libraries/net/minecraftforge/forge/1.21.1-52.1.20/") and modern[3] == "nogui")
        self.assertIn("-Xmx3G", (path / "user_jvm_args.txt").read_text())

    def test_installer_success_cleans_up_and_failure_explains(self):
        sid, path = self.make(kind="forge")
        (path / "forge-installer.jar").write_bytes(b"x")
        with mock.patch.object(sl.subprocess, "run", return_value=mock.Mock(returncode=0, stdout="", stderr="")) as run:
            sl.install_forge(path, "java")
        self.assertEqual(run.call_args.args[0], ["java", "-jar", "forge-installer.jar", "--installServer"])
        self.assertFalse((path / "forge-installer.jar").exists())
        (path / "forge-installer.jar").write_bytes(b"x")
        with mock.patch.object(sl.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="", stderr="boom\nNo internet")):
            with self.assertRaises(RuntimeError) as caught:
                sl.install_forge(path, "java")
        self.assertIn("No internet", str(caught.exception))

    def test_full_java_skips_mojangs_runtime_and_picks_the_lowest_fitting_version(self):
        bundled = str(motor.ROOT / "minecraft" / "runtime" / "x" / "bin" / "java")
        found = [{"path": "/usr/lib/jvm/j25/bin/java", "major": 25}, {"path": bundled, "major": 21},
                 {"path": "/usr/lib/jvm/j21/bin/java", "major": 21}, {"path": "/usr/lib/jvm/j17/bin/java", "major": 17}]
        with mock.patch("java_detect.find_java", return_value=found):
            self.assertEqual(sl.full_java(21), "/usr/lib/jvm/j21/bin/java")
            self.assertEqual(sl.full_java(25), "/usr/lib/jvm/j25/bin/java")
            self.assertIsNone(sl.full_java(26))

    def test_create_fails_clearly_when_there_is_no_full_java(self):
        info = {"url": "https://x", "size": None, "algo": None, "digest": None, "component": "c", "major": 21, "forge_build": "1"}
        with mock.patch.object(sl, "resolve", return_value=info), \
                mock.patch.object(sl, "download", lambda url, target, **k: target.write_bytes(b"i" * 2000)), \
                mock.patch.object(sl, "ensure_java", return_value="mojang-java"), mock.patch.object(sl, "full_java", return_value=None), \
                mock.patch("java_propio.install", side_effect=ValueError("sin red")):
            with self.assertRaises(RuntimeError) as caught:
                sl.create("Mods", "forge", "1.21.1", 4, 25581, eula=False)
        self.assertIn("Java completo", str(caught.exception))
        self.assertEqual(sl.all_servers(), [])

    def test_ensure_full_java_prefers_what_exists_and_downloads_only_when_needed(self):
        with mock.patch.object(sl, "full_java", return_value="/usr/bin/java"), mock.patch("java_propio.install") as install:
            self.assertEqual(sl.ensure_full_java(21), "/usr/bin/java")
            install.assert_not_called()
        notes = []
        with mock.patch.object(sl, "full_java", return_value=None), mock.patch("java_propio.install", return_value="/datos/java/temurin-21/bin/java") as install:
            self.assertEqual(sl.ensure_full_java(21, notes.append), "/datos/java/temurin-21/bin/java")
            install.assert_called_once()
        self.assertTrue(any("Java" in note for note in notes))

    def test_create_runs_the_installer_and_leaves_no_server_jar(self):
        info = {"url": "https://x", "size": None, "algo": None, "digest": None, "component": "c", "major": 21, "forge_build": "52.1.20"}
        ran = []
        with mock.patch.object(sl, "resolve", return_value=info), \
                mock.patch.object(sl, "download", lambda url, target, **k: target.write_bytes(b"i" * 2000)), \
                mock.patch.object(sl, "ensure_java", return_value="mojang-java"), \
                mock.patch.object(sl, "full_java", return_value="/usr/bin/java"), \
                mock.patch.object(sl, "install_forge", lambda path, java: ran.append((path.name, java))):
            meta = sl.create("Mods", "forge", "1.21.1", 4, 25580, eula=False)
        self.assertEqual(meta["forge_build"], "52.1.20")
        self.assertEqual(ran, [(meta["id"], "/usr/bin/java")])  # the installer runs on a full Java, not Mojang's runtime
        self.assertTrue((sl.folder(meta["id"]) / "forge-installer.jar").exists())
        self.assertFalse((sl.folder(meta["id"]) / "server.jar").exists())


class CatalogTests(Base):
    def test_search_filters_by_version_type_and_side(self):
        import json
        seen = {}

        def get(url, params=None, **k):
            seen.update(params)
            return mock.Mock(json=lambda: {"hits": [{"project_id": "AAAAAAAA", "title": "T", "description": "d", "downloads": 5}], "total_hits": 1})
        sid, path = self.make(kind="fabric", version="1.21.1")
        with mock.patch.object(sl, "_get", get):
            result = sl.catalog_search(sl.load(sid), "")
            facets = json.loads(seen["facets"])
            self.assertIn(["versions:1.21.1"], facets)
            self.assertIn(["project_type:mod"], facets)
            self.assertIn(["categories:fabric"], facets)
            self.assertIn(["server_side:required", "server_side:optional"], facets)
            self.assertEqual(seen["index"], "downloads")
            self.assertEqual(result["hits"][0]["title"], "T")
            sl.save({**sl.load(sid), "kind": "paper"})
            sl.catalog_search(sl.load(sid), "vault")
            facets = json.loads(seen["facets"])
            self.assertIn(["categories:paper", "categories:spigot", "categories:bukkit"], facets)
            self.assertIn(["project_type:plugin", "project_type:mod"], facets)
            self.assertNotIn(["server_side:required", "server_side:optional"], facets)
            self.assertEqual(seen["index"], "relevance")
            sl.save({**sl.load(sid), "kind": "vanilla"})
            with self.assertRaises(ValueError):
                sl.catalog_search(sl.load(sid))

    def release(self, name, deps=(), url=None, sha="ab" * 64, version_type="release"):
        return {"version_type": version_type, "version_number": "1.0", "dependencies": list(deps), "files": [
            {"primary": True, "filename": name, "url": url or "https://cdn.modrinth.com/data/x/versions/y/" + name, "size": 10,
             "hashes": {"sha512": sha}}]}

    def test_install_downloads_with_hash_follows_dependencies_and_records(self):
        sid, path = self.make(kind="fabric", version="1.21.1")
        data = {"MAINMAIN": [self.release("main.jar", deps=[{"dependency_type": "required", "project_id": "DEPDEPDE"},
                                                             {"dependency_type": "optional", "project_id": "OPTOPTOP"}])],
                "DEPDEPDE": [self.release("dep.jar", deps=[{"dependency_type": "required", "project_id": "MAINMAIN"}])]}
        calls = []

        def get(url, **k):
            return mock.Mock(json=lambda: data[url.split("/")[-2]])

        def fake_download(url, target, **k):
            calls.append((target.name, k["algo"], k["digest"]))
            target.write_bytes(b"j" * 2000)
        with mock.patch.object(sl, "_get", get), mock.patch.object(sl, "download", fake_download):
            installed = sl.catalog_install(path, sl.load(sid), "MAINMAIN", title="Principal")
        self.assertEqual(sorted(installed), ["dep.jar", "main.jar"])
        self.assertEqual(calls[0], ("main.jar", "sha512", "ab" * 64))
        self.assertTrue((path / "mods" / "dep.jar").exists())
        self.assertEqual(sl.catalog_installed(path)["MAINMAIN"]["title"], "Principal")
        self.assertNotIn("OPTOPTOP", sl.catalog_installed(path))
        sl.catalog_remove(path, sl.load(sid), "MAINMAIN")
        self.assertFalse((path / "mods" / "main.jar").exists())
        self.assertNotIn("MAINMAIN", sl.catalog_installed(path))

    def test_install_refuses_foreign_hosts_unsafe_names_and_missing_hash(self):
        sid, path = self.make(kind="paper", version="1.21.1")
        for bad in (self.release("a.jar", url="https://evil.example/a.jar"), self.release("../a.jar"), self.release("a.exe"),
                    self.release("a.jar", sha="")):
            with mock.patch.object(sl, "_get", lambda url, **k: mock.Mock(json=lambda: [bad])):
                with self.assertRaises(ValueError):
                    sl.catalog_install(path, sl.load(sid), "ABCDEFGH")
        with mock.patch.object(sl, "_get", lambda url, **k: mock.Mock(json=lambda: [])):
            with self.assertRaises(ValueError):
                sl.catalog_install(path, sl.load(sid), "ABCDEFGH")
        with self.assertRaises(ValueError):
            sl.catalog_install(path, sl.load(sid), "../etc")
        self.assertFalse((path / "plugins").exists() and any((path / "plugins").iterdir()))


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


class OrphanTests(Base):
    def test_a_port_with_recently_closed_connections_is_still_free(self):
        if sl.os.name == "nt":
            self.skipTest("TIME_WAIT behaviour differs on Windows")
        import socket
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        client = socket.create_connection(("127.0.0.1", port))
        connection, _ = listener.accept()
        connection.close()   # the side that closes first keeps the TIME_WAIT
        client.close()
        listener.close()
        self.assertTrue(sl.free_port(port))
        busy = socket.socket()
        busy.bind(("0.0.0.0", 0))
        busy.listen()
        try:
            self.assertFalse(sl.free_port(busy.getsockname()[1]))   # a real listener still counts as taken
        finally:
            busy.close()

    def test_process_identity(self):
        mine = sl.process_start(sl.os.getpid())
        self.assertIsNotNone(mine)
        self.assertEqual(mine, sl.process_start(sl.os.getpid()))
        self.assertIsNone(sl.process_start(0))
        self.assertIsNone(sl.process_start("no"))
        quick = subprocess_run_and_wait()
        self.assertIsNone(sl.process_start(quick))

    def test_reconnects_to_a_live_server_and_stops_it_without_commands(self):
        import subprocess
        sid, path = self.make()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
        self.addCleanup(lambda: (child.poll() is None and child.kill(), child.wait()))
        sl._write_pid(path, child.pid)
        (path / "logs").mkdir()
        (path / "logs" / "latest.log").write_text("[10:00:00] Done (1s)!\n")
        runner = sl.Runner(sid)
        self.assertTrue(runner.reattach())
        self.assertEqual((runner.state, runner.adopted), ("running", True))
        self.assertTrue(any("Reconectado" in line for line in runner.lines))
        with self.assertRaises(RuntimeError):
            runner.send("list")
        with open(path / "logs" / "latest.log", "a") as log:
            log.write("[10:00:05] Alex joined the game\n")
        end = time.monotonic() + 5
        while not any("Alex joined" in line for line in runner.lines) and time.monotonic() < end:
            time.sleep(0.1)
        self.assertTrue(any("Alex joined" in line for line in runner.lines))
        runner.stop()
        end = time.monotonic() + 15
        while runner.state != "stopped" and time.monotonic() < end:
            time.sleep(0.1)
        self.assertEqual(runner.state, "stopped")
        self.assertIsNotNone(child.wait(5))
        self.assertFalse((path / "nova-server.pid").exists())

    def test_a_reused_pid_is_never_adopted_or_signalled(self):
        sid, path = self.make()
        motor.save(path / "nova-server.pid", {"pid": sl.os.getpid(), "start": 12345})  # same PID, other start time
        runner = sl.Runner(sid)
        self.assertFalse(runner.reattach())
        self.assertEqual(runner.state, "stopped")
        self.assertFalse((path / "nova-server.pid").exists())

    def test_restart_waits_for_a_port_that_is_still_closing(self):
        runner = sl.Runner("0123456789ab")
        attempts = []

        def start():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("El puerto 25565 lo está usando otro programa")
        runner.start = start
        with mock.patch.object(sl.time, "sleep"):
            runner._start_again()
        self.assertEqual(len(attempts), 3)
        errors = []
        runner.listeners.append(lambda kind, payload: errors.append(kind))
        runner.start = mock.Mock(side_effect=RuntimeError("Hay que aceptar el EULA"))
        runner._start_again()
        self.assertEqual(runner.start.call_count, 1)
        self.assertEqual(errors, ["error"])


def subprocess_run_and_wait():
    import subprocess
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


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

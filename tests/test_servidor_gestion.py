from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import servidor_gestion as sg  # noqa: E402
import servidor_local as sl  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        sl.RUNNERS.clear()
        sg._SIZE_CACHE.clear()

    def tearDown(self):
        motor.ROOT = self.original

    def make(self, **extra):
        sid = "0123456789ab"
        path = sl.folder(sid)
        path.mkdir(parents=True, exist_ok=True)
        meta = {"id": sid, "name": "Mundo", "kind": "paper", "version": "1.21.1", "memory": 2, "port": 25590,
                "java_component": "x", "java_major": 21, "created": 1, "build": "10", **extra}
        sl.save(meta)
        return sid, path

    def world(self, path, text="uno"):
        (path / "world" / "region").mkdir(parents=True, exist_ok=True)
        (path / "world" / "level.dat").write_text(text)
        (path / "world" / "session.lock").write_text("lock")
        (path / "world_nether").mkdir(exist_ok=True)
        (path / "world_nether" / "DIM-1.dat").write_text("n")

    def running(self, sid, adopted=False, state="running"):
        runner = sl.runner(sid)
        runner.state, runner.adopted = state, adopted
        runner.send = mock.Mock()
        return runner


class BackupTests(Base):
    def test_backup_contains_the_worlds_but_not_the_lock(self):
        sid, path = self.make()
        with self.assertRaises(ValueError):
            sg.create_backup(sid)
        self.world(path)
        target = sg.create_backup(sid, "mundo")
        names = zipfile.ZipFile(target).namelist()
        self.assertIn("world/level.dat", names)
        self.assertIn("world_nether/DIM-1.dat", names)
        self.assertNotIn("world/session.lock", names)
        with self.assertRaises(ValueError):
            sg.create_backup(sid, "../x")
        self.assertEqual([p.suffix for p in (path / "backups").iterdir()], [".zip"])

    def test_a_running_server_saves_first_and_an_orphan_refuses(self):
        sid, path = self.make()
        self.world(path)
        runner = self.running(sid)
        with mock.patch.object(sg.time, "sleep"):
            sg.create_backup(sid)
        self.assertEqual([c.args[0] for c in runner.send.call_args_list], ["save-off", "save-all flush", "save-on"])
        runner.adopted = True
        with self.assertRaises(ValueError):
            sg.create_backup(sid)

    def test_list_prune_and_delete_only_touch_what_they_should(self):
        sid, path = self.make()
        (path / "backups").mkdir()
        for index, name in enumerate(["auto-1.zip", "auto-2.zip", "auto-3.zip", "mundo-1.zip", "antes-1.zip", "x.txt"]):
            file = path / "backups" / name
            file.write_text("z")
            sg.os.utime(file, (1000 + index, 1000 + index))
        listed = sg.list_backups(sid)
        self.assertEqual([i["name"] for i in listed][:2], ["antes-1.zip", "mundo-1.zip"])
        self.assertEqual({i["kind"] for i in listed}, {"auto", "mundo", "antes"})
        sg.prune_backups(sid, 2)
        left = {i["name"] for i in sg.list_backups(sid)}
        self.assertEqual(left, {"auto-3.zip", "auto-2.zip", "mundo-1.zip", "antes-1.zip"})
        sg.delete_backup(sid, "mundo-1.zip")
        with self.assertRaises(ValueError):
            sg.delete_backup(sid, "../../etc/passwd.zip")
        with self.assertRaises(ValueError):
            sg.delete_backup(sid, "mundo-1.zip")

    def test_restore_brings_the_old_world_back_and_keeps_a_safety_copy(self):
        sid, path = self.make()
        self.world(path, "uno")
        target = sg.create_backup(sid, "mundo")
        (path / "world" / "level.dat").write_text("dos")
        (path / "world" / "nueva.txt").write_text("x")
        result = sg.restore_backup(sid, target.name)
        self.assertEqual((path / "world" / "level.dat").read_text(), "uno")
        self.assertFalse((path / "world" / "nueva.txt").exists())
        self.assertTrue(result["safety"].startswith("antes-"))
        safety = zipfile.ZipFile(path / "backups" / result["safety"])
        self.assertEqual(safety.read("world/level.dat"), b"dos")

    def test_restore_refuses_a_running_server_and_hostile_zips(self):
        sid, path = self.make()
        self.world(path)
        good = sg.create_backup(sid)
        self.running(sid)
        with self.assertRaises(RuntimeError):
            sg.restore_backup(sid, good.name)
        sl.RUNNERS[sid].state = "stopped"
        evil = path / "backups" / "mundo-evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("../fuera.txt", "x")
        with self.assertRaises(ValueError):
            sg.restore_backup(sid, "mundo-evil.zip")
        self.assertFalse((path.parent / "fuera.txt").exists())
        self.assertEqual((path / "world" / "level.dat").read_text(), "uno")   # nothing was removed
        with self.assertRaises(ValueError):
            sg.restore_backup(sid, "../x.zip")

    def test_settings_and_scheduled_backups(self):
        self.assertEqual(sg.backup_settings({}), {"hours": 0, "keep": 5, "on_stop": False})
        self.assertEqual(sg.backup_settings({"backup_hours": 99999, "backup_keep": 0})["hours"], 0)
        sid, path = self.make(backup_hours=2, backup_keep=2)
        self.world(path)
        self.assertEqual(sg.auto_backups(), [])              # stopped: nothing to do
        self.running(sid)
        with mock.patch.object(sg.time, "sleep"):
            self.assertEqual(len(sg.auto_backups()), 1)
            self.assertEqual(sg.auto_backups(), [])          # a recent one exists
            later = time.time() + 3 * 3600
            self.assertEqual(len(sg.auto_backups(now=later)), 1)
            self.assertEqual(len(sg.auto_backups(now=later + 10 * 3600)), 1)
        self.assertLessEqual(len([i for i in sg.list_backups(sid) if i["kind"] == "auto"]), 2)

    def test_backup_after_stop_only_when_asked(self):
        sid, path = self.make()
        self.world(path)
        self.assertIsNone(sg.on_stopped(sid))
        sl.save({**sl.load(sid), "backup_on_stop": True})
        self.assertTrue(sg.on_stopped(sid).name.startswith("auto-"))


class PlayerTests(Base):
    def test_offline_uuid_is_stable_and_well_formed(self):
        first = sg.offline_uuid("Alex")
        self.assertEqual(first, sg.offline_uuid("Alex"))
        self.assertNotEqual(first, sg.offline_uuid("Sofi"))
        self.assertEqual(first[14], "3")
        self.assertIn(first[19], "89ab")

    def test_lookup_uses_mojang_only_for_online_mode(self):
        answer = mock.Mock(status_code=200, json=lambda: {"id": "069a79f444e94726a5befca90e38aaf5", "name": "Notch"})
        with mock.patch.object(sg.requests, "get", return_value=answer):
            self.assertEqual(sg.lookup_uuid("Notch"), "069a79f4-44e9-4726-a5be-fca90e38aaf5")
        with mock.patch.object(sg.requests, "get", return_value=mock.Mock(status_code=404)):
            with self.assertRaises(ValueError):
                sg.lookup_uuid("NoExisteNadie")
        with mock.patch.object(sg.requests, "get", side_effect=AssertionError("no network")):
            self.assertEqual(sg.lookup_uuid("Alex", online_mode=False), sg.offline_uuid("Alex"))
        for bad in ("", "ab", "x" * 17, "con espacio", "a;b"):
            with self.assertRaises(ValueError):
                sg.lookup_uuid(bad, online_mode=False)

    def test_stopped_server_edits_the_files(self):
        sid, path = self.make()
        (path / "server.properties").write_text("online-mode=false\n")
        self.assertEqual(sg.change_player(sid, "ops", "Alex"), "archivo")
        entry = sg.read_players(sid, "ops")[0]
        self.assertEqual((entry["name"], entry["level"], entry["uuid"]), ("Alex", 4, sg.offline_uuid("Alex")))
        sg.change_player(sid, "whitelist", "Sofi")
        sg.change_player(sid, "bans", "Troll")
        self.assertEqual(sg.read_players(sid, "bans")[0]["expires"], "forever")
        with self.assertRaises(ValueError):
            sg.change_player(sid, "whitelist", "sofi")           # same name, other case
        sg.change_player(sid, "whitelist", "SOFI", add=False)
        self.assertEqual(sg.read_players(sid, "whitelist"), [])
        with self.assertRaises(ValueError):
            sg.change_player(sid, "whitelist", "Sofi", add=False)
        with self.assertRaises(ValueError):
            sg.change_player(sid, "otra", "Alex")

    def test_running_server_gets_a_command_and_orphans_and_starting_servers_are_refused(self):
        sid, path = self.make()
        runner = self.running(sid)
        self.assertEqual(sg.change_player(sid, "ops", "Alex"), "comando")
        self.assertEqual(sg.change_player(sid, "whitelist", "Sofi", add=False), "comando")
        self.assertEqual([c.args[0] for c in runner.send.call_args_list], ["op Alex", "whitelist remove Sofi"])
        sg.kick(sid, "Alex", "juega mejor")
        self.assertEqual(runner.send.call_args.args[0], "kick Alex juega mejor")
        sg.refresh_online(sid)
        self.assertEqual(runner.send.call_args.args[0], "list")
        runner.adopted = True
        with self.assertRaises(RuntimeError):
            sg.change_player(sid, "ops", "Alex")
        with self.assertRaises(RuntimeError):
            sg.kick(sid, "Alex")
        runner.adopted, runner.state = False, "starting"
        with self.assertRaises(RuntimeError):
            sg.change_player(sid, "ops", "Alex")

    def test_damaged_files_read_as_empty(self):
        sid, path = self.make()
        (path / "ops.json").write_text("{no es json")
        (path / "whitelist.json").write_text('{"a": 1}')
        self.assertEqual((sg.read_players(sid, "ops"), sg.read_players(sid, "whitelist"), sg.read_players(sid, "bans")), ([], [], []))

    def test_online_players_follow_the_console(self):
        online = set()
        for line in ("[10:00:00] [Server thread/INFO]: Alex joined the game", "[10:00:01] [Server thread/INFO]: Sofi joined the game",
                     "[10:05:00] [Server thread/INFO]: Alex left the game"):
            sl.track_players(online, line)
        self.assertEqual(online, {"Sofi"})
        sl.track_players(online, "[10:06:00] [Server thread/INFO]: There are 2 of a max of 20 players online: Ana, Beto")
        self.assertEqual(online, {"Ana", "Beto"})
        sl.track_players(online, "[10:07:00] [Server thread/INFO]: There are 0 of a max of 20 players online: ")
        self.assertEqual(online, set())


class StatusTests(Base):
    def test_usage_reads_this_process_and_ignores_garbage(self):
        reading = sg.usage(sg.os.getpid())
        self.assertGreater(reading["rss"], 1_000_000)
        self.assertGreaterEqual(reading["cpu"], 0)
        self.assertIsNone(sg.usage("no"))
        self.assertIsNone(sg.usage(2 ** 22 + 12345))

    def test_cpu_percent_needs_two_readings_and_stays_in_range(self):
        sampler = sg.Sampler()
        self.assertIsNone(sampler.percent(sg.os.getpid()))
        end = time.monotonic() + 0.3
        while time.monotonic() < end:
            pass
        value = sampler.percent(sg.os.getpid())
        self.assertTrue(0 <= value <= 100)

    def test_status_of_stopped_and_running_servers(self):
        sid, path = self.make(memory=4)
        (path / "server.properties").write_text("max-players=8\nserver-port=25999\n")
        self.world(path)
        stopped = sg.status(sid)
        self.assertEqual((stopped["state"], stopped["players"], stopped["max_players"], stopped["port"]), ("stopped", [], 8, "25999"))
        self.assertGreater(stopped["world"], 0)
        self.assertGreater(stopped["total"], 0)
        runner = self.running(sid)
        runner.pid, runner.started_at, runner.online = sg.os.getpid(), time.time() - 90, {"Sofi", "Alex"}
        live = sg.status(sid, sg.Sampler())
        self.assertEqual(live["players"], ["Alex", "Sofi"])
        self.assertTrue(89 <= live["uptime"] <= 100)
        self.assertGreater(live["memory"], 0)
        self.assertEqual(live["memory_limit"], 4 * 1024**3)

    def test_world_size_is_cached(self):
        sid, path = self.make()
        self.world(path)
        first = sg.world_size(sid)
        (path / "world" / "grande.bin").write_bytes(b"x" * 5000)
        self.assertEqual(sg.world_size(sid), first)
        self.assertGreater(sg.world_size(sid, ttl=0), first)


class UpdateTests(Base):
    def info(self, build="11", **extra):
        return {"url": "https://x", "size": None, "algo": None, "digest": None, "component": "new-java", "major": 21, "build": build, **extra}

    def test_version_keys_and_newer_versions(self):
        self.assertEqual(sg.version_key("1.21.11"), (1, 21, 11))
        self.assertGreater(sg.version_key("26.3"), sg.version_key("1.21.11"))
        self.assertGreater(sg.version_key("1.21.11"), sg.version_key("1.21.2"))
        self.assertIsNone(sg.version_key("24w14a"))
        self.assertEqual(sg.newer_versions({"version": "1.21.2"}, ["26.3", "1.21.11", "1.21.2", "1.20.1", "24w14a"]), ["26.3", "1.21.11"])

    def test_check_update_compares_builds_and_lists_newer_versions(self):
        sid, path = self.make(build="10")
        meta = sl.load(sid)
        with mock.patch.object(sl, "resolve", return_value=self.info("11")), mock.patch.object(sl, "release_versions", return_value=["1.21.11", "1.21.1"]):
            result = sg.check_update(meta)
            self.assertEqual((result["build"], result["versions"]), (True, ["1.21.11"]))
        with mock.patch.object(sl, "resolve", return_value=self.info("10")), mock.patch.object(sl, "release_versions", return_value=[]):
            self.assertIs(sg.check_update(meta)["build"], False)
            self.assertIsNone(sg.check_update({**meta, "build": None})["build"])

    def fake_download(self, url, target, **kwargs):
        target.write_bytes(b"nuevo" * 500)

    def test_update_to_a_newer_version_backs_up_replaces_and_records(self):
        sid, path = self.make(version="1.21.1")
        (path / "server.jar").write_bytes(b"viejo" * 500)
        (path / "plugins").mkdir()
        (path / "plugins" / "A.jar").write_bytes(b"x")
        self.world(path)
        with mock.patch.object(sl, "resolve", return_value=self.info("77")), mock.patch.object(sl, "download", self.fake_download), \
                mock.patch.object(sl, "ensure_java", return_value="java"):
            result = sg.update_server(sid, "1.21.11")
        self.assertEqual((result["from"], result["to"], result["extensions"], result["changed_version"]), ("1.21.1", "1.21.11", 1, True))
        self.assertTrue(result["backup"].startswith("antes-"))
        self.assertEqual((path / "server.jar").read_bytes(), b"nuevo" * 500)
        self.assertEqual((path / "server.jar.old").read_bytes(), b"viejo" * 500)
        meta = sl.load(sid)
        self.assertEqual((meta["version"], meta["build"], meta["java_component"]), ("1.21.11", "77", "new-java"))
        self.assertFalse((path / "server.jar.new").exists())

    def test_update_refuses_downgrades_running_servers_and_failed_downloads_change_nothing(self):
        sid, path = self.make(version="1.21.1")
        (path / "server.jar").write_bytes(b"viejo" * 500)
        with self.assertRaises(ValueError):
            sg.update_server(sid, "1.20.1")
        self.running(sid)
        with self.assertRaises(RuntimeError):
            sg.update_server(sid)
        sl.RUNNERS[sid].state = "stopped"

        def boom(*a, **k):
            raise ValueError("falló")
        with mock.patch.object(sl, "resolve", return_value=self.info()), mock.patch.object(sl, "download", boom):
            with self.assertRaises(ValueError):
                sg.update_server(sid, "1.21.11")
        self.assertEqual((path / "server.jar").read_bytes(), b"viejo" * 500)
        self.assertEqual(sl.load(sid)["version"], "1.21.1")

    def test_forge_update_reinstalls_with_a_full_java_or_explains(self):
        sid, path = self.make(kind="forge", version="1.21.1", forge_build="52.1.20")
        info = self.info("52.1.21", forge_build="52.1.21")
        ran = []
        with mock.patch.object(sl, "resolve", return_value=info), mock.patch.object(sl, "download", self.fake_download), \
                mock.patch.object(sl, "full_java", return_value="/usr/bin/java"), mock.patch.object(sl, "install_forge", lambda p, j: ran.append(j)):
            sg.update_server(sid)
        self.assertEqual(ran, ["/usr/bin/java"])
        self.assertEqual(sl.load(sid)["forge_build"], "52.1.21")
        with mock.patch.object(sl, "resolve", return_value=info), mock.patch.object(sl, "download", self.fake_download), \
                mock.patch.object(sl, "full_java", return_value=None), mock.patch("java_propio.install", side_effect=ValueError("sin red")):
            with self.assertRaises(RuntimeError):
                sg.update_server(sid)
        self.assertFalse((path / "forge-installer.jar").exists())


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import catalogo  # noqa: E402
import motor  # noqa: E402


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data if isinstance(data, (bytes, str)) else json.dumps(data))
    return path


def fake_response(chunks, *, status=200, redirect=False, headers=None):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.is_redirect = redirect
    response.status_code = status
    response.headers = headers or {}
    response.iter_content.return_value = chunks
    return response


class TempRootCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(motor, "ROOT", self.folder / "root")
        patcher.start()
        self.addCleanup(patcher.stop)
        no_net = mock.patch.object(catalogo.requests, "get", side_effect=AssertionError("red"))
        no_net.start()
        self.addCleanup(no_net.stop)
        no_post = mock.patch.object(catalogo.requests, "post", side_effect=AssertionError("red"))
        no_post.start()
        self.addCleanup(no_post.stop)


class PackPathTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(catalogo.pack_path("mods/a.jar"), Path("mods/a.jar"))

    def test_dangerous_paths(self):
        for bad in ("../x", "a/../../x", "/etc/passwd", "a\\b", "C:/x", "", "a/../b"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                catalogo.pack_path(bad)


class DependencyTests(unittest.TestCase):
    def test_validate_ok(self):
        catalogo.validate_pack_dependencies({"minecraft": "1.21.4", "fabric-loader": "0.16.9"})
        catalogo.validate_pack_dependencies({"minecraft": "1.20.1"})

    def test_validate_rejects(self):
        for bad in ({}, {"fabric-loader": "1"}, {"minecraft": "1.20", "bogus": "1"},
                    {"minecraft": "1.20", "forge": "1", "fabric-loader": "2"},
                    {"minecraft": ".."}, {"minecraft": "1/../2"}, {"minecraft": 5},
                    {"minecraft": "1.20", "forge": "a b"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                catalogo.validate_pack_dependencies(bad)

    def test_curseforge_dependencies(self):
        manifest = {"manifestType": "minecraftModpack", "manifestVersion": 1,
                    "minecraft": {"version": "1.20.1", "modLoaders": [
                        {"id": "forge-47.1.0"}, {"id": "fabric-0.15.0", "primary": True}]}}
        self.assertEqual(catalogo.curseforge_dependencies(manifest),
                         {"minecraft": "1.20.1", "fabric-loader": "0.15.0"})
        manifest["minecraft"]["modLoaders"] = []
        self.assertEqual(catalogo.curseforge_dependencies(manifest), {"minecraft": "1.20.1"})

    def test_curseforge_rejects(self):
        base = {"manifestType": "minecraftModpack", "manifestVersion": 1,
                "minecraft": {"version": "1.20.1", "modLoaders": [{"id": "liteloader-1"}]}}
        with self.assertRaises(ValueError):
            catalogo.curseforge_dependencies(base)
        base["minecraft"]["modLoaders"] = [{"id": "forge"}]
        with self.assertRaises(ValueError):
            catalogo.curseforge_dependencies(base)
        with self.assertRaises(ValueError):
            catalogo.curseforge_dependencies({"manifestType": "other"})


class ReadIndexTests(TempRootCase):
    def test_priority_and_missing(self):
        path = make_zip(self.folder / "a.zip", {"nova-pack.json": {"x": 1}, "manifest.json": {"x": 2}})
        with zipfile.ZipFile(path) as pack:
            self.assertEqual(catalogo.read_pack_index(pack), ("nova-pack.json", {"x": 1}))
        empty = make_zip(self.folder / "b.zip", {"readme.txt": "hi"})
        with zipfile.ZipFile(empty) as pack, self.assertRaises(ValueError):
            catalogo.read_pack_index(pack)

    def test_oversized_index(self):
        path = make_zip(self.folder / "big.zip", {"nova-pack.json": " " * 10_000_001})
        with zipfile.ZipFile(path) as pack, self.assertRaises(ValueError):
            catalogo.read_pack_index(pack)

    def test_pack_summary(self):
        nova = make_zip(self.folder / "n.zip", {"nova-pack.json": {
            "formatVersion": 1, "name": "N", "dependencies": {"minecraft": "1.21", "forge": "52"}}})
        self.assertEqual(catalogo.pack_summary(nova), ("N", "1.21", "Forge", False))
        vanilla = make_zip(self.folder / "v.zip", {"nova-pack.json": {
            "formatVersion": 1, "name": "V", "dependencies": {"minecraft": "1.21"}}})
        self.assertEqual(catalogo.pack_summary(vanilla), ("V", "1.21", "Vanilla", False))
        curse = make_zip(self.folder / "c.zip", {"manifest.json": {
            "manifestType": "minecraftModpack", "manifestVersion": 1, "name": "C",
            "minecraft": {"version": "1.20.1", "modLoaders": []}, "files": [{"projectID": 1}]}})
        self.assertEqual(catalogo.pack_summary(curse), ("C", "1.20.1", "Vanilla", True))


class FetchFileTests(TempRootCase):
    def fetch(self, chunks, expected, name="f.bin", **kwargs):
        target = self.folder / "out" / name
        with mock.patch.object(catalogo.requests, "get", return_value=fake_response(chunks)):
            catalogo.fetch_file("https://cdn.modrinth.com/f", target, expected, **kwargs)
        return target

    def test_ok_and_mismatch(self):
        data = b"hello world"
        target = self.fetch([b"hello ", b"world"], hashlib.sha512(data).hexdigest())
        self.assertEqual(target.read_bytes(), data)
        with self.assertRaises(ValueError):
            self.fetch([b"x"], "0" * 128, "bad.bin")
        self.assertFalse((self.folder / "out" / "bad.bin").exists())

    def test_existing_file_survives_a_failed_download(self):
        target = self.folder / "out" / "keep.bin"
        target.parent.mkdir()
        target.write_bytes(b"good")
        with self.assertRaises(FileExistsError):
            self.fetch([b"x"], "0" * 128, "keep.bin")
        self.assertEqual(target.read_bytes(), b"good")

    def test_progress_reports_bytes_speed_and_total(self):
        data = b"x" * 1000
        calls = []
        response = fake_response([data[:500], data[500:]], headers={"Content-Length": "1000"})
        target = self.folder / "p.bin"
        with mock.patch.object(catalogo.requests, "get", return_value=response):
            catalogo.fetch_file("https://cdn.modrinth.com/f", target, hashlib.sha512(data).hexdigest(),
                                progress=lambda *args: calls.append(args))
        self.assertEqual(calls[-1][:2], (1000, 1000))
        self.assertFalse(target.with_name("p.bin.part").exists())

    def test_cut_connection_keeps_the_part_and_resumes_with_a_range(self):
        data = b"abcdefghij"
        target = self.folder / "r.bin"
        first = fake_response([])
        first.iter_content.side_effect = catalogo.requests.ConnectionError("cut")
        first_chunks = fake_response([data[:4]])
        # a stream that yields 4 bytes and then fails
        def broken(_size):
            yield data[:4]
            raise catalogo.requests.ConnectionError("cut")
        stream = fake_response([])
        stream.iter_content.side_effect = broken
        rest = fake_response([data[4:]], status=206, headers={"Content-Range": "bytes 4-9/10"})
        with mock.patch.object(catalogo.requests, "get", side_effect=[stream, rest]) as get, \
                mock.patch.object(catalogo.time, "sleep"):
            catalogo.fetch_file("https://cdn.modrinth.com/f", target, hashlib.sha512(data).hexdigest())
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(get.call_args_list[1].kwargs["headers"]["Range"], "bytes=4-")

    def test_server_that_ignores_range_restarts_from_zero(self):
        data = b"0123456789"
        target = self.folder / "i.bin"
        part = target.with_name("i.bin.part")
        part.write_bytes(b"junk")
        with mock.patch.object(catalogo.requests, "get", return_value=fake_response([data])):
            catalogo.fetch_file("https://cdn.modrinth.com/f", target, hashlib.sha512(data).hexdigest())
        self.assertEqual(target.read_bytes(), data)

    def test_range_not_satisfiable_discards_the_part(self):
        data = b"hello"
        target = self.folder / "s.bin"
        target.with_name("s.bin.part").write_bytes(b"toolongpartial")
        replies = [fake_response([], status=416), fake_response([data])]
        with mock.patch.object(catalogo.requests, "get", side_effect=replies):
            catalogo.fetch_file("https://cdn.modrinth.com/f", target, hashlib.sha512(data).hexdigest())
        self.assertEqual(target.read_bytes(), data)

    def test_resumed_file_with_wrong_checksum_is_discarded(self):
        target = self.folder / "w.bin"
        target.with_name("w.bin.part").write_bytes(b"abcd")
        rest = fake_response([b"efgh"], status=206, headers={"Content-Range": "bytes 4-7/8"})
        with mock.patch.object(catalogo.requests, "get", return_value=rest):
            with self.assertRaises(ValueError):
                catalogo.fetch_file("https://cdn.modrinth.com/f", target, "0" * 128)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name("w.bin.part").exists())

    def test_curseforge_host_and_size(self):
        target = self.folder / "cf.bin"
        with self.assertRaises(ValueError):
            catalogo.fetch_file("https://evil.example/f", target, "a", algorithm="sha1", size=3)
        with self.assertRaises(ValueError):
            catalogo.fetch_file("http://edge.forgecdn.net/f", target, "a", algorithm="sha1", size=3)
        digest = hashlib.sha1(b"abc").hexdigest()
        with mock.patch.object(catalogo.requests, "get", return_value=fake_response([b"abcd"])):
            with self.assertRaises(ValueError):
                catalogo.fetch_file("https://edge.forgecdn.net/f", target, digest,
                                    algorithm="sha1", size=3)

    def test_redirect_loop_is_bounded(self):
        redirect = fake_response([], status=302, redirect=True,
                                 headers={"Location": "https://edge.forgecdn.net/next"})
        with mock.patch.object(catalogo.requests, "get", return_value=redirect) as get:
            with self.assertRaises(ValueError):
                catalogo.fetch_file("https://edge.forgecdn.net/f", self.folder / "r.bin",
                                    "a", algorithm="sha1", size=3)
        self.assertEqual(get.call_count, 4)


class DownloadTests(TempRootCase):
    def version(self, **file):
        entry = {"filename": "a.jar", "primary": True, "url": "https://cdn.modrinth.com/a.jar",
                 "hashes": {"sha512": "ab"}}
        entry.update(file)
        return {"files": [entry]}

    def test_download_picks_file(self):
        with mock.patch.object(catalogo, "fetch_file") as fetch:
            target = catalogo.download(self.version(), self.folder / "d", ".jar")
        self.assertEqual(target, self.folder / "d" / "a.jar")
        fetch.assert_called_once_with("https://cdn.modrinth.com/a.jar", target, "ab", progress=None)

    def test_download_rejects_bad_input(self):
        for bad in (self.version(filename="../a.jar"), self.version(filename="x/a.jar"),
                    self.version(url="https://evil.example/a.jar"), self.version(filename="a.txt")):
            with self.subTest(bad=bad), mock.patch.object(catalogo, "fetch_file"):
                with self.assertRaises(ValueError):
                    catalogo.download(bad, self.folder / "d", ".jar")


class VersionsByHashTests(TempRootCase):
    def test_batches_and_filters(self):
        hashes = [f"{n:03d}" for n in range(150)]
        calls = []

        def post(url, **kwargs):
            calls.append(kwargs["json"]["hashes"])
            response = mock.MagicMock()
            response.json.return_value = {**{h: {"id": h} for h in kwargs["json"]["hashes"][:1]},
                                          "intruso": {"id": "x"}}
            return response

        with mock.patch.object(catalogo.requests, "post", side_effect=post):
            result = catalogo.versions_by_hash(hashes)
        self.assertEqual([len(call) for call in calls], [100, 50])
        self.assertEqual(set(result), {"000", "100"})


class CachedPackFileTests(TempRootCase):
    def test_invalid_digest(self):
        with self.assertRaises(ValueError):
            catalogo.cached_pack_file(self.folder / "t", "../../x", "sha1", lambda p: None)
        with self.assertRaises(ValueError):
            catalogo.cached_pack_file(self.folder / "t", "A" * 40, "sha1", lambda p: None)

    def test_cache_hit_and_corrupt_cache(self):
        data = b"jar"
        digest = hashlib.sha1(data).hexdigest()
        calls = []

        def retrieve(staged):
            calls.append(1)
            staged.write_bytes(data)

        catalogo.cached_pack_file(self.folder / "a" / "x.jar", digest, "sha1", retrieve)
        catalogo.cached_pack_file(self.folder / "b" / "x.jar", digest, "sha1", retrieve)
        self.assertEqual(len(calls), 1)
        self.assertEqual((self.folder / "b" / "x.jar").read_bytes(), data)
        (motor.ROOT / "pack-cache" / f"sha1-{digest}").write_bytes(b"corrupto")
        catalogo.cached_pack_file(self.folder / "c" / "x.jar", digest, "sha1", retrieve)
        self.assertEqual(len(calls), 2)
        self.assertEqual((self.folder / "c" / "x.jar").read_bytes(), data)


class ImportPackTests(TempRootCase):
    def instance(self, folder):
        return json.loads((folder / "instance.json").read_text())

    def test_import_nova_pack(self):
        path = make_zip(self.folder / "p.zip", {
            "nova-pack.json": {"formatVersion": 1, "name": "X" * 60, "dependencies": {
                "minecraft": "1.21", "fabric-loader": "auto"}},
            "overrides/config/a.toml": "x=1", "ignored/b.txt": "no"})
        result = catalogo.import_pack(path, 4096)
        settings = self.instance(result)
        self.assertEqual((settings["name"], settings["loader"], settings["loader_version"]),
                         ("X" * 40, "fabric", ""))
        self.assertEqual(settings["memory"], 4096)
        self.assertTrue(settings["pack"])
        self.assertEqual((result / "game/config/a.toml").read_text(), "x=1")
        self.assertFalse((result / "game/ignored").exists())
        self.assertEqual(list((motor.ROOT / "instances").iterdir()), [result])

    def test_zip_slip_is_rejected_and_cleaned(self):
        for evil in ("overrides/../../evil.txt", "overrides//abs.txt", "overrides/a/../../../e"):
            path = make_zip(self.folder / "evil.zip", {
                "nova-pack.json": {"formatVersion": 1, "name": "E",
                                   "dependencies": {"minecraft": "1.21"}},
                evil: "x"})
            with self.subTest(evil=evil), self.assertRaises(ValueError):
                catalogo.import_pack(path, 2048)
            self.assertEqual(list((motor.ROOT / "instances").iterdir()), [])
            self.assertFalse((self.folder / "evil.txt").exists())

    def test_unsupported_format(self):
        path = make_zip(self.folder / "f.zip", {"nova-pack.json": {
            "formatVersion": 2, "name": "F", "dependencies": {"minecraft": "1.21"}}})
        with self.assertRaises(ValueError):
            catalogo.import_pack(path, 2048)

    def mrpack(self, files, extra=None):
        return make_zip(self.folder / "m.mrpack", {
            "modrinth.index.json": {"formatVersion": 1, "game": "minecraft", "name": "M",
                                    "dependencies": {"minecraft": "1.21", "neoforge": "21.0.1"},
                                    "files": files},
            "overrides/options.txt": "o", "client-overrides/c.txt": "c", **(extra or {})})

    def test_import_mrpack_downloads_verified_files(self):
        data = b"mod-bytes"
        digest = hashlib.sha512(data).hexdigest()
        files = [
            {"path": "mods/a.jar", "hashes": {"sha512": digest},
             "downloads": ["https://evil.example/a.jar", "https://cdn.modrinth.com/a.jar"]},
            {"path": "mods/server.jar", "hashes": {"sha512": "0" * 128}, "env": {"client": "unsupported"},
             "downloads": ["https://cdn.modrinth.com/s.jar"]}]
        urls = []

        def fetch(url, staged, expected, **kwargs):
            urls.append(url)
            staged.write_bytes(data)

        with mock.patch.object(catalogo, "fetch_file", side_effect=fetch):
            result = catalogo.import_pack(self.mrpack(files), 3072, project="proj")
        self.assertEqual(urls, ["https://cdn.modrinth.com/a.jar"])
        self.assertEqual((result / "game/mods/a.jar").read_bytes(), data)
        self.assertFalse((result / "game/mods/server.jar").exists())
        self.assertEqual((result / "game/options.txt").read_text(), "o")
        self.assertEqual((result / "game/c.txt").read_text(), "c")
        settings = self.instance(result)
        self.assertEqual((settings["loader"], settings["loader_version"], settings["modrinth_pack"]),
                         ("neoforge", "21.0.1", "proj"))

    def test_mrpack_rejects_bad_files(self):
        digest = "a" * 128
        cases = {
            "traversal": [{"path": "../x.jar", "hashes": {"sha512": digest},
                           "downloads": ["https://cdn.modrinth.com/x"]}],
            "host": [{"path": "mods/x.jar", "hashes": {"sha512": digest},
                      "downloads": ["https://evil.example/x"]}],
            "duplicate": [{"path": "mods/x.jar", "hashes": {"sha512": digest},
                           "downloads": ["https://cdn.modrinth.com/x"]}] * 2,
        }
        for label, files in cases.items():
            with self.subTest(label=label), mock.patch.object(
                    catalogo, "fetch_file", side_effect=lambda u, s, e, **kw: s.write_bytes(b"x")):
                with self.assertRaises(ValueError):
                    catalogo.import_pack(self.mrpack(files), 2048)
            self.assertEqual(list((motor.ROOT / "instances").iterdir()), [])

    def test_mrpack_hash_failure_reports_error(self):
        files = [{"path": "mods/x.jar", "hashes": {"sha512": "b" * 128},
                  "downloads": ["https://cdn.modrinth.com/x"]}]
        with mock.patch.object(catalogo, "fetch_file", side_effect=ValueError("suma")):
            with self.assertRaisesRegex(ValueError, "suma"):
                catalogo.import_pack(self.mrpack(files), 2048)


if __name__ == "__main__":
    unittest.main()

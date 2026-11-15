from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fuentes_plugins as fp  # noqa: E402
import motor  # noqa: E402
import servidor_local as sl  # noqa: E402

META = {"id": "0123456789ab", "kind": "paper", "version": "1.21.11", "name": "x"}
SHA = "ab" * 32


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        self.base = Path(tempfile.mkdtemp())

    def tearDown(self):
        motor.ROOT = self.original

    def fake_download(self, calls):
        def run(url, target, **kwargs):
            calls.append((url, kwargs))
            target.write_bytes(b"PK" + b"x" * 2000)
        return run


class SourcesTests(Base):
    def test_which_sources_each_kind_gets(self):
        self.assertEqual(sl.catalog_sources(META), ["modrinth", "hangar", "spigot"])
        self.assertEqual(sl.catalog_sources({"kind": "fabric"}), ["modrinth"])
        self.assertEqual(sl.catalog_sources({"kind": "forge"}), ["modrinth"])
        self.assertEqual(sl.catalog_sources({"kind": "vanilla"}), [])
        with self.assertRaises(ValueError):
            sl.catalog_search({"kind": "fabric", "version": "1.21.1"}, "x", source="hangar")
        with self.assertRaises(ValueError):
            sl.catalog_search({"kind": "paper", "version": "1.21.1"}, "x", source="otra")


class HangarTests(Base):
    def project(self, owner="pop4959", slug="Chunky", name="Chunky"):
        return {"name": name, "namespace": {"owner": owner, "slug": slug}, "description": "d", "stats": {"downloads": 7}}

    def version(self, **extra):
        paper = {"fileInfo": {"name": "Chunky-1.0.jar", "sizeBytes": 2002, "sha256Hash": SHA},
                 "downloadUrl": "https://hangarcdn.papermc.io/plugins/pop4959/Chunky/versions/1.0/PAPER/Chunky-1.0.jar", "externalUrl": None}
        paper.update(extra)
        return {"name": "1.0", "channel": {"name": "Release"}, "downloads": {"PAPER": paper}}

    def test_search_maps_projects_and_keeps_only_valid_ids(self):
        data = {"result": [self.project(), self.project(owner="mal;o", slug="x")], "pagination": {"count": 50}}
        with mock.patch.object(fp, "_json", return_value=data) as call:
            result = fp.hangar_search(META, "", 0, 20)
        self.assertEqual([h["project_id"] for h in result["hits"]], ["hangar:pop4959/Chunky"])
        self.assertEqual((result["total"], result["next"], result["more"]), (50, 2, True))
        self.assertEqual(call.call_args.kwargs["version"], "1.21.11")
        self.assertEqual(call.call_args.kwargs["sort"], "-downloads")

    def test_install_checks_the_hash_origin_and_type_and_records_it(self):
        calls = []
        with mock.patch.object(fp, "_json", return_value={"result": [self.version()]}), mock.patch.object(sl, "download", self.fake_download(calls)):
            installed = fp.hangar_install(self.base, META, "pop4959/Chunky", title="Chunky")
        self.assertEqual(installed, ["Chunky-1.0.jar"])
        url, kwargs = calls[0]
        self.assertEqual((kwargs["algo"], kwargs["digest"], kwargs["magic"]), ("sha256", SHA, b"PK"))
        self.assertEqual(kwargs["allowed"], fp.HANGAR_FILES)
        self.assertEqual(sl.catalog_installed(self.base)["hangar:pop4959/Chunky"]["file"], "Chunky-1.0.jar")
        sl.catalog_remove(self.base, META, "hangar:pop4959/Chunky")
        self.assertFalse((self.base / "plugins" / "Chunky-1.0.jar").exists())

    def test_external_foreign_or_unsafe_downloads_are_refused(self):
        cases = [self.version(downloadUrl=None, externalUrl="https://example.com/p"),
                 self.version(downloadUrl="https://evil.example/x.jar"),
                 self.version(fileInfo={"name": "../x.jar", "sizeBytes": 10, "sha256Hash": SHA}),
                 self.version(fileInfo={"name": "a.jar", "sizeBytes": 10, "sha256Hash": "zz"})]
        for bad in cases:
            with mock.patch.object(fp, "_json", return_value={"result": [bad]}):
                with self.assertRaises(ValueError):
                    fp.hangar_install(self.base, META, "pop4959/Chunky")
        with mock.patch.object(fp, "_json", return_value={"result": []}):
            with self.assertRaises(ValueError):
                fp.hangar_install(self.base, META, "pop4959/Chunky")
        with self.assertRaises(ValueError):
            fp.hangar_install(self.base, META, "../etc")


class SpigotTests(Base):
    def resource(self, rid, tested, file_type=".jar", premium=False, name="Plugin"):
        file = {"type": file_type}
        if file_type == "external":
            file["externalUrl"] = "https://github.com/x/y/releases/tag/1"
        return {"id": rid, "name": name, "tag": "tag", "testedVersions": tested, "downloads": 5, "premium": premium, "file": file}

    def test_search_filters_premium_and_untested_and_flags_external_ones(self):
        raw = [self.resource(1, ["1.20", "1.21"]), self.resource(2, ["1.12"]), self.resource(3, ["1.21"], premium=True),
               self.resource(4, ["1.21"], file_type="external"), self.resource(5, ["1.21.11"])]
        with mock.patch.object(fp, "_json", return_value=raw):
            result = fp.spigot_search(META, "", 0, 20)
        keys = [h["project_id"] for h in result["hits"]]
        self.assertEqual(keys, ["spigot:1", "spigot:4", "spigot:5"])
        self.assertIn("external_url", result["hits"][1])
        self.assertNotIn("external_url", result["hits"][0])
        self.assertFalse(result["more"])
        with mock.patch.object(fp, "_json", return_value=[self.resource(i, ["1.21"]) for i in range(50)]):
            full = fp.spigot_search(META, "x", 50, 20)
        self.assertEqual((full["more"], full["next"], len(full["hits"])), (True, 100, 20))

    def test_tested_version_matching(self):
        self.assertTrue(fp._tested("1.21.11", ["1.21"]))
        self.assertTrue(fp._tested("1.21.11", ["1.21.11"]))
        self.assertTrue(fp._tested("26.3", ["26.3"]))
        self.assertFalse(fp._tested("1.21.11", ["1.2", "1.20"]))
        self.assertFalse(fp._tested("1.21.11", None))

    def test_install_downloads_from_the_cdn_only_and_checks_the_file_type(self):
        calls = []
        with mock.patch.object(fp, "_json", return_value=self.resource(13571, ["1.21"], name="Warp GUI!")), \
                mock.patch.object(sl, "download", self.fake_download(calls)):
            installed = fp.spigot_install(self.base, META, "13571", title="Warp GUI")
        self.assertEqual(installed, ["Warp GUI--spigot-13571.jar"])
        url, kwargs = calls[0]
        self.assertEqual(url, "https://api.spiget.org/v2/resources/13571/download")
        self.assertEqual((kwargs["allowed"], kwargs["magic"]), (fp.SPIGET_FILES, b"PK"))
        self.assertNotIn("digest", kwargs)    # there is no hash to check, and the code does not pretend otherwise

    def test_paid_external_untested_or_malformed_resources_are_refused(self):
        for resource in (self.resource(1, ["1.21"], premium=True), self.resource(1, ["1.21"], file_type="external"),
                         self.resource(1, ["1.12"])):
            with mock.patch.object(fp, "_json", return_value=resource):
                with self.assertRaises(ValueError):
                    fp.spigot_install(self.base, META, "1")
        with self.assertRaises(ValueError):
            fp.spigot_install(self.base, META, "../1")
        self.assertFalse((self.base / "plugins").exists() and any((self.base / "plugins").iterdir()))


class DownloadGuardTests(Base):
    class Response:
        def __init__(self, payload, url):
            self.payload, self.url = payload, url

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield self.payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_download_refuses_foreign_redirects_and_wrong_file_types(self):
        target = self.base / "a.jar"
        with mock.patch("servidor_local.requests.get", return_value=self.Response(b"PK" + b"x" * 2000, "https://cdn.spiget.org/f.jar")):
            sl.download("https://api.spiget.org/x", target, allowed=fp.SPIGET_FILES, magic=b"PK")
            self.assertTrue(target.exists())
            target.unlink()
        with mock.patch("servidor_local.requests.get", return_value=self.Response(b"PK" + b"x" * 2000, "https://evil.example/f.jar")):
            with self.assertRaises(ValueError):
                sl.download("https://api.spiget.org/x", target, allowed=fp.SPIGET_FILES, magic=b"PK")
        with mock.patch("servidor_local.requests.get", return_value=self.Response(b"<html>" + b"x" * 2000, "https://cdn.spiget.org/f.jar")):
            with self.assertRaises(ValueError):
                sl.download("https://api.spiget.org/x", target, allowed=fp.SPIGET_FILES, magic=b"PK")
        self.assertEqual([p.name for p in self.base.iterdir()], [])


if __name__ == "__main__":
    unittest.main()

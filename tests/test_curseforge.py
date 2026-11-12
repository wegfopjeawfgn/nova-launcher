import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import curseforge  # noqa: E402

KEY = "k" * 10 + "SECRETKEY" + "z" * 10
SHA = "a" * 40
CDN = "https://edge.forgecdn.net/files/1/2/a.jar"


def fake_response(payload=None, *, status=200, raw=None):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    body = raw if raw is not None else json.dumps(payload).encode()
    response.iter_content.return_value = [body[i:i + 1000] for i in range(0, len(body), 1000)]
    return response


def mod(**extra):
    item = {"id": 7, "name": "Sodium", "summary": "Fast", "downloadCount": 99,
            "authors": [{"name": "jelly"}, {"name": "other"}],
            "links": {"websiteUrl": "https://www.curseforge.com/minecraft/mc-mods/sodium"},
            "logo": {"thumbnailUrl": "https://media.forgecdn.net/t.png"},
            "latestFiles": [{"id": 5, "gameVersions": ["1.21.4", "Fabric"], "downloadUrl": CDN,
                             "hashes": [{"algo": 2, "value": "x"}, {"algo": 1, "value": SHA}],
                             "fileLength": 123, "fileName": "a.jar"}]}
    item.update(extra)
    return item


def call(response, *args, **kwargs):
    with mock.patch.object(curseforge.requests, "get", return_value=response) as get:
        try:
            result = curseforge.search(KEY, *args, **kwargs)
        except curseforge.CurseForgeError as error:
            return error, get
    return result, get


class SearchTests(unittest.TestCase):
    def test_params_and_key_only_in_header(self):
        _, get = call(fake_response({"data": []}), "sod", game_version="1.21.4",
                      loader="neoforge", page_size=500, index=40)
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://api.curseforge.com/v1/mods/search")
        params = kwargs["params"]
        self.assertEqual((params["gameId"], params["classId"], params["searchFilter"]), (432, 6, "sod"))
        self.assertEqual((params["sortField"], params["sortOrder"]), (2, "desc"))
        self.assertEqual((params["pageSize"], params["index"]), (50, 40))
        self.assertEqual((params["gameVersion"], params["modLoaderType"]), ("1.21.4", 6))
        self.assertEqual(kwargs["headers"]["x-api-key"], KEY)
        self.assertNotIn(KEY, repr(args) + repr(params))

    def test_loader_map(self):
        for loader, number in (("forge", 1), ("fabric", 4), ("quilt", 5), ("neoforge", 6)):
            _, get = call(fake_response({"data": []}), "x", loader=loader)
            self.assertEqual(get.call_args.kwargs["params"]["modLoaderType"], number)
        for loader in ("vanilla", "raro", None):
            _, get = call(fake_response({"data": []}), "x", loader=loader)
            self.assertNotIn("modLoaderType", get.call_args.kwargs["params"])
            self.assertNotIn("gameVersion", get.call_args.kwargs["params"])

    def test_normalization(self):
        result, _ = call(fake_response({"data": [mod()], "pagination": {"totalCount": 321}}), "s")
        self.assertEqual(result["total"], 321)
        item = result["results"][0]
        self.assertEqual((item["id"], item["name"], item["author"], item["downloads"]),
                         (7, "Sodium", "jelly", 99))
        self.assertEqual(item["logo"], "https://media.forgecdn.net/t.png")
        self.assertEqual(item["latest"], [{"file_id": 5, "game_versions": ["1.21.4", "Fabric"],
                                           "download_url": CDN, "sha1": SHA, "size": 123,
                                           "file_name": "a.jar"}])

    def test_missing_author_and_bad_links(self):
        for extra in ({"authors": []}, {"authors": None}):
            result, _ = call(fake_response({"data": [mod(**extra)]}), "s")
            self.assertEqual(result["results"][0]["author"], "")
        for site in ("http://www.curseforge.com/x", "https://evil.example/x",
                     "https://www.curseforge.com.evil.example/x", None):
            result, _ = call(fake_response({"data": [mod(links={"websiteUrl": site})]}), "s")
            self.assertEqual(result["results"][0]["url"], "")
        result, _ = call(fake_response({"data": [mod(logo={"thumbnailUrl": "http://x/t.png"})]}), "s")
        self.assertEqual(result["results"][0]["logo"], "")

    def test_file_without_hash_or_url(self):
        files = [{"id": 1, "gameVersions": [], "downloadUrl": None, "hashes": [], "fileLength": 5}]
        result, _ = call(fake_response({"data": [mod(latestFiles=files)]}), "s")
        latest = result["results"][0]["latest"][0]
        self.assertIsNone(latest["download_url"])
        self.assertIsNone(latest["sha1"])


class ErrorTests(unittest.TestCase):
    def check(self, response, text=None):
        error, _ = call(response, "s")
        self.assertIsInstance(error, curseforge.CurseForgeError)
        message = str(error)
        self.assertNotIn(KEY, message)
        self.assertNotIn("api.curseforge.com", message)
        self.assertNotIn("http", message)
        if text:
            self.assertEqual(message, text)

    def test_status_codes(self):
        auth = "La clave de API de CurseForge no es válida o no tiene permiso."
        self.check(fake_response({}, status=401), auth)
        self.check(fake_response({}, status=403), auth)
        self.check(fake_response({}, status=429), "CurseForge limitó las consultas, probá más tarde.")
        self.check(fake_response({}, status=500))

    def test_bad_bodies(self):
        self.check(fake_response(raw=b"no es json"))
        self.check(fake_response({"nada": 1}))
        self.check(fake_response({"data": {"a": 1}}))
        self.check(fake_response([1, 2]))
        self.check(fake_response(raw=b"x" * (curseforge.MAX_RESPONSE + 10)))

    def test_network_error_hides_details(self):
        boom = curseforge.requests.ConnectionError(f"https://api.curseforge.com/v1 {KEY}")
        with mock.patch.object(curseforge.requests, "get", side_effect=boom):
            with self.assertRaises(curseforge.CurseForgeError) as ctx:
                curseforge.search(KEY, "s")
        self.assertNotIn(KEY, str(ctx.exception))
        self.assertNotIn("http", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    def test_bad_key_makes_no_request(self):
        with mock.patch.object(curseforge.requests, "get", side_effect=AssertionError("red")):
            with self.assertRaises(curseforge.CurseForgeError):
                curseforge.search("corta", "s")


class LatestFileTests(unittest.TestCase):
    def run_latest(self, files):
        with mock.patch.object(curseforge.requests, "get",
                               return_value=fake_response({"data": files})) as get:
            result = curseforge.latest_file(KEY, 7, game_version="1.21.4", loader="fabric")
        return result, get

    def test_picks_newest_available(self):
        def f(i, date, ok=True):
            return {"id": i, "fileDate": date, "isAvailable": ok, "gameVersions": ["1.21.4"],
                    "downloadUrl": CDN, "hashes": [{"algo": 1, "value": SHA}],
                    "fileLength": 9, "fileName": f"{i}.jar"}
        result, get = self.run_latest([f(1, "2025-01-01T00:00:00Z"), f(3, "2025-06-01T00:00:00Z", False),
                                       f(2, "2025-03-01T00:00:00Z")])
        self.assertEqual(result["file_id"], 2)
        args, kwargs = get.call_args
        self.assertTrue(args[0].endswith("/mods/7/files"))
        self.assertEqual((kwargs["params"]["gameVersion"], kwargs["params"]["modLoaderType"]),
                         ("1.21.4", 4))
        self.assertEqual(kwargs["headers"]["x-api-key"], KEY)

    def test_none_when_nothing_available(self):
        self.assertIsNone(self.run_latest([])[0])
        self.assertIsNone(self.run_latest([{"id": 1, "isAvailable": False}])[0])


class SafeDownloadTests(unittest.TestCase):
    def info(self, **over):
        base = {"download_url": CDN, "sha1": SHA, "size": 10}
        base.update(over)
        return base

    def test_ok(self):
        self.assertTrue(curseforge.safe_download(self.info()))

    def test_rejected(self):
        for over in ({"download_url": "https://evil.example/a.jar"},
                     {"download_url": "http://edge.forgecdn.net/a.jar"},
                     {"download_url": "https://edge.forgecdn.net.evil.example/a.jar"},
                     {"download_url": None}, {"sha1": None}, {"sha1": "abc"},
                     {"sha1": "g" * 40}, {"size": 0}, {"size": None}):
            with self.subTest(over=over):
                self.assertFalse(curseforge.safe_download(self.info(**over)))
        self.assertFalse(curseforge.safe_download(None))


class ApiKeyTests(unittest.TestCase):
    def test_format(self):
        self.assertTrue(curseforge.api_key_ok("a" * 20))
        for bad in ("a" * 19, "a" * 201, "a" * 10 + " " + "b" * 10, "a" * 20 + "\n", None, 5):
            with self.subTest(bad=bad):
                self.assertFalse(curseforge.api_key_ok(bad))


if __name__ == "__main__":
    unittest.main()

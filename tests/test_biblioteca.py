import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402

try:
    import biblioteca  # noqa: E402
except (ImportError, ValueError) as error:  # GTK no disponible en este entorno
    biblioteca = None
    SKIP = str(error)

import requests  # noqa: E402


@unittest.skipIf(biblioteca is None, "GTK no disponible")
class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        no_net = mock.patch("catalogo.requests.post", side_effect=AssertionError("red"))
        no_net.start()
        self.addCleanup(no_net.stop)
        biblioteca.content_hash.cache_clear()

    def put(self, subfolder, name, data=b"x"):
        directory = self.folder / "game" / subfolder
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(data)
        return path


class ContentFilesTests(LibraryCase):
    def test_missing_directory(self):
        self.assertEqual(biblioteca.content_files(self.folder, "mod"), [])

    def test_mods_include_disabled_and_sort_casefold(self):
        for name in ("b.jar", "A.jar", "c.jar.disabled", "notes.txt", "d.zip", "E.JAR"):
            self.put("mods", name)
        names = [p.name for p in biblioteca.content_files(self.folder, "mod")]
        self.assertEqual(names, ["A.jar", "b.jar", "c.jar.disabled", "E.JAR"])

    def test_shaders_only_zip_and_no_disabled(self):
        for name in ("s.zip", "t.jar.disabled", "u.jar"):
            self.put("shaderpacks", name)
        self.assertEqual([p.name for p in biblioteca.content_files(self.folder, "shader")], ["s.zip"])

    def test_resourcepacks_zip_or_folder_with_mcmeta(self):
        self.put("resourcepacks", "z.zip")
        good = self.folder / "game" / "resourcepacks" / "dir"
        good.mkdir()
        (good / "pack.mcmeta").write_text("{}")
        (self.folder / "game" / "resourcepacks" / "bare").mkdir()
        names = [p.name for p in biblioteca.content_files(self.folder, "resourcepack")]
        self.assertEqual(names, ["dir", "z.zip"])


class ContentHashTests(LibraryCase):
    def test_sha512_and_cache(self):
        path = self.put("mods", "a.jar", b"data")
        stat = path.stat()
        key = (path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        self.assertEqual(biblioteca.content_hash(*key), hashlib.sha512(b"data").hexdigest())
        path.write_bytes(b"other")  # mismo clave: debe venir de la caché
        self.assertEqual(biblioteca.content_hash(*key), hashlib.sha512(b"data").hexdigest())


class InstalledProjectsTests(LibraryCase):
    def record(self, entries):
        motor.save(self.folder / "downloads.json", entries)

    def test_from_downloads_json_without_network(self):
        self.put("mods", "a.jar")
        self.put("mods", "b.jar.disabled")
        self.record({"pa": {"category": "mod", "file": "a.jar"},
                     "pb": {"category": "mod", "file": "b.jar"},
                     "ps": {"category": "shader", "file": "x.zip"},
                     "pm": {"category": "mod", "file": "gone.jar"}})
        result = biblioteca.installed_projects(self.folder, "mod", {"pa", "pb"})
        self.assertEqual(result, {"pa": "Instalado", "pb": "Instalado · desactivado"})

    def test_hash_lookup_for_untracked_files(self):
        active = self.put("mods", "manual.jar", b"one")
        disabled = self.put("mods", "off.jar.disabled", b"two")
        digests = {p.name: hashlib.sha512(p.read_bytes()).hexdigest() for p in (active, disabled)}
        remote = {digests["manual.jar"]: {"project_id": "P1"},
                  digests["off.jar.disabled"]: {"project_id": "P2"}}
        with mock.patch("catalogo.versions_by_hash", return_value=remote) as lookup:
            result = biblioteca.installed_projects(self.folder, "mod", {"P1", "P2"})
        self.assertEqual(set(lookup.call_args.args[0]), set(digests.values()))
        self.assertEqual(result, {"P1": "Instalado", "P2": "Instalado · desactivado"})

    def test_network_failure_is_tolerated(self):
        self.put("mods", "manual.jar", b"one")
        for error in (requests.ConnectionError("sin red"), ValueError("raro")):
            with self.subTest(error=error), mock.patch("catalogo.versions_by_hash", side_effect=error):
                self.assertEqual(biblioteca.installed_projects(self.folder, "mod", {"P1"}), {})

    def test_active_copy_wins_over_disabled_duplicate(self):
        data = b"same"
        self.put("mods", "a.jar", data)
        self.put("mods", "b.jar.disabled", data)
        digest = hashlib.sha512(data).hexdigest()
        with mock.patch("catalogo.versions_by_hash", return_value={digest: {"project_id": "P"}}):
            result = biblioteca.installed_projects(self.folder, "mod", {"P"})
        self.assertEqual(result, {"P": "Instalado"})

    def test_unreadable_file_is_skipped(self):
        path = self.put("mods", "a.jar")
        with mock.patch.object(biblioteca, "content_hash", side_effect=OSError), \
                mock.patch("catalogo.versions_by_hash", return_value={}) as lookup:
            self.assertEqual(biblioteca.installed_projects(self.folder, "mod", {"P"}), {})
        self.assertEqual(list(lookup.call_args.args[0]), [])
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()

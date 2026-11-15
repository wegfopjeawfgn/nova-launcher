import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import java_propio as jp  # noqa: E402
import motor  # noqa: E402


def tar_with(files, links=()):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as package:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            package.addfile(info, io.BytesIO(data))
        for name, target in links:
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            package.addfile(info)
    return buffer.getvalue()


class Response:
    def __init__(self, data=None, payload=b"", url="https://github.com/adoptium/x"):
        self._data, self.payload, self.url = data, payload, url

    def json(self):
        return self._data

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())

    def tearDown(self):
        motor.ROOT = self.original


class ChoiceTests(Base):
    def test_pick_major_takes_the_smallest_lts_that_fits(self):
        self.assertEqual([jp.pick_major(n) for n in (8, 16, 17, 18, 21, 22, 25)], [8, 17, 17, 21, 21, 25, 25])
        self.assertEqual(jp.pick_major(None), 8)
        with self.assertRaises(ValueError):
            jp.pick_major(26)

    def test_installed_prefers_the_lowest_that_fits(self):
        for major in (17, 25):
            path = jp.folder() / f"temurin-{major}" / "bin"
            path.mkdir(parents=True)
            (path / jp._exe()).write_text("x")
        self.assertTrue(jp.installed(16).endswith("temurin-17/bin/java"))
        self.assertTrue(jp.installed(21).endswith("temurin-25/bin/java"))
        self.assertIsNone(jp.installed(26))


class ReleaseTests(Base):
    def package(self, **extra):
        package = {"link": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21/OpenJDK21U-jre.tar.gz",
                   "size": 1000, "checksum": "ab" * 32, "name": "OpenJDK21U-jre.tar.gz", **extra}
        return [{"binary": {"package": package}}]

    def test_release_checks_the_origin_size_and_hash_format(self):
        with mock.patch.object(jp, "platform_names", return_value=("linux", "x64")):
            with mock.patch("java_propio.requests.get", return_value=Response(self.package())):
                self.assertEqual(jp.release(21)["sha256"], "ab" * 32)
            for bad in ({"link": "https://evil.example/x.tar.gz"}, {"size": 10 ** 12}, {"checksum": "zz"}, {"name": "x.exe"}):
                with mock.patch("java_propio.requests.get", return_value=Response(self.package(**bad))):
                    with self.assertRaises(ValueError, msg=bad):
                        jp.release(21)
            with mock.patch("java_propio.requests.get", return_value=Response([])):
                with self.assertRaises(ValueError):
                    jp.release(21)
        with mock.patch.object(jp, "platform_names", return_value=None):
            with self.assertRaises(ValueError):
                jp.release(21)


class ExtractTests(Base):
    def test_tar_and_zip_are_unpacked_and_hostile_paths_refused(self):
        work = Path(tempfile.mkdtemp())
        good = work / "j.tar.gz"
        good.write_bytes(tar_with({"jdk-21-jre/bin/java": b"#!/bin/sh\n", "jdk-21-jre/lib/x": b"1"}, links=[("jdk-21-jre/bin/jre", "java")]))
        target = work / "out"
        target.mkdir()
        jp.extract(good, target)
        self.assertTrue((target / "jdk-21-jre" / "bin" / "java").is_file())
        self.assertTrue((target / "jdk-21-jre" / "bin" / "jre").is_symlink())
        for name, links in (("../fuera", ()), ("/abs/x", ()), ("ok/x", [("ok/enlace", "../../../etc/passwd")])):
            evil = work / "evil.tar.gz"
            evil.write_bytes(tar_with({name: b"x"} if not links else {"ok/x": b"x"}, links=links))
            with self.assertRaises(ValueError, msg=name):
                jp.extract(evil, work / "out2")
            (work / "out2").mkdir(exist_ok=True)
        z = work / "j.zip"
        with zipfile.ZipFile(z, "w") as package:
            package.writestr("jdk/bin/java.exe", "x")
        jp.extract(z, work / "outz")
        self.assertTrue((work / "outz" / "jdk" / "bin" / "java.exe").is_file())
        zbad = work / "bad.zip"
        with zipfile.ZipFile(zbad, "w") as package:
            package.writestr("../fuera.txt", "x")
        with self.assertRaises(ValueError):
            jp.extract(zbad, work / "outz2")
        self.assertFalse((work / "fuera.txt").exists())


class InstallTests(Base):
    def run_install(self, data, digest=None):
        info = {"link": "https://github.com/adoptium/x.tar.gz", "size": len(data), "sha256": digest or hashlib.sha256(data).hexdigest(),
                "name": "x.tar.gz"}
        with mock.patch.object(jp, "release", return_value=info), mock.patch("java_propio.requests.get", return_value=Response(payload=data)):
            return jp.install(21)

    def test_install_verifies_unpacks_and_is_idempotent(self):
        data = tar_with({"jdk-21-jre/bin/java": b"#!/bin/sh\n", "jdk-21-jre/release": b"x"})
        path = self.run_install(data)
        self.assertTrue(path.endswith("temurin-21/bin/java"))
        self.assertEqual(jp.installed(21), path)
        with mock.patch.object(jp, "release", side_effect=AssertionError("no network needed")):
            self.assertEqual(jp.install(21), path)
        self.assertEqual([p.name for p in jp.folder().iterdir()], ["temurin-21"])

    def test_a_wrong_hash_or_a_foreign_redirect_leaves_nothing(self):
        data = tar_with({"jdk/bin/java": b"x"})
        with self.assertRaises(ValueError):
            self.run_install(data, digest="0" * 64)
        info = {"link": "https://github.com/adoptium/x.tar.gz", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "name": "x.tar.gz"}
        with mock.patch.object(jp, "release", return_value=info), mock.patch("java_propio.requests.get", return_value=Response(payload=data, url="https://evil.example/x")):
            with self.assertRaises(ValueError):
                jp.install(21)
        self.assertEqual(list(jp.folder().iterdir()), [])

    def test_an_archive_without_a_java_program_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_install(tar_with({"jdk/readme.txt": b"x"}))
        self.assertEqual(list(jp.folder().iterdir()), [])


if __name__ == "__main__":
    unittest.main()

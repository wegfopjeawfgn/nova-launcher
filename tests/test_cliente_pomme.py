from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cliente_pomme as pomme  # noqa: E402
import motor  # noqa: E402

LINUX = ("pomme-client-linux-x64-gnu.AppImage", "pomme.AppImage")
WINDOWS = ("pomme-client-windows-x64.zip", "pomme-client.exe")
PAYLOAD = b"#!/bin/sh\necho pomme\n"


class Fake:
    """Stands in for requests: the release API answer, then the file bytes."""

    def __init__(self, status=200, data=None, chunks=()):
        self.status, self.data, self.chunks = status, data, chunks

    def raise_for_status(self):
        if self.status >= 400:
            raise pomme.requests.HTTPError(str(self.status))

    def json(self):
        return self.data

    def iter_content(self, _):
        return iter(self.chunks)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def api(asset, size, sha, tag="client-v0.2.10+26.2", url=None, **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, "assets": [{
        "name": asset, "size": size, "digest": "sha256:" + sha,
        "browser_download_url": url or f"{pomme.DOWNLOAD_PREFIX}client-v0.2.10%2B26.2/{asset}", **extra}]}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        self.addCleanup(setattr, motor, "ROOT", self.original)

    def serve(self, asset, body, **kw):
        """requests.get answers the API first, then the download."""
        answers = [Fake(data=api(asset[0], len(body), kw.pop("digest", sha(body)), **kw)), Fake(chunks=[body[:5], body[5:]])]
        return mock.patch.object(pomme.requests, "get", side_effect=answers)


class ReleaseTests(Base):
    def get(self, data):
        with mock.patch.object(pomme.requests, "get", return_value=Fake(data=data)):
            return pomme.release(LINUX[0])

    def test_accepts_the_official_asset(self):
        info = self.get(api(LINUX[0], 10, "a" * 64))
        self.assertEqual((info["tag"], info["size"], info["sha256"]), ("client-v0.2.10+26.2", 10, "a" * 64))

    def test_refuses_foreign_urls_bad_digests_sizes_and_drafts(self):
        with self.assertRaises(ValueError):
            self.get(api(LINUX[0], 10, "a" * 64, url="https://evil.example/" + LINUX[0]))
        with self.assertRaises(ValueError):
            self.get(api(LINUX[0], 10, "xyz"))
        with self.assertRaises(ValueError):
            self.get(api(LINUX[0], pomme.MAX_BYTES + 1, "a" * 64))
        with self.assertRaises(ValueError):
            self.get({**api(LINUX[0], 10, "a" * 64), "draft": True})
        with self.assertRaisesRegex(ValueError, "no incluye"):
            self.get(api("other.zip", 10, "a" * 64))

    def test_supported_systems(self):
        with mock.patch.object(pomme.platform, "machine", return_value="aarch64"):
            self.assertIsNone(pomme.supported())
        with mock.patch.object(pomme.platform, "machine", return_value="x86_64"), \
                mock.patch.object(pomme.os, "name", "nt"):
            self.assertEqual(pomme.supported(), WINDOWS)


class InstallTests(Base):
    def run_install(self, asset, body, **kw):
        with mock.patch.object(pomme, "supported", return_value=asset), self.serve(asset, body, **kw):
            return pomme.install()

    def test_linux_install_is_verified_executable_and_recorded(self):
        info = self.run_install(LINUX, PAYLOAD)
        self.assertEqual(info["tag"], "client-v0.2.10+26.2")
        self.assertEqual(info["exe"].read_bytes(), PAYLOAD)
        self.assertTrue(info["exe"].stat().st_mode & 0o100)
        self.assertEqual(pomme.installed()["tag"], "client-v0.2.10+26.2")
        self.assertEqual([p.name for p in (motor.ROOT / "clients").iterdir()], ["pomme"])

    def test_windows_zip_must_hold_exactly_the_one_executable(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("pomme-client.exe", b"MZ fake")
        info = self.run_install(WINDOWS, buffer.getvalue())
        self.assertEqual(info["exe"].read_bytes(), b"MZ fake")
        evil = io.BytesIO()
        with zipfile.ZipFile(evil, "w") as package:
            package.writestr("../escape.exe", b"x")
        with self.assertRaisesRegex(ValueError, "inesperado"):
            self.run_install(WINDOWS, evil.getvalue())
        self.assertFalse((motor.ROOT / "escape.exe").exists())

    def test_wrong_checksum_is_discarded_and_keeps_the_previous_install(self):
        self.run_install(LINUX, PAYLOAD)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.run_install(LINUX, b"tampered bytes here", digest="b" * 64)
        self.assertEqual(pomme.installed()["exe"].read_bytes(), PAYLOAD)
        self.assertEqual([p.name for p in (motor.ROOT / "clients").iterdir()], ["pomme"])

    def test_download_larger_or_shorter_than_announced_is_refused(self):
        answers = [Fake(data=api(LINUX[0], 5, "a" * 64)), Fake(chunks=[b"123456789"])]
        with mock.patch.object(pomme, "supported", return_value=LINUX), \
                mock.patch.object(pomme.requests, "get", side_effect=answers):
            with self.assertRaisesRegex(ValueError, "más grande"):
                pomme.install()
        answers = [Fake(data=api(LINUX[0], 50, "a" * 64)), Fake(chunks=[b"123"])]
        with mock.patch.object(pomme, "supported", return_value=LINUX), \
                mock.patch.object(pomme.requests, "get", side_effect=answers):
            with self.assertRaisesRegex(ValueError, "incompleta"):
                pomme.install()
        self.assertIsNone(pomme.installed())

    def test_reinstall_replaces_the_old_version(self):
        self.run_install(LINUX, PAYLOAD, tag="client-v0.2.10+26.2")
        newer = PAYLOAD + b"# newer\n"
        info = self.run_install(LINUX, newer)
        self.assertEqual(info["exe"].read_bytes(), newer)
        self.assertEqual([p.name for p in (motor.ROOT / "clients").iterdir()], ["pomme"])

    def test_unsupported_system_says_so(self):
        with mock.patch.object(pomme, "supported", return_value=None):
            with self.assertRaisesRegex(ValueError, "todavía no tiene versión"):
                pomme.install()


class InstalledTests(Base):
    def test_missing_or_tampered_records_mean_not_installed(self):
        self.assertIsNone(pomme.installed())
        folder = pomme.folder()
        folder.mkdir(parents=True)
        (folder / "installed.json").write_text(json.dumps({"tag": "v1", "exe": "../../bin/sh"}))
        self.assertIsNone(pomme.installed())
        (folder / "installed.json").write_text("{not json")
        self.assertIsNone(pomme.installed())
        (folder / "installed.json").write_text(json.dumps({"tag": "v1", "exe": "pomme.AppImage"}))
        self.assertIsNone(pomme.installed())  # the file itself is gone


class LaunchTests(Base):
    def test_launch_runs_the_file_with_a_log_and_no_shell(self):
        instance = motor.ROOT / "instances" / "x"
        instance.mkdir(parents=True)
        exe = motor.ROOT / "p.sh"
        exe.write_text("#!/bin/sh\necho hola desde pomme\n")
        exe.chmod(0o755)
        process = pomme.launch({"tag": "v1", "exe": exe}, instance)
        self.assertEqual(process.wait(timeout=10), 0)
        self.assertIn("hola desde pomme", (instance / "pomme.log").read_text())


if __name__ == "__main__":
    unittest.main()

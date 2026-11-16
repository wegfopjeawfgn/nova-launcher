import tempfile
import unittest
from pathlib import Path
from unittest import mock

import instalar_actualizacion as ia


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(ia, "UPDATES", self.dir)
        patch.start()
        self.addCleanup(patch.stop)

    def rpm(self, body=b"rpm"):
        path = self.dir / "nova-launcher-1.14.0-1.noarch.rpm"
        path.write_bytes(body)
        return path

    def test_staged_path_only_for_nova_names(self):
        url = "https://github.com/x/y/releases/download/v1.14.0/nova-launcher-1.14.0-1.noarch.rpm"
        self.assertEqual(ia.staged_path(url), self.dir / "nova-launcher-1.14.0-1.noarch.rpm")
        self.assertEqual(ia.staged_path(url.replace("1.noarch.rpm", "windows-x64-setup.exe")).suffix, ".exe")
        for bad in ("https://x/evil.rpm", "https://x/nova-launcher-1.0.0-1.noarch.rpm.sha256",
                    "https://x/..%2Fnova-launcher-1.0.0-1.noarch.rpm", "https://x/nova-launcher-1.0.0.exe"):
            with self.assertRaises(ValueError):
                ia.staged_path(bad)

    def test_verified_until_the_file_changes(self):
        path = self.rpm()
        self.assertFalse(ia.is_verified(path))
        ia.mark_verified(path, "v1.14.0")
        self.assertTrue(ia.is_verified(path))
        path.write_bytes(b"otro")
        self.assertFalse(ia.is_verified(path))

    def test_unverified_is_not_applied(self):
        with self.assertRaises(ValueError):
            ia.apply(self.rpm())

    def test_fedora_runs_dnf_through_pkexec(self):
        path = self.rpm()
        ia.mark_verified(path, "v1.14.0")
        with mock.patch.object(ia.os, "name", "posix"), mock.patch.object(ia.subprocess, "run") as run:
            ia.apply(path)
        self.assertEqual(run.call_args[0][0], ["pkexec", "dnf", "install", "-y", str(path)])

    def test_windows_argv_is_silent_and_relaunches(self):
        argv = ia.install_argv(Path("C:/x/nova-launcher-1.14.0-windows-x64-setup.exe"), windows=True)
        for flag in ("/VERYSILENT", "/NORESTART", "/RELAUNCH=1"):
            self.assertIn(flag, argv)

    def test_clean_keeps_only_the_current_one(self):
        keep = self.rpm()
        old = self.dir / "nova-launcher-1.0.0-1.noarch.rpm"
        old.write_bytes(b"x")
        ia.mark_verified(keep, "v")
        ia.clean(keep)
        self.assertTrue(keep.exists() and (self.dir / (keep.name + ".ok")).exists())
        self.assertFalse(old.exists())

    def test_failure_text(self):
        cancelled = mock.Mock(returncode=126, stderr="", stdout="")
        self.assertIn("canceló", ia.failure_text(cancelled))
        failed = mock.Mock(returncode=1, stderr="Error: algo\nNo hay conexión", stdout="")
        self.assertIn("No hay conexión", ia.failure_text(failed))


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402
import tunel_playit as tp  # noqa: E402

CLI = """#!/bin/sh
case "$1 $2" in
  "claim generate") echo abc123def4 ;;
  "claim url") echo "https://playit.gg/claim/$3" ;;
  "claim exchange") echo "waiting"; echo "0123456789abcdef0123456789abcdef" ;;
esac
"""
DAEMON = """#!/bin/sh
echo "agent started"
echo "tunnel connected"
sleep 30
"""


class Response:
    def __init__(self, data=None, payload=b""):
        self._data, self.payload = data, payload

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


def fake_release(daemon=b"d" * 3000, cli=b"c" * 2000, **override):
    def asset(name, data):
        return {"name": name, "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "browser_download_url": f"{tp.DOWNLOAD_PREFIX}v2.0.2/{name}"}
    data = {"tag_name": "v2.0.2", "draft": False, "prerelease": False,
            "assets": [asset("playit-linux-amd64", daemon), asset("playit-cli-linux-amd64", cli)]}
    data.update(override)
    return data


class Base(unittest.TestCase):
    def setUp(self):
        self.original = motor.ROOT
        motor.ROOT = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(tp, "supported", return_value=("playit-linux-amd64", "playit-cli-linux-amd64"))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        tp.AGENT.stop()

    def tearDown(self):
        tp.AGENT.stop()
        motor.ROOT = self.original

    def fake_install(self):
        tp.folder().mkdir(parents=True)
        for name, text in (("playit-cli", CLI), ("playitd", DAEMON)):
            (tp.folder() / name).write_text(text)
            (tp.folder() / name).chmod(0o755)
        (tp.folder() / "installed.json").write_text(json.dumps({"tag": "v2.0.2"}))


class InstallTests(Base):
    def get(self, release, payloads):
        def fake(url, **kwargs):
            if url == tp.API:
                return Response(release)
            return Response(payload=payloads[url.rsplit("/", 1)[1]])
        return fake

    def test_install_checks_every_hash_and_makes_the_files_executable(self):
        release = fake_release()
        with mock.patch("tunel_playit.requests.get", self.get(release, {"playit-linux-amd64": b"d" * 3000, "playit-cli-linux-amd64": b"c" * 2000})):
            info = tp.install()
        self.assertEqual(info["tag"], "v2.0.2")
        self.assertTrue(stat.S_IMODE(info["daemon"].stat().st_mode) & 0o100)
        self.assertEqual(info["cli"].read_bytes(), b"c" * 2000)

    def test_a_wrong_hash_changes_nothing_and_an_update_keeps_the_account(self):
        self.fake_install()
        (tp.folder() / "secret.key").write_text("keep")
        before = (tp.folder() / "playitd").read_text()
        with mock.patch("tunel_playit.requests.get", self.get(fake_release(), {"playit-linux-amd64": b"x" * 3000, "playit-cli-linux-amd64": b"c" * 2000})):
            with self.assertRaises(ValueError):
                tp.install()
        self.assertEqual((tp.folder() / "playitd").read_text(), before)
        with mock.patch("tunel_playit.requests.get", self.get(fake_release(), {"playit-linux-amd64": b"d" * 3000, "playit-cli-linux-amd64": b"c" * 2000})):
            tp.install()
        self.assertEqual((tp.folder() / "secret.key").read_text(), "keep")
        self.assertEqual([p.name for p in tp.folder().parent.iterdir()], ["playit"])

    def test_release_refuses_unexpected_data(self):
        names = ("playit-linux-amd64", "playit-cli-linux-amd64")
        for bad in (fake_release(prerelease=True), fake_release(tag_name="v/../x")):
            with mock.patch("tunel_playit.requests.get", return_value=Response(bad)):
                with self.assertRaises(ValueError):
                    tp.release(names)
        wrong = fake_release()
        wrong["assets"][0]["browser_download_url"] = "https://evil.example/playit-linux-amd64"
        with mock.patch("tunel_playit.requests.get", return_value=Response(wrong)):
            with self.assertRaises(ValueError):
                tp.release(names)
        missing = fake_release()
        missing["assets"].pop()
        with mock.patch("tunel_playit.requests.get", return_value=Response(missing)):
            with self.assertRaises(ValueError):
                tp.release(names)

    def test_unsupported_systems_are_refused(self):
        self.patch.stop()
        try:
            with mock.patch.object(tp.sys, "platform", "win32"):
                self.assertIsNone(tp.supported())
                with self.assertRaises(ValueError):
                    tp.install()
        finally:
            self.patch.start()


class AccountTests(Base):
    def test_claim_flow_stores_the_key_privately(self):
        self.fake_install()
        self.assertFalse(tp.has_secret())
        code, url = tp.claim_start()
        self.assertEqual((code, url), ("abc123def4", "https://playit.gg/claim/abc123def4"))
        self.assertTrue(tp.claim_finish(code, wait=5))
        self.assertTrue(tp.has_secret())
        self.assertEqual(stat.S_IMODE(tp.secret_path().stat().st_mode), 0o600)
        self.assertEqual(tp.secret_path().read_text(), "0123456789abcdef0123456789abcdef")
        tp.forget_account()
        self.assertFalse(tp.has_secret())

    def test_an_unexpected_cli_answer_is_not_trusted(self):
        self.fake_install()
        (tp.folder() / "playit-cli").write_text("#!/bin/sh\necho 'rm -rf / evil'\n")
        with self.assertRaises(tp.ClaimError):
            tp.claim_start()
        (tp.folder() / "playit-cli").write_text("#!/bin/sh\necho abc123def4\n")
        with self.assertRaises(tp.ClaimError):   # the url step prints a code, not a playit.gg link
            tp.claim_start()
        with self.assertRaises(tp.ClaimError):
            tp.claim_finish("abc123def4", wait=1)   # no secret printed
        self.assertFalse(tp.has_secret())

    def test_claim_needs_the_agent(self):
        with self.assertRaises(tp.ClaimError):
            tp.claim_start()


class AgentTests(Base):
    def test_agent_runs_logs_and_stops(self):
        self.fake_install()
        with self.assertRaises(RuntimeError):
            tp.AGENT.start()          # no account yet
        tp.secret_path().write_text("0123456789abcdef0123456789abcdef")
        tp.AGENT.start()
        end = time.monotonic() + 5
        while not any("tunnel connected" in line for line in tp.AGENT.lines) and time.monotonic() < end:
            time.sleep(0.05)
        self.assertTrue(tp.AGENT.running)
        self.assertTrue(any("tunnel connected" in line for line in tp.AGENT.lines))
        tp.AGENT.stop()
        self.assertFalse(tp.AGENT.running)

    def test_valid_address(self):
        self.assertEqual(tp.valid_address(" amigos.joinmc.link "), "amigos.joinmc.link")
        self.assertEqual(tp.valid_address("a-b.gl.at.ply.gg:12345"), "a-b.gl.at.ply.gg:12345")
        for bad in ("", "http://x.com", "x y", "x.com:99999", "x.com:0", "../x", None):
            self.assertIsNone(tp.valid_address(bad))


if __name__ == "__main__":
    unittest.main()

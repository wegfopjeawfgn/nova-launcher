import threading
import time
import unittest
import urllib.request
from unittest import mock

import roblox_cuenta as rc


class PkceTests(unittest.TestCase):
    def test_rfc7636_example(self):
        self.assertEqual(rc.challenge_for("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_pkce_pair_matches(self):
        verifier, challenge = rc.pkce()
        self.assertEqual(rc.challenge_for(verifier), challenge)
        self.assertGreaterEqual(len(verifier), 43)

    def test_authorize_url_asks_only_identity(self):
        url = rc.authorize_url("cid", "st", "ch", 1234)
        for part in ("client_id=cid", "scope=openid+profile", "code_challenge_method=S256", "state=st",
                     "redirect_uri=http%3A%2F%2Flocalhost%3A1234%2Froblox", "response_type=code"):
            self.assertIn(part, url)


def _visit(port, query, delay=0.3):
    def go():
        time.sleep(delay)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/roblox?{query}", timeout=5).read()
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()


class WaitTests(unittest.TestCase):
    PORT = 53991

    def test_code_with_right_state(self):
        _visit(self.PORT, "code=abc&state=xyz")
        self.assertEqual(rc.wait_for_code("xyz", self.PORT, timeout=5), "abc")

    def test_wrong_state_is_refused(self):
        _visit(self.PORT + 1, "code=abc&state=otro")
        with self.assertRaises(ValueError):
            rc.wait_for_code("xyz", self.PORT + 1, timeout=5)

    def test_denied(self):
        _visit(self.PORT + 2, "error=access_denied&state=xyz")
        with self.assertRaises(PermissionError):
            rc.wait_for_code("xyz", self.PORT + 2, timeout=5)

    def test_timeout(self):
        with self.assertRaises(TimeoutError):
            rc.wait_for_code("xyz", self.PORT + 3, timeout=0.5)


class ProfileTests(unittest.TestCase):
    def test_profile(self):
        reply = mock.Mock(json=lambda: {"sub": "156", "name": "Constructor", "preferred_username": "builderman",
                                        "picture": "https://tr.rbxcdn.com/x"})
        with mock.patch.object(rc.requests, "get", return_value=reply):
            self.assertEqual(rc.profile("t"), {"id": 156, "name": "builderman", "display": "Constructor",
                                               "picture": "https://tr.rbxcdn.com/x"})

    def test_profile_without_id(self):
        with mock.patch.object(rc.requests, "get", return_value=mock.Mock(json=lambda: {"name": "x"})):
            with self.assertRaises(ValueError):
                rc.profile("t")

    def test_picture_must_be_https(self):
        reply = mock.Mock(json=lambda: {"sub": "1", "picture": "http://evil/x"})
        with mock.patch.object(rc.requests, "get", return_value=reply):
            self.assertEqual(rc.profile("t")["picture"], "")

    def test_exchange_failure_message(self):
        with mock.patch.object(rc.requests, "post", return_value=mock.Mock(status_code=400)):
            with self.assertRaises(ValueError):
                rc.exchange("cid", "code", "ver")

    def test_login_drops_tokens(self):
        opened = []
        with mock.patch.object(rc, "wait_for_code", return_value="code") as wait, \
                mock.patch.object(rc, "exchange", return_value={"access_token": "a", "refresh_token": "r"}), \
                mock.patch.object(rc, "profile", return_value={"id": 1}), \
                mock.patch.object(rc, "revoke") as revoke:
            wait.side_effect = lambda state, port, ready: (ready(), "code")[1]
            person = rc.login("cid", opened.append, 1234)
        self.assertEqual(person, {"id": 1})
        self.assertEqual(len(opened), 1)
        self.assertEqual(revoke.call_count, 2)


if __name__ == "__main__":
    unittest.main()

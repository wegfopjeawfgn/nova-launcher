from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actualizaciones  # noqa: E402
import seguridad  # noqa: E402


class OAuthCallbackTests(unittest.TestCase):
    def test_accepts_the_expected_state(self):
        self.assertTrue(seguridad.oauth_callback_ok("/?code=abc&state=xyz", "xyz"))
        self.assertTrue(seguridad.oauth_callback_ok("/?error=access_denied&state=xyz", "xyz"))

    def test_rejects_wrong_missing_or_repeated_state(self):
        for path in ("/?code=abc", "/?code=abc&state=other", "/?code=abc&state=xyz&state=xyz", "/?state=xyz",
                     "/favicon.ico", "/?code=abc&state="):
            with self.subTest(path=path):
                self.assertFalse(seguridad.oauth_callback_ok(path, "xyz"))

    def test_rejects_everything_without_an_expected_state(self):
        self.assertFalse(seguridad.oauth_callback_ok("/?code=abc&state=xyz", ""))
        self.assertFalse(seguridad.oauth_callback_ok("/?code=abc", None))


class UpdateUrlTests(unittest.TestCase):
    good = "https://github.com/o/r/releases/download/v1.4.0/nova-launcher-1.4.0-1.noarch.rpm"

    def test_accepts_github_release_downloads(self):
        self.assertTrue(seguridad.safe_update_url(self.good))

    def test_rejects_other_hosts_schemes_and_tricks(self):
        for url in ("http://github.com/o/r/releases/download/v1/a.rpm",
                    "https://evil.example/o/r/releases/download/v1/a.rpm",
                    "https://github.com.evil.example/o/r/releases/download/v1/a.rpm",
                    "https://user@github.com/o/r/releases/download/v1/a.rpm",
                    "https://github.com:8443/o/r/releases/download/v1/a.rpm",
                    "https://github.com/o/r/archive/main.zip",
                    "https://github.com/o/r/releases/download/../../x.rpm",
                    "file:///etc/passwd", ""):
            with self.subTest(url=url):
                self.assertFalse(seguridad.safe_update_url(url))

    def test_download_refuses_unsafe_urls_before_any_request(self):
        destination = Path("/tmp/nunca.rpm")
        with self.assertRaises(ValueError):
            actualizaciones.download("https://evil.example/a.rpm", destination)


if __name__ == "__main__":
    unittest.main()

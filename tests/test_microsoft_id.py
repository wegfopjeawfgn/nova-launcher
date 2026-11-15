from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import cuentas  # noqa: E402
except ImportError as error:   # minecraft_launcher_lib is installed by CI; skip where it is not
    raise unittest.SkipTest(f"falta una dependencia: {error}")

ID = "12345678-1234-5678-1234-567812345678"


class BuiltInIdTests(unittest.TestCase):
    def test_no_built_in_id_means_the_form_with_its_guide(self):
        with mock.patch.object(cuentas, "DEFAULT_CLIENT_ID", ""):
            self.assertIsNone(cuentas.default_client_id())
        with mock.patch.object(cuentas, "DEFAULT_CLIENT_ID", "no-es-un-uuid"):
            self.assertIsNone(cuentas.default_client_id())

    def test_a_valid_built_in_id_is_normalised(self):
        with mock.patch.object(cuentas, "DEFAULT_CLIENT_ID", ID.upper()):
            self.assertEqual(cuentas.default_client_id(), ID)

    def test_connect_uses_the_built_in_id_without_asking_unless_the_person_wants_their_own(self):
        app = mock.Mock()
        with mock.patch.object(cuentas, "DEFAULT_CLIENT_ID", ID), \
                mock.patch.object(cuentas.microsoft, "get_secure_login_data", return_value=("https://login", "s", "v")) as login, \
                mock.patch.object(cuentas, "wait_for_callback", return_value=None), mock.patch.object(cuentas.Gio.AppInfo, "launch_default_for_uri"), \
                mock.patch.object(cuentas.GLib, "idle_add"):
            cuentas.connect(app)
            login.assert_called_once_with(ID, cuentas.REDIRECT)
            app.microsoft_guide.assert_not_called()
            cuentas.connect(app, own=True)
            app.microsoft_guide.assert_called_once()
        app = mock.Mock()
        with mock.patch.object(cuentas, "DEFAULT_CLIENT_ID", ""):
            cuentas.connect(app)
            app.microsoft_guide.assert_called_once()


if __name__ == "__main__":
    unittest.main()

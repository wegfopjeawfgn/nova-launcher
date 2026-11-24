import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402


def root_with(env):
    # shortcut: motor.ROOT is computed at import, so reload under a mocked env and restore afterwards.
    with mock.patch.dict(os.environ, env, clear=False):
        for key in ("FLATPAK_ID", "XDG_DATA_HOME"):
            if key not in env:
                os.environ.pop(key, None)
        return importlib.reload(motor).ROOT


class FlatpakDataTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(motor)

    @unittest.skipIf(os.name == "nt", "XDG is not used on Windows")
    def test_native_respects_xdg(self):
        self.assertEqual(root_with({"XDG_DATA_HOME": "/tmp/xdg"}), Path("/tmp/xdg/nova-launcher"))

    @unittest.skipIf(os.name == "nt", "XDG is not used on Windows")
    def test_flatpak_uses_real_home(self):
        root = root_with({"FLATPAK_ID": "io.nova.launcher", "XDG_DATA_HOME": "/tmp/sandbox/data"})
        self.assertEqual(root, Path.home() / ".local/share/nova-launcher")


if __name__ == "__main__":
    unittest.main()

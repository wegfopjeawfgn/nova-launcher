import os
from pathlib import Path
import platform
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor  # noqa: E402,F401  (importing it installs the cached platform.architecture)
import widgets  # noqa: E402


class ArchitectureTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "Windows does not start `file`")
    def test_architecture_is_looked_up_once_not_once_per_library(self):
        platform.architecture.cache_clear()
        with mock.patch.object(platform, "_syscmd_file", return_value="") as lookup:
            for _ in range(95):
                platform.architecture()
        self.assertLessEqual(lookup.call_count, 1)

    def test_cached_answer_is_the_real_one(self):
        platform.architecture.cache_clear()
        self.assertEqual(platform.architecture(), platform.architecture.__wrapped__())

    def test_importing_motor_again_does_not_wrap_twice(self):
        wrapped = platform.architecture
        import importlib
        importlib.reload(motor)
        self.assertIs(platform.architecture, wrapped)


class CoverTests(unittest.TestCase):
    def test_the_cover_sheet_is_decoded_once_for_every_cover(self):
        widgets._default_covers.cache_clear()
        sheet = mock.Mock()
        sheet.new_subpixbuf.side_effect = lambda *box: ("pixels", box)
        with mock.patch.object(widgets.GdkPixbuf.Pixbuf, "new_from_file", return_value=sheet) as decode, \
                mock.patch.object(widgets.Gdk.Texture, "new_for_pixbuf", side_effect=lambda pixels: pixels):
            covers = [widgets.default_cover(index) for index in range(7)]
            self.assertEqual(decode.call_count, 1)
        self.assertEqual(covers[0], covers[3])  # indexes wrap around the three covers
        self.assertNotEqual(covers[0], covers[1])
        self.assertEqual(covers[0][1], widgets.DEFAULT_COVERS[0])
        widgets._default_covers.cache_clear()


if __name__ == "__main__":
    unittest.main()

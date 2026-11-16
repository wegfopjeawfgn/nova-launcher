import tempfile
import unittest
from pathlib import Path
from unittest import mock

import motor
import pantalla_carga as pc


class LoadingScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.object(motor, "instance_lock", lambda folder: mock.MagicMock())
        patch.start()
        self.addCleanup(patch.stop)
        self.fabric = {"version": "1.21.11", "loader": "fabric"}

    def read(self):
        return motor.read(pc.config_path(self.folder), {})

    def test_apply_writes_the_cyan_palette_and_marks_the_instance(self):
        self.assertEqual(pc.status(self.folder), "off")
        pc.apply(self.folder, self.fabric)
        self.assertEqual(self.read()["bar"], "8fd6e8")
        self.assertEqual(pc.status(self.folder), "on")
        self.assertTrue(motor.read(self.folder / pc.MARKER, {})["logo"])

    def test_logo_only_where_it_is_supported(self):
        pc.apply(self.folder, {"version": "1.20.1", "loader": "fabric"})
        self.assertFalse(motor.read(self.folder / pc.MARKER, {})["logo"])

    def test_remove_restores_what_the_player_had(self):
        motor.save(pc.config_path(self.folder), {"bar": "ff0000", "other": 1})
        pc.apply(self.folder, self.fabric)
        pc.apply(self.folder, self.fabric)       # applying twice must not forget the first state
        pc.remove(self.folder)
        data = self.read()
        self.assertEqual(data["bar"], "ff0000")
        self.assertNotIn("background", data)      # it was not there before: gone again
        self.assertEqual(data["other"], 1)
        self.assertEqual(pc.status(self.folder), "off")
        pc.remove(self.folder)                    # removing twice is harmless

    def test_old_palette_is_upgraded_at_the_next_start(self):
        motor.save(pc.config_path(self.folder), {"bar": "bb94f5", "background": "101022"})
        motor.save(self.folder / pc.MARKER, {"logo": True, "palette": 1})
        pc.upgrade(self.folder)
        self.assertEqual(self.read()["bar"], "8fd6e8")
        self.assertEqual(motor.read(self.folder / pc.MARKER, {})["palette"], pc.VERSION)

    def test_upgrade_leaves_alone_instances_without_the_screen(self):
        motor.save(pc.config_path(self.folder), {"bar": "bb94f5"})
        pc.upgrade(self.folder)
        self.assertEqual(self.read()["bar"], "bb94f5")


if __name__ == "__main__":
    unittest.main()

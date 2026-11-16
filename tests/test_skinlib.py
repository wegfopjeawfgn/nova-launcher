import base64
import json
import unittest
from unittest import mock

import skin3d
import skinlib as sl


def px(pixels, x, y):
    return bytes(pixels[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4])


class LayoutTests(unittest.TestCase):
    def test_faces_do_not_overlap_in_the_classic_model(self):
        seen = {}
        for part, side, overlay, (u, v, w, h) in sl.faces(False):
            for y in range(v, v + h):
                for x in range(u, u + w):
                    self.assertNotIn((x, y), seen, (part, side, overlay))
                    seen[(x, y)] = 1
        self.assertTrue(all(0 <= x < 64 and 0 <= y < 64 for x, y in seen))

    def test_face_at_and_overlay(self):
        self.assertEqual(sl.face_at(10, 10)[:3], (0, 0, False))      # front of the head
        self.assertEqual(sl.face_at(42, 10)[:3], (0, 0, True))       # front of the hat
        self.assertTrue(sl.is_overlay(42, 10))
        self.assertFalse(sl.paintable(0, 16))                       # unused corner of the sheet

    def test_slim_arms_are_three_wide(self):
        self.assertEqual(sl.face(2, 0, slim=True)[2], 3)
        self.assertEqual(sl.face(2, 0, slim=False)[2], 4)

    def test_mirror_is_its_own_inverse(self):
        for slim in (False, True):
            for part, side, overlay, (u, v, w, h) in sl.faces(slim):
                for x, y in ((u, v), (u + w - 1, v + h - 1)):
                    other = sl.mirror_texel(x, y, slim)
                    self.assertIsNotNone(other)
                    self.assertEqual(sl.mirror_texel(*other, slim), (x, y), (part, side, overlay, slim))

    def test_mirror_swaps_arms_and_legs(self):
        u, v, _, _ = sl.face(2, 0)
        x, y = sl.mirror_texel(u, v)
        self.assertEqual(sl.face_at(x, y)[:2], (3, 0))
        self.assertEqual(sl.face_at(*sl.mirror_texel(*sl.face(4, 0)[:2]))[:2], (5, 0))


class PixelTests(unittest.TestCase):
    def test_seed_covers_the_whole_base_layer(self):
        self.assertFalse(sl.base_has_holes(sl.seed()))
        self.assertTrue(sl.base_has_holes(sl.blank()))

    def test_flood_fill_stays_inside_the_face(self):
        pixels = sl.seed()
        u, v, w, h = sl.face(0, 0)
        changed = sl.flood_fill(pixels, u, v, (1, 2, 3, 255))
        self.assertEqual(changed, w * h - 2)  # the two eye texels keep their colour
        self.assertEqual(px(pixels, u - 1, v), px(sl.seed(), u - 1, v))   # the face next to it is untouched
        self.assertEqual(sl.flood_fill(pixels, u, v, (1, 2, 3, 255)), 0)
        self.assertEqual(sl.flood_fill(pixels, 0, 16, (1, 2, 3, 255)), 0)

    def test_legacy_skin_gets_mirrored_limbs(self):
        legacy = bytearray(64 * 32 * 4)
        for i in range(4):  # the front of the right leg: a gradient left to right
            for j in range(12):
                legacy[((20 + j) * 64 + 4 + i) * 4:((20 + j) * 64 + 4 + i) * 4 + 4] = bytes((10 * (i + 1), 0, 0, 255))
        full = sl.upgrade_legacy(legacy)
        self.assertEqual(len(full), 64 * 64 * 4)
        left_front = sl.face(5, 0)
        row = [px(full, left_front[0] + i, left_front[1])[0] for i in range(4)]
        self.assertEqual(row, [40, 30, 20, 10])       # mirrored
        with self.assertRaises(ValueError):
            sl.upgrade_legacy(bytearray(10))

    def test_guess_slim(self):
        pixels = sl.seed()
        self.assertFalse(sl.guess_slim(pixels))
        for y in range(20, 32):
            pixels[(y * 64 + 47) * 4 + 3] = 0
        self.assertFalse(sl.guess_slim(pixels))      # only one arm: not enough
        for y in range(52, 64):
            pixels[(y * 64 + 39) * 4 + 3] = 0
        self.assertTrue(sl.guess_slim(pixels))

    def test_head_icon_prefers_the_hat(self):
        pixels = sl.seed()
        pixels[(8 * 64 + 40) * 4:(8 * 64 + 40) * 4 + 4] = bytes((9, 9, 9, 255))
        icon = sl.head_icon(pixels)
        self.assertEqual(icon[:4], bytes((9, 9, 9, 255)))
        self.assertEqual(len(icon), 8 * 8 * 4)


class MojangTests(unittest.TestCase):
    def profile(self, url, model=None):
        skin = {"url": url, **({"metadata": {"model": model}} if model else {})}
        value = base64.b64encode(json.dumps({"textures": {"SKIN": skin}}).encode()).decode()
        return {"properties": [{"name": "textures", "value": value}]}

    def test_texture_urls_only_from_mojang(self):
        self.assertTrue(sl.valid_texture_url("https://textures.minecraft.net/texture/abc"))
        self.assertTrue(sl.valid_texture_url("http://textures.minecraft.net/texture/abc"))
        for bad in ("ftp://textures.minecraft.net/texture/a", "https://evil.com/texture/a",
                    "https://textures.minecraft.net.evil.com/texture/a", "https://textures.minecraft.net/x", None, 5):
            self.assertFalse(sl.valid_texture_url(bad))

    def test_skin_from_profile(self):
        url = "https://textures.minecraft.net/texture/abc"
        self.assertEqual(sl.skin_from_profile(self.profile(url, "slim")), (url, True))
        self.assertEqual(sl.skin_from_profile(self.profile(url)), (url, False))
        self.assertEqual(sl.skin_from_profile(self.profile("http://textures.minecraft.net/texture/abc"))[0], url)
        self.assertIsNone(sl.skin_from_profile(self.profile("https://evil.com/texture/a")))
        self.assertIsNone(sl.skin_from_profile({"properties": [{"name": "textures", "value": "!!"}]}))
        self.assertIsNone(sl.skin_from_profile({}))

    def test_fetch_validates_the_name_first(self):
        with mock.patch.object(sl.requests, "get") as get:
            for bad in ("", "ab", "con espacio", "x" * 17, "a/b"):
                with self.assertRaises(ValueError):
                    sl.fetch_player_skin(bad)
            get.assert_not_called()

    def test_fetch_rate_limited(self):
        with mock.patch.object(sl.requests, "get", return_value=mock.Mock(status_code=429)):
            with self.assertRaises(ValueError) as caught:
                sl.fetch_player_skin("jeb_")
            self.assertIn("esperar", str(caught.exception))

    def test_fetch_unknown_player(self):
        with mock.patch.object(sl.requests, "get", return_value=mock.Mock(status_code=404)):
            with self.assertRaises(ValueError) as caught:
                sl.fetch_player_skin("NoExiste123")
            self.assertIn("No existe", str(caught.exception))


class ViewTests(unittest.TestCase):
    def test_scene_draws_quads_and_skips_transparent_texels(self):
        full = skin3d.scene(sl.seed(), yaw=0.0, pitch=0.0)
        self.assertGreater(len(full), 100)
        self.assertEqual(skin3d.scene(sl.blank()), [])
        for corners, color in full[:20]:
            self.assertEqual(len(corners), 4)
            self.assertTrue(all(0 <= c <= 1 for c in color))

    def test_back_faces_are_culled(self):
        front = skin3d.scene(sl.seed(), yaw=0.0, pitch=0.0)
        turned = skin3d.scene(sl.seed(), yaw=3.14159, pitch=0.0)
        self.assertEqual(len(front), len(turned))   # the same number of faces show from the back
        self.assertNotEqual([q[1] for q in front[:5]], [q[1] for q in turned[:5]])


if __name__ == "__main__":
    unittest.main()

import unittest

try:
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
except (ImportError, ValueError):
    GdkPixbuf = None

import skinlib


@unittest.skipIf(GdkPixbuf is None, "GTK no disponible")
class DecodeTests(unittest.TestCase):
    def png(self, width, height, alpha=True, fill=(10, 20, 30, 255)):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, alpha, 8, width, height)
        pixbuf.fill(int.from_bytes(bytes(fill), "big"))
        return pixbuf.save_to_bufferv("png", [], [])[1]

    def decode(self, data):
        import skins
        return skins.decode_skin(data)

    def test_64x64_and_legacy_64x32(self):
        pixels, slim = self.decode(self.png(64, 64))
        self.assertEqual((len(pixels), slim), (64 * 64 * 4, False))
        pixels, slim = self.decode(self.png(64, 32))
        self.assertEqual(len(pixels), 64 * 64 * 4)              # grown to 64x64 with mirrored limbs
        self.assertEqual(pixels[(48 * 64 + 20) * 4 + 3], 255)   # the left leg now exists

    def test_png_without_alpha(self):
        pixels, _ = self.decode(self.png(64, 64, alpha=False))
        self.assertEqual(pixels[3], 255)

    def test_refuses_other_sizes_and_junk(self):
        for data in (self.png(128, 128), self.png(64, 16), b"no es un png", b"\x89PNG\r\n\x1a\n" + b"x" * 20,
                     b"\x89PNG\r\n\x1a\n" + b"0" * (skinlib.MAX_SKIN_BYTES + 1)):
            with self.assertRaises(ValueError):
                self.decode(data)
        with self.assertRaises(ValueError) as caught:
            self.decode(self.png(128, 128))
        self.assertIn("128", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

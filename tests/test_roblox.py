import unittest
from unittest import mock

import roblox


class RobloxTests(unittest.TestCase):
    def test_parse_place(self):
        self.assertEqual(roblox.parse_place("606849621"), 606849621)
        self.assertEqual(roblox.parse_place("https://www.roblox.com/games/606849621/Jailbreak"), 606849621)
        self.assertEqual(roblox.parse_place("https://www.roblox.com/es/games/606849621"), 606849621)
        for bad in ("", "obby", "0", "https://evil.com/games/5", "roblox://x"):
            self.assertIsNone(roblox.parse_place(bad))

    def test_place_uri(self):
        self.assertEqual(roblox.place_uri(5), "roblox://experiences/start?placeId=5")
        for bad in (0, -1, "5", True, None):
            with self.assertRaises(ValueError):
                roblox.place_uri(bad)

    def test_game_filters_incomplete(self):
        self.assertIsNone(roblox._game({"name": "x"}))
        self.assertEqual(roblox._game({"rootPlaceId": 7, "name": "A", "universeId": 9, "playerCount": 3})["players"], 3)

    def test_categories_and_wide_cover(self):
        sorts = {"sorts": [{"sortId": "filters_v5"}, {"sortId": "fun-with-friends", "games": [
            {"rootPlaceId": 1, "name": "A", "universeId": 2}, {"name": "sin lugar"}]}]}
        with mock.patch.object(roblox, "_get", return_value=sorts):
            self.assertEqual(list(roblox.categories()), ["fun-with-friends"])
            self.assertEqual(roblox.categories()["fun-with-friends"][0]["place"], 1)
        thumbs = {"data": [{"thumbnails": [{"state": "Pending", "imageUrl": "https://a"},
                                           {"state": "Completed", "imageUrl": "https://b"}]}]}
        with mock.patch.object(roblox, "_get", return_value=thumbs):
            self.assertEqual(roblox.wide_cover(2), "https://b")
        with mock.patch.object(roblox, "_get", return_value={"data": []}):
            self.assertIsNone(roblox.wide_cover(2))

    def test_popular_and_search(self):
        found = {"searchResults": [{"contentGroupType": "Game", "contents": [
            {"rootPlaceId": 3, "name": "B", "universeId": 4}]}, {"contentGroupType": "Ad", "contents": [{}]}]}
        with mock.patch.object(roblox, "_get", return_value=found):
            self.assertEqual([g["place"] for g in roblox.search("x")], [3])

    def test_icons_only_https_completed(self):
        data = {"data": [{"targetId": 1, "state": "Completed", "imageUrl": "https://tr.rbxcdn.com/a"},
                         {"targetId": 2, "state": "Pending", "imageUrl": "https://x"},
                         {"targetId": 3, "state": "Completed", "imageUrl": "http://x"}]}
        with mock.patch.object(roblox, "_get", return_value=data):
            self.assertEqual(roblox.icons([1, 2, 3]), {1: "https://tr.rbxcdn.com/a"})
        self.assertEqual(roblox.icons([]), {})

    def test_play_linux_needs_sober(self):
        with mock.patch.object(roblox.sys, "platform", "linux"), \
                mock.patch.object(roblox, "sober_installed", return_value=False):
            with self.assertRaises(RuntimeError):
                roblox.play(5)
        with mock.patch.object(roblox.sys, "platform", "linux"), \
                mock.patch.object(roblox, "sober_installed", return_value=True), \
                mock.patch.object(roblox.subprocess, "Popen") as popen:
            roblox.play(5)
            self.assertEqual(popen.call_args[0][0], ["flatpak", "run", roblox.SOBER, "roblox://experiences/start?placeId=5"])


if __name__ == "__main__":
    unittest.main()

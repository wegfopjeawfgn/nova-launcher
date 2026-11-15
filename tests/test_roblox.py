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


class FriendsTests(unittest.TestCase):
    def test_follow_uri(self):
        self.assertEqual(roblox.follow_uri(156), "roblox://experiences/start?userId=156")
        for bad in (0, "1", True, None):
            with self.assertRaises(ValueError):
                roblox.follow_uri(bad)

    def test_find_user_validates_before_asking(self):
        with mock.patch.object(roblox.requests, "post") as post:
            for bad in ("", "ab", "con espacio", "x" * 21, "a;b"):
                self.assertIsNone(roblox.find_user(bad))
            post.assert_not_called()

    def test_find_user(self):
        reply = mock.Mock(json=lambda: {"data": [{"id": 7, "name": "Pepe", "displayName": "Pepito"}]})
        with mock.patch.object(roblox.requests, "post", return_value=reply):
            self.assertEqual(roblox.find_user("Pepe"), {"id": 7, "name": "Pepe", "display": "Pepito"})
        with mock.patch.object(roblox.requests, "post", return_value=mock.Mock(json=lambda: {"data": []})):
            self.assertIsNone(roblox.find_user("Nadie"))

    def test_headshots_and_rating(self):
        data = {"data": [{"targetId": 7, "state": "Completed", "imageUrl": "https://tr.rbxcdn.com/h"},
                         {"targetId": 8, "state": "Blocked", "imageUrl": ""}]}
        with mock.patch.object(roblox, "_get", return_value=data):
            self.assertEqual(roblox.headshots([7, 8]), {7: "https://tr.rbxcdn.com/h"})
        self.assertEqual(roblox._rating({"totalUpVotes": 90, "totalDownVotes": 10}), 90)
        self.assertIsNone(roblox._rating({"totalUpVotes": 3, "totalDownVotes": 1}))
        self.assertIsNone(roblox._rating({}))

    def test_prices_only_paid_games(self):
        data = {"data": [{"id": 1, "price": 100}, {"id": 2, "price": None}, {"id": 3, "price": 0}, {"id": "x", "price": 5}]}
        with mock.patch.object(roblox, "_get", return_value=data):
            self.assertEqual(roblox.prices([1, 2, 3]), {1: 100})
        self.assertEqual(roblox.prices([]), {})

    def test_join_friend_opens_the_link(self):
        with mock.patch.object(roblox.sys, "platform", "linux"), \
                mock.patch.object(roblox, "sober_installed", return_value=True), \
                mock.patch.object(roblox.subprocess, "Popen") as popen:
            roblox.join_friend(156)
            self.assertEqual(popen.call_args[0][0][-1], "roblox://experiences/start?userId=156")

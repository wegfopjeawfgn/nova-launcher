"""Roblox in Nova: explore public experiences and open one straight into the game.
Nova never plays Roblox itself and never sees a Roblox password: it hands a roblox:// link to the
official client (Windows, macOS) or to Sober, the community client for Linux. Signing in happens there."""
import os
import re
import shutil
import subprocess
import sys
import uuid

import requests

SOBER = "org.vinegarhq.Sober"
SORTS = "https://apis.roblox.com/explore-api/v1/get-sorts"
SEARCH = "https://apis.roblox.com/search-api/omni-search"
THUMBS = "https://thumbnails.roblox.com/v1/games/multiget/thumbnails"
ICONS = "https://thumbnails.roblox.com/v1/games/icons"
USER_AGENT = "NovaLauncher"
_PLACE = re.compile(r"^(?:https?://(?:www\.)?roblox\.com/(?:[a-z]{2}/)?games/)?(\d{1,15})(?:[/?#].*)?$", re.I)


def parse_place(text):
    """A place id from a bare number or a roblox.com/games/<id>/... link, else None."""
    found = _PLACE.match((text or "").strip())
    return int(found.group(1)) if found and int(found.group(1)) > 0 else None


def place_uri(place_id):
    if not isinstance(place_id, int) or isinstance(place_id, bool) or place_id <= 0:
        raise ValueError("Identificador de juego no válido")
    return f"roblox://experiences/start?placeId={place_id}"


def sober_installed():
    if not sys.platform.startswith("linux") or not shutil.which("flatpak"):
        return False
    done = subprocess.run(["flatpak", "info", SOBER], capture_output=True, timeout=20)
    return done.returncode == 0


def launcher_state():
    """('ready', note) when a client can open games; ('missing', how to get one) otherwise."""
    if sys.platform.startswith("linux"):
        if sober_installed():
            return "ready", "Se abre con Sober. La primera vez iniciás sesión ahí."
        return "missing", "Instalá Sober (flatpak install flathub org.vinegarhq.Sober) para jugar en Linux."
    return "ready", "Se abre con el cliente oficial de Roblox. Si no lo tenés, Roblox te lo ofrece."


def play(place_id):
    """Open the game in the client. Returns the process or None when the OS handles the link."""
    uri = place_uri(place_id)
    if sys.platform.startswith("linux"):
        if not sober_installed():
            raise RuntimeError("Sober no está instalado")
        return subprocess.Popen(["flatpak", "run", SOBER, uri], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if sys.platform == "win32":
        os.startfile(uri)  # noqa: the OS routes roblox:// to the installed client
        return None
    subprocess.Popen(["open", uri])
    return None


def _get(url, **params):
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()


def _game(raw):
    place = raw.get("rootPlaceId")
    name = str(raw.get("name") or "").strip()
    if not isinstance(place, int) or place <= 0 or not name:
        return None
    return {"place": place, "universe": raw.get("universeId"), "name": name[:80],
            "players": raw.get("playerCount") if isinstance(raw.get("playerCount"), int) else 0}


CATEGORIES = (("top-trending", "Tendencias"), ("top-playing-now", "Más jugados"),
              ("up-and-coming", "Emergentes"), ("fun-with-friends", "Con amigos"))


def categories(limit=30):
    """{sortId: [games]} for every category Nova shows, in one request."""
    data = _get(SORTS, sessionId=str(uuid.uuid4()), device="computer", country="all")
    wanted = dict(CATEGORIES)
    found = {}
    for sort in data.get("sorts", []):
        if sort.get("sortId") in wanted:
            found[sort["sortId"]] = [g for g in map(_game, sort.get("games", [])) if g][:limit]
    return found


def wide_cover(universe):
    """A 16:9 thumbnail url of a game, or None."""
    data = _get(THUMBS, universeIds=universe, size="768x432", format="Png", countPerUniverse=1)
    for item in data.get("data", []):
        for thumb in item.get("thumbnails", []):
            if thumb.get("state") == "Completed" and str(thumb.get("imageUrl", "")).startswith("https://"):
                return thumb["imageUrl"]
    return None


def search(query, limit=30):
    data = _get(SEARCH, searchQuery=query, sessionId=str(uuid.uuid4()), pageType="all")
    games = []
    for group in data.get("searchResults", []):
        if group.get("contentGroupType") == "Game":
            games += [_game(g) for g in group.get("contents", [])]
    return [g for g in games if g][:limit]


def icons(universes):
    """{universeId: image url} for the given games; missing ones are left out."""
    ids = ",".join(str(u) for u in universes if isinstance(u, int))
    if not ids:
        return {}
    data = _get(ICONS, universeIds=ids, size="150x150", format="Png", returnPolicy="PlaceHolder")
    return {item["targetId"]: item["imageUrl"] for item in data.get("data", [])
            if item.get("state") == "Completed" and item.get("imageUrl", "").startswith("https://")}

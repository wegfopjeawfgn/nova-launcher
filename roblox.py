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
USERS = "https://users.roblox.com/v1/usernames/users"
HEADSHOTS = "https://thumbnails.roblox.com/v1/users/avatar-headshot"
GAMES = "https://games.roblox.com/v1/games"
SERVERS = "https://games.roblox.com/v1/games/{place}/servers/Public"
SEARCH = "https://apis.roblox.com/search-api/omni-search"
THUMBS = "https://thumbnails.roblox.com/v1/games/multiget/thumbnails"
ICONS = "https://thumbnails.roblox.com/v1/games/icons"
USER_AGENT = "NovaLauncher"
_PLACE = re.compile(r"^(?:https?://(?:www\.)?roblox\.com/(?:[a-z]{2}/)?games/)?(\d{1,15})(?:[/?#].*)?$", re.I)


def parse_place(text):
    """A place id from a bare number or a roblox.com/games/<id>/... link, else None."""
    found = _PLACE.match((text or "").strip())
    return int(found.group(1)) if found and int(found.group(1)) > 0 else None


def follow_uri(user_id):
    """Roblox's own link to join a player: the client checks, with your session, if you may join them."""
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("Identificador de usuario no válido")
    return f"roblox://experiences/start?userId={user_id}"


_JOB = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def server_uri(place_id, job_id):
    """Link to a game's specific server (its job id). Roblox's client decides whether it still accepts it."""
    if not isinstance(job_id, str) or not _JOB.fullmatch(job_id):
        raise ValueError("Identificador de servidor no válido")
    return f"{place_uri(place_id)}&gameInstanceId={job_id.lower()}"


def join_server(place_id, job_id):
    return _open(server_uri(place_id, job_id))


def game_page(place_id):
    """The game's page on roblox.com, where its Servers tab sells and manages private servers."""
    place_uri(place_id)  # validates the id
    return f"https://www.roblox.com/games/{place_id}"


def servers(place_id, order="Desc", limit=25):
    """Public servers of a game: [{'id', 'playing', 'max', 'ping'}]. order 'Desc' = fullest first, 'Asc' = emptiest."""
    place_uri(place_id)
    data = _get(SERVERS.format(place=place_id), sortOrder="Asc" if order == "Asc" else "Desc", limit=limit)
    found = []
    for item in data.get("data", []):
        if isinstance(item.get("id"), str) and _JOB.fullmatch(item["id"]) and isinstance(item.get("playing"), int):
            found.append({"id": item["id"], "playing": item["playing"],
                          "max": item["maxPlayers"] if isinstance(item.get("maxPlayers"), int) else 0,
                          "ping": round(item["ping"]) if isinstance(item.get("ping"), (int, float)) else None})
    return found


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
    return _open(place_uri(place_id))


def join_friend(user_id):
    return _open(follow_uri(user_id))


def _open(uri):
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


def find_user(name):
    """{'id', 'name', 'display'} for a Roblox username, or None. Public data only."""
    name = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", name):
        return None
    response = requests.post(USERS, json={"usernames": [name], "excludeBannedUsers": True},
                             headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    found = response.json().get("data", [])
    if not found or not isinstance(found[0].get("id"), int):
        return None
    return {"id": found[0]["id"], "name": found[0].get("name", name), "display": found[0].get("displayName", name)}


def headshots(user_ids):
    """{userId: image url} avatar pictures."""
    ids = ",".join(str(u) for u in user_ids if isinstance(u, int))
    if not ids:
        return {}
    data = _get(HEADSHOTS, userIds=ids, size="150x150", format="Png", isCircular="false")
    return {item["targetId"]: item["imageUrl"] for item in data.get("data", [])
            if item.get("state") == "Completed" and str(item.get("imageUrl", "")).startswith("https://")}


def _rating(raw):
    up, down = raw.get("totalUpVotes"), raw.get("totalDownVotes")
    if isinstance(up, int) and isinstance(down, int) and up + down >= 100:
        return round(up * 100 / (up + down))
    return None


def _game(raw):
    place = raw.get("rootPlaceId")
    name = str(raw.get("name") or "").strip()
    if not isinstance(place, int) or place <= 0 or not name:
        return None
    return {"place": place, "universe": raw.get("universeId"), "name": name[:80],
            "players": raw.get("playerCount") if isinstance(raw.get("playerCount"), int) else 0,
            "rating": _rating(raw)}


CATEGORIES = (("top-trending", "Tendencias"), ("top-playing-now", "Más jugados"),
              ("up-and-coming", "Emergentes"), ("fun-with-friends", "En grupo"))


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


def prices(universes):
    """{universeId: Robux} for games you must buy to play. Free games are left out.
    Roblox does not say, without your session, whether you already own it."""
    ids = list(dict.fromkeys(u for u in universes if isinstance(u, int)))
    found = {}
    for start in range(0, len(ids), 50):  # the API refuses long lists
        data = _get(GAMES, universeIds=",".join(map(str, ids[start:start + 50])))
        found.update({item["id"]: item["price"] for item in data.get("data", [])
                      if isinstance(item.get("id"), int) and isinstance(item.get("price"), int) and item["price"] > 0})
    return found

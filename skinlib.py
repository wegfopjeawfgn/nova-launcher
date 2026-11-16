"""Skin helpers without any GTK: the 64x64 layout, old 64x32 skins, mirroring, fill and Mojang lookups."""
import base64
import json
import re
from functools import lru_cache
from urllib.parse import urlparse

import requests

SIZE = 64
OVERLAYS = ((32, 0), (16, 32), (40, 32), (48, 48), (0, 32), (0, 48))
PART_NAMES = ("Cabeza", "Torso", "Brazo derecho", "Brazo izquierdo", "Pierna derecha", "Pierna izquierda")
FACE_NAMES = ("Frente", "Costado izquierdo", "Espalda", "Costado derecho", "Arriba", "Abajo")
# u, v, width, height, depth, x and y of the part in the front view (pixels of the model)
PARTS = (
    (0, 0, 8, 8, 8, -4, 0),
    (16, 16, 8, 12, 4, -4, 8),
    (40, 16, 4, 12, 4, -8, 8),
    (32, 48, 4, 12, 4, 4, 8),
    (0, 16, 4, 12, 4, -4, 20),
    (16, 48, 4, 12, 4, 0, 20),
)
USER_AGENT = "NovaLauncher"
MAX_SKIN_BYTES = 1_000_000


def face(part, side, slim=False, overlay=False):
    """(u, v, w, h) of one face of one part in the 64x64 texture. Sides: 0 front, 1 left, 2 back, 3 right, 4 top, 5 bottom."""
    u, v, w, h, d, _, _ = PARTS[part]
    if overlay:
        u, v = OVERLAYS[part]
    if slim and part in (2, 3):
        w = 3
    return ((u + d, v + d, w, h), (u + d + w, v + d, d, h), (u + 2 * d + w, v + d, w, h),
            (u, v + d, d, h), (u + d, v, w, d), (u + d + w, v, w, d))[side]


@lru_cache(maxsize=2)
def faces(slim):
    """Every paintable face: [(part, side, overlay, (u, v, w, h))]."""
    return tuple((part, side, overlay, face(part, side, slim, overlay))
                 for overlay in (False, True) for part in range(len(PARTS)) for side in range(6))


@lru_cache(maxsize=2)
def _index(slim):
    found = {}
    for part, side, overlay, (u, v, w, h) in faces(slim):
        for y in range(v, v + h):
            for x in range(u, u + w):
                found[(x, y)] = (part, side, overlay, (u, v, w, h))
    return found


def face_at(x, y, slim=False):
    """The face that owns this texel, or None for the unused parts of the sheet."""
    return _index(bool(slim)).get((x, y))


def is_overlay(x, y, slim=False):
    found = face_at(x, y, slim)
    return bool(found and found[2])


def paintable(x, y, slim=False):
    return face_at(x, y, slim) is not None


def mirror_texel(x, y, slim=False):
    """The texel that mirrors this one across the body (left/right), or None."""
    found = face_at(x, y, slim)
    if not found:
        return None
    part, side, overlay, (u, v, w, h) = found
    other_part = {2: 3, 3: 2, 4: 5, 5: 4}.get(part, part)
    other_side = {1: 3, 3: 1}.get(side, side)
    u2, v2, w2, _ = face(other_part, other_side, slim, overlay)
    return u2 + (w2 - 1 - (x - u)), v2 + (y - v)


def blank():
    return bytearray(SIZE * SIZE * 4)


def seed():
    """A plain starting skin so there is something to paint on."""
    pixels = blank()
    palette = ((226, 168, 132), (133, 91, 201), (161, 117, 219), (161, 117, 219), (64, 76, 121), (64, 76, 121))
    for part, rgb in enumerate(palette):
        for side in range(6):
            u, v, w, h = face(part, side)
            for y in range(v, v + h):
                for x in range(u, u + w):
                    pixels[(y * SIZE + x) * 4:(y * SIZE + x) * 4 + 4] = bytes((*rgb, 255))
    for x in (10, 13):
        pixels[(12 * SIZE + x) * 4:(12 * SIZE + x) * 4 + 4] = bytes((53, 37, 65, 255))
    return pixels


# Old skins are 64x32: the left arm and leg did not exist, the game copied the right ones mirrored.
_LEGACY_COPIES = ((4, 16, 16, 32, 4, 4), (8, 16, 16, 32, 4, 4), (0, 20, 24, 32, 4, 12), (4, 20, 16, 32, 4, 12),
                  (8, 20, 8, 32, 4, 12), (12, 20, 16, 32, 4, 12), (44, 16, -8, 32, 4, 4), (48, 16, -8, 32, 4, 4),
                  (40, 20, 0, 32, 4, 12), (44, 20, -8, 32, 4, 12), (48, 20, -16, 32, 4, 12), (52, 20, -8, 32, 4, 12))


def upgrade_legacy(pixels):
    """RGBA bytes of a 64x32 skin -> a 64x64 one with the left arm and leg filled in (mirrored copies)."""
    if len(pixels) != SIZE * 32 * 4:
        raise ValueError("Una skin antigua mide 64 × 32 píxeles.")
    out = blank()
    out[:len(pixels)] = pixels
    for x, y, dx, dy, w, h in _LEGACY_COPIES:
        for j in range(h):
            for i in range(w):
                src = ((y + j) * SIZE + x + i) * 4
                dst = ((y + dy + j) * SIZE + x + dx + (w - 1 - i)) * 4
                out[dst:dst + 4] = out[src:src + 4]
    return out


def flood_fill(pixels, x, y, rgba, slim=False):
    """Fill the touching same-colour texels inside one face. Returns how many changed."""
    found = face_at(x, y, slim)
    if not found:
        return 0
    u, v, w, h = found[3]
    target = bytes(pixels[(y * SIZE + x) * 4:(y * SIZE + x) * 4 + 4])
    rgba = bytes(rgba)
    if target == rgba:
        return 0
    stack, changed = [(x, y)], 0
    while stack:
        cx, cy = stack.pop()
        if not (u <= cx < u + w and v <= cy < v + h):
            continue
        index = (cy * SIZE + cx) * 4
        if bytes(pixels[index:index + 4]) != target:
            continue
        pixels[index:index + 4] = rgba
        changed += 1
        stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
    return changed


def head_icon(pixels):
    """8x8 RGBA bytes of the face (base layer plus hat) for the library thumbnails."""
    out = bytearray(8 * 8 * 4)
    for j in range(8):
        for i in range(8):
            base = ((8 + j) * SIZE + 8 + i) * 4
            hat = ((8 + j) * SIZE + 40 + i) * 4
            pixel = pixels[hat:hat + 4] if pixels[hat + 3] else pixels[base:base + 4]
            out[(j * 8 + i) * 4:(j * 8 + i) * 4 + 4] = pixel
    return bytes(out)


def guess_slim(pixels):
    """Slim (Alex) skins leave the 4th column of both arms empty."""
    right = all(not pixels[(y * SIZE + 47) * 4 + 3] for y in range(20, 32))
    left = all(not pixels[(y * SIZE + 39) * 4 + 3] for y in range(52, 64))
    return right and left


def count_painted(pixels):
    return sum(1 for alpha in pixels[3::4] if alpha)


def base_has_holes(pixels, slim=False):
    """True if some base-layer texel is transparent (the game draws those as black)."""
    for part, side, overlay, (u, v, w, h) in faces(bool(slim)):
        if overlay:
            continue
        for y in range(v, v + h):
            for x in range(u, u + w):
                if not pixels[(y * SIZE + x) * 4 + 3]:
                    return True
    return False


# ---------------------------------------------------------------- Mojang
USERNAME = re.compile(r"[A-Za-z0-9_]{3,16}")


def valid_texture_url(url):
    parsed = urlparse(url if isinstance(url, str) else "")
    # Mojang's profiles still list these as http://; the host is what matters and the download is made over https
    return parsed.scheme in ("http", "https") and parsed.hostname == "textures.minecraft.net" \
        and parsed.path.startswith("/texture/")


def skin_from_profile(profile):
    """(url, slim) from a sessionserver profile; None when the player has the default skin."""
    for item in profile.get("properties", []):
        if item.get("name") != "textures":
            continue
        try:
            data = json.loads(base64.b64decode(item["value"]))
        except (ValueError, KeyError, TypeError):
            return None
        skin = (data.get("textures") or {}).get("SKIN") or {}
        url = skin.get("url")
        if valid_texture_url(url):
            return "https://" + url.split("://", 1)[1], (skin.get("metadata") or {}).get("model") == "slim"
    return None


def _check(reply):
    if reply.status_code == 429:
        raise ValueError("Mojang pidió esperar un poco entre consultas. Probá de nuevo en un minuto.")
    reply.raise_for_status()


def fetch_player_skin(name):
    """Download a player's current skin from Mojang: (png bytes, slim). Raises ValueError with a message for people."""
    if not USERNAME.fullmatch(name or ""):
        raise ValueError("Escribí un nombre de jugador de Minecraft (3 a 16 letras, números o guion bajo).")
    headers = {"User-Agent": USER_AGENT}
    reply = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{name}", headers=headers, timeout=15)
    if reply.status_code in (204, 404):
        raise ValueError(f"No existe el jugador «{name}».")
    _check(reply)
    uuid = reply.json().get("id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", uuid):
        raise ValueError("Mojang no devolvió un jugador válido.")
    profile = requests.get(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}", headers=headers, timeout=15)
    _check(profile)
    found = skin_from_profile(profile.json())
    if not found:
        raise ValueError(f"«{name}» usa la skin por defecto: no hay nada que traer.")
    url, slim = found
    with requests.get(url, headers=headers, timeout=15, stream=True) as download:
        _check(download)
        data = download.raw.read(MAX_SKIN_BYTES + 1, decode_content=True)
    if len(data) > MAX_SKIN_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("La skin descargada no es un PNG válido.")
    return data, slim

"""Plugins de Paper desde Hangar (PaperMC) y SpigotMC (a través de Spiget), para el catálogo de «Mi servidor».

Hangar publica el SHA-256 de cada archivo y Nova lo comprueba. SpigotMC no deja bajar directo y Spiget guarda copias sin hash:
esos archivos se bajan solo desde el CDN de Spiget, se comprueba que sean un .jar y se avisa que no hay suma de verificación.
Los recursos de pago o alojados fuera de SpigotMC no se descargan solos: se ofrece abrir su página.
"""
import re

import requests

import motor
import servidor_local as sl

HANGAR = "https://hangar.papermc.io/api/v1"
HANGAR_FILES = ("https://hangarcdn.papermc.io/",)
SPIGET = "https://api.spiget.org/v2"
SPIGET_FILES = ("https://cdn.spiget.org/", "https://api.spiget.org/")
MAX_PLUGIN = 200 * 1024**2
HANGAR_ID = re.compile(r"[A-Za-z0-9_-]{1,64}/[A-Za-z0-9_.-]{1,64}")


def _json(url, **params):
    response = requests.get(url, params=params, headers={"User-Agent": sl.USER_AGENT}, timeout=20)
    response.raise_for_status()
    return response.json()


def _record(base, key, title, name, version):
    records = sl.catalog_installed(base)
    records[key] = {"title": title or name, "file": name, "version": version}
    motor.save(sl._catalog_path(base), records)


def _safe_name(text, suffix):
    stem = re.sub(r"[^A-Za-z0-9._+() -]+", "-", text).strip(" .-")[:90] or "plugin"
    name = f"{stem}{suffix}"
    if not sl.FILE_RE.fullmatch(name):
        raise ValueError("Nombre de archivo no válido.")
    return name


# ------------------------------------------------------------------ Hangar
def hangar_search(meta, query="", offset=0, limit=20):
    data = _json(f"{HANGAR}/projects", platform="PAPER", version=meta["version"], q=query.strip()[:80], limit=limit, offset=offset,
                 sort="-downloads" if not query.strip() else None)
    hits = []
    for item in data.get("result", []):
        space = item.get("namespace") or {}
        ident = f"{space.get('owner', '')}/{space.get('slug', '')}"
        if HANGAR_ID.fullmatch(ident):
            hits.append({"project_id": "hangar:" + ident, "title": item.get("name", ident), "description": item.get("description", ""),
                         "downloads": (item.get("stats") or {}).get("downloads", 0), "author": space.get("owner", ""), "source": "hangar"})
    total = (data.get("pagination") or {}).get("count", len(hits))
    return {"hits": hits, "total": total, "next": offset + len(data.get("result", [])), "more": offset + len(data.get("result", [])) < total}


def hangar_install(base, meta, ident, *, title="", progress=None):
    """Install the newest release of a Hangar plugin for this Minecraft version, with its SHA-256 checked."""
    if not HANGAR_ID.fullmatch(ident or ""):
        raise ValueError("Proyecto no válido.")
    owner, slug = ident.split("/")
    versions = _json(f"{HANGAR}/projects/{slug}/versions", platform="PAPER", platformVersion=meta["version"], limit=10).get("result", [])
    release = next((item for item in versions if (item.get("channel") or {}).get("name") == "Release"), versions[0] if versions else None)
    if release is None:
        raise ValueError("Ese plugin no tiene una versión para este servidor.")
    download = (release.get("downloads") or {}).get("PAPER") or {}
    info = download.get("fileInfo") or {}
    if not download.get("downloadUrl"):
        raise ValueError(f"Este plugin se descarga desde su sitio: {download.get('externalUrl') or 'https://hangar.papermc.io/' + ident}")
    name, digest = info.get("name", ""), info.get("sha256Hash", "")
    if (not str(download["downloadUrl"]).startswith(HANGAR_FILES) or not sl.FILE_RE.fullmatch(name)
            or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(info.get("sizeBytes"), int) or not 0 < info["sizeBytes"] <= MAX_PLUGIN):
        raise ValueError("Hangar devolvió datos inesperados para la descarga.")
    destination = base / sl.UPLOAD_DIRS[meta["kind"]]
    destination.mkdir(exist_ok=True)
    target = destination / name
    installed = []
    if not target.exists():
        sl.download(download["downloadUrl"], target, size=info["sizeBytes"], algo="sha256", digest=digest, progress=progress,
                    allowed=HANGAR_FILES, magic=b"PK")
        installed.append(name)
    _record(base, "hangar:" + ident, title, name, release.get("name", ""))
    return installed


# ------------------------------------------------------------------ SpigotMC (Spiget)
def _tested(version, listed):
    """Whether a Spigot resource lists this Minecraft version (or its major.minor family, like 1.21 for 1.21.11) as tested."""
    parts = version.split(".")
    family = ".".join(parts[:2])
    return any(entry in (version, family) for entry in listed or [])


def spigot_search(meta, query="", offset=0, limit=20):
    """Spiget cannot filter by version, so each page is filtered here; ``next`` moves on by whole pages."""
    size, page = 50, offset // 50
    fields = "id,name,tag,testedVersions,downloads,premium,file"
    if query.strip():
        raw = _json(f"{SPIGET}/search/resources/{requests.utils.quote(query.strip()[:80], safe='')}", field="name", size=size, page=page,
                    sort="-downloads", fields=fields)
    else:
        raw = _json(f"{SPIGET}/resources", size=size, page=page, sort="-downloads", fields=fields)
    hits = []
    for item in raw if isinstance(raw, list) else []:
        if item.get("premium") or not _tested(meta["version"], item.get("testedVersions")) or not isinstance(item.get("id"), int):
            continue
        file = item.get("file") or {}
        hit = {"project_id": f"spigot:{item['id']}", "title": item.get("name", ""), "description": item.get("tag", ""),
               "downloads": item.get("downloads", 0), "author": "", "source": "spigot"}
        if file.get("type") != ".jar":   # hosted elsewhere (GitHub, a website…): the person has to get it from there
            hit["external_url"] = file.get("externalUrl") or f"https://www.spigotmc.org/resources/{item['id']}/"
        hits.append(hit)
    full_page = isinstance(raw, list) and len(raw) == size
    return {"hits": hits[:limit], "total": None, "next": (page + 1) * size, "more": full_page}


def spigot_install(base, meta, ident, *, title="", progress=None):
    """Install a plugin hosted on SpigotMC. There is no hash to check: the origin, the size and the file type are."""
    if not re.fullmatch(r"[0-9]{1,9}", ident or ""):
        raise ValueError("Proyecto no válido.")
    info = _json(f"{SPIGET}/resources/{ident}")
    file = info.get("file") or {}
    if info.get("premium") or file.get("type") != ".jar":
        raise ValueError("Este plugin es de pago o se descarga desde otro sitio: abrí su página para bajarlo.")
    if not _tested(meta["version"], info.get("testedVersions")):
        raise ValueError("Este plugin no figura como probado para la versión de este servidor.")
    name = _safe_name(f"{info.get('name', 'plugin')}-spigot-{ident}", ".jar")
    destination = base / sl.UPLOAD_DIRS[meta["kind"]]
    destination.mkdir(exist_ok=True)
    target = destination / name
    installed = []
    if not target.exists():
        sl.download(f"{SPIGET}/resources/{ident}/download", target, progress=progress, allowed=SPIGET_FILES, magic=b"PK")
        installed.append(name)
    _record(base, "spigot:" + ident, title or info.get("name", ""), name, "")
    return installed

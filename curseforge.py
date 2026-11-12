"""Minimal client for the official CurseForge API (never scrapes the website).

The API key is supplied by the caller, sent only in the ``x-api-key`` header and
never stored, logged or included in exceptions.
"""
import json
import re
from urllib.parse import urlsplit

import requests

import catalogo
import motor

API = "https://api.curseforge.com/v1"
GAME_ID = 432  # Minecraft
MAX_RESPONSE = 2 * 1024 * 1024
MAX_PAGE_SIZE = 50
LOADERS = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
SHA1_RE = re.compile(r"[0-9a-fA-F]{40}")


class CurseForgeError(Exception):
    pass


def api_key_ok(key):
    return (isinstance(key, str) and 20 <= len(key) <= 200
            and not any(c.isspace() for c in key))


def _get(api_key, path, params, timeout):
    if not api_key_ok(api_key):
        raise CurseForgeError("La clave de API de CurseForge no es válida o no tiene permiso.")
    generic = CurseForgeError("No se pudo consultar CurseForge, probá más tarde.")
    try:
        with requests.get(API + path, params=params, timeout=timeout, stream=True,
                          headers={"x-api-key": api_key, "Accept": "application/json",
                                   "User-Agent": motor.USER_AGENT}) as response:
            status = response.status_code
            if status in (401, 403):
                raise CurseForgeError(
                    "La clave de API de CurseForge no es válida o no tiene permiso.")
            if status == 429:
                raise CurseForgeError("CurseForge limitó las consultas, probá más tarde.")
            if status >= 400:
                raise generic
            body = b""
            for chunk in response.iter_content(64 * 1024):
                body += chunk
                if len(body) > MAX_RESPONSE:
                    raise generic
        payload = json.loads(body.decode("utf-8"))
    except CurseForgeError:
        raise
    except (requests.RequestException, ValueError):
        raise generic from None  # no `from error`: keep URL/headers out of the chain
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CurseForgeError("CurseForge devolvió una respuesta inesperada.")
    return payload


def _normalize_file(item):
    if not isinstance(item, dict):
        return None
    versions = item.get("gameVersions")
    url = item.get("downloadUrl")
    hashes = item.get("hashes")
    sha1 = None
    for entry in hashes if isinstance(hashes, list) else []:
        if isinstance(entry, dict) and entry.get("algo") == 1 and isinstance(entry.get("value"), str):
            sha1 = entry["value"]
            break
    size = item.get("fileLength")
    return {"file_id": item.get("id"),
            "game_versions": [v for v in versions if isinstance(v, str)]
            if isinstance(versions, list) else [],
            "download_url": url if isinstance(url, str) else None,
            "sha1": sha1,
            "size": size if isinstance(size, int) and not isinstance(size, bool) else 0,
            "file_name": item.get("fileName") if isinstance(item.get("fileName"), str) else ""}


def _normalize_mod(item):
    if not isinstance(item, dict) or not isinstance(item.get("id"), int):
        return None
    links = item.get("links") if isinstance(item.get("links"), dict) else {}
    site = links.get("websiteUrl")
    logo = item.get("logo") if isinstance(item.get("logo"), dict) else {}
    thumb = logo.get("thumbnailUrl")
    authors = item.get("authors")
    author = ""
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        author = str(authors[0].get("name") or "")
    # latestFiles carries downloadUrl/hashes/size; latestFilesIndexes only has ids.
    latest = [f for f in map(_normalize_file, item.get("latestFiles") or []) if f]
    downloads = item.get("downloadCount")
    return {"id": item["id"], "name": str(item.get("name") or ""),
            "summary": str(item.get("summary") or ""),
            "downloads": int(downloads) if isinstance(downloads, (int, float)) else 0,
            "author": author,
            "url": site if isinstance(site, str)
            and site.startswith("https://www.curseforge.com/") else "",
            "logo": thumb if isinstance(thumb, str) and thumb.startswith("https://") else "",
            "latest": latest}


def search(api_key, query, *, game_version=None, loader=None, class_id=6, index=0,
           page_size=20, timeout=15):
    params = {"gameId": GAME_ID, "classId": class_id, "searchFilter": query,
              "sortField": 2, "sortOrder": "desc", "index": max(0, int(index)),
              "pageSize": max(1, min(int(page_size), MAX_PAGE_SIZE))}
    if game_version:
        params["gameVersion"] = game_version
    if loader in LOADERS:
        params["modLoaderType"] = LOADERS[loader]
    payload = _get(api_key, "/mods/search", params, timeout)
    results = [m for m in map(_normalize_mod, payload["data"]) if m]
    pagination = payload.get("pagination")
    total = pagination.get("totalCount") if isinstance(pagination, dict) else None
    return {"results": results, "total": total if isinstance(total, int) else len(results)}


def latest_file(api_key, mod_id, *, game_version, loader, timeout=15):
    params = {"gameVersion": game_version, "pageSize": MAX_PAGE_SIZE}
    if loader in LOADERS:
        params["modLoaderType"] = LOADERS[loader]
    payload = _get(api_key, f"/mods/{int(mod_id)}/files", params, timeout)
    files = [f for f in payload["data"] if isinstance(f, dict) and f.get("isAvailable") is True]
    if not files:
        return None
    newest = max(files, key=lambda f: str(f.get("fileDate") or ""))  # ISO-8601 sorts as text
    return _normalize_file(newest)


def safe_download(file_info):
    try:
        url = file_info.get("download_url")
        parsed = urlsplit(url)
        sha1 = file_info.get("sha1")
        size = file_info.get("size")
        return (parsed.scheme == "https" and parsed.netloc in catalogo.CURSEFORGE_CDN
                and isinstance(sha1, str) and SHA1_RE.fullmatch(sha1) is not None
                and isinstance(size, int) and not isinstance(size, bool) and size > 0)
    except (AttributeError, TypeError, ValueError):
        return False

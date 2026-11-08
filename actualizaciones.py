"""Read the stable release channel without installing anything automatically."""
import hashlib
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import requests

VERSION = "1.0.0"
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")


def repository(value):
    value = value.strip().removeprefix("https://github.com/").rstrip("/")
    if value and (not REPO.fullmatch(value) or value.split("/")[1] in {".", ".."}):
        raise ValueError("Ingresá el repositorio público en formato usuario/repositorio.")
    return value


def numeric_version(tag):
    match = re.fullmatch(r"v?(\d{1,6})\.(\d{1,6})(?:\.(\d{1,6}))?", tag)
    return tuple(int(piece or 0) for piece in match.groups()) if match else None


def check(repo):
    repo = repository(repo)
    if not repo:
        raise ValueError("Configurá tu repositorio público de GitHub en Ajustes.")
    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"NovaLauncher/{VERSION}"},
        timeout=12,
    )
    if response.status_code == 404:
        raise ValueError("GitHub no encontró una versión estable pública para este repositorio.")
    response.raise_for_status()
    release = response.json()
    tag = release["tag_name"]
    remote = numeric_version(tag)
    if remote is None:
        raise ValueError("La versión de GitHub debe usar una etiqueta como v0.9.1.")
    if release.get("draft") or release.get("prerelease") or remote <= numeric_version(VERSION):
        return None
    page = f"https://github.com/{repo}/releases/tag/{tag}"
    prefix = f"https://github.com/{repo}/releases/download/{tag}/"
    rpm = next((asset["browser_download_url"] for asset in release.get("assets", [])
                if asset["name"].lower().endswith(".noarch.rpm")
                and asset["browser_download_url"].lower().startswith(prefix.lower())), None)
    return tag, rpm, page, (release.get("body") or "")[:4000]


def download(url, destination):
    if destination.suffix.lower() != ".rpm":
        raise ValueError("Guardá la actualización con extensión .rpm.")
    with TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / "update.rpm"
        with requests.get(url, timeout=30, stream=True) as response:
            response.raise_for_status()
            size = 0
            with staged.open("wb") as output:
                for chunk in response.iter_content(128 * 1024):
                    size += len(chunk)
                    if size > 128 * 1024**2:
                        raise ValueError("El RPM supera los 128 MiB.")
                    output.write(chunk)
        with staged.open("rb") as source:
            if source.read(4) != bytes.fromhex("edabeedb"):
                raise ValueError("La descarga no es un paquete RPM.")
            source.seek(0)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        # The checksum asset is published with every official Nova RPM.
        with requests.get(url + ".sha256", timeout=15, stream=True) as response:
            response.raise_for_status()
            expected = response.raw.read(256, decode_content=True).split()
        if not expected or expected[0] != digest.encode("ascii"):
            raise ValueError("El SHA-256 del RPM no coincide con el publicado.")
        staged.replace(destination)

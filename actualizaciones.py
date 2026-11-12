"""Read the stable release channel without installing anything automatically."""
import hashlib
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import requests

import seguridad
from nova_version import NOVA_VERSION as VERSION
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}")


def repository(value):
    value = value.strip().removeprefix("https://github.com/").rstrip("/")
    if value and (not REPO.fullmatch(value) or value.split("/")[1] in {".", ".."}):
        raise ValueError("Ingresá el repositorio público en formato usuario/repositorio.")
    return value


def numeric_version(tag):
    match = re.fullmatch(r"v?(\d{1,6})\.(\d{1,6})(?:\.(\d{1,6}))?", tag)
    return tuple(int(piece or 0) for piece in match.groups()) if match else None


def newest(releases, beta):
    candidates = [(numeric_version(r.get("tag_name", "")), r) for r in releases
                  if not r.get("draft") and (beta or not r.get("prerelease"))
                  and numeric_version(r.get("tag_name", ""))]
    return max(candidates, key=lambda item: item[0], default=(None, None))


def check(repo, beta=False):
    repo = repository(repo)
    if not repo:
        raise ValueError("Configurá tu repositorio público de GitHub en Ajustes.")
    response = requests.get(
        f"https://api.github.com/repos/{repo}/releases",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"NovaLauncher/{VERSION}"},
        params={"per_page": 20},
        timeout=12,
    )
    if response.status_code == 404:
        raise ValueError("GitHub no encontró versiones públicas para este repositorio.")
    response.raise_for_status()
    remote, release = newest(response.json(), beta)
    if release is None:
        raise ValueError("No hay versiones con una etiqueta como v0.9.1.")
    if remote <= numeric_version(VERSION):
        return None
    tag = release["tag_name"]
    page = f"https://github.com/{repo}/releases/tag/{tag}"
    prefix = f"https://github.com/{repo}/releases/download/{tag}/"
    suffix = "-windows-x64-setup.exe" if os.name == "nt" else ".noarch.rpm"
    rpm = next((asset["browser_download_url"] for asset in release.get("assets", [])
                if asset["name"].lower().endswith(suffix)
                and asset["browser_download_url"].lower().startswith(prefix.lower())), None)
    return tag, rpm, page, (release.get("body") or "")[:4000]


def download(url, destination, *, progress=lambda _: None):
    if not seguridad.safe_update_url(url):
        raise ValueError("La actualización debe descargarse desde una release de GitHub por HTTPS.")
    extension = ".exe" if os.name == "nt" else ".rpm"
    if destination.suffix.lower() != extension:
        raise ValueError(f"Guardá la actualización con extensión {extension}.")
    maximum = (512 if os.name == "nt" else 128) * 1024**2
    signature = b"MZ" if os.name == "nt" else bytes.fromhex("edabeedb")
    with TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / ("update" + extension)
        with requests.get(url, timeout=30, stream=True) as response:
            response.raise_for_status()
            size = 0
            reported = -1
            with staged.open("wb") as output:
                for chunk in response.iter_content(128 * 1024):
                    size += len(chunk)
                    if size > maximum:
                        raise ValueError("El instalador supera el tamaño permitido.")
                    output.write(chunk)
                    mib = size // (1024**2)
                    if mib != reported:
                        progress(f"Descargando actualización · {size / 1024**2:.1f} MiB")
                        reported = mib
        with staged.open("rb") as source:
            if source.read(len(signature)) != signature:
                raise ValueError("La descarga no es un instalador válido.")
            source.seek(0)
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        # The checksum asset is published with every official Nova RPM.
        with requests.get(url + ".sha256", timeout=15, stream=True) as response:
            response.raise_for_status()
            expected = response.raw.read(256, decode_content=True).split()
        if not expected or expected[0] != digest.encode("ascii"):
            raise ValueError("El SHA-256 del instalador no coincide con el publicado.")
        progress("Guardando el instalador verificado…")
        staged.replace(destination)

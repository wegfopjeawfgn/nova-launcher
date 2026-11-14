"""Pomme: an unofficial Minecraft Java client written in Rust, installed from its own GitHub releases.

Nova only downloads the release asset GitHub lists for this system, checks its size and the SHA-256 GitHub reports,
and opens it. It never signs in for the player: Pomme has its own Microsoft login.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile

import requests

import motor

REPO = "PommeMC/Client"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
MAX_BYTES = 200 * 1024 * 1024
# release asset -> file that ends up on disk
ASSETS = {"linux": ("pomme-client-linux-x64-gnu.AppImage", "pomme.AppImage"),
          "windows": ("pomme-client-windows-x64.zip", "pomme-client.exe")}


def supported():
    """``(asset_name, file_name)`` for this system, or ``None`` (Pomme ships x64 for Linux and Windows)."""
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        return None
    if os.name == "nt":
        return ASSETS["windows"]
    return ASSETS["linux"] if sys.platform.startswith("linux") else None


def folder():
    return motor.ROOT / "clients" / "pomme"


def release(asset_name):
    """The newest release and its asset for this system, checked before anything is downloaded."""
    response = requests.get(API, timeout=15, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": motor.USER_AGENT})
    response.raise_for_status()
    data = response.json()
    tag = data.get("tag_name")
    if data.get("draft") or data.get("prerelease") or not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,40}", tag):
        raise ValueError("GitHub no devolvió una versión estable de Pomme.")
    asset = next((item for item in data.get("assets", []) if item.get("name") == asset_name), None)
    if asset is None:
        raise ValueError("Esta versión de Pomme no incluye el archivo para tu sistema.")
    url, size, digest = asset.get("browser_download_url"), asset.get("size"), asset.get("digest")
    if (not isinstance(url, str) or not url.startswith(DOWNLOAD_PREFIX) or not url.endswith("/" + asset_name)
            or not isinstance(size, int) or not 0 < size <= MAX_BYTES
            or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
        raise ValueError("GitHub devolvió datos inesperados para la descarga de Pomme.")
    return {"tag": tag, "url": url, "size": size, "sha256": digest[7:]}


def installed():
    """``{"tag", "exe"}`` when Pomme is installed and its file is still there, else ``None``."""
    try:
        data = json.loads((folder() / "installed.json").read_text(encoding="utf-8"))
        tag, name = data["tag"], data["exe"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    exe = folder() / name if isinstance(name, str) else None
    if not isinstance(tag, str) or name not in {entry[1] for entry in ASSETS.values()} or not exe.is_file():
        return None
    return {"tag": tag, "exe": exe}


def _download(url, target, size, progress):
    digest, done = hashlib.sha256(), 0
    with requests.get(url, stream=True, timeout=30, headers={"User-Agent": motor.USER_AGENT}) as response:
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_content(1 << 20):
                done += len(chunk)
                if done > size:
                    raise ValueError("La descarga es más grande de lo que informó GitHub.")
                digest.update(chunk)
                output.write(chunk)
                if progress:
                    progress(done, size)
    if done != size:
        raise ValueError("La descarga quedó incompleta.")
    return digest.hexdigest()


def install(progress=None):
    """Download, verify and install the newest Pomme. A failed install leaves the previous one untouched."""
    asset = supported()
    if asset is None:
        raise ValueError("Pomme todavía no tiene versión para este sistema.")
    info = release(asset[0])
    root = motor.ROOT / "clients"
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=root, prefix=".pomme-"))
    try:
        archive = work / "download"
        if _download(info["url"], archive, info["size"], progress) != info["sha256"]:
            raise ValueError("La suma SHA-256 no coincide con la que publica GitHub. Se descartó la descarga.")
        staged = work / "pomme"
        staged.mkdir()
        exe = staged / asset[1]
        if asset[0].endswith(".zip"):
            with zipfile.ZipFile(archive) as package:
                if package.namelist() != [asset[1]]:
                    raise ValueError("El paquete de Pomme tiene un contenido inesperado.")
                with package.open(asset[1]) as source, exe.open("wb") as output:
                    shutil.copyfileobj(source, output)
        else:
            archive.replace(exe)
        exe.chmod(0o755)
        (staged / "installed.json").write_text(json.dumps({"tag": info["tag"], "exe": asset[1]}), encoding="utf-8")
        target, previous = folder(), None
        if target.exists():
            previous = root / f".pomme-old-{uuid.uuid4().hex[:8]}"
            target.rename(previous)
        try:
            staged.rename(target)
        except OSError:
            if previous is not None:
                previous.rename(target)
            raise
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return installed()


def launch(info, instance_folder):
    """Open Pomme. Its output goes to ``pomme.log`` in the instance folder; the caller waits on the process."""
    env = dict(os.environ)
    if os.name != "nt":
        env["APPIMAGE_EXTRACT_AND_RUN"] = "1"  # works without FUSE
    home = folder() / "home"
    home.mkdir(parents=True, exist_ok=True)
    with (instance_folder / "pomme.log").open("wb") as log:
        return subprocess.Popen([str(info["exe"])], cwd=home, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=os.name != "nt")

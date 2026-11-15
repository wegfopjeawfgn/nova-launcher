"""Java completo propio de Nova (Eclipse Temurin), para lo que no anda con el Java recortado de Mojang, como el instalador de Forge.

Se baja desde la API de Adoptium (los binarios están en GitHub), se comprueba el SHA-256 que publican, se extrae sin salirse de la
carpeta de destino y queda en ``java/temurin-<versión>`` dentro de los datos de Nova. Nunca toca el Java del sistema.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import uuid
import zipfile

import requests

import motor

API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"
LTS = (8, 11, 17, 21, 25)
DOWNLOAD_PREFIXES = ("https://github.com/adoptium/",)
MAX_BYTES = 400 * 1024**2


def folder():
    return motor.ROOT / "java"


def platform_names():
    """``(os, architecture)`` as Adoptium names them, or None where Nova has no build to offer."""
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "aarch64", "arm64": "aarch64"}.get(machine)
    system = "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else None
    if arch is None or system is None or (system == "windows" and arch != "x64"):
        return None
    return system, arch


def pick_major(required):
    """The smallest long-term-support Java that is at least ``required``."""
    try:
        required = int(required or 8)
    except (TypeError, ValueError):
        required = 8
    fitting = [major for major in LTS if major >= required]
    if not fitting:
        raise ValueError(f"No hay un Java para la versión {required} o más nueva.")
    return fitting[0]


def _exe():
    return "java.exe" if os.name == "nt" else "java"


def installed_path(major):
    path = folder() / f"temurin-{major}" / "bin" / _exe()
    return path if path.is_file() else None


def installed(required):
    """Path of the lowest own Java that is at least ``required``, or None."""
    for major in LTS:
        if major >= int(required or 8) and (path := installed_path(major)):
            return str(path)
    return None


def release(major):
    """``{"link", "size", "sha256", "name"}`` of the newest Temurin JRE for this system, checked before downloading."""
    names = platform_names()
    if names is None:
        raise ValueError("Nova todavía no puede bajar un Java propio para este sistema.")
    response = requests.get(API.format(major=major), timeout=20, headers={"User-Agent": motor.USER_AGENT},
                            params={"architecture": names[1], "image_type": "jre", "os": names[0], "vendor": "eclipse"})
    response.raise_for_status()
    data = response.json()
    package = (data[0].get("binary") or {}).get("package") if isinstance(data, list) and data else None
    if not isinstance(package, dict):
        raise ValueError("Adoptium no devolvió un Java para este sistema.")
    link, size, checksum, name = package.get("link"), package.get("size"), package.get("checksum"), package.get("name")
    expected = ".zip" if names[0] == "windows" else ".tar.gz"
    if (not isinstance(link, str) or not link.startswith(DOWNLOAD_PREFIXES) or not isinstance(name, str) or not name.endswith(expected)
            or not isinstance(size, int) or not 0 < size <= MAX_BYTES or not isinstance(checksum, str)
            or not re.fullmatch(r"[0-9a-f]{64}", checksum)):
        raise ValueError("Adoptium devolvió datos inesperados para la descarga de Java.")
    return {"link": link, "size": size, "sha256": checksum, "name": name}


def _download(info, target, progress=None):
    hasher, done = hashlib.sha256(), 0
    with requests.get(info["link"], stream=True, timeout=30, headers={"User-Agent": motor.USER_AGENT}) as response:
        response.raise_for_status()
        if not response.url.startswith(("https://github.com/", "https://objects.githubusercontent.com/", "https://release-assets.githubusercontent.com/")):
            raise ValueError("La descarga de Java se redirigió a un lugar inesperado.")
        with target.open("wb") as output:
            for chunk in response.iter_content(1 << 20):
                done += len(chunk)
                if done > info["size"]:
                    raise ValueError("La descarga es más grande de lo que informó Adoptium.")
                hasher.update(chunk)
                output.write(chunk)
                if progress:
                    progress(done, info["size"])
    if done != info["size"]:
        raise ValueError("La descarga de Java quedó incompleta.")
    if hasher.hexdigest() != info["sha256"]:
        raise ValueError("La suma SHA-256 de Java no coincide con la que publica Adoptium. Se descartó la descarga.")


def _inside(base, name):
    parts = [part for part in name.replace("\\", "/").split("/") if part not in ("", ".")]
    if not parts or ".." in parts or name.startswith(("/", "\\")) or ":" in parts[0]:
        raise ValueError("El archivo de Java tiene rutas no válidas.")
    return base.joinpath(*parts)


def extract(archive, destination):
    """Unpack a ``.zip`` or ``.tar.gz`` into ``destination``; nothing can land outside it."""
    base = destination.resolve()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                target = _inside(base, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        return
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            target = _inside(base, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o755 | 0o600)
            elif member.issym():
                link = (target.parent / member.linkname).resolve()
                if base not in link.parents and link != base:
                    raise ValueError("El archivo de Java tiene un enlace que sale de su carpeta.")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() and not target.is_symlink():
                    target.symlink_to(member.linkname)
            else:
                raise ValueError("El archivo de Java tiene un contenido inesperado.")


def install(required, progress=None):
    """Download and unpack Temurin for at least Java ``required``. Returns the path of its ``java`` program."""
    major = pick_major(required)
    if (path := installed_path(major)):
        return str(path)
    info = release(major)
    root = folder()
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=root, prefix=".java-"))
    try:
        archive = work / info["name"]
        _download(info, archive, progress)
        staged = work / "unpacked"
        staged.mkdir()
        extract(archive, staged)
        children = [child for child in staged.iterdir()]
        home = children[0] if len(children) == 1 and children[0].is_dir() else staged
        target = root / f"temurin-{major}"
        if target.exists():
            shutil.rmtree(target)
        home.rename(target)
        if not (target / "bin" / _exe()).is_file():
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError("El Java descargado no trae el programa java.")
        (target / "nova-java.json").write_text(json.dumps({"major": major, "source": info["link"], "id": uuid.uuid4().hex[:8]}), encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(target / "bin" / _exe())

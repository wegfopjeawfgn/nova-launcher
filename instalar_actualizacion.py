"""Apply an update that Nova already downloaded and checked, in one click and without a terminal.
Nothing here downloads: `actualizaciones.download` verifies the SHA-256 against the release, and this module
records that and re-checks it right before installing, so a file swapped in between is refused."""
import hashlib
import json
import os
import re
import subprocess

import motor

UPDATES = motor.ROOT / "updates"
NAME = re.compile(r"nova-launcher-\d{1,4}\.\d{1,4}\.\d{1,4}(?:-1\.noarch\.rpm|-windows-x64-setup\.exe)")
DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def staged_path(url):
    """Where an update from this release URL is kept; refuses names Nova never publishes."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if not NAME.fullmatch(name):
        raise ValueError("Nombre de instalador no reconocido.")
    return UPDATES / name


def _marker(path):
    return path.with_name(path.name + ".ok")


def _digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def mark_verified(path, tag):
    _marker(path).write_text(json.dumps({"sha256": _digest(path), "tag": tag}), encoding="utf-8")


def is_verified(path):
    """True only for a file Nova verified, unchanged since."""
    try:
        if not NAME.fullmatch(path.name) or not path.is_file():
            return False
        saved = json.loads(_marker(path).read_text(encoding="utf-8"))
        return isinstance(saved.get("sha256"), str) and saved["sha256"] == _digest(path)
    except (OSError, ValueError):
        return False


def install_argv(path, windows=None):
    windows = (os.name == "nt") if windows is None else windows
    if windows:  # per-user installer: no administrator rights; /RELAUNCH=1 opens Nova again when it ends
        return [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"]
    return ["pkexec", "dnf", "install", "-y", str(path)]


def apply(path):
    """Windows: start the installer detached (the caller then quits Nova). Fedora: run it and return the result."""
    if not is_verified(path):
        raise ValueError("El instalador no está verificado. Descargalo de nuevo.")
    argv = install_argv(path)
    if os.name == "nt":
        subprocess.Popen(argv, creationflags=DETACHED, close_fds=True)
        return None
    return subprocess.run(argv, capture_output=True, text=True, timeout=900)


def relaunch():
    """Open a fresh Nova (Fedora, after the RPM was installed)."""
    subprocess.Popen(["nova-launcher"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def clean(keep=None):
    """Delete older downloaded installers and their markers."""
    if not UPDATES.is_dir():
        return
    for item in UPDATES.iterdir():
        if keep is not None and item.name in (keep.name, keep.name + ".ok"):
            continue
        try:
            item.unlink()
        except OSError:
            pass


def failure_text(result):
    """A short, human message for a failed `pkexec dnf install`."""
    if result.returncode in (126, 127) and "dnf" not in (result.stderr or ""):
        return "Se canceló o no se autorizó la instalación."
    tail = [line for line in (result.stderr or result.stdout or "").strip().splitlines() if line.strip()][-2:]
    return "No se pudo instalar: " + (" ".join(tail) if tail else f"código {result.returncode}")

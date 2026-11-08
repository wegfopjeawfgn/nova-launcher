"""Persist isolated instances and start Minecraft on Linux."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import requests

VERSION = "1.21.4"
ROOT = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "nova-launcher"
LOADERS = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge",
           "neoforge": "NeoForge", "quilt": "Quilt"}
DEFAULTS = {"version": VERSION, "loader": "vanilla", "loader_version": "", "java": ""}
USER_AGENT = "NovaLauncher/0.9.4 (desktop Minecraft launcher)"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def read(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def versions():
    cache = ROOT / "versions.json"
    try:
        response = requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
                                timeout=12)
        response.raise_for_status()
        entries = response.json()["versions"]
    except requests.RequestException:
        return read(cache, [{"id": VERSION, "type": "release"}])
    save(cache, entries)
    return entries


def create(name, memory, artwork, **settings):
    folder = ROOT / "instances" / uuid.uuid4().hex
    save(folder / "instance.json", {**DEFAULTS, **settings, "name": name,
                                    "memory": memory, "artwork": artwork})
    return folder


@contextmanager
def instance_lock(folder):
    with (folder / ".nova.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("La instancia está abierta o tiene una descarga en curso.") from None
        yield lock


def prepare(instance, status):
    from minecraft_launcher_lib import command, install, mod_loader

    version = instance["version"]
    loader_id = instance["loader"]
    requested = instance["loader_version"]
    shared = ROOT / "minecraft"
    shared.mkdir(exist_ok=True)
    cache = shared / "nova-installations.json"
    key = json.dumps([version, loader_id, requested])
    with (shared / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        installed = read(cache, {})
        launch_id = installed.get(key)
        if loader_id == "vanilla" and (shared / f".ready-{version}").exists():
            launch_id = version
        if launch_id and (shared / "versions" / launch_id / f"{launch_id}.json").is_file():
            return shared, launch_id
        status(f"Instalando {version} · {LOADERS[loader_id]}…")
        if loader_id == "vanilla":
            install.install_minecraft_version(version, str(shared))
            launch_id = version
        else:
            loader = mod_loader.get_mod_loader(loader_id)
            if not loader.is_minecraft_version_supported(version):
                raise ValueError(f"{LOADERS[loader_id]} no ofrece soporte para Minecraft {version}.")
            install.install_minecraft_version(version, str(shared))
            java = instance["java"] or command.get_minecraft_command(version, str(shared), {
                "username": "Nova", "uuid": "0", "token": "0",
            })[0]
            launch_id = loader.install(version, str(shared), loader_version=requested or None, java=java)
        installed[key] = launch_id
        save(cache, installed)
        return shared, launch_id


def launch(folder, profile, instance, status, session=None, *, on_started=None, detach=False):
    from minecraft_launcher_lib import command

    if not session and not re.fullmatch(r"[A-Za-z0-9_]{3,16}", profile):
        raise ValueError("Elegí un nombre offline de 3 a 16 letras, números o guiones bajos.")
    game = folder / "game"
    game.mkdir(exist_ok=True)
    with instance_lock(folder) as lock:
        shared, launch_id = prepare(instance, status)
        player_id = uuid.UUID(bytes=hashlib.md5(
            f"OfflinePlayer:{profile}".encode(), usedforsecurity=False
        ).digest(), version=3)
        options = {
            "username": profile, "uuid": player_id.hex, "token": "0",
            "gameDirectory": str(game), "launcherName": "Nova Launcher",
            "launcherVersion": "0.9.4", "jvmArguments": [f"-Xmx{instance['memory']}G"],
        }
        if (instance["version"] == "1.21.11" and instance["loader"] == "fabric"
                and read(folder / "nova-loading.json", {}).get("logo")):
            logo_agent = Path(__file__).resolve().parent / "branding" / "nova-loading.jar"
            options["jvmArguments"].append(f"-javaagent:{logo_agent}")
        resolution = instance.get("resolution", "")
        if re.fullmatch(r"[0-9]{3,4}x[0-9]{3,4}", resolution):
            width, height = resolution.split("x")
            options.update(customResolution=True, resolutionWidth=width, resolutionHeight=height)
        if session:
            options.update(username=session["name"], uuid=session["id"], token=session["access_token"])
        if instance["java"]:
            options["executablePath"] = instance["java"]
        args = command.get_minecraft_command(launch_id, str(shared), options)
        with (folder / "minecraft.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(args, cwd=game, stdout=log, stderr=subprocess.STDOUT,
                                       pass_fds=(lock.fileno(),), start_new_session=detach)
            status("Minecraft abierto · " + profile)
            if on_started:
                try:
                    return process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    on_started()
            return process.wait()

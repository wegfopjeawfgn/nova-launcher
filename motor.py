"""Persist isolated instances and start Minecraft on Linux."""
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import uuid

import requests

import servidores
from nova_version import NOVA_VERSION

if os.name == "nt":
    import msvcrt
else:
    import fcntl

VERSION = "1.21.4"
DATA_HOME = (Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
             if os.name == "nt" else Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"))
ROOT = DATA_HOME / "nova-launcher"
LOADERS = {"vanilla": "Vanilla", "fabric": "Fabric", "forge": "Forge",
           "neoforge": "NeoForge", "quilt": "Quilt"}
DEFAULTS = {"version": VERSION, "loader": "vanilla", "loader_version": "", "java": "", "jvm_args": "",
            "memory_min": 0}
USER_AGENT = f"NovaLauncher/{NOVA_VERSION} (desktop Minecraft launcher)"


def save(path, data):
    """Write JSON atomically and keep the previous good copy as ``.bak``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            output.write(json.dumps(data, ensure_ascii=False))
            output.flush()
            os.fsync(output.fileno())
        if path.is_file():
            try:
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            except OSError:
                pass
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read(path, default):
    """Read JSON, falling back to the backup (or ``default``) if the file is damaged."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        backup = path.with_name(path.name + ".bak")
        try:
            path.replace(path.with_name(path.name + ".corrupt"))
        except OSError:
            pass
        try:
            data = json.loads(backup.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return default
        try:
            shutil.copy2(backup, path)
        except OSError:
            pass
        return data


def parse_jvm_args(text):
    """Split user JVM arguments, accepting only flags that start with ``-``."""
    try:
        pieces = shlex.split(text or "")
    except ValueError as error:
        raise ValueError("Los argumentos de Java tienen comillas sin cerrar.") from error
    if any(not piece.startswith("-") for piece in pieces):
        raise ValueError("Cada argumento de Java debe empezar con un guion, por ejemplo -XX:+UseG1GC.")
    if any(piece.startswith(("-Xmx", "-javaagent")) for piece in pieces):
        raise ValueError("La memoria se ajusta en RAM asignada. Los agentes de Java no se permiten aquí.")
    return pieces


def heap_arguments(instance):
    """-Xmx from the instance's maximum RAM, plus -Xms when a valid minimum was chosen (0 = let Java decide)."""
    maximum = instance["memory"]
    arguments = [f"-Xmx{maximum}G"]
    minimum = instance.get("memory_min", 0)
    if isinstance(minimum, int) and not isinstance(minimum, bool) and 1 <= minimum <= maximum:
        arguments.insert(0, f"-Xms{minimum}G")
    return arguments


def rotate_log(path, keep=3):
    """Keep the previous ``keep`` Minecraft logs instead of overwriting them."""
    if not path.is_file():
        return
    for number in range(keep, 1, -1):
        older = path.with_name(f"{path.name}.{number - 1}")
        if older.is_file():
            older.replace(path.with_name(f"{path.name}.{number}"))
    path.replace(path.with_name(path.name + ".1"))


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
def file_lock(path, *, blocking=False):
    with path.open("a+b") as lock:
        if os.name == "nt":
            lock.seek(0)
            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            try:
                msvcrt.locking(lock.fileno(), mode, 1)
            except OSError as error:
                raise RuntimeError("La carpeta está en uso por otra operación.") from error
        else:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                raise RuntimeError("La instancia está abierta o tiene una descarga en curso.") from None
        yield lock


def instance_lock(folder):
    return file_lock(folder / ".nova.lock")


def open_folder(path):
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])


def java_report(instance):
    from minecraft_launcher_lib.runtime import get_executable_path

    shared = ROOT / "minecraft"
    version = instance["version"]
    metadata = read(shared / "versions" / version / f"{version}.json", {})
    java = metadata.get("javaVersion", {})
    runtime = get_executable_path(java["component"], str(shared)) if java.get("component") else None
    executable = instance.get("java") or runtime or shutil.which("java")
    required = java.get("majorVersion")
    if not executable:
        return "Java se prepara al iniciar Minecraft.", required, None
    result = subprocess.run([executable, "-version"], capture_output=True, text=True,
                            errors="replace", timeout=8, check=True)
    match = re.search(r'version\s+"(?:1\.)?(\d+)', result.stderr + result.stdout)
    return str(executable), required, int(match[1]) if match else None


def prepare(instance, status, *, repair=False, offline=False):
    from minecraft_launcher_lib import command, install, mod_loader

    version = instance["version"]
    loader_id = instance["loader"]
    requested = instance["loader_version"]
    shared = ROOT / "minecraft"
    shared.mkdir(exist_ok=True)
    cache = shared / "nova-installations.json"
    key = json.dumps([version, loader_id, requested])
    with file_lock(shared / ".install.lock", blocking=True):
        installed = read(cache, {})
        launch_id = installed.get(key)
        if loader_id == "vanilla" and (shared / f".ready-{version}").exists():
            launch_id = version
        if not repair and launch_id and (shared / "versions" / launch_id / f"{launch_id}.json").is_file():
            return shared, launch_id
        if offline:
            raise ValueError("Esta instalación todavía necesita descargarse. Iniciá la instancia con conexión primero.")
        status(f"Descargando Minecraft {version}…")

        def install_status(message):
            stages = {"Download Libraries": "Descargando bibliotecas de Minecraft…",
                      "Download Assets": "Descargando recursos de Minecraft…",
                      "Install java runtime": "Preparando Java…"}
            if message in stages:
                status(stages[message])

        callback = {"setStatus": install_status}
        if loader_id == "vanilla":
            install.install_minecraft_version(version, str(shared), callback=callback)
            launch_id = version
        else:
            loader = mod_loader.get_mod_loader(loader_id)
            if not loader.is_minecraft_version_supported(version):
                raise ValueError(f"{LOADERS[loader_id]} no ofrece soporte para Minecraft {version}.")
            install.install_minecraft_version(version, str(shared), callback=callback)
            status(f"Preparando {LOADERS[loader_id]}…")
            java = instance["java"] or command.get_minecraft_command(version, str(shared), {
                "username": "Nova", "uuid": "0", "token": "0",
            })[0]
            launch_id = loader.install(version, str(shared), loader_version=requested or None, java=java)
        installed[key] = launch_id
        save(cache, installed)
        return shared, launch_id


def launch(folder, profile, instance, status, session=None, *, on_started=None, detach=False, server=None, game=None, log_path=None, held_lock=None, offline=False):
    from minecraft_launcher_lib import command

    if not session and not re.fullmatch(r"[A-Za-z0-9_]{3,16}", profile):
        raise ValueError("Elegí un nombre offline de 3 a 16 letras, números o guiones bajos.")
    game = game or folder / "game"
    game.mkdir(exist_ok=True)
    with (nullcontext(held_lock) if held_lock else instance_lock(folder)) as lock:
        shared, launch_id = prepare(instance, status, offline=True) if offline else prepare(instance, status)
        player_id = uuid.UUID(bytes=hashlib.md5(
            f"OfflinePlayer:{profile}".encode(), usedforsecurity=False
        ).digest(), version=3)
        options = {
            "username": profile, "uuid": player_id.hex, "token": "0",
            "gameDirectory": str(game), "launcherName": "Nova Launcher",
            "launcherVersion": NOVA_VERSION, "jvmArguments": heap_arguments(instance),
        }
        options["jvmArguments"].extend(parse_jvm_args(instance.get("jvm_args", "")))
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
        if server:
            host, port = servidores.address_parts(server)
            options["quickPlayMultiplayer"] = f"{host}:{port}" if port else host
        status("Iniciando Minecraft…" if not server else f"Iniciando Minecraft para entrar a {server}…")
        args = command.get_minecraft_command(launch_id, str(shared), options)
        if server and "--quickPlayMultiplayer" not in args:
            version = re.match(r"^(\d+)\.(\d+)", instance["version"])
            if version and tuple(map(int, version.groups())) < (1, 20):
                args.extend(("--server", host.strip("[]")))
                if port:
                    args.extend(("--port", port))
            else:
                args.extend(("--quickPlayMultiplayer", options["quickPlayMultiplayer"]))
        log_file = log_path or folder / "minecraft.log"
        rotate_log(log_file)
        with log_file.open("w", encoding="utf-8") as log:
            platform_options = ({} if os.name == "nt" else
                                {"pass_fds": (lock.fileno(),), "start_new_session": detach})
            process = subprocess.Popen(args, cwd=game, stdout=log, stderr=subprocess.STDOUT,
                                       **platform_options)
            status("Minecraft abierto · " + profile)
            if on_started:
                try:
                    return process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    on_started()
            return process.wait()

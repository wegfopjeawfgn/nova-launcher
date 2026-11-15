"""Gestión de servidores locales: respaldos del mundo, jugadores y permisos, estado del proceso y actualizaciones.

Todo se apoya en ``servidor_local``. Las acciones que cambian el mundo (restaurar, actualizar) exigen el servidor apagado
y hacen primero un respaldo; nada se borra sin dejar una copia.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid
import zipfile

import requests

import servidor_local as sl

BACKUPS = "backups"
BACKUP_RE = re.compile(r"[A-Za-z0-9._() -]{1,120}\.zip")
NAME_RE = re.compile(r"[A-Za-z0-9_]{3,16}")
LISTS = {"ops": "ops.json", "whitelist": "whitelist.json", "bans": "banned-players.json"}
MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/"
MAX_HOURS = 24 * 14


# ================================================================ respaldos
def world_dirs(base):
    base = base.resolve()
    return [path for path in sorted(base.iterdir()) if path.is_dir() and not path.is_symlink()
            and (path.name == "world" or path.name.startswith("world_") or (path / "level.dat").is_file())]


def _running_with_commands(sid):
    runner = sl.RUNNERS.get(sid)
    return bool(runner and runner.state == "running" and not runner.adopted)


def create_backup(sid, label="mundo"):
    """Zip the world folders into ``backups/<label>-<date>.zip``. A running server is asked to save first."""
    if not re.fullmatch(r"[a-z-]{1,30}", label):
        raise ValueError("Etiqueta de respaldo no válida.")
    base = sl.folder(sid).resolve()
    runner = sl.RUNNERS.get(sid)
    if runner and runner.state != "stopped" and runner.adopted:
        raise ValueError("Este servidor siguió encendido cuando Nova se cerró y no puede guardar el mundo a pedido. "
                         "Apagalo (se guarda solo) y volvé a intentar.")
    folders = world_dirs(base)
    if not folders:
        raise ValueError("Todavía no hay un mundo: se crea la primera vez que se enciende el servidor.")
    live = _running_with_commands(sid)
    if live:
        runner.send("save-off")
        runner.send("save-all flush")
        time.sleep(4)
    try:
        (base / BACKUPS).mkdir(exist_ok=True)
        target = sl.unique_name(base / BACKUPS, time.strftime(f"{label}-%Y-%m-%d-%H%M%S.zip"))
        part = target.with_name(target.name + ".part")
        try:
            with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as archive:
                for folder in folders:
                    for current, _, files in os.walk(folder):
                        for name in files:
                            file = Path(current) / name
                            if not file.is_symlink() and file.name != "session.lock":
                                archive.write(file, file.relative_to(base).as_posix())
            part.replace(target)
        finally:
            part.unlink(missing_ok=True)
    finally:
        if live:
            try:
                runner.send("save-on")
            except RuntimeError:
                pass
    return target


def list_backups(sid):
    folder = sl.folder(sid) / BACKUPS
    found = []
    try:
        for path in folder.iterdir():
            if path.is_file() and BACKUP_RE.fullmatch(path.name):
                info = path.stat()
                kind = path.name.split("-", 1)[0]
                found.append({"name": path.name, "size": info.st_size, "modified": info.st_mtime,
                              "kind": kind if kind in ("auto", "mundo", "antes") else "mundo"})
    except OSError:
        return []
    return sorted(found, key=lambda item: -item["modified"])


def backup_path(sid, name):
    if not BACKUP_RE.fullmatch(name or ""):
        raise ValueError("Nombre de respaldo no válido.")
    path = sl.folder(sid) / BACKUPS / name
    if not path.is_file() or path.is_symlink():
        raise ValueError("Ese respaldo ya no existe.")
    return path


def delete_backup(sid, name):
    backup_path(sid, name).unlink()


def prune_backups(sid, keep):
    """Delete the oldest automatic backups beyond ``keep`` (manual ones are never touched)."""
    autos = [item for item in list_backups(sid) if item["kind"] == "auto"]
    for old in autos[max(1, int(keep)):]:
        try:
            delete_backup(sid, old["name"])
        except (OSError, ValueError):
            pass


def restore_backup(sid, name):
    """Put a backup back as the world. Needs the server stopped; the current world is saved to a new backup first."""
    runner = sl.RUNNERS.get(sid)
    if runner and runner.state != "stopped":
        raise RuntimeError("Apagá el servidor antes de restaurar un respaldo.")
    path = backup_path(sid, name)
    base = sl.folder(sid).resolve()
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        tops = set()
        for member in members:
            parts = [part for part in member.filename.replace("\\", "/").split("/") if part]
            if not parts or member.filename.startswith(("/", "\\")) or ".." in parts or ":" in parts[0]:
                raise ValueError("El respaldo tiene rutas no válidas y no se restauró.")
            tops.add(parts[0])
        if not tops:
            raise ValueError("El respaldo está vacío.")
        safety = None
        if world_dirs(base):
            safety = create_backup(sid, "antes")
        for top in tops:                       # replace exactly the folders the backup contains
            target = base / top
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
        for member in members:
            destination = (base / member.filename).resolve()
            if base not in destination.parents and destination != base:
                raise ValueError("El respaldo tiene rutas no válidas.")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    return {"restored": name, "safety": safety.name if safety else None, "folders": sorted(tops)}


def backup_settings(meta):
    hours = meta.get("backup_hours", 0)
    keep = meta.get("backup_keep", 5)
    return {"hours": hours if isinstance(hours, int) and 0 <= hours <= MAX_HOURS else 0,
            "keep": keep if isinstance(keep, int) and 1 <= keep <= 50 else 5,
            "on_stop": bool(meta.get("backup_on_stop"))}


def auto_backups(now=None):
    """Called every minute: make the scheduled backups of servers that are running. Returns the ones created."""
    now = now or time.time()
    made = []
    for meta in sl.all_servers():
        settings = backup_settings(meta)
        if not settings["hours"] or not _running_with_commands(meta["id"]):
            continue
        autos = [item for item in list_backups(meta["id"]) if item["kind"] == "auto"]
        if autos and now - autos[0]["modified"] < settings["hours"] * 3600:
            continue
        try:
            made.append((meta["id"], create_backup(meta["id"], "auto")))
            prune_backups(meta["id"], settings["keep"])
        except (OSError, ValueError, RuntimeError):
            continue
    return made


def on_stopped(sid):
    """Stop hook: a backup right after the server stops, if that option is on (the world is consistent then)."""
    meta = sl.load(sid)
    if not meta or not backup_settings(meta)["on_stop"]:
        return None
    try:
        path = create_backup(sid, "auto")
        prune_backups(sid, backup_settings(meta)["keep"])
        return path
    except (OSError, ValueError, RuntimeError):
        return None


# ================================================================ jugadores y permisos
def offline_uuid(name):
    digest = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def lookup_uuid(name, online_mode=True):
    """The player's UUID: from Mojang for premium servers, derived from the name for offline-mode ones."""
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("El nombre de un jugador tiene de 3 a 16 letras, números o guiones bajos.")
    if not online_mode:
        return offline_uuid(name)
    response = requests.get(MOJANG_PROFILE + name, headers={"User-Agent": sl.USER_AGENT}, timeout=15)
    if response.status_code in (204, 404):
        raise ValueError(f"«{name}» no existe en Minecraft.")
    response.raise_for_status()
    raw = response.json().get("id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", raw):
        raise ValueError("Mojang devolvió un dato inesperado.")
    return str(uuid.UUID(raw))


def read_players(sid, kind):
    """Entries of ops / whitelist / bans as ``[{"name", "uuid", ...}]`` (empty if the file is missing or damaged)."""
    try:
        data = json.loads((sl.folder(sid) / LISTS[kind]).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return []
    return [item for item in data if isinstance(item, dict) and isinstance(item.get("name"), str)] if isinstance(data, list) else []


def _write_players(sid, kind, entries):
    sl._write_atomic(sl.folder(sid) / LISTS[kind], json.dumps(entries, indent=2, ensure_ascii=False) + "\n")


def _commands(kind, add):
    return {("ops", True): "op {}", ("ops", False): "deop {}", ("whitelist", True): "whitelist add {}",
            ("whitelist", False): "whitelist remove {}", ("bans", True): "ban {}", ("bans", False): "pardon {}"}[(kind, add)]


def change_player(sid, kind, name, add=True):
    """Add or remove a player from ops / whitelist / bans. Returns "comando" (sent to the server) or "archivo" (edited)."""
    if kind not in LISTS:
        raise ValueError("Lista no válida.")
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("El nombre de un jugador tiene de 3 a 16 letras, números o guiones bajos.")
    runner = sl.RUNNERS.get(sid)
    state = runner.state if runner else "stopped"
    if state in ("starting", "stopping"):
        raise RuntimeError("Esperá a que el servidor termine de encenderse o apagarse.")
    if runner and runner.adopted and state != "stopped":
        raise RuntimeError("Este servidor siguió encendido cuando Nova se cerró y no acepta comandos. Reinicialo desde Nova.")
    if state == "running":
        runner.send(_commands(kind, add).format(name))
        return "comando"
    online = sl.read_properties(sl.folder(sid)).get("online-mode", "true") != "false"
    entries = read_players(sid, kind)
    lowered = name.casefold()
    if add:
        if any(item["name"].casefold() == lowered for item in entries):
            raise ValueError(f"«{name}» ya está en la lista.")
        entry = {"uuid": lookup_uuid(name, online), "name": name}
        if kind == "ops":
            entry.update(level=4, bypassesPlayerLimit=False)
        elif kind == "bans":
            entry.update(created=time.strftime("%Y-%m-%d %H:%M:%S +0000", time.gmtime()), source="Nova Launcher",
                         expires="forever", reason="Baneado desde Nova")
        entries.append(entry)
    else:
        kept = [item for item in entries if item["name"].casefold() != lowered]
        if len(kept) == len(entries):
            raise ValueError(f"«{name}» no estaba en la lista.")
        entries = kept
    _write_players(sid, kind, entries)
    return "archivo"


def kick(sid, name, reason=""):
    runner = sl.RUNNERS.get(sid)
    if not NAME_RE.fullmatch(name or ""):
        raise ValueError("Nombre no válido.")
    if not _running_with_commands(sid):
        raise RuntimeError("El servidor tiene que estar encendido para expulsar a alguien.")
    runner.send(f"kick {name} {reason.strip()[:100]}".strip())


def refresh_online(sid):
    """Ask the server who is connected (the answer updates ``runner.online``)."""
    if _running_with_commands(sid):
        sl.RUNNERS[sid].send("list")


# ================================================================ estado y rendimiento
def usage(pid):
    """``{"rss": bytes, "cpu": seconds}`` for a process, or None. No extra packages needed."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
        if not handle:
            return None
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time),
                                          ctypes.byref(user_time)):
                return None
            ticks = lambda ft: (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            return {"rss": counters.WorkingSetSize, "cpu": (ticks(kernel_time) + ticks(user_time)) / 1e7}
        finally:
            kernel.CloseHandle(handle)
    try:
        stat = Path(f"/proc/{pid}/stat").read_bytes().rsplit(b")", 1)[1].split()
        pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
        return {"rss": pages * os.sysconf("SC_PAGE_SIZE"),
                "cpu": (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")}
    except (OSError, IndexError, ValueError):
        pass
    try:  # macOS and other systems without /proc
        result = subprocess.run(["ps", "-o", "rss=,time=", "-p", str(pid)], capture_output=True, text=True, timeout=5)
        rss, clock = result.stdout.split()
        parts = [float(piece) for piece in clock.replace("-", ":").split(":")]
        seconds = sum(value * factor for value, factor in zip(reversed(parts), (1, 60, 3600, 86400)))
        return {"rss": int(rss) * 1024, "cpu": seconds}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class Sampler:
    """Turns two readings of the process' CPU time into a percentage of the whole machine."""

    def __init__(self):
        self.last = None

    def percent(self, pid):
        reading = usage(pid)
        now = time.monotonic()
        if reading is None:
            self.last = None
            return None
        previous, self.last = self.last, (now, reading["cpu"], pid)
        if previous is None or previous[2] != pid or now <= previous[0]:
            return None
        return max(0.0, min(100.0, (reading["cpu"] - previous[1]) / (now - previous[0]) / (os.cpu_count() or 1) * 100))


_SIZE_CACHE = {}


def world_size(sid, ttl=30):
    """Size of the world folders; cached because walking a big world on every refresh would be wasteful."""
    cached = _SIZE_CACHE.get(sid)
    if cached and time.monotonic() - cached[0] < ttl:
        return cached[1]
    total = sum(sl.folder_size(path) for path in world_dirs(sl.folder(sid)))
    _SIZE_CACHE[sid] = (time.monotonic(), total)
    return total


def status(sid, sampler=None):
    """Everything the Estado screen shows, in one dict."""
    meta = sl.load(sid)
    runner = sl.RUNNERS.get(sid)
    state = runner.state if runner else "stopped"
    props = sl.read_properties(sl.folder(sid))
    pid = runner.pid if runner and state != "stopped" else None
    reading = usage(pid) if pid else None
    max_players = props.get("max-players", "20")
    return {
        "state": state, "adopted": bool(runner and runner.adopted),
        "uptime": time.time() - runner.started_at if runner and runner.started_at and state != "stopped" else None,
        "players": sorted(runner.online) if runner and state != "stopped" else [],
        "max_players": int(max_players) if max_players.isdigit() else 20,
        "memory": reading["rss"] if reading else None, "memory_limit": int(meta["memory"]) * 1024**3,
        "cpu": sampler.percent(pid) if sampler and pid else None,
        "world": world_size(sid), "total": sl.folder_size(sl.folder(sid)) if state == "stopped" else None,
        "port": props.get("server-port", meta["port"]),
    }


# ================================================================ actualizar
def version_key(version):
    """Sortable key for release versions like 1.21.11 or 26.3 (None for anything else, such as snapshots)."""
    return tuple(int(part) for part in version.split(".")) if re.fullmatch(r"\d+(\.\d+){1,3}", version or "") else None


def newer_versions(meta, available):
    current = version_key(meta["version"])
    return [version for version in available if current and (key := version_key(version)) and key > current]


def check_update(meta):
    """What can be updated: ``{"build": True/False/None, "versions": [newer Minecraft versions]}``.

    ``build`` says whether the same Minecraft version has a newer build of the server (None when it cannot be known,
    as for servers created before Nova kept track of it)."""
    info = sl.resolve(meta["kind"], meta["version"])
    installed = meta.get("build")
    build = None if installed is None else (str(info.get("build")) != str(installed))
    return {"build": build, "versions": newer_versions(meta, sl.release_versions(meta["kind"])), "latest": info.get("build")}


def update_server(sid, version=None, status=None, progress=None):
    """Update to the newest build of this Minecraft version, or to a newer version. Needs the server stopped.

    The world is backed up first. Going back to an older version is refused: worlds do not open on older versions."""
    status = status or (lambda text: None)
    runner = sl.RUNNERS.get(sid)
    if runner and runner.state != "stopped":
        raise RuntimeError("Apagá el servidor antes de actualizarlo.")
    meta = sl.load(sid)
    if meta is None:
        raise ValueError("El servidor ya no existe.")
    target = version or meta["version"]
    if target != meta["version"] and not (version_key(target) and version_key(target) > version_key(meta["version"])):
        raise ValueError("Solo se puede actualizar a una versión más nueva: un mundo no abre en una versión anterior.")
    folder = sl.folder(sid)
    status("Buscando la nueva versión…")
    info = sl.resolve(meta["kind"], target)
    backup = None
    if world_dirs(folder):
        status("Respaldando el mundo antes de actualizar…")
        backup = create_backup(sid, "antes")
    new = {**meta, "version": target, "java_component": info["component"], "java_major": info["major"], "build": info.get("build")}
    status("Descargando…")
    if meta["kind"] == "forge":
        new["forge_build"] = info["forge_build"]
        sl.download(info["url"], folder / "forge-installer.jar", size=info["size"], algo=info["algo"], digest=info["digest"], progress=progress)
        try:
            java = sl.ensure_full_java(info["major"], status, progress)
        except RuntimeError:
            (folder / "forge-installer.jar").unlink(missing_ok=True)
            raise
        status("Instalando Forge… puede tardar unos minutos.")
        sl.install_forge(folder, java)
    else:
        fresh = folder / "server.jar.new"
        sl.download(info["url"], fresh, size=info["size"], algo=info["algo"], digest=info["digest"], progress=progress)
        sl.ensure_java(new, status)
        if (folder / "server.jar").exists():
            shutil.copy2(folder / "server.jar", folder / "server.jar.old")   # one step back, in case the new one misbehaves
        fresh.replace(folder / "server.jar")
        new["jar"] = "server.jar"   # an imported server may have run a differently named jar before
    sl.save(new)
    jars = [path for sub in (sl.UPLOAD_DIRS[meta["kind"]],) if sub and (folder / sub).is_dir() for path in (folder / sub).glob("*.jar")]
    return {"from": meta["version"], "to": target, "backup": backup.name if backup else None, "extensions": len(jars),
            "changed_version": target != meta["version"]}

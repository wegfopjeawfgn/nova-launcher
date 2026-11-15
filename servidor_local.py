"""Servidores de Minecraft Java en este equipo, creados y manejados desde Nova.

Cada servidor vive en su carpeta (``servidores/<id>``) con un ``nova-server.json``. Nova descarga el servidor
oficial (Vanilla), Paper (plugins) o Fabric (mods), comprueba el hash cuando el proveedor lo publica, usa el
Java que Mojang pide para esa versión y nunca acepta el EULA de Mojang por la persona.
"""
import collections
import hashlib
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import threading
import time
import uuid

import requests

import motor
from nova_version import NOVA_VERSION

KINDS = {"vanilla": "Vanilla (oficial)", "paper": "Paper (plugins)", "fabric": "Fabric (mods)", "forge": "Forge (mods)"}
UPLOAD_DIRS = {"vanilla": None, "paper": "plugins", "fabric": "mods", "forge": "mods"}
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge/"
MANIFEST = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
USER_AGENT = f"NovaLauncher/{NOVA_VERSION} (https://github.com/wegfopjeawfgn/nova-launcher)"
EULA_URL = "https://aka.ms/MinecraftEULA"
MAX_JAR = 500 * 1024**2
MAX_TEXT = 512 * 1024
MAX_LIST = 3000
TEXT_SUFFIXES = {".properties", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".conf", ".ini", ".log", ".md", ".mcmeta"}
VERSION_RE = re.compile(r"[0-9A-Za-z._+-]{1,40}")
ID_RE = re.compile(r"[a-f0-9]{12}")


class EulaError(Exception):
    """The Mojang EULA has not been accepted for this server."""


def root():
    return motor.ROOT / "servidores"


# ---------------------------------------------------------------- lista y datos
def folder(sid):
    if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
        raise ValueError("Identificador de servidor no válido.")
    return root() / sid


def load(sid):
    try:
        data = motor.read(folder(sid) / "nova-server.json", None)
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict) or data.get("kind") not in KINDS or not isinstance(data.get("name"), str):
        return None
    return {**data, "id": sid}


def all_servers():
    found = []
    try:
        names = sorted(path.name for path in root().iterdir() if path.is_dir())
    except OSError:
        return []
    for name in names:
        if ID_RE.fullmatch(name) and (meta := load(name)):
            found.append(meta)
    return sorted(found, key=lambda meta: (meta.get("created", 0), meta["name"].casefold()))


def save(meta):
    clean = {key: value for key, value in meta.items() if key != "id"}
    motor.save(folder(meta["id"]) / "nova-server.json", clean)


# ---------------------------------------------------------------- descargas
def _get(url, **kwargs):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, **kwargs)
    response.raise_for_status()
    return response


def forge_builds():
    """{minecraft version: forge build} using Forge's recommended build when there is one, else the latest."""
    promos = _get(FORGE_PROMOS).json().get("promos", {})
    builds = {}
    for key, build in promos.items():
        mc, _, channel = key.rpartition("-")
        if channel in ("latest", "recommended") and VERSION_RE.fullmatch(mc) and VERSION_RE.fullmatch(str(build)):
            if channel == "recommended" or mc not in builds:
                builds[mc] = str(build)
    return builds


def release_versions(kind=None):
    """Release versions from Mojang's manifest, newest first; for Forge only those it supports."""
    data = _get(MANIFEST).json()
    found = [item["id"] for item in data["versions"] if item.get("type") == "release" and VERSION_RE.fullmatch(item["id"])]
    if kind == "forge":
        supported = forge_builds()
        found = [version for version in found if version in supported]
    return found


def mojang_info(version):
    """Server download and Java requirement for a version, from Mojang's own metadata."""
    if not VERSION_RE.fullmatch(version):
        raise ValueError("Versión no válida.")
    entry = next((item for item in _get(MANIFEST).json()["versions"] if item["id"] == version), None)
    if entry is None or not entry["url"].startswith("https://piston-meta.mojang.com/"):
        raise ValueError(f"Mojang no tiene la versión {version}.")
    data = _get(entry["url"]).json()
    java = data.get("javaVersion") or {"component": "jre-legacy", "majorVersion": 8}
    server = (data.get("downloads") or {}).get("server")
    return {"server": server, "component": java.get("component"), "major": java.get("majorVersion")}


def resolve(kind, version):
    """{url, size, algo, digest, component, major} for the server file of this kind and version."""
    if kind not in KINDS:
        raise ValueError("Tipo de servidor no válido.")
    info = mojang_info(version)
    out = {"component": info["component"], "major": info["major"], "algo": None, "digest": None, "size": None}
    if kind == "vanilla":
        server = info["server"]
        if not server or not server["url"].startswith("https://piston-data.mojang.com/"):
            raise ValueError(f"Mojang no publica un servidor para {version}.")
        out.update(url=server["url"], size=server.get("size"), algo="sha1", digest=server.get("sha1"))
    elif kind == "paper":
        builds = _get(f"https://fill.papermc.io/v3/projects/paper/versions/{version}/builds").json()
        stable = next((item for item in builds if item.get("channel") == "STABLE"), None)
        download = (stable or {}).get("downloads", {}).get("server:default")
        if not download or not download.get("url", "").startswith("https://fill-data.papermc.io/"):
            raise ValueError(f"Paper todavía no tiene una versión estable para {version}.")
        out.update(url=download["url"], size=download.get("size"), algo="sha256",
                   digest=(download.get("checksums") or {}).get("sha256"))
    elif kind == "forge":
        build = forge_builds().get(version)
        if not build:
            raise ValueError(f"Forge todavía no tiene una versión para {version}.")
        base = f"{FORGE_MAVEN}{version}-{build}/forge-{version}-{build}-installer.jar"
        digest = _get(base + ".sha256").text.split()[0].strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Forge devolvió una suma de verificación inesperada.")
        out.update(url=base, algo="sha256", digest=digest, forge_build=build)
    else:
        loaders = _get(f"https://meta.fabricmc.net/v2/versions/loader/{version}").json()
        installers = _get("https://meta.fabricmc.net/v2/versions/installer").json()
        loader = next((item["loader"]["version"] for item in loaders if item["loader"].get("stable")), None)
        installer = next((item["version"] for item in installers if item.get("stable")), None)
        if not loader or not installer:
            raise ValueError(f"Fabric todavía no es compatible con {version}.")
        out.update(url=f"https://meta.fabricmc.net/v2/versions/loader/{version}/{loader}/{installer}/server/jar")
    return out


def download(url, target, *, size=None, algo=None, digest=None, progress=None):
    """Download to a temporary file, check size and hash when known, then move into place."""
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.part")
    hasher = hashlib.new(algo) if algo else None
    done = 0
    try:
        with requests.get(url, stream=True, timeout=30, headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1 << 20):
                    done += len(chunk)
                    if done > MAX_JAR or (size and done > size):
                        raise ValueError("La descarga es más grande de lo esperado.")
                    if hasher:
                        hasher.update(chunk)
                    output.write(chunk)
                    if progress:
                        progress(done, size or 0)
        if size and done != size:
            raise ValueError("La descarga quedó incompleta.")
        if hasher and digest and hasher.hexdigest() != digest.lower():
            raise ValueError("La suma de verificación no coincide. Se descartó la descarga.")
        if done < 1000:
            raise ValueError("El archivo descargado es demasiado chico para ser un servidor.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_java(meta, status=None):
    """Path to a Java that can run this server: Mojang's runtime (downloaded if needed) or a suitable system Java."""
    from minecraft_launcher_lib.runtime import get_executable_path, install_jvm_runtime
    shared = motor.ROOT / "minecraft"
    component = meta.get("java_component")
    if component:
        path = get_executable_path(component, str(shared))
        if not path:
            if status:
                status("Descargando Java para el servidor…")
            shared.mkdir(parents=True, exist_ok=True)
            install_jvm_runtime(component, str(shared))
            path = get_executable_path(component, str(shared))
        if path:
            return path
    import java_detect
    required = meta.get("java_major") or 8
    for info in java_detect.find_java():
        if info["major"] >= required:
            return info["path"]
    raise RuntimeError(f"No se encontró Java {required} para este servidor.")


# ---------------------------------------------------------------- crear y borrar
def free_port(port, others=()):
    if port in others:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def check_new(name, kind, version, memory, port):
    name = (name or "").strip()
    if not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
        raise ValueError("Poné un nombre de hasta 60 caracteres.")
    if kind not in KINDS:
        raise ValueError("Elegí un tipo de servidor.")
    if not VERSION_RE.fullmatch(version or ""):
        raise ValueError("Elegí una versión de Minecraft.")
    if not 1 <= int(memory) <= 64:
        raise ValueError("La memoria debe estar entre 1 y 64 GB.")
    if not 1024 <= int(port) <= 65535:
        raise ValueError("El puerto debe estar entre 1024 y 65535.")
    if int(port) in {m.get("port") for m in all_servers()}:
        raise ValueError("Otro servidor de Nova ya usa ese puerto.")
    return name


def create(name, kind, version, memory, port, *, eula, progress=None, status=None):
    """Download everything and write a ready-to-start server. Nothing is left behind if it fails."""
    name = check_new(name, kind, version, memory, port)
    status = status or (lambda text: None)
    status("Buscando la versión…")
    info = resolve(kind, version)
    sid = uuid.uuid4().hex[:12]
    target = folder(sid)
    target.mkdir(parents=True)
    try:
        status("Descargando el servidor…")
        jar = "forge-installer.jar" if kind == "forge" else "server.jar"
        download(info["url"], target / jar, size=info["size"], algo=info["algo"], digest=info["digest"], progress=progress)
        meta = {"id": sid, "name": name, "kind": kind, "version": version, "memory": int(memory), "port": int(port),
                "java_component": info["component"], "java_major": info["major"], "created": int(time.time()),
                "eula": bool(eula)}
        if kind == "forge":
            meta["forge_build"] = info["forge_build"]
        java = ensure_java(meta, status)
        if kind == "forge":
            java = full_java(info["major"])
            if java is None:
                raise RuntimeError(f"Forge necesita un Java completo instalado en tu equipo (versión {info['major']} o más nueva), "
                                   "no solo el que baja Nova. Instalá OpenJDK o Temurin y volvé a intentar.")
            status("Instalando Forge… puede tardar unos minutos.")
            install_forge(target, java)
        write_properties(target, {"server-port": str(int(port)), "motd": f"{name} · Nova Launcher",
                                  "query.port": str(int(port))})
        if eula:
            write_eula(target)
        save(meta)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return load(sid)


def write_eula(path):
    (path / "eula.txt").write_text(
        "# Aceptado desde Nova Launcher por la persona que creó el servidor. " + EULA_URL + "\neula=true\n",
        encoding="utf-8")


def eula_accepted(path):
    try:
        text = (path / "eula.txt").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"^\s*eula\s*=\s*true\s*$", text, re.M | re.I) is not None


def delete(sid):
    """Remove a stopped server and everything in its folder."""
    runner = RUNNERS.get(sid)
    if runner and runner.state != "stopped":
        raise RuntimeError("Apagá el servidor antes de eliminarlo.")
    target = folder(sid)
    if target.parent != root() or not (target / "nova-server.json").is_file():
        raise ValueError("Esa carpeta no es un servidor de Nova.")
    shutil.rmtree(target)
    RUNNERS.pop(sid, None)


# ---------------------------------------------------------------- server.properties
def read_properties(path):
    values = {}
    try:
        text = (path / "server.properties").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def write_properties(path, updates):
    """Change only the given keys, keeping comments, order and every other line."""
    for key, value in updates.items():
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,60}", key) or "\n" in value or "\r" in value:
            raise ValueError(f"Valor no válido para {key}.")
    file = path / "server.properties"
    lines = file.read_text(encoding="utf-8", errors="replace").splitlines() if file.exists() else []
    pending = dict(updates)
    for index, line in enumerate(lines):
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in pending:
                lines[index] = f"{key}={pending.pop(key)}"
    lines += [f"{key}={value}" for key, value in pending.items()]
    _write_atomic(file, "\n".join(lines) + "\n")


def _write_atomic(file, text):
    temporary = file.with_name(f".{file.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(file)
    finally:
        temporary.unlink(missing_ok=True)


# ---------------------------------------------------------------- proceso
def full_java(required):
    """A complete Java from this computer (not Mojang's trimmed runtime) of at least ``required``, or None.

    Forge's installer produces files with a different checksum when it runs on Mojang's trimmed-down runtime, so Forge
    needs a normal JDK or JRE. The lowest version that satisfies the request is preferred."""
    import java_detect
    bundled = str(motor.ROOT / "minecraft" / "runtime")
    options = [info for info in java_detect.find_java() if info["major"] >= (required or 8) and not info["path"].startswith(bundled)]
    return min(options, key=lambda info: (info["major"], info["path"]))["path"] if options else None


def install_forge(path, java, timeout=1800):
    """Run Forge's own installer in the server folder (it downloads Minecraft and the libraries it needs)."""
    installer = path / "forge-installer.jar"
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        result = subprocess.run([str(java), "-jar", installer.name, "--installServer"], cwd=path, capture_output=True,
                                text=True, errors="replace", timeout=timeout, **flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError("El instalador de Forge tardó demasiado.")
    if result.returncode != 0:
        tail = " ".join((result.stdout + result.stderr).strip().splitlines()[-3:])[:300]
        raise RuntimeError(f"El instalador de Forge falló: {tail or 'sin detalles'}")
    installer.unlink(missing_ok=True)
    (path / "forge-installer.jar.log").unlink(missing_ok=True)


def _forge_command(meta, path, java):
    memory = int(meta["memory"])
    args_name = "win_args.txt" if os.name == "nt" else "unix_args.txt"
    modern = sorted(path.glob(f"libraries/net/minecraftforge/forge/*/{args_name}"))
    if modern:
        (path / "user_jvm_args.txt").write_text(
            f"# Nova Launcher escribe esto cada vez que enciende el servidor.\n-Xmx{memory}G\n-Xms{min(memory, 2)}G\n",
            encoding="utf-8")
        return [str(java), "@user_jvm_args.txt", "@" + modern[-1].relative_to(path).as_posix(), "nogui"]
    legacy = sorted(jar for jar in path.glob("forge-*.jar") if "installer" not in jar.name)
    if legacy:
        return [str(java), f"-Xmx{memory}G", f"-Xms{min(memory, 2)}G", "-jar", legacy[-1].name, "nogui"]
    raise RuntimeError("Forge no está instalado en este servidor. Eliminalo y volvé a crearlo.")


def launch_command(meta, path, java):
    if meta.get("kind") == "forge":
        return _forge_command(meta, path, java)
    return [str(java), f"-Xmx{int(meta['memory'])}G", f"-Xms{min(int(meta['memory']), 2)}G", "-jar", "server.jar", "nogui"]


class Runner:
    """One server process: start, command, stop, restart and a rolling copy of its console."""

    def __init__(self, sid):
        self.sid = sid
        self.state = "stopped"          # stopped | starting | running | stopping
        self.lines = collections.deque(maxlen=3000)
        self.listeners = []              # called from worker threads: listener(kind, payload)
        self.process = None
        self.lock = threading.RLock()
        self._restart = False

    def _emit(self, kind, payload=None):
        for listener in list(self.listeners):
            try:
                listener(kind, payload)
            except Exception:
                pass

    def _set(self, state):
        self.state = state
        self._emit("state", state)

    def start(self, status=None):
        with self.lock:
            if self.state != "stopped":
                raise RuntimeError("El servidor ya está encendido.")
            meta = load(self.sid)
            if meta is None:
                raise ValueError("El servidor ya no existe.")
            path = folder(self.sid)
            if not eula_accepted(path):
                raise EulaError("Hay que aceptar el EULA de Mojang para encender el servidor.")
            port = int(read_properties(path).get("server-port", meta["port"]))
            if not free_port(port):
                raise RuntimeError(f"El puerto {port} ya está en uso. Cambialo en Ajustes o cerrá lo que lo usa.")
            java = ensure_java(meta, status)
            flags = {}
            if os.name == "nt":
                flags["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                flags["start_new_session"] = True
            self.process = subprocess.Popen(launch_command(meta, path, java), cwd=path, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                            encoding="utf-8", errors="replace", bufsize=1, **flags)
            self.lines.append(f"[Nova] Encendiendo «{meta['name']}»…")
            self._set("starting")
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()

    def _read(self, process):
        for line in process.stdout:
            line = line.rstrip("\r\n")
            self.lines.append(line)
            self._emit("line", line)
            if self.state == "starting" and re.search(r"\bDone \(", line):
                self._set("running")
        code = process.wait()
        for pipe in (process.stdout, process.stdin):
            try:
                pipe.close()
            except OSError:
                pass
        with self.lock:
            self.process = None
            note = f"[Nova] El servidor se apagó (código {code})."
            self.lines.append(note)
            self._emit("line", note)
            self._set("stopped")
            again, self._restart = self._restart, False
        if again:
            try:
                self.start()
            except Exception as error:
                self._emit("error", str(error))

    def send(self, command):
        command = command.strip().lstrip("/")
        if not command or "\n" in command or len(command) > 500:
            return
        with self.lock:
            if self.process is None or self.state not in ("starting", "running"):
                raise RuntimeError("El servidor está apagado.")
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except OSError:
                raise RuntimeError("No se pudo enviar el comando.")

    def stop(self, wait=45):
        """Ask nicely with the server's own ``stop`` (it saves the world), then terminate, then kill."""
        with self.lock:
            process = self.process
            if process is None or self.state in ("stopped", "stopping"):
                return
            self._set("stopping")
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
            except OSError:
                pass

        def escalate():
            for action, grace in ((None, wait), (process.terminate, 10), (process.kill, 5)):
                if action:
                    try:
                        action()
                    except OSError:
                        pass
                try:
                    process.wait(grace)
                    return
                except subprocess.TimeoutExpired:
                    continue
        threading.Thread(target=escalate, daemon=True).start()

    def restart(self):
        with self.lock:
            if self.state == "stopped":
                self.start()
                return
            self._restart = True
        self.stop()


RUNNERS = {}


def runner(sid):
    folder(sid)  # validates the id
    return RUNNERS.setdefault(sid, Runner(sid))


def running():
    return [sid for sid, item in RUNNERS.items() if item.state != "stopped"]


def stop_all(wait=30):
    """Stop every server and wait for them, used when Nova closes."""
    for sid in running():
        RUNNERS[sid].stop(wait=wait)
    end = time.monotonic() + wait + 20
    while running() and time.monotonic() < end:
        time.sleep(0.2)


def local_address(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            ip = probe.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    return f"{ip}:{port}"


# ---------------------------------------------------------------- archivos
def safe_path(base, relative=""):
    """A path inside ``base`` (symbolic links that point outside are refused)."""
    base = base.resolve()
    parts = [part for part in str(relative).replace("\\", "/").split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("Esa ruta queda fuera del servidor.")
    path = base.joinpath(*parts)
    resolved = path.parent.resolve() / path.name if path.is_symlink() else path.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError("Esa ruta queda fuera del servidor.")
    return path


def list_dir(base, relative=""):
    path = safe_path(base, relative)
    entries = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))[:MAX_LIST]:
        try:
            info = child.lstat()
        except OSError:
            continue
        entries.append({"name": child.name, "dir": stat.S_ISDIR(info.st_mode), "size": info.st_size,
                        "modified": info.st_mtime, "link": stat.S_ISLNK(info.st_mode)})
    return entries


def unique_name(folder_path, name):
    name = Path(name).name
    if not name or name in (".", ".."):
        raise ValueError("Nombre de archivo no válido.")
    candidate, stem, suffix, n = folder_path / name, Path(name).stem, Path(name).suffix, 1
    while candidate.exists() or candidate.is_symlink():
        n += 1
        candidate = folder_path / f"{stem} ({n}){suffix}"
    return candidate


def add_files(base, relative, sources):
    """Copy files or folders from the computer into the server; names never overwrite anything."""
    destination = safe_path(base, relative)
    added = []
    for source in sources:
        source = Path(source)
        target = unique_name(destination, source.name)
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target)
        added.append(target.name)
    return added


def make_dir(base, relative, name):
    if not re.fullmatch(r"[^/\\\x00-\x1f]{1,100}", name or "") or name in (".", ".."):
        raise ValueError("Nombre de carpeta no válido.")
    target = unique_name(safe_path(base, relative), name)
    target.mkdir()
    return target.name


def rename(base, relative, new_name):
    path = safe_path(base, relative)
    if path == base.resolve() or not re.fullmatch(r"[^/\\\x00-\x1f]{1,150}", new_name or "") or new_name in (".", ".."):
        raise ValueError("Nombre no válido.")
    target = path.with_name(new_name)
    if target.exists():
        raise ValueError("Ya existe algo con ese nombre.")
    path.rename(target)


def remove(base, relative):
    path = safe_path(base, relative)
    if path == base.resolve() or relative in ("", "."):
        raise ValueError("No se puede borrar la carpeta del servidor desde acá.")
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def read_text(base, relative):
    path = safe_path(base, relative)
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("ops.json", "whitelist.json", "banned-players.json"):
        raise ValueError("Ese tipo de archivo no se puede editar acá.")
    if path.stat().st_size > MAX_TEXT:
        raise ValueError("El archivo es demasiado grande para editarlo acá (máximo 512 KB).")
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(base, relative, text):
    path = safe_path(base, relative)
    if len(text.encode("utf-8")) > MAX_TEXT:
        raise ValueError("El texto es demasiado grande (máximo 512 KB).")
    _write_atomic(path, text)


def folder_size(path):
    total = 0
    for current, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(current) / name).lstat().st_size
            except OSError:
                pass
    return total


# ---------------------------------------------------------------- archivos: extras
def set_enabled(base, relative, enabled):
    """Turn a mod or plugin off or on by renaming ``x.jar`` <-> ``x.jar.disabled`` (the server ignores the second)."""
    path = safe_path(base, relative)
    if enabled and path.name.endswith(".jar.disabled"):
        target = path.with_name(path.name[:-len(".disabled")])
    elif not enabled and path.suffix == ".jar":
        target = path.with_name(path.name + ".disabled")
    else:
        raise ValueError("Solo se pueden activar o desactivar archivos .jar.")
    if target.exists():
        raise ValueError("Ya existe un archivo con ese nombre.")
    path.rename(target)
    return target.name


def export(base, relative, destination):
    """Copy a file or folder out of the server into any folder on the computer; never overwrites."""
    source = safe_path(base, relative)
    target = unique_name(Path(destination), source.name)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)
    return target


def backup_world(base):
    """Zip the world folders into ``backups/``. The caller should ask a running server to save first."""
    import zipfile
    base = base.resolve()
    folders = [path for path in sorted(base.iterdir()) if path.is_dir() and not path.is_symlink()
               and (path.name == "world" or path.name.startswith("world_") or (path / "level.dat").is_file())]
    if not folders:
        raise ValueError("Todavía no hay un mundo: se crea la primera vez que se enciende el servidor.")
    (base / "backups").mkdir(exist_ok=True)
    target = unique_name(base / "backups", time.strftime("mundo-%Y-%m-%d-%H%M%S.zip"))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder_path in folders:
            for current, _, files in os.walk(folder_path):
                for name in files:
                    file = Path(current) / name
                    if not file.is_symlink() and file.name != "session.lock":
                        archive.write(file, file.relative_to(base).as_posix())
    return target


def summary(base, relative=""):
    """(items, bytes of the files directly inside) for the status line."""
    entries = list_dir(base, relative)
    return len(entries), sum(entry["size"] for entry in entries if not entry["dir"])


# ---------------------------------------------------------------- catálogo de mods y plugins (Modrinth)
MODRINTH = "https://api.modrinth.com/v2"
CDN = "https://cdn.modrinth.com/"
LOADERS = {"paper": ("paper", "spigot", "bukkit"), "fabric": ("fabric",), "forge": ("forge",)}
MAX_MOD = 200 * 1024**2
FILE_RE = re.compile(r"[A-Za-z0-9._+() \-]{1,150}\.jar")


def catalog_available(meta):
    return meta.get("kind") in LOADERS


def catalog_search(meta, query="", offset=0, limit=20):
    """Mods or plugins that work on this server's Minecraft version and type, from Modrinth."""
    if not catalog_available(meta):
        raise ValueError("Un servidor Vanilla no admite mods ni plugins. Creá uno Paper, Fabric o Forge.")
    import json
    # Modrinth files most Paper plugins under the "plugin" project type and mods under "mod".
    types = ["project_type:plugin", "project_type:mod"] if meta["kind"] == "paper" else ["project_type:mod"]
    facets = [types, [f"versions:{meta['version']}"], [f"categories:{name}" for name in LOADERS[meta["kind"]]]]
    if meta["kind"] != "paper":
        facets.append(["server_side:required", "server_side:optional"])
    data = _get(f"{MODRINTH}/search", params={"query": query.strip()[:80], "facets": json.dumps(facets), "limit": limit,
                                              "offset": offset, "index": "relevance" if query.strip() else "downloads"}).json()
    hits = [{"project_id": hit["project_id"], "title": hit["title"], "description": hit.get("description", ""),
             "downloads": hit.get("downloads", 0), "author": hit.get("author", "")} for hit in data.get("hits", [])]
    return {"hits": hits, "total": data.get("total_hits", len(hits))}


def _catalog_path(base):
    return base / "nova-catalogo.json"


def catalog_installed(base):
    data = motor.read(_catalog_path(base), {})
    return data if isinstance(data, dict) else {}


def catalog_install(base, meta, project_id, *, title="", progress=None, _seen=None, _depth=0):
    """Install the newest compatible release (and its required dependencies) with its SHA-512 checked."""
    import json
    if not catalog_available(meta):
        raise ValueError("Un servidor Vanilla no admite mods ni plugins.")
    if not re.fullmatch(r"[A-Za-z0-9]{8}", project_id or ""):
        raise ValueError("Proyecto no válido.")
    seen = _seen if _seen is not None else set()
    if project_id in seen:
        return []
    seen.add(project_id)
    versions = _get(f"{MODRINTH}/project/{project_id}/version", params={
        "loaders": json.dumps(list(LOADERS[meta["kind"]])), "game_versions": json.dumps([meta["version"]])}).json()
    if not versions:
        raise ValueError("Ese proyecto no tiene una versión para este servidor.")
    release = next((item for item in versions if item.get("version_type") == "release"), versions[0])
    file = next((item for item in release["files"] if item.get("primary")), release["files"][0])
    if not file["url"].startswith(CDN) or not FILE_RE.fullmatch(file["filename"]) or not file.get("hashes", {}).get("sha512"):
        raise ValueError("Modrinth devolvió datos inesperados para la descarga.")
    folder_name = UPLOAD_DIRS[meta["kind"]]
    destination = base / folder_name
    destination.mkdir(exist_ok=True)
    target = destination / file["filename"]
    installed = []
    if not target.exists():
        download(file["url"], target, size=file.get("size"), algo="sha512", digest=file["hashes"]["sha512"], progress=progress)
        installed.append(file["filename"])
    records = catalog_installed(base)
    records[project_id] = {"title": title or file["filename"], "file": file["filename"], "version": release.get("version_number", "")}
    motor.save(_catalog_path(base), records)
    if _depth < 3:
        for dependency in release.get("dependencies", []):
            if dependency.get("dependency_type") == "required" and dependency.get("project_id"):
                try:
                    installed += catalog_install(base, meta, dependency["project_id"], progress=progress, _seen=seen, _depth=_depth + 1)
                except (ValueError, OSError, requests.RequestException):
                    pass  # an optional-looking or unavailable dependency should not undo the main install
    return installed


def catalog_remove(base, meta, project_id):
    records = catalog_installed(base)
    record = records.pop(project_id, None)
    if record is None:
        raise ValueError("Eso no está instalado desde el catálogo.")
    name = record.get("file", "")
    if FILE_RE.fullmatch(name):
        path = safe_path(base, f"{UPLOAD_DIRS[meta['kind']]}/{name}")
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".disabled").unlink(missing_ok=True)
    motor.save(_catalog_path(base), records)

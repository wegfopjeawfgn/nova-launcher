"""Túnel para que amigos de otras redes entren a tu servidor local, con el agente oficial de playit.gg (servicio externo).

Nova baja el agente desde las releases de ``playit-cloud/playit-agent`` (código abierto, BSD-2), comprueba el SHA-256 que
GitHub publica y lo usa tal cual: ``playit-cli claim`` para conectar tu cuenta en el navegador (Nova nunca ve tu contraseña)
y el daemon ``playit`` con la clave que playit entrega. El túnel en sí se crea en el panel de playit.gg; Nova guarda la
dirección que te da. Solo Linux x86_64 por ahora.
"""
import collections
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
import threading
import uuid

import requests

import motor

REPO = "playit-cloud/playit-agent"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SITE = "https://playit.gg"
TUNNELS_URL = f"{SITE}/account/tunnels"
MAX_BYTES = 60 * 1024 * 1024
# (daemon, command-line tool) release assets for this system
ASSETS = {"linux": ("playit-linux-amd64", "playit-cli-linux-amd64")}
CODE_RE = re.compile(r"[A-Za-z0-9]{6,64}")
SECRET_RE = re.compile(r"[A-Za-z0-9_\-]{16,200}")


def supported():
    """The ``(daemon, cli)`` asset names for this system, or None."""
    if platform.machine().lower() in ("x86_64", "amd64") and sys.platform.startswith("linux") and os.name != "nt":
        return ASSETS["linux"]
    return None


def folder():
    return motor.ROOT / "clients" / "playit"


def secret_path():
    return folder() / "secret.key"


def installed():
    """``{"tag", "daemon", "cli"}`` when both programs are in place, else None."""
    assets = supported()
    try:
        data = json.loads((folder() / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if assets is None or not isinstance(data.get("tag"), str):
        return None
    daemon, cli = folder() / "playitd", folder() / "playit-cli"
    return {"tag": data["tag"], "daemon": daemon, "cli": cli} if daemon.is_file() and cli.is_file() else None


def has_secret():
    return secret_path().is_file() and secret_path().stat().st_size > 0


def release(names):
    """Newest stable release and the checked details of the assets for this system."""
    response = requests.get(API, timeout=15, headers={"Accept": "application/vnd.github+json", "User-Agent": motor.USER_AGENT})
    response.raise_for_status()
    data = response.json()
    tag = data.get("tag_name")
    if data.get("draft") or data.get("prerelease") or not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,40}", tag):
        raise ValueError("GitHub no devolvió una versión estable del agente de playit.")
    found = {}
    for name in names:
        asset = next((item for item in data.get("assets", []) if item.get("name") == name), None)
        if asset is None:
            raise ValueError("Esta versión del agente de playit no incluye los archivos para tu sistema.")
        url, size, digest = asset.get("browser_download_url"), asset.get("size"), asset.get("digest")
        if (not isinstance(url, str) or not url.startswith(DOWNLOAD_PREFIX) or not url.endswith("/" + name)
                or not isinstance(size, int) or not 0 < size <= MAX_BYTES
                or not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)):
            raise ValueError("GitHub devolvió datos inesperados para la descarga del agente de playit.")
        found[name] = {"url": url, "size": size, "sha256": digest[7:]}
    return tag, found


def _download(url, target, size, digest, progress=None, offset=0, total=0):
    hasher, done = hashlib.sha256(), 0
    with requests.get(url, stream=True, timeout=30, headers={"User-Agent": motor.USER_AGENT}) as response:
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_content(1 << 20):
                done += len(chunk)
                if done > size:
                    raise ValueError("La descarga es más grande de lo que informó GitHub.")
                hasher.update(chunk)
                output.write(chunk)
                if progress:
                    progress(offset + done, total or size)
    if done != size:
        raise ValueError("La descarga quedó incompleta.")
    if hasher.hexdigest() != digest:
        raise ValueError("La suma SHA-256 no coincide con la que publica GitHub. Se descartó la descarga.")


def install(progress=None):
    """Download and verify the agent. A failed install leaves the previous one untouched; the secret is kept."""
    assets = supported()
    if assets is None:
        raise ValueError("El túnel de playit todavía no está disponible para este sistema.")
    tag, found = release(assets)
    root = motor.ROOT / "clients"
    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=root, prefix=".playit-"))
    try:
        total = sum(item["size"] for item in found.values())
        done = 0
        for name, target_name in zip(assets, ("playitd", "playit-cli")):
            item = found[name]
            _download(item["url"], work / target_name, item["size"], item["sha256"], progress, done, total)
            (work / target_name).chmod(0o755)
            done += item["size"]
        (work / "installed.json").write_text(json.dumps({"tag": tag}), encoding="utf-8")
        target = folder()
        for keep in ("secret.key",):   # the account link survives an update
            if (target / keep).is_file():
                shutil.copy2(target / keep, work / keep)
        previous = None
        if target.exists():
            previous = root / f".playit-old-{uuid.uuid4().hex[:8]}"
            target.rename(previous)
        try:
            work.rename(target)
        except OSError:
            if previous is not None:
                previous.rename(target)
            raise
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return installed()


# ---------------------------------------------------------------- cuenta (reclamo en el navegador)
class ClaimError(Exception):
    """A message that can be shown to the person as is."""


def _run(args, timeout):
    try:
        result = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ClaimError("Se acabó el tiempo de espera. Probá de nuevo.")
    except OSError as error:
        raise ClaimError(f"No se pudo ejecutar el agente de playit: {error}")
    return result


def claim_start():
    """``(code, url)``: the person opens the url in the browser and approves the agent on playit.gg."""
    info = installed()
    if info is None:
        raise ClaimError("Primero descargá el agente de playit.")
    code = _run([str(info["cli"]), "claim", "generate"], 15).stdout.strip()
    if not CODE_RE.fullmatch(code):
        raise ClaimError("El agente de playit devolvió un código inesperado.")
    url = _run([str(info["cli"]), "claim", "url", code, "--name", "Nova Launcher"], 15).stdout.strip()
    if not url.startswith(SITE + "/") or " " in url or "\n" in url:
        raise ClaimError("El agente de playit devolvió un enlace inesperado.")
    return code, url


def claim_finish(code, wait=600):
    """Wait for the approval and keep the key (readable only by this user). Returns True when the account is linked."""
    info = installed()
    if info is None or not CODE_RE.fullmatch(code):
        raise ClaimError("Primero descargá el agente de playit.")
    result = _run([str(info["cli"]), "claim", "exchange", code, "--wait", str(int(wait))], wait + 30)
    secret = result.stdout.strip().splitlines()[-1].strip() if result.stdout.strip() else ""
    if result.returncode != 0 or not SECRET_RE.fullmatch(secret):
        raise ClaimError("No se pudo vincular la cuenta. ¿Aprobaste el enlace en playit.gg?")
    folder().mkdir(parents=True, exist_ok=True)
    temporary = secret_path().with_name(f"secret.{uuid.uuid4().hex[:8]}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(secret)
        temporary.replace(secret_path())
    finally:
        temporary.unlink(missing_ok=True)
    return True


def forget_account():
    """Unlink the account: the key is deleted from this computer."""
    secret_path().unlink(missing_ok=True)


# ---------------------------------------------------------------- el agente en marcha
class Agent:
    """The playit daemon as a child of Nova: it exits together with Nova, so a tunnel is never left open by accident."""

    def __init__(self):
        self.process = None
        self.lines = collections.deque(maxlen=500)
        self.listeners = []
        self.lock = threading.RLock()

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def _emit(self, kind, payload=None):
        for listener in list(self.listeners):
            try:
                listener(kind, payload)
            except Exception:
                pass

    def start(self):
        with self.lock:
            if self.running:
                return
            info = installed()
            if info is None or not has_secret():
                raise RuntimeError("Falta descargar el agente o vincular tu cuenta de playit.")
            folder().mkdir(parents=True, exist_ok=True)
            kwargs = {}
            if sys.platform.startswith("linux"):
                import ctypes

                def die_with_parent():
                    ctypes.CDLL("libc.so.6").prctl(1, 15)  # PR_SET_PDEATHSIG, SIGTERM
                kwargs["preexec_fn"] = die_with_parent
            self.process = subprocess.Popen(
                [str(info["daemon"]), "--secret-path", str(secret_path()), "--socket-path", str(folder() / "playit.sock"),
                 "--log-path", str(folder() / "playit.log")],
                cwd=folder(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1, **kwargs)
            self.lines.append("[Nova] Conectando con playit.gg…")
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
            self._emit("state", "running")

    def _read(self, process):
        for line in process.stdout:
            line = line.rstrip("\r\n")
            self.lines.append(line)
            self._emit("line", line)
        code = process.wait()
        self.lines.append(f"[Nova] El agente de playit se detuvo (código {code}).")
        self._emit("state", "stopped")

    def stop(self):
        with self.lock:
            process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            process.kill()


AGENT = Agent()


def valid_address(text):
    """A host or host:port to show friends (no scheme, no spaces)."""
    text = (text or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9._-]{1,200}(:[0-9]{1,5})?", text) and (":" not in text or 1 <= int(text.rsplit(":", 1)[1]) <= 65535) else None

"""Importar a «Mi servidor» una carpeta de servidor de Minecraft que ya existe.

Nova mira la carpeta para adivinar el tipo (Vanilla, Paper, Fabric o Forge), la versión, el puerto y la memoria, la persona lo
confirma o corrige, y Nova **copia** la carpeta: la original no se toca ni se mueve.
"""
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid
import zipfile

import motor
import servidor_local as sl

JAR_RE = re.compile(r"[A-Za-z0-9._+() -]{1,150}\.jar")
SKIP = {"nova-server.json", "nova-server.pid"}
VERSION = r"(\d+(?:\.\d+){1,3})"


def _read_text(path, limit=200_000):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _vanilla_version(jar):
    """Minecraft's own server jars carry a version.json at their root."""
    try:
        with zipfile.ZipFile(jar) as package:
            return json.loads(package.read("version.json")).get("id")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None


def detect(folder):
    """What Nova can tell about a server folder: kind, version, build, jar, port, memory, EULA and a few notes (never raises on odd content)."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("Elegí una carpeta.")
    props = sl.read_properties(folder)
    out = {"name": folder.name[:60] or "Servidor importado", "kind": None, "version": None, "build": None, "forge_build": None,
           "jar": None, "port": 25565, "memory": 4, "eula": sl.eula_accepted(folder), "notes": []}
    if props.get("server-port", "").isdigit() and 1024 <= int(props["server-port"]) <= 65535:
        out["port"] = int(props["server-port"])
    for candidate in (folder / "user_jvm_args.txt", folder / "start.sh", folder / "run.sh", folder / "start.bat", folder / "run.bat"):
        if match := re.search(r"-Xmx(\d+)([GgMm])", _read_text(candidate)):
            gigabytes = int(match.group(1)) if match.group(2) in "Gg" else max(1, int(match.group(1)) // 1024)
            out["memory"] = min(64, max(1, gigabytes))
            break
    jars = sorted(path.name for path in folder.glob("*.jar") if JAR_RE.fullmatch(path.name))

    modern = sorted((folder / "libraries" / "net" / "minecraftforge" / "forge").glob("*/unix_args.txt")) \
        if (folder / "libraries" / "net" / "minecraftforge" / "forge").is_dir() else []
    legacy = [name for name in jars if re.fullmatch(rf"forge-{VERSION}-[\d.]+.*\.jar", name) and "installer" not in name]
    history = _read_text(folder / "version_history.json")
    paper_jars = [name for name in jars if re.fullmatch(rf"paper-{VERSION}-\d+\.jar", name)]

    if modern:
        mc, _, build = modern[-1].parent.name.partition("-")
        out.update(kind="forge", version=mc, forge_build=build, build=build)
    elif legacy:
        match = re.fullmatch(rf"forge-{VERSION}-([\d.]+).*\.jar", legacy[-1])
        out.update(kind="forge", version=match.group(1), forge_build=match.group(2), build=match.group(2), jar=legacy[-1])
    elif "fabric-server-launch.jar" in jars or (folder / ".fabric").is_dir() or (folder / "fabric-server-launcher.properties").is_file():
        out.update(kind="fabric", jar="fabric-server-launch.jar" if "fabric-server-launch.jar" in jars else "server.jar")
        found = sorted((folder / "libraries" / "net" / "fabricmc" / "intermediary").glob("*")) if (folder / "libraries" / "net" / "fabricmc" / "intermediary").is_dir() else []
        if found:
            out["version"] = found[-1].name
    elif paper_jars or re.search(r"git-\w+-\d+ \(MC: ", history) or (folder / "config" / "paper-global.yml").is_file():
        out.update(kind="paper")
        if paper_jars:
            match = re.fullmatch(rf"paper-{VERSION}-(\d+)\.jar", paper_jars[-1])
            out.update(jar=paper_jars[-1], version=match.group(1), build=match.group(2))
        if match := re.search(r"git-(\w+)-(\d+) \(MC: " + VERSION + r"\)", history):
            flavor, build, version = match.groups()
            out["build"], out["version"] = out["build"] or build, out["version"] or version
            if flavor != "Paper":
                out["notes"].append(f"Es {flavor}: Nova lo trata como Paper. Funciona igual, pero al actualizarlo se instalaría Paper.")
    else:
        for name in ("server.jar", *jars):
            if name in jars and (version := _vanilla_version(folder / name)):
                out.update(kind="vanilla", jar=name, version=version)
                break
        if out["kind"] is None and jars:
            out["notes"].append("No se reconoció el tipo de servidor: elegilo vos.")
    if out["version"] is None:
        if match := re.search(r"Starting minecraft server version " + VERSION, _read_text(folder / "logs" / "latest.log")):
            out["version"] = match.group(1)
    if out["kind"] in ("paper", "vanilla") and out["jar"] is None:
        out["jar"] = "server.jar" if "server.jar" in jars else (jars[0] if len(jars) == 1 else None)
    if out["kind"] in (None, "vanilla", "paper", "fabric") and not jars:
        out["notes"].append("No hay ningún .jar en la carpeta: ¿es la carpeta del servidor?")
    if not (props or jars or modern):
        out["notes"].append("Esta carpeta no parece de un servidor de Minecraft.")
    return out


def _inside_nova(source):
    source = source.resolve()
    for guarded in (sl.root().resolve(), motor.ROOT.resolve()):
        if source == guarded or guarded in source.parents or source in guarded.parents:
            return True
    return False


def folder_size(source):
    return sl.folder_size(Path(source))


def import_server(source, *, name, kind, version, memory, port, jar=None, forge_build=None, build=None, accept_eula=False, progress=None, status=None):
    """Copy a server folder into Nova and register it. The original stays as it was."""
    status = status or (lambda text: None)
    source = Path(source)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Elegí una carpeta de servidor.")
    if _inside_nova(source):
        raise ValueError("Esa carpeta ya es parte de los datos de Nova.")
    name = sl.check_new(name, kind, version, memory, port)
    if kind == "forge" and not (forge_build and re.fullmatch(r"[0-9A-Za-z._+-]{1,40}", str(forge_build))):
        raise ValueError("Para un servidor Forge hace falta saber su compilación de Forge.")
    if jar is not None and not JAR_RE.fullmatch(jar):
        raise ValueError("El nombre del .jar del servidor no es válido.")
    if kind != "forge" and not (source / (jar or "server.jar")).is_file():
        raise ValueError(f"No encontré {jar or 'server.jar'} en esa carpeta.")
    status("Buscando lo que pide esta versión…")
    info = sl.mojang_info(version)
    sid = uuid.uuid4().hex[:12]
    target = sl.folder(sid)
    files = sum(1 for _, _, names in os.walk(source) for n in names if n not in SKIP)
    copied = {"n": 0}

    def copy(src, dst, **kwargs):
        shutil.copy2(src, dst, **kwargs)
        copied["n"] += 1
        if progress and files:
            progress(copied["n"], files)

    status("Copiando el servidor…")
    try:
        shutil.copytree(source, target, symlinks=True, ignore=lambda directory, names: [n for n in names if n in SKIP], copy_function=copy)
        meta = {"id": sid, "name": name, "kind": kind, "version": version, "memory": int(memory), "port": int(port),
                "java_component": info["component"], "java_major": info["major"], "created": int(time.time()),
                "eula": bool(sl.eula_accepted(target) or accept_eula), "build": build, "imported": True}
        if jar and kind != "forge":
            meta["jar"] = jar
        if kind == "forge":
            meta["forge_build"] = str(forge_build)
        if sl.read_properties(target).get("server-port") != str(int(port)):
            sl.write_properties(target, {"server-port": str(int(port)), "query.port": str(int(port))})
        if accept_eula and not sl.eula_accepted(target):
            sl.write_eula(target)
        sl.save(meta)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return sl.load(sid)

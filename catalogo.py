"""Modrinth catalog and verified downloads for an instance."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import uuid
import zipfile

import requests

import motor

API = "https://api.modrinth.com/v2"
DESTINATIONS = {"mod": ("mods", ".jar"), "shader": ("shaderpacks", ".zip"),
                "resourcepack": ("resourcepacks", ".zip")}
PACK_LOADERS = {"forge": "forge", "neoforge": "neoforge", "fabric-loader": "fabric",
                "quilt-loader": "quilt"}


def api(path, **params):
    response = requests.get(API + path, params=params, timeout=20,
                            headers={"User-Agent": motor.USER_AGENT})
    response.raise_for_status()
    return response.json()


def search(query, category, instance, offset=0):
    facets = [[f"project_type:{category}"]]
    if category != "modpack":
        facets.append([f"versions:{instance['version']}"])
    if category == "mod":
        facets.append([f"categories:{instance['loader']}"])
    return api("/search", query=query, facets=json.dumps(facets), limit=18, offset=offset)


def releases(project, category, instance):
    params = {}
    if category != "modpack":
        params["game_versions"] = json.dumps([instance["version"]])
    if category == "mod":
        params["loaders"] = json.dumps([instance["loader"]])
    return api(f"/project/{project}/version", **params)


def download(version, destination, suffix):
    files = [item for item in version["files"] if item["filename"].endswith(suffix)]
    if not files:
        raise ValueError(f"La publicación no incluye archivos {suffix}.")
    item = next((entry for entry in files if entry["primary"]), files[0])
    name = item["filename"]
    if name != Path(name).name or not item["url"].startswith("https://cdn.modrinth.com/"):
        raise ValueError("El archivo tiene una ruta de descarga inválida.")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / name
    fetch_file(item["url"], target, item["hashes"]["sha512"])
    return target


def fetch_file(url, target, expected):
    digest = hashlib.sha512()
    target.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=45, stream=True,
                      headers={"User-Agent": motor.USER_AGENT}) as response:
        response.raise_for_status()
        with target.open("xb") as file:
            for chunk in response.iter_content(1024 * 256):
                file.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"No coincide la suma de verificación de {target.name}.")


def install_content(folder, instance, category, version, *, update=False):
    subfolder, suffix = DESTINATIONS[category]
    destination = folder / "game" / subfolder
    resolved = {}
    root_project = version["project_id"]

    def resolve(release):
        project = release["project_id"]
        if project in resolved:
            if resolved[project]["id"] != release["id"]:
                raise ValueError("Dos dependencias requieren versiones distintas del mismo mod.")
            return
        previous = installed.get(project)
        if previous and previous["id"] != release["id"] and not (update and project == root_project):
            raise ValueError("Ya hay otra versión instalada. Quitala desde Contenido instalado.")
        if category == "mod" and (instance["version"] not in release["game_versions"]
                                  or instance["loader"] not in release["loaders"]):
            raise ValueError("Una dependencia no es compatible con esta instancia.")
        resolved[project] = release
        for dependency in release["dependencies"]:
            if dependency["dependency_type"] != "required" or category != "mod":
                continue
            if dependency["version_id"]:
                resolve(api(f"/version/{dependency['version_id']}"))
            elif dependency["project_id"]:
                choices = releases(dependency["project_id"], category, instance)
                if not choices:
                    raise ValueError("No se encontró una versión compatible de una dependencia.")
                resolve(choices[0])
            else:
                raise ValueError(f"Instalá primero la dependencia {dependency['file_name']}.")

    with motor.instance_lock(folder), TemporaryDirectory(dir=folder) as temp:
        installed = motor.read(folder / "downloads.json", {})
        previous = installed.get(root_project)
        old = None
        if update:
            if category != "mod" or not previous or previous["category"] != "mod":
                raise ValueError("Este mod no está administrado por Nova.")
            if previous["id"] == version["id"]:
                return
            old = destination / previous["file"]
            if not old.is_file():
                old = old.with_name(old.name + ".disabled")
            if not old.is_file():
                raise ValueError("El archivo de la versión actual no está en la instancia.")
        resolve(version)
        staged = {}
        for project, release in resolved.items():
            previous = installed.get(project)
            if previous and not (update and project == root_project):
                existing = destination / previous["file"]
                if existing.is_file() or existing.with_name(existing.name + ".disabled").is_file():
                    continue
            file = download(release, Path(temp), suffix)
            target = destination / file.name
            disabled = target.with_name(target.name + ".disabled")
            if any(candidate.exists() and candidate != old for candidate in (target, disabled)):
                raise ValueError(f"Ya existe {file.name} en la instancia.")
            staged[project] = file
        destination.mkdir(parents=True, exist_ok=True)
        placed = []
        backup = None
        try:
            for project, file in staged.items():
                target = destination / file.name
                entry = {"id": resolved[project]["id"], "file": file.name,
                         "category": category, "name": resolved[project]["name"]}
                if old and project == root_project:
                    prior = {k: v for k, v in installed[project].items() if k != "rollback"}
                    token = uuid.uuid4().hex
                    backup = folder / "mod-backups" / token
                    backup.parent.mkdir(exist_ok=True)
                    old.rename(backup)
                    entry["rollback"] = {"token": token, "entry": prior}
                    if old.name.endswith(".disabled"):
                        target = target.with_name(target.name + ".disabled")
                file.rename(target)
                placed.append(target)
                installed[project] = entry
            motor.save(folder / "downloads.json", installed)
        except OSError:
            for file in placed:
                file.unlink(missing_ok=True)
            if backup and backup.exists():
                backup.rename(old)
            raise


def restore_mod(folder, project):
    with motor.instance_lock(folder), TemporaryDirectory(dir=folder) as temp:
        database = folder / "downloads.json"
        entries = motor.read(database, {})
        current = entries.get(project)
        if not current or not current.get("rollback"):
            raise ValueError("No hay una versión anterior guardada.")
        rollback = current["rollback"]
        backup = folder / "mod-backups" / rollback["token"]
        mods = folder / "game" / "mods"
        active = mods / current["file"]
        disabled = not active.is_file()
        if disabled:
            active = active.with_name(active.name + ".disabled")
        previous = rollback["entry"]
        target = mods / (previous["file"] + (".disabled" if disabled else ""))
        alternate = mods / (previous["file"] + ("" if disabled else ".disabled"))
        if not active.is_file() or not backup.is_file():
            raise ValueError("Falta el archivo instalado o su copia anterior.")
        if alternate.exists() or (target.exists() and target != active):
            raise ValueError("Ya hay un archivo con el nombre de la versión anterior.")
        displaced = Path(temp) / "current.jar"
        active.rename(displaced)
        try:
            backup.rename(target)
            entries[project] = previous
            motor.save(database, entries)
        except OSError:
            if target.exists():
                target.rename(backup)
            displaced.rename(active)
            raise


def pack_path(name):
    path = Path(name)
    if path.is_absolute() or not path.parts or ".." in path.parts or "\\" in name:
        raise ValueError("El modpack contiene una ruta inválida.")
    return path


def import_pack(path, memory):
    parent = motor.ROOT / "instances"
    parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as pack, TemporaryDirectory(dir=parent) as temporary:
        info = pack.getinfo("modrinth.index.json")
        if info.file_size > 10_000_000:
            raise ValueError("El índice del modpack es demasiado grande.")
        index = json.loads(pack.read(info))
        if index["game"] != "minecraft" or index["formatVersion"] != 1:
            raise ValueError("Formato de modpack no compatible.")
        deps = index["dependencies"]
        if "minecraft" not in deps or set(deps) - {"minecraft", *PACK_LOADERS} or len(deps) > 2:
            raise ValueError("El modpack requiere un loader que Nova no reconoce.")
        if any(not re.fullmatch(r"[A-Za-z0-9._+-]+", v) or v in {".", ".."} for v in deps.values()):
            raise ValueError("El modpack tiene una versión inválida.")
        loader = next((key for key in PACK_LOADERS if key in deps), None)
        staged = Path(temporary) / "instance"
        game = staged / "game"
        game.mkdir(parents=True)
        for item in index["files"]:
            if item.get("env", {}).get("client", "required") != "required":
                continue
            target = game / pack_path(item["path"])
            mirrors = [url for url in item["downloads"] if url.startswith((
                "https://cdn.modrinth.com/", "https://github.com/",
                "https://raw.githubusercontent.com/", "https://gitlab.com/",
            ))]
            if not mirrors:
                raise ValueError("El modpack incluye un archivo de un servidor no compatible.")
            if target.exists():
                raise ValueError(f"El modpack repite la ruta {item['path']}.")
            for url in mirrors:
                try:
                    fetch_file(url, target, item["hashes"]["sha512"])
                except (requests.RequestException, ValueError) as error:
                    target.unlink(missing_ok=True)
                    last_error = error
                else:
                    break
            else:
                raise ValueError(f"No se pudo verificar {item['path']}: {last_error}") from last_error
        for prefix in ("overrides/", "client-overrides/"):
            for entry in pack.infolist():
                if entry.is_dir() or not entry.filename.startswith(prefix):
                    continue
                target = game / pack_path(entry.filename.removeprefix(prefix))
                target.parent.mkdir(parents=True, exist_ok=True)
                with pack.open(entry) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        settings = {**motor.DEFAULTS, "name": index["name"][:40], "memory": memory,
                    "artwork": 1, "version": deps["minecraft"], "pack": True,
                    "loader": PACK_LOADERS[loader] if loader else "vanilla",
                    "loader_version": deps[loader] if loader else ""}
        motor.save(staged / "instance.json", settings)
        return staged.rename(parent / uuid.uuid4().hex)


def install_pack(version, memory):
    with TemporaryDirectory() as temporary:
        return import_pack(download(version, Path(temporary), ".mrpack"), memory)

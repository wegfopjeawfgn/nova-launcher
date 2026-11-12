"""Create complete local instance copies and recover them as new instances."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import uuid
import zipfile

import catalogo
import motor


MANIFEST = "backup-manifest.json"


def build_manifest(root):
    """Size and SHA-256 of every file in a backup, relative to its root."""
    root = Path(root)
    manifest = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in {MANIFEST, "backup.json"}:
            with path.open("rb") as handle:
                manifest[relative] = [path.stat().st_size, hashlib.file_digest(handle, "sha256").hexdigest()]
    return manifest


def verify_backup(folder):
    """Return (state, problems): "ok", "dañado" or "sin_manifiesto" for backups made before 1.4.0."""
    folder = Path(folder)
    manifest = motor.read(folder / MANIFEST, None)
    if not isinstance(manifest, dict):
        return "sin_manifiesto", []
    problems = []
    for relative, expected in manifest.items():
        path = folder / relative
        try:
            size, digest = expected
            if path.is_symlink() or not path.is_file():
                problems.append(f"Falta {relative}")
                continue
            with path.open("rb") as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if path.stat().st_size != size or actual != digest:
                problems.append(f"Cambió {relative}")
        except (OSError, ValueError, TypeError):
            problems.append(f"No se pudo leer {relative}")
    return ("dañado" if problems else "ok"), problems


def describe_backup(folder):
    """Facts shown in the backup list, read from the backup itself."""
    folder = Path(folder)
    info = motor.read(folder / "backup.json", {})
    instance = motor.read(folder / "instance.json", {})
    return {"folder": folder, "name": instance.get("name", ""), "created": str(info.get("created", "")),
            "auto": bool(info.get("auto")), "source": str(info.get("source", "")),
            "size": int(info.get("size", 0) or 0), "worlds": int(info.get("worlds", 0) or 0),
            "mods": int(info.get("mods", 0) or 0)}


def list_backups():
    found = []
    for config in (motor.ROOT / "backups").glob("*/backup.json"):
        item = describe_backup(config.parent)
        if item["name"]:
            found.append(item)
    return sorted(found, key=lambda item: item["created"], reverse=True)


def copy_instance(source, mode, *, auto=False):
    destination = motor.ROOT / ("backups" if mode == "backup" else "instances")
    destination.mkdir(parents=True, exist_ok=True)
    with motor.instance_lock(source), TemporaryDirectory(dir=destination) as temporary:
        staged = Path(temporary) / "instance"

        def skip(path, names):
            omitted = {".nova.lock", "session.lock"} & set(names)
            if Path(path) == source:
                omitted |= {"minecraft.log"} & set(names)
            for name in set(names) - omitted:
                if (Path(path) / name).is_symlink():
                    raise ValueError(f"Quitá el enlace simbólico {name} antes de copiar la instancia.")
            return omitted

        shutil.copytree(source, staged, ignore=skip)
        settings = motor.read(staged / "instance.json", {})
        if not settings.get("name"):
            raise ValueError("La copia no contiene una instancia de Nova válida.")
        if mode == "backup":
            manifest = build_manifest(staged)
            motor.save(staged / MANIFEST, manifest)
            game = staged / "game"
            motor.save(staged / "backup.json", {
                "created": datetime.now().astimezone().isoformat(timespec="minutes"), "auto": auto,
                "source": source.name, "size": sum(size for size, _ in manifest.values()),
                "worlds": len([p for p in (game / "saves").glob("*") if p.is_dir()]) if (game / "saves").is_dir() else 0,
                "mods": len(list((game / "mods").glob("*.jar"))) if (game / "mods").is_dir() else 0})
        else:
            (staged / "backup.json").unlink(missing_ok=True)
            (staged / MANIFEST).unlink(missing_ok=True)
            suffix = " (restaurada)" if mode == "restore" else " (copia)"
            settings["name"] = settings["name"][:40-len(suffix)] + suffix
            motor.save(staged / "instance.json", settings)
        return staged.rename(destination / uuid.uuid4().hex)


def export_instance(source, destination, include_worlds):
    """Share portable settings, verified references and optional worlds."""
    extension = destination.suffix.lower()
    if extension not in {".zip", ".mrpack"}:
        raise ValueError("Guardá la instancia con extensión .zip o .mrpack.")

    with motor.instance_lock(source), TemporaryDirectory(dir=destination.parent) as temporary:
        settings = motor.read(source / "instance.json", {})
        dependencies = {"minecraft": settings["version"]}
        loader = settings["loader"]
        if loader != "vanilla":
            dependencies[{"fabric": "fabric-loader", "quilt": "quilt-loader"}.get(loader, loader)] = (
                settings["loader_version"] or "auto")
        manifest = {"formatVersion": 1, "name": settings["name"], "dependencies": dependencies}
        game = source / "game"
        manifest_name = "nova-pack.json"
        if extension == ".mrpack":
            if loader != "vanilla" and not settings["loader_version"]:
                raise ValueError("Fijá una versión del cargador antes de exportar un .mrpack.")
            manifest_name = "modrinth.index.json"
            manifest.update(game="minecraft", versionId="1.0.0", files=modrinth_references(game))
        staged = Path(temporary) / "instance.zip"
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(manifest_name, json.dumps(manifest))
            saves = game / "saves"
            total = 0
            if include_worlds:
                if game.is_symlink() or saves.is_symlink():
                    raise ValueError("La carpeta de mundos no puede ser un enlace simbólico.")
                for path in saves.rglob("*"):
                    if path.is_symlink():
                        raise ValueError("Quitá los enlaces simbólicos de los mundos antes de exportar.")
                    if path.is_file() and path.name != "session.lock":
                        total += path.stat().st_size
                        if total > 4 * 1024**3:
                            raise ValueError("Los mundos superan el límite de 4 GiB.")
                        archive.write(path, f"overrides/{path.relative_to(game).as_posix()}")
        staged.replace(destination)


def modrinth_references(game):
    files = {}
    for directory, suffix in catalogo.DESTINATIONS.values():
        root = game / directory
        if root.is_symlink():
            continue
        for path in sorted(root.glob(f"*{suffix}")):
            if path.is_symlink() or not path.is_file():
                continue
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha512").hexdigest()
            files.setdefault(digest, []).append(path)
    versions = catalogo.versions_by_hash(files)
    references = []
    for digest, paths in files.items():
        match = next((entry for entry in versions.get(digest, {}).get("files", [])
                      if entry["hashes"].get("sha512") == digest
                      and entry["hashes"].get("sha1")
                      and entry["url"].startswith("https://cdn.modrinth.com/")), None)
        if match:
            for path in paths:
                references.append({"path": path.relative_to(game).as_posix(),
                                   "hashes": match["hashes"], "downloads": [match["url"]],
                                   "fileSize": path.stat().st_size})
    return references


def worlds(folder, *, backups=False):
    directory = folder / "world-backups" if backups else folder / "game" / "saves"
    if not directory.is_dir() or directory.is_symlink() or directory.parent.is_symlink():
        return []
    return sorted(
        (path for path in directory.iterdir()
         if not path.is_symlink() and (path / "level.dat").is_file()),
        key=lambda path: path.name.casefold(),
    )


def copy_world(folder, source, *, restore=False):
    if source not in worlds(folder, backups=restore):
        raise ValueError("Ese mundo ya no está disponible.")
    destination = folder / "game" / "saves" if restore else folder / "world-backups"
    with motor.instance_lock(folder):
        destination.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink() or destination.parent.is_symlink():
            raise ValueError("La carpeta de destino debe ser local a la instancia.")
        with TemporaryDirectory(dir=destination) as temporary:
            staged = Path(temporary) / "world"

            def ignore(directory, names):
                for name in names:
                    if (Path(directory) / name).is_symlink():
                        raise ValueError("El mundo contiene un enlace simbólico.")
                return {"session.lock"} & set(names)

            shutil.copytree(source, staged, ignore=ignore)
            name = f"{source.name[:90]} (copia)" if restore else source.name[:90]
            target = destination / name
            index = 2
            while target.exists() or target.is_symlink():
                target = destination / f"{name} {index}"
                index += 1
            return staged.rename(target)


def prism_details(source):
    components = {entry["uid"]: entry["version"]
                  for entry in motor.read(source / "mmc-pack.json", {})["components"]
                  if entry.get("uid") and entry.get("version")}
    loaders = {"net.fabricmc.fabric-loader": "fabric", "net.minecraftforge": "forge",
               "net.neoforged": "neoforge", "org.quiltmc.quilt-loader": "quilt"}
    selected = [(loader, components[uid]) for uid, loader in loaders.items() if uid in components]
    version = components.get("net.minecraft")
    if not version or len(selected) > 1:
        raise ValueError("La instancia de Prism tiene una versión o un cargador incompatible.")
    loader, loader_version = selected[0] if selected else ("vanilla", "")
    for value in (version, loader_version):
        if value and (value in {".", ".."} or not all(
                char.isascii() and (char.isalnum() or char in ".+-_") for char in value)):
            raise ValueError("La instancia de Prism contiene una versión inválida.")
    game = next((source / name for name in (".minecraft", "minecraft")
                 if (source / name).is_dir() and not (source / name).is_symlink()), None)
    if game is None:
        raise ValueError("No se encontró la carpeta de Minecraft de Prism.")
    config = source / "instance.cfg"
    name = source.name
    if config.is_file():
        with config.open(encoding="utf-8", errors="replace") as stream:
            name = next((line.partition("=")[2].strip() for line in stream
                         if line.startswith("name=")), name)
    return name[:40] or source.name[:40], version, loader, loader_version, game


def import_prism(source, memory):
    name, version, loader, loader_version, game = prism_details(source)
    destination = motor.ROOT / "instances"
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination) as temporary:
        staged = Path(temporary) / "instance"

        def ignore(directory, names):
            excluded = {"session.lock", "logs", "crash-reports"} & set(names)
            for name in set(names) - excluded:
                if (Path(directory) / name).is_symlink():
                    raise ValueError("La instancia de Prism contiene un enlace simbólico.")
            return excluded

        shutil.copytree(game, staged / "game", ignore=ignore)
        motor.save(staged / "instance.json", {
            **motor.DEFAULTS, "name": name, "version": version, "loader": loader,
            "loader_version": loader_version, "memory": memory, "artwork": 1,
        })
        return staged.rename(destination / uuid.uuid4().hex)

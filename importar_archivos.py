"""Add content to an instance from files on this computer.

Understands mods (.jar), resource packs, shader packs and data packs (.zip) and recognises modpacks
(.mrpack or ZIP). Files are only inspected, never unpacked: a ZIP is read for its entry names and a few
small metadata files, and the original is copied byte for byte into the right folder of the instance.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
import zipfile

import motor

MiB = 1024 * 1024
MAX_BYTES = {"mod": 256 * MiB, "resourcepack": 1024 * MiB, "shader": 1024 * MiB, "datapack": 256 * MiB,
             "modpack": 2048 * MiB}
MAX_METADATA = MiB
KIND_NAMES = {"mod": "Mod", "resourcepack": "Textura", "shader": "Shader", "datapack": "Paquete de datos",
              "modpack": "Modpack"}
FOLDERS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}
JAR_LOADERS = (("fabric.mod.json", "fabric"), ("quilt.mod.json", "quilt"),
               ("META-INF/neoforge.mods.toml", "neoforge"), ("META-INF/mods.toml", "forge"),
               ("mcmod.info", "forge"))
ACCEPTS = {"fabric": {"fabric"}, "quilt": {"quilt", "fabric"}, "forge": {"forge"}, "neoforge": {"neoforge"}}
UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


@dataclass
class Item:
    path: Path
    kind: str = ""          # empty when the file is not recognised
    title: str = ""
    detail: str = ""
    loaders: tuple = ()
    problem: str = ""       # why it cannot be imported; empty when it can
    size: int = 0

    @property
    def ok(self):
        return bool(self.kind) and not self.problem


def human_size(size):
    for unit, step in (("GB", 1024 ** 3), ("MB", MiB), ("KB", 1024)):
        if size >= step:
            return f"{size / step:.1f} {unit}" if unit != "KB" else f"{size / step:.0f} KB"
    return f"{size} B"


def _read_json(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA:
        return {}
    try:
        data = json.loads(archive.read(info).decode("utf-8-sig", errors="replace"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _text(value, limit=80):
    return re.sub(r"\s+", " ", value).strip()[:limit] if isinstance(value, str) else ""


def _mod_metadata(archive, names):
    """Loaders the jar declares, plus a display name and version when they are easy to read."""
    loaders = tuple(dict.fromkeys(loader for entry, loader in JAR_LOADERS if entry in names))
    title = version = ""
    if "fabric.mod.json" in names:
        data = _read_json(archive, "fabric.mod.json")
        title, version = _text(data.get("name") or data.get("id")), _text(data.get("version"), 40)
    elif "quilt.mod.json" in names:
        meta = _read_json(archive, "quilt.mod.json").get("quilt_loader", {})
        meta = meta if isinstance(meta, dict) else {}
        info = meta.get("metadata", {}) if isinstance(meta.get("metadata"), dict) else {}
        title, version = _text(info.get("name") or meta.get("id")), _text(meta.get("version"), 40)
    else:
        toml = next((n for n in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml") if n in names), None)
        if toml and archive.getinfo(toml).file_size <= MAX_METADATA:
            text = archive.read(toml).decode("utf-8", errors="replace")
            found = re.search(r'^\s*displayName\s*=\s*"([^"\n]{1,80})"', text, re.M)
            title = _text(found.group(1)) if found else ""
            found = re.search(r'^\s*version\s*=\s*"([^"\n$]{1,40})"', text, re.M)
            version = _text(found.group(1), 40) if found else ""
    return loaders, title, version


def _inspect_jar(item):
    try:
        with zipfile.ZipFile(item.path) as archive:
            names = set(archive.namelist())
            loaders, title, version = _mod_metadata(archive, names)
    except (zipfile.BadZipFile, OSError):
        item.problem = "El archivo está dañado o no es un .jar válido."
        return item
    if not loaders:
        item.problem = ("No parece un mod: no declara Fabric, Quilt, Forge ni NeoForge. "
                        "Puede ser una librería u otro tipo de archivo.")
        return item
    item.kind = "mod"
    item.title = title or item.path.stem
    item.loaders = loaders
    names_loaders = " / ".join(motor.LOADERS[loader] for loader in loaders)
    item.detail = f"{names_loaders}" + (f" · {version}" if version else "")
    return item


def _pack_description(archive):
    meta = _read_json(archive, "pack.mcmeta").get("pack", {})
    description = meta.get("description") if isinstance(meta, dict) else None
    return _text(description) if isinstance(description, str) else ""


def _inspect_zip(item):
    try:
        with zipfile.ZipFile(item.path) as archive:
            names = set(archive.namelist())
            description = _pack_description(archive) if "pack.mcmeta" in names else ""
            is_modpack = ("modrinth.index.json" in names or "nova-pack.json" in names
                          or ("manifest.json" in names
                              and _read_json(archive, "manifest.json").get("manifestType") == "minecraftModpack"))
    except (zipfile.BadZipFile, OSError):
        item.problem = "El archivo está dañado o no es un .zip válido."
        return item
    item.title = item.path.stem
    if is_modpack:
        return _inspect_modpack(item)
    if any(name.startswith("shaders/") for name in names):
        item.kind = "shader"
        item.detail = "Paquete de shaders"
    elif "pack.mcmeta" in names:
        has_assets = any(name.startswith("assets/") for name in names)
        has_data = any(name.startswith("data/") for name in names)
        if has_data and not has_assets:
            item.kind, item.detail = "datapack", description or "Paquete de datos"
        else:
            item.kind, item.detail = "resourcepack", description or "Paquete de texturas"
    elif any(re.match(r"[^/]+/shaders/", name) for name in names):
        item.problem = ("Los shaders están dentro de una carpeta, y Minecraft no los reconocería. "
                        "Extraé el ZIP y volvé a comprimir el contenido de esa carpeta.")
    elif any(re.match(r"[^/]+/pack\.mcmeta$", name) for name in names):
        item.problem = ("El pack está dentro de una carpeta, y Minecraft no lo reconocería. "
                        "Extraé el ZIP y volvé a comprimir el contenido de esa carpeta.")
    else:
        item.problem = "No reconozco este ZIP: no es un pack de texturas, shaders, datos ni un modpack."
    return item


def _inspect_modpack(item):
    import catalogo  # heavy imports; only needed when a modpack shows up
    item.kind = "modpack"
    try:
        name, version, loader, _ = catalogo.pack_summary(item.path)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        item.problem = f"No se pudo leer el modpack: {error}"
        return item
    item.title = _text(name, 100) or item.path.stem
    item.detail = f"Minecraft {version} · {loader} · crea una instancia nueva"
    return item


def inspect(path):
    """Describe one file: what it is, whether it can be imported and, if not, why."""
    path = Path(path)
    item = Item(path=path, title=path.name)
    try:
        if not path.is_file():
            item.problem = "Elegí archivos, no carpetas. Para un pack, comprimilo en un .zip."
            return item
        item.size = path.stat().st_size
    except OSError as error:
        item.problem = f"No se puede leer el archivo: {error.strerror or error}"
        return item
    suffix = path.suffix.lower()
    if item.size == 0:
        item.problem = "El archivo está vacío."
    elif suffix == ".jar":
        _inspect_jar(item)
    elif suffix == ".zip":
        _inspect_zip(item)
    elif suffix == ".mrpack":
        _inspect_modpack(item)
    else:
        item.problem = f"Formato no admitido ({suffix or 'sin extensión'}). Se admiten .jar, .zip y .mrpack."
    limit = MAX_BYTES.get(item.kind)
    if item.ok and limit and item.size > limit:
        item.problem = f"Pesa {human_size(item.size)}; el máximo para este tipo es {human_size(limit)}."
    return item


def inspect_many(paths):
    seen, items = set(), []
    for path in paths:
        key = str(Path(path))
        if key not in seen:
            seen.add(key)
            items.append(inspect(path))
    return items


def warning(item, instance):
    """Something the person should know before importing; the import is still allowed."""
    loader = instance.get("loader", "vanilla")
    if item.kind == "mod":
        if loader == "vanilla":
            return "Esta instancia es Vanilla: no carga mods. Cambiá el cargador desde Editar."
        if item.loaders and not set(item.loaders) & ACCEPTS.get(loader, set()):
            needed = " o ".join(motor.LOADERS[name] for name in item.loaders)
            return f"Es un mod de {needed}, y esta instancia usa {motor.LOADERS[loader]}."
    if item.kind == "shader" and loader == "vanilla":
        return "Los shaders necesitan Iris u OptiFine. En una instancia Vanilla no se aplican."
    return ""


def worlds(folder):
    saves = folder / "game" / "saves"
    if not saves.is_dir():
        return []
    return sorted((entry.name for entry in saves.iterdir() if (entry / "level.dat").is_file()), key=str.casefold)


def safe_name(path):
    name = UNSAFE_NAME.sub("_", Path(path).name).strip(" .")
    suffix = Path(name).suffix.lower()
    stem = name[:-len(suffix)] if suffix else name
    return (stem[:120] or "archivo") + suffix


def destination(folder, item, world=None):
    if item.kind == "datapack":
        if not world:
            raise ValueError("Elegí el mundo donde instalar el paquete de datos.")
        if world not in worlds(folder):
            raise ValueError(f"El mundo «{world}» no existe en esta instancia.")
        return folder / "game" / "saves" / world / "datapacks"
    return folder / "game" / FOLDERS[item.kind]


def _digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(MiB):
            sha.update(chunk)
    return sha.hexdigest()


def _identical_file(directory, item):
    """An existing file in ``directory`` with exactly the same content, if there is one."""
    wanted = None
    for existing in directory.iterdir():
        if existing.is_file() and existing.stat().st_size == item.size:
            wanted = wanted or _digest(item.path)
            if _digest(existing) == wanted:
                return existing
    return None


def _free_name(directory, name, kind):
    def taken(candidate):
        return (directory / candidate).exists() or (kind == "mod" and (directory / (candidate + ".disabled")).exists())

    if not taken(name):
        return name
    stem, suffix = os.path.splitext(name)
    for number in range(2, 1000):
        candidate = f"{stem} ({number}){suffix}"
        if not taken(candidate):
            return candidate
    raise ValueError("Hay demasiadas copias de este archivo.")


def install(folder, item, world=None, progress=None):
    """Copy ``item`` into the instance. Returns ``(destination_path_or_None, message)``.

    Never overwrites: an identical file is skipped and a different one with the same name gets a
    number. The copy goes to a temporary name first, so an interrupted import leaves nothing behind.
    """
    if not item.ok or item.kind == "modpack":
        raise ValueError(item.problem or "Este archivo no se importa como contenido suelto.")
    directory = destination(folder, item, world)
    name = safe_name(item.path)
    with motor.instance_lock(folder):
        directory.mkdir(parents=True, exist_ok=True)
        existing = _identical_file(directory, item)
        if existing is not None:
            return None, f"{existing.name} ya estaba instalado."
        target = directory / _free_name(directory, name, item.kind)
        temporary = directory / f".{target.name}.{uuid.uuid4().hex[:8]}.nova-part"
        try:
            copied = 0
            with item.path.open("rb") as source, temporary.open("wb") as output:
                while chunk := source.read(MiB):
                    output.write(chunk)
                    copied += len(chunk)
                    if progress:
                        progress(copied, item.size)
                output.flush()
                os.fsync(output.fileno())
            if copied != item.size:
                raise OSError("El archivo cambió mientras se copiaba.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target, f"{target.name} instalado."

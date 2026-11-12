"""Nova Smart Mods: read mod metadata and report problems that can be verified from it.

A problem is only reported when the mods' own metadata proves it. Two mods being installed
together is never a reason on its own. Severity levels:
  "confirmado"  the metadata proves the problem (missing dependency, declared incompatibility...)
  "posible"     the metadata declares a conflict that may or may not affect this setup
  "aviso"       something worth knowing that does not stop the game
"""
import io
import json
from pathlib import Path
import re
import tomllib
import zipfile

SEVERITY_ORDER = {"confirmado": 0, "posible": 1, "aviso": 2}
# Dependencies that the game or the loader provides, not another mod.
BUILTIN = {"minecraft", "java", "fabricloader", "fabric-loader", "quilt_loader", "quilt-loader", "forge",
           "neoforge", "fml", "javafml", "lowcodefml", "mixin", "fabric", "quilt_base"}
LOADER_ALIASES = {"fabric": {"fabric"}, "quilt": {"quilt", "fabric"}, "forge": {"forge"},
                  "neoforge": {"neoforge"}, "vanilla": set()}
MAX_NESTED = 64
MAX_METADATA = 2 * 1024 * 1024


# ---- version ranges -------------------------------------------------------------------------

def parse_version(text):
    """Leading numeric parts of a version: '0.92.0+1.20.1' -> (0, 92, 0). None if there are none."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text))
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def _compare(left, right):
    size = max(len(left), len(right))
    left += (0,) * (size - len(left))
    right += (0,) * (size - len(right))
    return (left > right) - (left < right)


def _atom(version, atom):
    """True/False when the atom can be decided, None when it cannot."""
    atom = atom.strip()
    if atom in {"", "*", "x"}:
        return True
    match = re.fullmatch(r"(>=|<=|>|<|=|~|\^)?\s*v?([\dxX*]+(?:\.[\dxX*]+)*)(?:[-+].*)?", atom)
    if not match:
        return None
    operator, number = match.groups()
    parts = number.replace("X", "x").replace("*", "x").split(".")
    wildcard = "x" in parts
    numeric = tuple(int(part) for part in parts if part != "x")
    if wildcard:  # 1.21.x
        return version[:len(numeric)] == numeric
    if operator in (None, "="):
        return _compare(version, numeric) == 0 if len(numeric) >= len(version) else version[:len(numeric)] == numeric
    if operator == "~":
        return _compare(version, numeric) >= 0 and version[:max(1, len(numeric) - 1)] == numeric[:max(1, len(numeric) - 1)]
    if operator == "^":
        return _compare(version, numeric) >= 0 and version[:1] == numeric[:1]
    result = _compare(version, numeric)
    return {">=": result >= 0, "<=": result <= 0, ">": result > 0, "<": result < 0}[operator]


def _maven(version, text):
    """Maven/Forge ranges such as [1.21,1.22) or (,2.0]. Several ranges are alternatives."""
    outcomes = []
    for match in re.finditer(r"([\[(])\s*([^,\[\]()]*?)\s*(?:(,)\s*([^,\[\]()]*?))?\s*([\])])", text):
        opening, low, comma, high, closing = match.groups()
        if not comma:  # [1.21] means exactly that version
            exact = parse_version(low)
            outcomes.append(None if exact is None else _compare(version, exact) == 0)
            continue
        ok = True
        if low:
            bound = parse_version(low)
            if bound is None:
                outcomes.append(None)
                continue
            ok &= _compare(version, bound) > 0 if opening == "(" else _compare(version, bound) >= 0
        if high:
            bound = parse_version(high)
            if bound is None:
                outcomes.append(None)
                continue
            ok &= _compare(version, bound) < 0 if closing == ")" else _compare(version, bound) <= 0
        outcomes.append(ok)
    return outcomes


def satisfies(version, requirement):
    """True if the version meets the requirement, False if it provably does not, None if unknown."""
    if requirement is None:
        return True
    if isinstance(requirement, (list, tuple)):
        outcomes = [satisfies(version, item) for item in requirement]
        if True in outcomes:
            return True
        return None if None in outcomes else False
    actual = parse_version(version)
    text = str(requirement).strip()
    if actual is None:
        return None
    if text.startswith(("[", "(")):
        outcomes = _maven(actual, text)
        if not outcomes:
            return None
        if True in outcomes:
            return True
        return None if None in outcomes else False
    for alternative in text.split("||"):  # any alternative may match; inside one, all atoms must
        atoms = [piece for piece in re.split(r"[\s,]+", alternative.strip()) if piece]
        results = [_atom(actual, piece) for piece in atoms] or [True]
        if None in results:
            return None
        if all(results):
            return True
    return False


# ---- reading mods ---------------------------------------------------------------------------

def _json(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA:
        raise ValueError("metadata too large")
    return json.loads(archive.read(name).decode("utf-8-sig"))


def _toml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA:
        raise ValueError("metadata too large")
    return tomllib.loads(archive.read(name).decode("utf-8"))


def _fabric(data):
    depends, optional, breaks, conflicts = {}, {}, {}, {}
    for key, target in (("depends", depends), ("recommends", optional), ("suggests", optional),
                        ("breaks", breaks), ("conflicts", conflicts)):
        value = data.get(key)
        if isinstance(value, dict):
            target.update({str(name): requirement for name, requirement in value.items()})
    provides = [str(item) for item in data.get("provides", []) if isinstance(item, str)]
    return {"id": str(data.get("id", "")), "name": str(data.get("name") or data.get("id", "")),
            "version": str(data.get("version", "")), "depends": depends, "optional": optional,
            "breaks": breaks, "conflicts": conflicts, "provides": provides, "loader": "fabric"}


def _quilt(data):
    loader = data.get("quilt_loader", {})
    depends, breaks = {}, {}
    for key, target in (("depends", depends), ("breaks", breaks)):
        for item in loader.get(key, []):
            if isinstance(item, str):
                target[item] = None
            elif isinstance(item, dict) and item.get("id") and not item.get("optional"):
                target[str(item["id"])] = item.get("versions")
    provides = [str(item["id"] if isinstance(item, dict) else item) for item in loader.get("provides", [])
                if isinstance(item, (str, dict))]
    metadata = loader.get("metadata", {})
    return {"id": str(loader.get("id", "")), "name": str(metadata.get("name") or loader.get("id", "")),
            "version": str(loader.get("version", "")), "depends": depends, "optional": {}, "breaks": breaks,
            "conflicts": {}, "provides": provides, "loader": "quilt"}


def _forge(data, loader):
    mods = data.get("mods") or [{}]
    first = mods[0] if isinstance(mods[0], dict) else {}
    mod_id = str(first.get("modId", ""))
    depends, optional = {}, {}
    declared = data.get("dependencies", {})
    for item in declared.get(mod_id, []) if isinstance(declared, dict) else []:
        if not isinstance(item, dict) or not item.get("modId"):
            continue
        required = item.get("mandatory", item.get("type", "required") == "required")
        (depends if required in (True, "required") else optional)[str(item["modId"])] = item.get("versionRange")
    return {"id": mod_id, "name": str(first.get("displayName") or mod_id),
            "version": str(first.get("version", "")), "depends": depends, "optional": optional, "breaks": {},
            "conflicts": {}, "provides": [str(m.get("modId")) for m in mods[1:] if isinstance(m, dict) and m.get("modId")],
            "loader": loader}


def _read_archive(archive):
    """Metadata of every loader this jar declares, plus ids provided by jars nested inside it."""
    found = []
    names = set(archive.namelist())
    for name, parser in (("fabric.mod.json", _fabric), ("quilt.mod.json", _quilt)):
        if name in names:
            found.append(parser(_json(archive, name)))
    for name, loader in (("META-INF/neoforge.mods.toml", "neoforge"), ("META-INF/mods.toml", "forge")):
        if name in names:
            found.append(_forge(_toml(archive, name), loader))
    nested = []
    for name in sorted(names):
        if name.startswith("META-INF/jars/") and name.endswith(".jar") and len(nested) < MAX_NESTED:
            try:
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as inner:
                    nested.extend(_read_archive(inner)[0])
            except (zipfile.BadZipFile, ValueError, KeyError, OSError, RecursionError):
                continue
    return found, nested


def read_mod(path):
    """Describe one jar. Raises zipfile.BadZipFile or OSError when the file cannot be read."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        found, nested = _read_archive(archive)
    return {"file": path.name, "path": path, "disabled": path.name.lower().endswith(".disabled"),
            "metadata": found, "nested": nested}


# ---- analysis -------------------------------------------------------------------------------

def _issue(mod, severity, title, reason, fix, **extra):
    return {"mod": mod, "severity": severity, "title": title, "reason": reason, "fix": fix, **extra}


def analyze(mods_folder, instance):
    """Return a list of issues for the mods in a folder. Never changes any file."""
    issues = []
    loader = instance.get("loader", "vanilla")
    minecraft = instance.get("version", "")
    jars = sorted((p for p in Path(mods_folder).glob("*") if p.is_file() and p.name.lower().endswith((".jar", ".jar.disabled"))),
                  key=lambda p: p.name.casefold())
    mods = []
    for jar in jars:
        try:
            mods.append(read_mod(jar))
        except (zipfile.BadZipFile, OSError, ValueError, KeyError, UnicodeDecodeError, tomllib.TOMLDecodeError,
                json.JSONDecodeError, RecursionError) as error:
            issues.append(_issue(jar.name, "confirmado", "Archivo dañado",
                                 f"No se puede leer como un archivo JAR válido ({type(error).__name__}).",
                                 "Volvé a descargarlo o quitalo de la carpeta de mods.", file=jar.name))
    active = [mod for mod in mods if not mod["disabled"]]
    disabled = [mod for mod in mods if mod["disabled"]]

    def ids_of(group):
        result = {}
        for mod in group:
            for meta in mod["metadata"] + mod["nested"]:
                for key in [meta["id"], *meta["provides"]]:
                    if key:
                        result.setdefault(key, meta)
        return result

    provided = ids_of(active)
    provided_disabled = ids_of(disabled)
    allowed = LOADER_ALIASES.get(loader, set())
    seen = {}
    for mod in active:
        if not mod["metadata"]:
            issues.append(_issue(mod["file"], "aviso", "Sin información de mod",
                                 "El archivo no declara metadatos de Fabric, Quilt, Forge ni NeoForge. "
                                 "Puede ser una biblioteca o un mod muy antiguo.", "No hace falta actuar si funciona.",
                                 file=mod["file"]))
            continue
        usable = [meta for meta in mod["metadata"] if meta["loader"] in allowed]
        if not usable:
            names = ", ".join(sorted({meta["loader"] for meta in mod["metadata"]}))
            issues.append(_issue(mod["file"], "confirmado", "Cargador incorrecto",
                                 f"Está hecho para {names} y esta instancia usa {loader}.",
                                 "Buscá la versión para el cargador de la instancia o quitá el mod.", file=mod["file"]))
            continue
        meta = usable[0]
        label = meta["name"] or mod["file"]
        if meta["id"]:
            seen.setdefault(meta["id"], []).append((mod, meta))
        requirement = meta["depends"].get("minecraft")
        if requirement is not None and minecraft and satisfies(minecraft, requirement) is False:
            issues.append(_issue(label, "confirmado", "Versión de Minecraft incompatible",
                                 f"Pide Minecraft {requirement} y la instancia usa {minecraft}.",
                                 "Instalá la versión del mod para tu versión de Minecraft.", file=mod["file"]))
        for dependency, needed in meta["depends"].items():
            if dependency in BUILTIN or dependency == "minecraft":
                continue
            target = provided.get(dependency)
            if target is None:
                where = provided_disabled.get(dependency)
                fix = ("Activá el mod desactivado que lo incluye." if where else
                       f"Instalá {dependency} (buscalo en Explorar).")
                issues.append(_issue(label, "confirmado", "Falta una dependencia",
                                     f"Necesita «{dependency}» y no está instalada.", fix, file=mod["file"]))
            elif needed is not None and target["version"] and satisfies(target["version"], needed) is False:
                issues.append(_issue(label, "confirmado", "Versión de dependencia incompatible",
                                     f"Necesita {dependency} {needed} y está instalada la {target['version']}.",
                                     "Actualizá o cambiá la dependencia a una versión compatible.", file=mod["file"]))
        for key, severity, title in (("breaks", "confirmado", "Incompatibilidad declarada"),
                                     ("conflicts", "posible", "Posible conflicto declarado")):
            for other, needed in meta[key].items():
                target = provided.get(other)
                if target is None or target is meta:
                    continue
                hit = True if not needed or not target["version"] else satisfies(target["version"], needed)
                if hit:
                    issues.append(_issue(label, severity, title,
                                         f"El propio mod declara que {'rompe' if key == 'breaks' else 'puede chocar'} "
                                         f"con «{other}»{' ' + str(needed) if needed else ''} y está instalado.",
                                         "Quitá uno de los dos o buscá versiones que lo resuelvan.", file=mod["file"]))
    for mod_id, entries in seen.items():
        if len({entry[0]["file"] for entry in entries}) > 1:
            files = [entry[0]["file"] for entry in entries]
            older = sorted(entries, key=lambda e: parse_version(e[1]["version"]) or (0,))[0][0]
            issues.append(_issue(mod_id, "confirmado", "Mod duplicado",
                                 "El mismo mod está instalado en varios archivos: " + ", ".join(files) + ".",
                                 f"Desactivá uno; el más antiguo parece ser {older['file']}.", file=older["file"],
                                 action="disable"))
    issues.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], str(item["mod"]).casefold()))
    return issues


def disable(path):
    """Rename a .jar to .jar.disabled. Reversible; the caller must have asked the user first."""
    path = Path(path)
    if path.suffix.lower() != ".jar":
        raise ValueError("Solo se pueden desactivar archivos .jar.")
    target = path.with_name(path.name + ".disabled")
    if target.exists():
        raise FileExistsError(target.name)
    path.rename(target)
    return target

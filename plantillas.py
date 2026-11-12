"""Instance templates and portable profiles.

A template only pre-fills the "new instance" form. A profile is a JSON file with an instance's
portable settings. Importing one never installs anything by itself: it opens the form so the user
reviews every value first. The Java path is never exported, because it only makes sense on one machine."""
import json
from pathlib import Path
import re

import motor

PROFILE_MARK = "nova-profile"
PROFILE_VERSION = 1
MAX_PROFILE_BYTES = 256 * 1024
RESOLUTIONS = {"default", "854x480", "1280x720", "1600x900", "1920x1080", "2560x1440"}
G1 = "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200"

TEMPLATES = {
    "vanilla": {"title": "Minecraft Vanilla", "detail": "El juego sin mods, con ajustes estándar.",
                "loader": "vanilla", "memory": 4, "jvm_args": ""},
    "supervivencia": {"title": "Supervivencia", "detail": "Vanilla con la recolección de basura G1 ajustada.",
                      "loader": "vanilla", "memory": 4, "jvm_args": G1},
    "pvp": {"title": "PvP", "detail": "Fabric con memoria moderada, pensado para añadir mods de rendimiento.",
            "loader": "fabric", "memory": 4, "jvm_args": G1},
    "modpacks": {"title": "Modpacks", "detail": "Fabric con más memoria para paquetes de muchos mods.",
                 "loader": "fabric", "memory": 6, "jvm_args": G1},
    "rendimiento": {"title": "Rendimiento", "detail": "Fabric con poca memoria para sumar mods de optimización.",
                    "loader": "fabric", "memory": 3, "jvm_args": G1},
    "creativo": {"title": "Creativo", "detail": "Vanilla con memoria extra para construir en mundos grandes.",
                 "loader": "vanilla", "memory": 6, "jvm_args": G1},
    "experimentacion": {"title": "Experimentación", "detail": "Fabric para probar mods y versiones sin riesgo.",
                        "loader": "fabric", "memory": 4, "jvm_args": G1,
                        "notes": "Instancia de pruebas"},
}


def apply_template(key, *, ram_mb=None):
    """Settings for a new instance. Memory never goes above half of the installed RAM when it is known."""
    if key not in TEMPLATES:
        raise ValueError("Esa plantilla no existe.")
    template = TEMPLATES[key]
    memory = template["memory"]
    if ram_mb:
        memory = max(1, min(memory, int(ram_mb * 0.5) // 1024))
    settings = {"loader": template["loader"], "memory": memory, "jvm_args": template["jvm_args"]}
    if template.get("notes"):
        settings["notes"] = template["notes"]
    motor.parse_jvm_args(settings["jvm_args"])  # a template must never ship arguments Nova refuses
    return settings


def export_profile(instance, mods=()):
    """Portable description of an instance. `mods` is [(id, name, version)], kept only for reference."""
    return {
        "format": PROFILE_MARK, "format_version": PROFILE_VERSION,
        "name": str(instance.get("name", ""))[:40], "version": instance.get("version", ""),
        "loader": instance.get("loader", "vanilla"), "loader_version": instance.get("loader_version", ""),
        "memory": instance.get("memory", 4), "jvm_args": instance.get("jvm_args", ""),
        "resolution": instance.get("resolution", "default"), "notes": str(instance.get("notes", ""))[:160],
        "mods": [{"id": str(m[0])[:100], "name": str(m[1])[:100], "version": str(m[2])[:50]} for m in list(mods)[:500]],
    }


def read_profile(path):
    """Validate a profile file and return clean settings. Raises ValueError with a message for the user."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_PROFILE_BYTES:
            raise ValueError("El perfil es demasiado grande.")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("No se pudo leer el archivo del perfil.") from error
    except json.JSONDecodeError as error:
        raise ValueError("El archivo no es un perfil de Nova válido.") from error
    if not isinstance(data, dict) or data.get("format") != PROFILE_MARK:
        raise ValueError("El archivo no es un perfil de Nova válido.")
    if data.get("format_version") != PROFILE_VERSION:
        raise ValueError("Este perfil es de una versión de Nova que no se entiende.")

    def text(key, limit, default=""):
        value = data.get(key, default)
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"El campo «{key}» del perfil no es válido.")
        return value.strip()

    name = text("name", 40)
    version = text("version", 32)
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,32}", version):
        raise ValueError("La versión de Minecraft del perfil no es válida.")
    loader = text("loader", 16, "vanilla")
    if loader not in motor.LOADERS:
        raise ValueError("El cargador del perfil no existe en Nova.")
    loader_version = text("loader_version", 64)
    if loader_version and not re.fullmatch(r"[0-9A-Za-z._+-]{1,64}", loader_version):
        raise ValueError("La versión del cargador del perfil no es válida.")
    memory = data.get("memory", 4)
    if not isinstance(memory, int) or isinstance(memory, bool) or not 1 <= memory <= 64:
        raise ValueError("La RAM del perfil debe ser un entero entre 1 y 64 GB.")
    jvm_args = text("jvm_args", 500)
    motor.parse_jvm_args(jvm_args)
    resolution = text("resolution", 16, "default")
    if resolution not in RESOLUTIONS:
        resolution = "default"
    mods = []
    for item in data.get("mods", [])[:500] if isinstance(data.get("mods", []), list) else []:
        if isinstance(item, dict) and all(isinstance(item.get(k, ""), str) for k in ("id", "name", "version")):
            mods.append({k: item.get(k, "")[:100] for k in ("id", "name", "version")})
    return {"name": name, "version": version, "loader": loader, "loader_version": loader_version, "memory": memory,
            "jvm_args": jvm_args, "resolution": resolution, "notes": text("notes", 160), "mods": mods}


def describe_profile(profile):
    """Lines shown to the user before anything is created."""
    lines = [f"Minecraft {profile['version']} · {motor.LOADERS[profile['loader']]}"
             + (f" {profile['loader_version']}" if profile["loader_version"] else ""),
             f"RAM: {profile['memory']} GB"]
    if profile["jvm_args"]:
        lines.append("Argumentos de Java: " + profile["jvm_args"])
    if profile["resolution"] != "default":
        lines.append("Ventana: " + profile["resolution"].replace("x", " × "))
    if profile["notes"]:
        lines.append("Notas: " + profile["notes"])
    if profile["mods"]:
        lines.append(f"Mods de referencia: {len(profile['mods'])} (no se instalan automáticamente)")
    return lines

"""Nova Repair: find problems in an instance and apply the few repairs that are safe.

Every finding says what was found, what it means, what it can cause and how to fix it.
Repairs never delete files; they only rewrite instance.json after keeping a timestamped copy.
"""
from datetime import datetime
import os
from pathlib import Path
import shutil

import motor

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
TEMPORARY_SUFFIXES = (".part", ".tmp", ".download", ".crdownload")


def physical_memory_mb():
    """Installed RAM in MiB, or None when the system does not say."""
    try:
        if os.name == "nt":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("free", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pf", ctypes.c_ulonglong),
                            ("vt", ctypes.c_ulonglong), ("vf", ctypes.c_ulonglong), ("ef", ctypes.c_ulonglong)]

            status = Status(length=ctypes.sizeof(Status))
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.total // 1024**2)
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, AttributeError):
        return None
    return None


def _finding(key, severity, title, meaning, consequence, fix, **extra):
    return {"id": key, "severity": severity, "title": title, "meaning": meaning,
            "consequence": consequence, "fix": fix, "action": None, **extra}


def invalid_settings(instance):
    """Fields of instance.json that cannot work, as {field: reason}."""
    problems = {}
    memory = instance.get("memory")
    if not isinstance(memory, int) or isinstance(memory, bool) or not 1 <= memory <= 64:
        problems["memory"] = "La RAM asignada debe ser un número entero de GB entre 1 y 64."
    try:
        motor.parse_jvm_args(instance.get("jvm_args", ""))
    except ValueError as error:
        problems["jvm_args"] = str(error)
    if instance.get("loader") not in motor.LOADERS:
        problems["loader"] = "El cargador guardado no existe en esta versión de Nova."
    if not isinstance(instance.get("version"), str) or not instance.get("version"):
        problems["version"] = "Falta la versión de Minecraft."
    return problems


def diagnose(folder, instance, *, shared=None, java=None, memory_mb=None):
    """List the findings for one instance. `java` and `memory_mb` can be passed in for tests."""
    folder = Path(folder)
    shared = Path(shared) if shared else motor.ROOT / "minecraft"
    found = []
    problems = invalid_settings(instance)
    if problems:
        repairable = [name for name in problems if name in {"memory", "jvm_args"}]
        found.append(_finding(
            "settings", "error", "Configuración incorrecta",
            "; ".join(problems.values()),
            "Minecraft puede no iniciar o usar valores inesperados.",
            "Corregí los valores en Editar instancia." if not repairable else
            "Nova puede restablecer RAM y argumentos de Java a valores seguros (guarda una copia antes).",
            action="reset_settings" if repairable else None))
    version = instance.get("version", "")
    metadata = shared / "versions" / version / f"{version}.json" if version else None
    jar = shared / "versions" / version / f"{version}.jar" if version else None
    if metadata and metadata.is_file():
        if not jar.is_file() or jar.stat().st_size == 0:
            found.append(_finding(
                "install", "error", "Instalación incompleta",
                f"Existe la información de Minecraft {version} pero falta su archivo principal.",
                "El juego no va a abrir hasta completarla.",
                "Usá Más acciones → Reparar instalación para volver a descargarla."))
        elif not (shared / "libraries").is_dir():
            found.append(_finding(
                "libraries", "error", "Faltan las bibliotecas",
                "La carpeta de bibliotecas compartida no existe.",
                "Minecraft se cierra al iniciar por clases que no encuentra.",
                "Usá Más acciones → Reparar instalación."))
    elif metadata:
        found.append(_finding(
            "install", "info", "Todavía no instalada",
            f"Minecraft {version} aún no se descargó en esta computadora.",
            "Nada falla: se instala la primera vez que jugás.", "Tocá Jugar para instalarla."))
    if not problems.get("version"):
        try:
            executable, required, detected = java() if java else motor.java_report(instance)
        except (OSError, ValueError, KeyError, ImportError, motor.subprocess.SubprocessError) as error:
            found.append(_finding("java", "warning", "No se pudo comprobar Java",
                                  f"La comprobación falló ({type(error).__name__}).",
                                  "Si Java no responde, Minecraft no va a iniciar.",
                                  "Revisá el ejecutable de Java en Editar instancia o en Ajustes."))
        else:
            custom = instance.get("java")
            if custom and not Path(custom).is_file():
                found.append(_finding("java", "error", "Java no encontrado",
                                      f"El ejecutable configurado no existe: {custom}",
                                      "Minecraft no va a iniciar.",
                                      "Elegí otro Java o dejá el campo vacío para usar el de Nova."))
            elif required and detected and detected < required:
                found.append(_finding("java", "error", "Java demasiado antiguo",
                                      f"Minecraft {version} necesita Java {required} y se detectó Java {detected}.",
                                      "El juego se cierra al iniciar con un error de versión de clase.",
                                      "Dejá el campo de Java vacío para que Nova use el compatible."))
    ram = memory_mb if memory_mb is not None else physical_memory_mb()
    memory = instance.get("memory")
    if "memory" not in problems and ram:
        if memory * 1024 > ram * 0.8:
            found.append(_finding("memory", "warning", "RAM asignada muy alta",
                                  f"Asignaste {memory} GB y la computadora tiene unos {ram // 1024} GB.",
                                  "El sistema puede quedarse sin memoria y volverse lento o cerrar el juego.",
                                  f"Bajá la RAM a {max(2, int(ram * 0.5) // 1024)} GB o menos en Editar instancia."))
        elif memory < 2 and instance.get("loader") != "vanilla":
            found.append(_finding("memory", "warning", "Poca RAM para mods",
                                  f"Tenés {memory} GB asignado con un cargador de mods.",
                                  "Con pocos GB los mods suelen dar tirones o cerrar el juego.",
                                  "Probá con 4 GB en Editar instancia."))
    leftovers = []
    for sub in ("mods", "resourcepacks", "shaderpacks"):
        directory = folder / "game" / sub
        if directory.is_dir():
            leftovers += [p.name for p in directory.iterdir() if p.is_file() and p.name.lower().endswith(TEMPORARY_SUFFIXES)]
    if leftovers:
        found.append(_finding(
            "partial", "warning", "Posibles descargas incompletas",
            "Hay archivos temporales: " + ", ".join(sorted(leftovers)[:5]) + (" …" if len(leftovers) > 5 else ""),
            "Pueden ser restos de una descarga cortada. Nova no los borra porque no sabe si son tuyos.",
            "Revisalos y borralos a mano si no los reconocés."))
    found.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["title"]))
    return found


def apply(action, folder):
    """Run one safe repair and return a summary of what changed. Raises ValueError for unknown actions."""
    if action != "reset_settings":
        raise ValueError("Reparación desconocida.")
    config = Path(folder) / "instance.json"
    instance = motor.read(config, None)
    if not isinstance(instance, dict):
        raise ValueError("No se pudo leer instance.json.")
    problems = invalid_settings(instance)
    changes = []
    if not {"memory", "jvm_args"} & set(problems):
        return changes
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config, config.with_name(f"instance.json.bak-{stamp}"))
    if "memory" in problems:
        changes.append(f"RAM: {instance.get('memory')!r} → 4 GB")
        instance["memory"] = 4
    if "jvm_args" in problems:
        changes.append("Argumentos de Java: vaciados")
        instance["jvm_args"] = ""
    motor.save(config, instance)
    return changes

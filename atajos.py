"""Create an application-menu shortcut that starts one Nova instance directly (Linux)."""
import os
from pathlib import Path
import re
import shutil

import motor

INSTANCE_ID = re.compile(r"[0-9a-f]{32}")


def valid_instance_id(value):
    return bool(INSTANCE_ID.fullmatch(value or ""))


def _quote(argument):
    """Quote one Exec argument following the Desktop Entry specification."""
    escaped = re.sub(r'(["`$\\])', r"\\\1", argument).replace("%", "%%")
    return f'"{escaped}"'


def launcher_path():
    installed = shutil.which("nova-launcher")
    if installed:
        return Path(installed)
    return Path(__file__).resolve().parent / "iniciar.sh"


def desktop_entry(instance_id, name, launcher):
    if not valid_instance_id(instance_id):
        raise ValueError("Identificador de instancia no válido.")
    title = re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip()[:60] or "Instancia"
    return ("[Desktop Entry]\nType=Application\n"
            f"Name={title} · Nova\n"
            f"Comment=Iniciar {title} con Nova Launcher\n"
            f"Exec={_quote(str(launcher))} --jugar {instance_id}\n"
            "Icon=io.nova.launcher\nTerminal=false\nCategories=Game;\n"
            "StartupWMClass=io.nova.launcher\n")


def shortcut_path(instance_id):
    if not valid_instance_id(instance_id):
        raise ValueError("Identificador de instancia no válido.")
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return data / "applications" / f"io.nova.launcher.{instance_id}.desktop"


def create(folder, name, launcher=None):
    if os.name == "nt":
        raise RuntimeError("Los atajos de instancia todavía solo están disponibles en Linux.")
    path = shortcut_path(folder.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(desktop_entry(folder.name, name, launcher or launcher_path()),
                             encoding="utf-8")
        temporary.chmod(0o755)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def remove(folder):
    try:
        shortcut_path(folder.name).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass

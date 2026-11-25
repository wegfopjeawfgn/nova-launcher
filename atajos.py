"""Create an application-menu shortcut that starts one Nova instance directly (Linux .desktop, Windows .lnk)."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


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


# Fixed script: every value comes from the environment, so an instance name can never become PowerShell code.
LNK_SCRIPT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:NOVA_LNK); "
              "$s.TargetPath = $env:NOVA_TARGET; $s.Arguments = $env:NOVA_ARGS; "
              "$s.WorkingDirectory = $env:NOVA_DIR; $s.Description = $env:NOVA_NOTE; $s.Save()")


def start_menu():
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / "Microsoft/Windows/Start Menu/Programs/Nova Launcher"


def lnk_name(name, tag=""):
    title = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]+', " ", name).strip(" .")[:60].strip(" .") or "Instancia"
    return f"{title}{tag} · Nova.lnk"


def windows_command(instance_id):
    """(target, arguments, folder) like the Start-menu entry of nova.iss: pythonw.exe "…\\nova.py" --jugar <id>."""
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    app = Path(__file__).resolve().parent
    return (str(windowless if windowless.is_file() else python),
            subprocess.list2cmdline([str(app / "nova.py"), "--jugar", instance_id]), str(app))


def create_windows(folder, name):
    if not valid_instance_id(folder.name):
        raise ValueError("Identificador de instancia no válido.")
    remove_windows(folder)  # a renamed instance must not leave its old shortcut behind
    path = start_menu() / lnk_name(name)
    if path.exists():  # another instance with the same name: keep both
        path = path.with_name(lnk_name(name, f" ({folder.name[:6]})"))
    path.parent.mkdir(parents=True, exist_ok=True)
    target, arguments, working = windows_command(folder.name)
    env = {**os.environ, "NOVA_LNK": str(path), "NOVA_TARGET": target, "NOVA_ARGS": arguments,
           "NOVA_DIR": working, "NOVA_NOTE": "Iniciar con Nova Launcher"}
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", LNK_SCRIPT], env=env,
                       capture_output=True, timeout=30, check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.SubprocessError as error:
        raise RuntimeError("Windows no dejó crear el acceso directo.") from error
    if not path.is_file():
        raise RuntimeError("Windows no dejó crear el acceso directo.")
    return path


def remove_windows(folder):
    """The .lnk is named after the instance, so find it by the id stored (UTF-16) in its arguments."""
    marker = folder.name.encode("utf-16-le")
    for link in start_menu().glob("*.lnk"):
        try:
            if marker in link.read_bytes():
                link.unlink()
        except OSError:
            pass


def create(folder, name, launcher=None):
    if os.name == "nt":
        return create_windows(folder, name)
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
    if os.name == "nt":
        remove_windows(folder)
        return
    try:
        shortcut_path(folder.name).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass

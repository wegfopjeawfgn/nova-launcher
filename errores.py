import platform
import traceback
from datetime import datetime

import motor
from nova_version import NOVA_VERSION

ISSUES_URL = "https://github.com/wegfopjeawfgn/nova-launcher/issues/new"


def log_path():
    return motor.ROOT / "errors.log"


def record(error, where):
    """Keep the traceback of a failure that the UI only shows as one line."""
    try:
        path = log_path()
        motor.rotate_log(path, keep=2)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {where}\n")
            handle.write("".join(traceback.format_exception(error)) + "\n")
    except OSError:
        pass  # logging must never hide the original failure


def report(lines=60):
    """Plain text to paste into an issue. Contains no paths or account names."""
    try:
        tail = log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        tail = []
    home = str(motor.Path.home())
    body = "\n".join(tail).replace(home, "~") or "Sin errores registrados."
    return (f"Nova {NOVA_VERSION} · {platform.system()} {platform.release()} · "
            f"Python {platform.python_version()}\n\n{body}")

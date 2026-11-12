"""Nova Insights: local-only play history. Nothing here touches the network."""
import math
import re
import sys
from datetime import datetime

import errores
import motor

FILE_NAME = "insights.json"
_HEADER = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] .+")


def _path():
    return motor.ROOT / FILE_NAME


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_id(value):
    return isinstance(value, str) and bool(value) and "/" not in value and "\\" not in value \
        and "\0" not in value and value not in (".", "..")


def _clean(entry):
    """Return a normalized session or None for anything malformed."""
    if not isinstance(entry, dict):
        return None
    instance, start, seconds = entry.get("instance"), entry.get("start"), entry.get("seconds")
    launch, ok = entry.get("launch"), entry.get("ok")
    if not _valid_id(instance) or not isinstance(start, str) or not _number(seconds) or seconds < 0:
        return None
    if launch is not None and not (_number(launch) and launch >= 0):
        return None
    if not isinstance(ok, bool):
        return None
    return {"instance": instance, "start": start, "seconds": int(seconds),
            "launch": None if launch is None else float(launch), "ok": ok}


def _load():
    try:
        data = motor.read(_path(), [])
    except OSError:
        return []
    if not isinstance(data, list):
        return []
    return [clean for clean in map(_clean, data) if clean]


def record_session(instance_id, *, started_at, seconds, launch_seconds=None, ok=True, limit=200):
    """Append one session, keeping only the last ``limit``. Returns True if stored."""
    if not _valid_id(instance_id) or not _number(started_at) or not _number(seconds):
        return False
    if launch_seconds is not None and not (_number(launch_seconds) and launch_seconds >= 0):
        launch_seconds = None
    if seconds < 1 or not isinstance(limit, int) or limit < 1:
        return False
    try:
        start = datetime.fromtimestamp(started_at).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return False
    sessions = _load()
    sessions.append({"instance": instance_id, "start": start, "seconds": int(seconds),
                     "launch": None if launch_seconds is None else float(launch_seconds),
                     "ok": bool(ok)})
    try:
        motor.save(_path(), sessions[-limit:])
    except OSError:
        return False
    return True


def summary(names=None):
    names = names or {}
    sessions = _load()
    launches = [item["launch"] for item in sessions if item["launch"] is not None]
    totals = {}
    for item in sessions:
        row = totals.setdefault(item["instance"], {"instance": item["instance"],
                                                   "name": names.get(item["instance"], item["instance"]),
                                                   "sessions": 0, "seconds": 0})
        row["sessions"] += 1
        row["seconds"] += item["seconds"]
    return {"sessions": len(sessions),
            "total_seconds": sum(item["seconds"] for item in sessions),
            "average_launch": sum(launches) / len(launches) if launches else None,
            "failed": sum(1 for item in sessions if not item["ok"]),
            "per_instance": sorted(totals.values(), key=lambda row: -row["seconds"]),
            "recent": sessions[-10:][::-1]}


def clear():
    path = _path()
    removed = False
    for target in (path, path.with_name(path.name + ".bak"), path.with_name(path.name + ".corrupt")):
        try:
            target.unlink()
            removed = removed or target == path
        except OSError:
            pass
    return removed


def describe():
    return ("Nova guarda solo en tu computadora: la fecha y hora de inicio, la duración, el tiempo "
            "de arranque, si terminó bien y el identificador de la instancia. Nada sale de tu "
            "computadora y puedes borrarlo cuando quieras.")


def _meminfo_mb(text, key):
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) // 1024
    return None


def system_memory_mb():
    result = {"total": None, "available": None}
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="utf-8") as handle:
                text = handle.read()
            result["total"] = _meminfo_mb(text, "MemTotal")
            result["available"] = _meminfo_mb(text, "MemAvailable")
        elif sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                result["total"] = status.ullTotalPhys // (1024 * 1024)
                result["available"] = status.ullAvailPhys // (1024 * 1024)
    except Exception:  # never raise: this only feeds an informational label
        return {"total": None, "available": None}
    return result


def recent_errors(limit=5):
    """Last ``[date] context`` headers of the error log; no tracebacks or paths."""
    try:
        lines = errores.log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    headers = [line.strip() for line in lines if _HEADER.match(line)]
    return headers[-limit:] if limit > 0 else []

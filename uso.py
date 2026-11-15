"""Optional anonymous usage count: once a day, a random install id, the Nova version and the OS family.

Off until the person says yes. Nothing else is sent: no account, name, IP address, instances or mods.
"""
import os
import sys
import time
import uuid

import requests

import motor
from nova_version import NOVA_VERSION

URL = os.environ.get("NOVA_USO_URL", "https://studiosnova.vercel.app/api/uso")
DAY = 86400


def _path():
    return motor.ROOT / "uso.json"


def system():
    return "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "otro"


def due(now=None):
    """The ping to send now, or ``None`` when one already went out in the last day."""
    data = motor.read(_path(), {})
    install = data.get("id") if isinstance(data.get("id"), str) and len(data["id"]) == 32 else uuid.uuid4().hex
    last = data.get("last") if isinstance(data.get("last"), (int, float)) else 0
    if (now or time.time()) - last < DAY:
        return None
    return {"id": install, "version": NOVA_VERSION, "os": system()}


def send(payload, now=None):
    """Post the ping; the day is only marked as done when the server accepted it. Never raises."""
    try:
        if requests.post(URL, json=payload, timeout=10, headers={"User-Agent": motor.USER_AGENT}).ok:
            motor.save(_path(), {"id": payload["id"], "last": now or time.time()})
            return True
    except (requests.RequestException, OSError):
        pass
    return False


def forget():
    """Delete the install id, so turning the count off leaves nothing that identifies this install."""
    _path().unlink(missing_ok=True)

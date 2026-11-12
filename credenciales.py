"""Keep the Microsoft session between runs in a file only the current user can read."""
import json
import os
import uuid

import motor


def _path():
    return motor.ROOT / "microsoft.json"


def save_session(client_id, session):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"microsoft.{uuid.uuid4().hex[:8]}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"client_id": client_id, "session": session}, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_session():
    """Return ``(client_id, session)`` or ``None`` when nothing usable is stored."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        client_id, session = data["client_id"], data["session"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    required = ("id", "name", "access_token", "refresh_token")
    if not isinstance(session, dict) or not all(session.get(key) for key in required):
        return None
    return client_id, session


def clear_session():
    _path().unlink(missing_ok=True)

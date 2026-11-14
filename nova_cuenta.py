"""Cuenta Nova: the same account as Nova Music, connected through the browser.

The launcher never sees the password. It asks the Nova Studios site for a short code, the person
approves that code on the site, and the launcher receives its own access token, kept in a file only
the current user can read. Nova Launcher has no paid plan: the account only provides name and avatar.
"""
import json
import os
import time
import uuid

import requests

import motor
from nova_version import NOVA_VERSION

API = os.environ.get("NOVA_CUENTA_URL", "https://studiosnova.vercel.app").rstrip("/")
HEADERS = {"User-Agent": f"NovaLauncher/{NOVA_VERSION}"}
TIMEOUT = 15


class CuentaError(Exception):
    """A message that can be shown to the person as is."""


def _path():
    return motor.ROOT / "nova-cuenta.json"


def _valid_user(user):
    return (isinstance(user, dict) and isinstance(user.get("username"), str) and user["username"].strip()
            and len(user["username"]) <= 50)


def _clean_user(user):
    emoji = user.get("avatar_emoji") if isinstance(user.get("avatar_emoji"), str) else ""
    return {"username": user["username"].strip(), "avatar_emoji": emoji[:16] or "😎"}


def save(token, user):
    """Store the access token and the public profile, readable only by the current user."""
    if not isinstance(token, str) or len(token) != 64 or not _valid_user(user):
        raise CuentaError("La respuesta de Nova no es válida.")
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"nova-cuenta.{uuid.uuid4().hex[:8]}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"token": token, "usuario": _clean_user(user)}, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load():
    """Return ``{"token", "usuario"}`` or ``None`` when nothing usable is stored."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        token, user = data["token"], data["usuario"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(token, str) or len(token) != 64 or not _valid_user(user):
        return None
    return {"token": token, "usuario": _clean_user(user)}


def clear():
    _path().unlink(missing_ok=True)


def _post(body, token=None):
    headers = dict(HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(f"{API}/api/dispositivo", json=body, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        raise CuentaError("No se pudo conectar con Nova Studios. Revisá tu conexión.") from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code == 429:
        return {"estado": "esperar"}
    if not response.ok:
        message = data.get("error") if isinstance(data, dict) else None
        raise CuentaError(message if isinstance(message, str) else "Nova Studios no respondió. Probá más tarde.")
    if not isinstance(data, dict):
        raise CuentaError("La respuesta de Nova no es válida.")
    return data


def start():
    """Ask for a connection code. Returns the code, the page to open and the polling schedule."""
    data = _post({"accion": "iniciar", "app": "launcher"})
    code, device, page = data.get("user_code"), data.get("device_code"), data.get("verification_uri_complete")
    # Only ever open a page on the configured Nova Studios site.
    if (not isinstance(code, str) or not isinstance(device, str) or not isinstance(page, str)
            or not page.startswith(API + "/conectar?")):
        raise CuentaError("La respuesta de Nova no es válida.")
    interval = data.get("interval") if isinstance(data.get("interval"), int) else 5
    expires = data.get("expires_in") if isinstance(data.get("expires_in"), int) else 600
    return {"codigo": code, "device_code": device, "pagina": page,
            "intervalo": min(max(interval, 2), 30), "vence": min(max(expires, 60), 1800)}


def wait_for_approval(connection, cancelled, poll=None, sleep=time.sleep, clock=time.monotonic):
    """Poll until the code is approved, denied or expired, or ``cancelled()`` returns true.

    Returns ``("aprobado", token, usuario)``, ``("rechazado",)``, ``("expirado",)`` or ``("cancelado",)``.
    """
    poll = poll or (lambda device: _post({"accion": "consultar", "device_code": device}))
    deadline = clock() + connection["vence"]
    delay = connection["intervalo"]
    while clock() < deadline:
        for _ in range(int(delay * 4)):
            if cancelled():
                return ("cancelado",)
            sleep(0.25)
        try:
            result = poll(connection["device_code"])
        except CuentaError:
            delay = min(delay * 2, 30)  # Brief network trouble: keep waiting, more slowly.
            continue
        state = result.get("estado")
        if state == "aprobado":
            return ("aprobado", result.get("token"), result.get("usuario"))
        if state in ("rechazado", "expirado"):
            return (state,)
        if state == "esperar":
            delay = min(delay + 5, 30)
    return ("expirado",)


def profile(token):
    """Fresh public profile, or ``None`` when the connection was revoked or expired."""
    try:
        response = requests.get(f"{API}/api/dispositivo", headers={**HEADERS, "Authorization": f"Bearer {token}"},
                                timeout=TIMEOUT)
    except requests.RequestException:
        raise CuentaError("No se pudo conectar con Nova Studios.") from None
    if response.status_code == 401:
        return None
    try:
        user = response.json().get("usuario")
    except (ValueError, AttributeError):
        user = None
    if not response.ok or not _valid_user(user):
        raise CuentaError("Nova Studios no respondió. Probá más tarde.")
    return _clean_user(user)


def revoke(token):
    """Tell the server to forget this launcher's token. Best effort: local sign-out happens anyway."""
    try:
        _post({"accion": "revocar"}, token)
    except CuentaError:
        pass

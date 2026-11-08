"""Connect an approved Microsoft desktop application using OAuth with PKCE."""
import threading
import uuid

from gi.repository import Gio, GLib
from minecraft_launcher_lib import microsoft_account as microsoft

REDIRECT = "http://localhost:8765"


def connect(app):
    app.accounts.popdown()

    def configure(value, _):
        client_id = str(uuid.UUID(value))
        url, state, verifier = microsoft.get_secure_login_data(client_id, REDIRECT)
        Gio.AppInfo.launch_default_for_uri(url, None)
        GLib.idle_add(request_callback, client_id, state, verifier)

    def request_callback(client_id, state, verifier):
        def finish(callback, _):
            try:
                code = microsoft.parse_auth_code_url(callback, state)
            except (AssertionError, KeyError, ValueError):
                raise ValueError("Pegá la URL completa de la redirección de este inicio de sesión.") from None
            app.status.set_text("Conectando con Microsoft…")

            def worker():
                try:
                    session = microsoft.complete_login(client_id, None, REDIRECT, code, verifier)
                    if not session.get("id") or not session.get("name"):
                        raise ValueError("Perfil no disponible")
                except Exception:
                    GLib.idle_add(app.status.set_text,
                                  "No se pudo iniciar sesión. Revisá que el ID tenga acceso a Minecraft Java.")
                else:
                    GLib.idle_add(app.use_microsoft, client_id, session)

            threading.Thread(target=worker, daemon=True).start()

        app.form("Completar inicio de sesión", "Pegá la URL a la que te envió el navegador", "", finish)

    app.form("Conectar Microsoft", "ID de aplicación aprobada · Redirección " + REDIRECT, "", configure)


def refresh(client_id, session):
    try:
        return microsoft.complete_refresh(client_id, None, REDIRECT, session["refresh_token"])
    except Exception:
        raise RuntimeError("La sesión de Microsoft venció. Volvé a conectarla desde Cuentas.") from None

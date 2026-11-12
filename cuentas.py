"""Connect an approved Microsoft desktop application using OAuth with PKCE."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import uuid

from gi.repository import Gio, GLib
from minecraft_launcher_lib import microsoft_account as microsoft

import errores
import seguridad

REDIRECT = "http://localhost:8765"
PAGE = ("<!doctype html><meta charset=utf-8><title>Nova Launcher</title>"
        "<body style='font-family:sans-serif;background:#10121a;color:#eee;text-align:center;padding-top:20vh'>"
        "<h2>Listo, podés volver a Nova Launcher.</h2><p>Esta pestaña ya se puede cerrar.</p>")


def wait_for_callback(state, timeout=180):
    """Listen on localhost for the OAuth redirect; return ``(url_getter, close)`` or ``None``."""
    result = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            accepted = seguridad.oauth_callback_ok(self.path, state)
            if accepted:
                result["url"] = REDIRECT + self.path
                done.set()
            self.send_response(200 if accepted else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode() if accepted else "Solicitud ignorada.".encode())

        def log_message(self, *_):
            pass

    try:
        server = HTTPServer(("127.0.0.1", 8765), Handler)
    except OSError:
        return None
    server.timeout = 1

    def serve():
        waited = 0
        while not done.is_set() and waited < timeout:
            server.handle_request()
            waited += 1
        server.server_close()
        done.set()

    threading.Thread(target=serve, daemon=True).start()
    return lambda: (done.wait(timeout + 5), result.get("url"))[1]


def connect(app):
    app.accounts.popdown()

    def configure(value, _):
        client_id = str(uuid.UUID(value))
        url, state, verifier = microsoft.get_secure_login_data(client_id, REDIRECT)
        waiter = wait_for_callback(state)
        Gio.AppInfo.launch_default_for_uri(url, None)
        if not waiter:
            GLib.idle_add(request_callback, client_id, state, verifier)
            return
        app.status.set_text("Esperando el inicio de sesión en el navegador…")

        def listen():
            callback = waiter()
            if not callback:
                GLib.idle_add(app.status.set_text, "No llegó la respuesta de Microsoft. Probá de nuevo.")
                return
            GLib.idle_add(safe_finish, client_id, state, verifier, callback)

        threading.Thread(target=listen, daemon=True).start()

    def safe_finish(client_id, state, verifier, callback):
        try:
            finish_login(client_id, state, verifier, callback)
        except ValueError as error:
            app.status.set_text(str(error))

    def finish_login(client_id, state, verifier, callback):
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
            except Exception as error:
                errores.record(error, "cuentas.worker")
                GLib.idle_add(app.status.set_text,
                              "No se pudo iniciar sesión (" + type(error).__name__ + "). "
                              "Revisá que el ID tenga acceso a Minecraft Java.")
            else:
                GLib.idle_add(app.use_microsoft, client_id, session)

        threading.Thread(target=worker, daemon=True).start()

    def request_callback(client_id, state, verifier):
        app.form("Completar inicio de sesión", "Pegá la URL a la que te envió el navegador", "",
                 lambda callback, _: finish_login(client_id, state, verifier, callback))

    app.form("Conectar Microsoft", "ID de aplicación aprobada · Redirección " + REDIRECT, "", configure)


def refresh(client_id, session):
    try:
        return microsoft.complete_refresh(client_id, None, REDIRECT, session["refresh_token"])
    except Exception as error:
        errores.record(error, "cuentas.refresh")
        raise RuntimeError("La sesión de Microsoft venció. Volvé a conectarla desde Cuentas.") from None

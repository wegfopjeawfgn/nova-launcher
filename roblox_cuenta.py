"""Sign in with Roblox (OAuth 2.0 + PKCE, public client). The password is typed on roblox.com, never in Nova.
Roblox's sign-in only shares identity (name, avatar): no friends and no presence, so Nova asks for nothing else and
throws the tokens away right after reading the profile."""
import base64
import hashlib
import http.server
import secrets
import threading
import urllib.parse

import requests

import motor

DEFAULT_CLIENT_ID = ""      # set when Nova has its own registered app; until then the person brings theirs
PORT = 53682
PATH = "/roblox"
AUTHORIZE = "https://apis.roblox.com/oauth/v1/authorize"
TOKEN = "https://apis.roblox.com/oauth/v1/token"
USERINFO = "https://apis.roblox.com/oauth/v1/userinfo"
REVOKE = "https://apis.roblox.com/oauth/v1/token/revoke"
CREATOR_HUB = "https://create.roblox.com/dashboard/credentials?activeTab=OAuthTab"
SIGN_UP = "https://www.roblox.com/CreateAccount"
FILE = motor.ROOT / "roblox-cuenta.json"
USER_AGENT = "NovaLauncher"


def redirect_uri(port=PORT):
    return f"http://localhost:{port}{PATH}"


def pkce():
    """(verifier, S256 challenge) as in RFC 7636."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def challenge_for(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorize_url(client_id, state, challenge, port=PORT):
    query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri(port), "scope": "openid profile",
                                    "response_type": "code", "code_challenge": challenge,
                                    "code_challenge_method": "S256", "state": state})
    return f"{AUTHORIZE}?{query}"


class _Wait(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path != PATH:
            self.send_response(404)
            self.end_headers()
            return
        self.server.result = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        body = ("<!doctype html><meta charset=utf-8><title>Nova Launcher</title>"
                "<body style='font-family:sans-serif;background:#0b0d12;color:#eef0f5;text-align:center;padding:4rem'>"
                "<h1>Listo</h1><p>Ya podés volver a Nova Launcher y cerrar esta pestaña.</p>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):
        pass


def wait_for_code(state, port=PORT, timeout=180, ready=None):
    """Listen on this PC only for Roblox's redirect; returns the authorization code."""
    server = http.server.HTTPServer(("127.0.0.1", port), _Wait)
    server.result = None
    server.timeout = timeout
    if ready:
        ready()
    timer = threading.Timer(timeout, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()
    result = server.result
    if not result:
        raise TimeoutError("No llegó la autorización de Roblox a tiempo.")
    if not secrets.compare_digest(result.get("state", ""), state):
        raise ValueError("La respuesta de Roblox no coincide con tu pedido; no se usó.")
    if result.get("error"):
        raise PermissionError("Cancelaste el inicio de sesión." if result["error"] == "access_denied"
                              else f"Roblox respondió: {result['error']}")
    if not result.get("code"):
        raise ValueError("Roblox no devolvió el código de autorización.")
    return result["code"]


def exchange(client_id, code, verifier, port=PORT):
    response = requests.post(TOKEN, data={"grant_type": "authorization_code", "code": code, "client_id": client_id,
                                          "code_verifier": verifier, "redirect_uri": redirect_uri(port)},
                             headers={"User-Agent": USER_AGENT}, timeout=20)
    if response.status_code != 200:
        raise ValueError(f"Roblox no aceptó la autorización ({response.status_code}). Revisá el ID de la aplicación y la redirección.")
    return response.json()


def profile(access_token):
    response = requests.get(USERINFO, headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    data = response.json()
    try:
        user_id = int(data["sub"])
    except (KeyError, ValueError, TypeError):
        raise ValueError("Roblox no devolvió tu identificador.")
    picture = data.get("picture") if str(data.get("picture", "")).startswith("https://") else ""
    name = data.get("preferred_username") or data.get("nickname") or str(user_id)
    return {"id": user_id, "name": str(name)[:40], "display": str(data.get("name") or name)[:40], "picture": picture}


def revoke(client_id, token):
    try:
        requests.post(REVOKE, data={"token": token, "client_id": client_id}, headers={"User-Agent": USER_AGENT}, timeout=10)
    except requests.RequestException:
        pass  # the tokens are short-lived and never saved; this is a courtesy


def login(client_id, open_url, port=PORT):
    """Open roblox.com's sign-in, wait for the redirect, read the profile, drop the tokens."""
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    url = authorize_url(client_id, state, challenge, port)
    code = wait_for_code(state, port, ready=lambda: open_url(url))
    tokens = exchange(client_id, code, verifier, port)
    try:
        return profile(tokens["access_token"])
    finally:
        for key in ("access_token", "refresh_token"):
            if tokens.get(key):
                revoke(client_id, tokens[key])


def load():
    data = motor.read(FILE, {})
    return data if isinstance(data.get("id"), int) else None


def save(person):
    motor.save(FILE, person)


def sign_out():
    try:
        FILE.unlink()
    except FileNotFoundError:
        pass

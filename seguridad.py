"""Small, dependency-free checks used where Nova accepts input from the network or the browser."""
from urllib.parse import parse_qs, urlsplit


def oauth_callback_ok(path, state):
    """True only for a redirect that carries the expected `state` and a code or an error.

    Anything else (a stray request, a replay, another site posting to localhost) is ignored, so it
    can neither finish nor spoil a login that is in progress."""
    query = parse_qs(urlsplit(path).query)
    if not state or query.get("state") != [state]:
        return False
    return "code" in query or "error" in query


def safe_update_url(url):
    """True for an https GitHub release download URL. Nova never fetches an installer from elsewhere."""
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname == "github.com" and parts.port is None
            and not parts.username and "/releases/download/" in parts.path and ".." not in parts.path)

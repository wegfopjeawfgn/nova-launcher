"""Text for the home strip at the top of the library: last game, downloads, account and Nova itself."""


def ago(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "hace un momento"
    minutes = seconds // 60
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"hace {hours} h"
    days = hours // 24
    return f"hace {days} día" + ("" if days == 1 else "s")


def summary(*, recent, names, now, downloading, queued, account, update):
    """Four cards: [{"key", "title", "text"}]. `recent` maps instance id -> last play time (epoch seconds),
    `names` maps instance id -> name, `account` is (kind, name) with kind "microsoft", "offline" or None."""
    last = None
    for key, when in (recent or {}).items():
        if key in names and isinstance(when, (int, float)) and not isinstance(when, bool):
            if last is None or when > last[1]:
                last = (key, when)
    cards = [{"key": "last", "title": "Última partida",
              "text": f"{names[last[0]]} · {ago(now - last[1])}" if last else "Todavía no jugaste"}]
    parts = []
    if downloading:
        parts.append("1 en curso")
    if queued:
        parts.append(f"{queued} en cola")
    cards.append({"key": "downloads", "title": "Descargas", "text": " · ".join(parts) or "Sin descargas"})
    kind, name = account if account else (None, "")
    if kind == "microsoft":
        text = f"Microsoft · {name}"
    elif kind == "offline":
        text = f"Sin conexión · {name}"
    else:
        text = "Sin cuenta: elegí un nombre"
    cards.append({"key": "account", "title": "Cuenta", "text": text})
    cards.append({"key": "nova", "title": "Nova", "text": f"Hay una versión nueva: {update}" if update else "Al día"})
    return cards

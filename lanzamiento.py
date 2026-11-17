"""What Nova's start screen says while Minecraft opens: maps the launcher's messages to four steps."""

STEPS = ("Preparar", "Archivos", "Iniciar Java", "En juego")


def stage(message):
    """(index of the current step, short text for people) for a message from the launch worker."""
    text = (message or "").strip()
    if text.startswith("Minecraft abierto"):
        return 3, "Minecraft se abrió. ¡A jugar!"
    if text.startswith("Iniciando"):
        return 2, text
    if text.startswith(("Descargando", "Preparando Java")) or (text.startswith("Preparando ") and "Minecraft" not in text):
        return 1, text
    return 0, text or "Preparando Minecraft…"


def state_of(step, current, failed=False):
    """'done', 'active', 'failed' or 'pending' for one step."""
    if step < current:
        return "done"
    if step == current:
        return "failed" if failed else ("done" if current == len(STEPS) - 1 else "active")
    return "pending"

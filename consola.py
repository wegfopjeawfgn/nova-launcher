"""Show the current Minecraft log and recognize common startup errors."""
import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


PATTERNS = (
    ("UnsupportedClassVersionError",
     "Esta versión necesita un Java más reciente. Revisá la ruta en Editar instancia."),
    ("OutOfMemoryError", "Java se quedó sin memoria. Revisá la RAM asignada en Editar instancia."),
    ("Could not reserve enough space",
     "Java no pudo reservar tanta memoria. Bajá la RAM asignada en Editar instancia."),
    ("Invalid maximum heap size", "La memoria asignada no es válida. Revisá la RAM en Editar instancia."),
    ("Unrecognized option", "Un argumento de Java no existe en esta versión. Revisá los argumentos extra."),
    ("GLFW error", "Falló la ventana gráfica. Actualizá los drivers de video o probá otra versión de Java."),
    ("Failed to create the window", "No se pudo crear la ventana de OpenGL. Revisá los drivers de video."),
    ("Address already in use", "Un puerto ya está en uso. Cerrá otras instancias de Minecraft."),
    ("UnsatisfiedLinkError", "Falta una biblioteca nativa. Usá Reparar en la instancia."),
    ("MixinApplyError", "Falló un mod al cargar. Buscá el primer error del registro y probá desactivar el mod indicado."),
    ("MixinTransformerError", "Falló un mod al cargar. Buscá el primer error del registro y probá desactivar el mod indicado."),
)
DEPENDENCY = re.compile(r"requires .* (missing|not installed)|missing mandatory dependencies|"
                        r"incompatible mods found|mod resolution encountered", re.I)


def diagnose(text):
    for marker, advice in PATTERNS[:2]:
        if marker in text:
            return advice
    if DEPENDENCY.search(text):
        return "Revisá las dependencias y versiones en Mods → Instalados."
    for marker, advice in PATTERNS[2:]:
        if marker in text:
            return advice
    return ""


def report(text, lines=80):
    """Build a shareable report: platform, Nova version, the hint and the log tail."""
    import platform
    from nova_version import NOVA_VERSION
    tail = "\n".join((text or "").splitlines()[-lines:])
    return (f"Nova Launcher {NOVA_VERSION} · {platform.system()} {platform.release()} · "
            f"Python {platform.python_version()}\n"
            f"Diagnóstico: {diagnose(text or '') or 'sin causa identificada'}\n\n{tail}")


def read_log(path):
    with path.open("rb") as log:
        size = log.seek(0, 2)
        log.seek(max(0, size - 160_000))
        return log.read(160_000).decode(errors="replace")


def open_console(parent, path):
    window = Gtk.Window(title="Registro de Minecraft", transient_for=parent,
                        default_width=800, default_height=490)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, css_classes=["menu"])
    status = Gtk.Label(xalign=0, wrap=True, css_classes=["muted"])
    box.append(status)
    copy = Gtk.Button(label="Copiar diagnóstico", halign=Gtk.Align.START)
    copy.connect("clicked", lambda _: (
        Gdk.Display.get_default().get_clipboard().set(
            report(previous)),
        copy.set_label("Diagnóstico copiado"),
    ))
    box.append(copy)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    scroll.set_child(view)
    box.append(scroll)
    window.set_child(box)
    previous = None
    last_read = None

    def update():
        nonlocal previous, last_read
        try:
            stat = path.stat()
            signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            if signature == last_read:
                return True
            text = read_log(path)
            last_read = signature
        except OSError:
            last_read = None
            status.set_text("Esperando el registro de Minecraft…")
            return True
        if text != previous:
            adjustment = scroll.get_vadjustment()
            at_end = adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 24
            buffer = view.get_buffer()
            buffer.set_text(text)
            if at_end:
                buffer.place_cursor(buffer.get_end_iter())
                view.scroll_mark_onscreen(buffer.get_insert())
            status.set_text(diagnose(text) or "Registro en vivo · Últimos 160 KB")
            previous = text
        return True

    update()
    timer = GLib.timeout_add(750, update)
    window.connect("close-request", lambda _: (GLib.source_remove(timer), False)[1])
    window.present()

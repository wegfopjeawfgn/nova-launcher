"""Show the current Minecraft log and recognize common startup errors."""
import re

from gi.repository import Gdk, GLib, Gtk


def diagnose(text):
    if "UnsupportedClassVersionError" in text:
        return "Esta versión necesita un Java más reciente. Revisá la ruta en Editar instancia."
    if "OutOfMemoryError" in text:
        return "Java se quedó sin memoria. Revisá la RAM asignada en Editar instancia."
    for line in text.splitlines():
        if re.search(r"requires .* (missing|not installed)|missing mandatory dependencies|"
                     r"incompatible mods found|mod resolution encountered", line, re.I):
            return "Revisá las dependencias y versiones en Mods → Instalados. "
    if "MixinApplyError" in text or "MixinTransformerError" in text:
        return "Falló un mod al cargar. Buscá el primer error del registro y probá desactivar el mod indicado."
    return ""


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
            diagnose(previous or "") or "Nova no identificó la causa en el registro de Minecraft."),
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

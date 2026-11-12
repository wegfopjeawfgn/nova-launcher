"""Nova window: descargas."""
import os
from pathlib import Path
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gio, Gtk

import historial
import motor
from widgets import label, button


class DescargasMixin:
    def record(self, entry, error, cancel, message):
        state = "ok" if not error else "cancelled" if cancel.is_set() else "error"
        self.history.finish(entry, state, message)
        if state == "ok":
            self.retries.pop(entry, None)
        if self.history_view:
            self.history_view()

    def set_download_progress(self, message):
        self.download_progress = message
        self.status.set_text(message)
        if self.download_view:
            text, cancel = self.download_view
            text.set_text(message)
            cancel.set_sensitive(self.cancel_download is not None)

    def show_downloads(self):
        dialog = Gtk.Window(title="Descargas", transient_for=self.window, modal=False, default_width=440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Centro de descargas", "subheading"))
        text = label(self.download_progress, "muted")
        text.set_wrap(True)
        box.append(text)

        def cancel_current():
            if self.cancel_download:
                self.cancel_download.set()
                text.set_text("Cancelando al terminar el archivo actual…")
                control.set_sensitive(False)

        control = button("Cancelar descarga", cancel_current)
        control.set_sensitive(self.cancel_download is not None)
        box.append(control)
        self.download_view = text, control
        box.append(label("Historial reciente", "subheading"))
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroller = Gtk.ScrolledWindow(min_content_height=170, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(rows)
        box.append(scroller)

        def retry(entry_id):
            action = self.retries.get(entry_id)
            if action and not self.busy and not self.cancel_download:
                action()

        def render():
            while (child := rows.get_first_child()):
                rows.remove(child)
            entries = self.history.recent()
            if not entries:
                rows.append(label("Todavía no hay descargas ni importaciones.", "muted"))
            for item in entries:
                line = Gtk.Box(spacing=8)
                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
                info.append(label(f"{item['title']} · {historial.STATES.get(item['state'], item['state'])}"))
                detail = label(f"{item['time'].replace('T', ' ')}  {item['message']}".strip(), "muted")
                detail.set_wrap(True)
                detail.set_max_width_chars(48)
                info.append(detail)
                line.append(info)
                if item["state"] in {"error", "cancelled"} and item["id"] in self.retries:
                    line.append(button("Reintentar", lambda i=item["id"]: retry(i)))
                rows.append(line)

        render()
        self.history_view = render
        box.append(button("Limpiar historial", lambda: (self.history.clear_finished(), render()), "quiet-button"))

        def closed(*_):
            self.history_view = None
            if self.download_view and self.download_view[0] is text:
                self.download_view = None
            return False

        dialog.connect("close-request", closed)
        dialog.set_child(box)
        dialog.present()

    def show_storage(self):
        dialog = Gtk.Window(title="Almacenamiento", transient_for=self.window, modal=True, default_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Almacenamiento de Nova", "subheading"))
        usage = label("Calculando…", "muted")
        usage.set_wrap(True)
        box.append(usage)
        cache = motor.ROOT / "pack-cache"

        def calculate():
            lines = []
            for name, directory in (("Instancias", "instances"), ("Respaldos", "backups"),
                                    ("Minecraft y Java", "minecraft"), ("Caché de modpacks", "pack-cache")):
                total = 0
                for root, _, files in os.walk(motor.ROOT / directory, followlinks=False):
                    for name_in_dir in files:
                        path = Path(root) / name_in_dir
                        try:
                            if not path.is_symlink():
                                total += path.stat().st_size
                        except OSError:
                            continue
                lines.append(f"{name} · {total / 1024**2:,.1f} MiB")
            GLib.idle_add(usage.set_text, "\n".join(lines))

        def clear():
            dialog.destroy()

            def task():
                with motor.file_lock(motor.ROOT / ".pack-cache.lock", blocking=True):
                    if cache.exists():
                        Gio.File.new_for_path(str(cache)).trash(None)

            self.background_file("Moviendo caché a la Papelera…", task, "Caché de modpacks limpiada.")

        remove = button("Mover la caché de modpacks a la Papelera", clear, "danger")
        remove.set_sensitive(cache.is_dir() and not self.busy)
        box.append(remove)
        dialog.set_child(box)
        dialog.present()
        threading.Thread(target=calculate, daemon=True).start()

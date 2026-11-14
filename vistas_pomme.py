"""Nova window: jugar una instancia con Pomme, el cliente de Minecraft Java escrito en Rust (no oficial)."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import cliente_pomme
import errores
import estadisticas
import tiempo
from widgets import label

ABOUT = ("Pomme es un cliente de Minecraft Java no oficial, escrito en Rust y todavía en desarrollo. "
         "No usa los mods de Java y tiene su propio inicio de sesión de Microsoft.")


class PommeMixin:
    def play_pomme(self):
        if cliente_pomme.supported() is None:
            self.status.set_text("Pomme todavía no tiene versión para este sistema.")
        elif cliente_pomme.installed():
            self.start_pomme()
        else:
            self.confirm_pomme_install()

    def confirm_pomme_install(self):
        dialog = Gtk.Dialog(title="Descargar Pomme", transient_for=self.window, modal=True, default_width=460)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Descargar y jugar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        box.append(label("Descargar Pomme", "subheading"))
        for text in (ABOUT, "Nova lo descarga desde github.com/PommeMC/Client y comprueba su suma SHA-256 antes de abrirlo."):
            line = label(text, "muted")
            line.set_wrap(True)
            box.append(line)

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.install_pomme(then=self.start_pomme)

        dialog.connect("response", respond)
        dialog.present()

    def install_pomme(self, then=None):
        if self.busy or self.parallel:
            return
        self.busy = True
        self.status.set_text("Descargando Pomme…")
        self.refresh()

        def progress(done, total):
            GLib.idle_add(self.status.set_text, f"Descargando Pomme… {done * 100 // total}%")

        def worker():
            try:
                info = cliente_pomme.install(progress)
            except (OSError, ValueError, RuntimeError, cliente_pomme.requests.RequestException) as error:
                GLib.idle_add(self.finished, f"No se pudo instalar Pomme: {error}")
            except Exception as error:
                errores.record(error, "vistas_pomme.install")
                GLib.idle_add(self.finished, f"No se pudo instalar Pomme: {error}")
            else:
                GLib.idle_add(done, info)

        def done(info):
            self.finished(f"Pomme {info['tag']} instalado.")
            if then:
                then()

        threading.Thread(target=worker, daemon=True).start()

    def start_pomme(self):
        folder, info = self.selected, cliente_pomme.installed()
        if folder is None or info is None or self.busy or self.parallel:
            return
        try:
            process = cliente_pomme.launch(info, folder)
        except OSError as error:
            self.status.set_text(f"No se pudo abrir Pomme: {error}")
            return
        self.busy = True
        self.library["selected"] = folder.name
        self.library.setdefault("recent", {})[folder.name] = time.time()
        self.save_library()
        self.status.set_text("Pomme está abierto. Iniciá sesión dentro del cliente.")
        self.refresh()
        began, wall = time.monotonic(), time.time()

        def finish(code):
            seconds = time.monotonic() - began
            tiempo.add(self.library, folder.name, seconds)
            self.save_library()
            estadisticas.record_session(folder.name, started_at=wall, seconds=seconds, launch_seconds=0, ok=code == 0)
            self.finished("Pomme se cerró." if code == 0 else
                          f"Pomme se cerró con el código {code}. Mirá pomme.log en la carpeta de la instancia.")

        threading.Thread(target=lambda: GLib.idle_add(finish, process.wait()), daemon=True).start()

"""Nova window: actualizar."""
import os
import shlex
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk

import actualizaciones
import motor
from widgets import label, button


class ActualizarMixin:
    def release_details(self):
        dialog = Gtk.Window(title="Versiones de Nova", transient_for=self.window, modal=True,
                            default_width=440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        box.append(label(f"Versión instalada · Nova {actualizaciones.VERSION}", "subheading"))
        notice = label("Launcher de terceros para Minecraft Java Edition. Sin afiliación con Mojang o Microsoft.",
                       "muted")
        notice.set_wrap(True)
        box.append(notice)
        release = getattr(self, "available_release", None)
        if release:
            tag, rpm, page, notes = release
            box.append(label(f"Nueva versión disponible · {tag}", "form-label"))
            if rpm:
                def save_update():
                    dialog.destroy()
                    self.save_file("Guardar actualización de Nova", rpm.rsplit("/", 1)[-1],
                                   lambda path: self.download_update(rpm, path, tag))

                box.append(button("Descargar instalador de Windows" if os.name == "nt" else
                                  "Descargar RPM para Fedora", save_update, "primary"))
            if notes:
                changelog = Gtk.TextView(editable=False, cursor_visible=False,
                                         wrap_mode=Gtk.WrapMode.WORD_CHAR)
                changelog.get_buffer().set_text(notes)
                scroll = Gtk.ScrolledWindow(min_content_height=120, max_content_height=220,
                                            propagate_natural_height=True)
                scroll.set_child(changelog)
                box.append(scroll)
            box.append(Gtk.LinkButton(uri=page, label="Ver cambios en GitHub"))
        box.append(button("Buscar actualizaciones", lambda: (dialog.destroy(), self.check_release(manual=True))))
        dialog.set_child(box)
        dialog.present()

    def download_update(self, url, path, tag):
        if self.busy or self.cancel_download:
            return
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
        entry = self.history.start("update", f"Actualización {tag}")
        self.retries[entry] = lambda: self.download_update(url, path, tag)
        self.set_download_progress("Descargando actualización…")
        self.refresh()

        def progress(message):
            if cancel.is_set():
                raise InterruptedError("Descarga cancelada.")
            GLib.idle_add(self.set_download_progress, message)

        def finish(error):
            self.cancel_download = None
            message = error or "Actualización lista para instalar."
            self.record(entry, error, cancel, message)
            self.set_download_progress(message)
            self.finished(message)
            if not error:
                self.update_ready(path, tag)

        def worker():
            try:
                actualizaciones.download(url, path, progress=progress)
            except Exception as error:
                GLib.idle_add(finish, f"No se descargó la actualización: {error}")
            else:
                GLib.idle_add(finish, None)

        threading.Thread(target=worker, daemon=True).start()

    def update_ready(self, path, tag):
        dialog = Gtk.Window(title="Actualización de Nova", transient_for=self.window, modal=True,
                            default_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label(f"{tag} · Lista para instalar", "subheading"))
        box.append(label(f"Versión instalada · {actualizaciones.VERSION}", "muted"))
        box.append(label("Ejecutá el instalador y volvé a abrir Nova." if os.name == "nt" else
                         "Instalá el RPM y volvé a abrir Nova.", "muted"))
        box.append(button("Abrir carpeta", lambda: motor.open_folder(path.parent)))

        def copy_command():
            dialog.get_clipboard().set(f"sudo dnf install {shlex.quote(str(path.absolute()))}")
            copy.set_label("Comando copiado")

        if os.name != "nt":
            copy = button("Copiar comando de instalación", copy_command, "primary")
            box.append(copy)
        dialog.set_child(box)
        dialog.present()

    def check_release(self, manual=False):
        if self.checking_release:
            return
        repo = self.preferences.get("release_repo", self.release_repo)
        self.checking_release = True
        if manual:
            self.status.set_text("Consultando GitHub…")

        def finish(release, error):
            self.checking_release = False
            if repo != self.preferences.get("release_repo", self.release_repo):
                self.check_release(manual)
                return
            self.available_release = release
            self.release_button.set_label(f"Actualizar a {release[0]}" if release
                                          else f"Nova {actualizaciones.VERSION}")
            if release:
                self.release_button.add_css_class("primary")
                if manual:
                    self.status.set_text(f"Nueva versión de Nova · {release[0]}")
                    self.release_details()
            else:
                self.release_button.remove_css_class("primary")
                if manual:
                    self.status.set_text(error or "Ya tenés la última versión.")

        def worker():
            try:
                release = actualizaciones.check(repo)
            except Exception as error:
                GLib.idle_add(finish, None, str(error))
            else:
                GLib.idle_add(finish, release, None)

        threading.Thread(target=worker, daemon=True).start()

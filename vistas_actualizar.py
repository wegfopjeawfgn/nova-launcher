"""Nova window: actualizar."""
import os
import shlex
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk

import actualizaciones
import instalar_actualizacion
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
            staged = self.staged_update()
            if staged:
                def install_now():
                    dialog.destroy()
                    self.install_update(*staged)

                box.append(button("Reiniciar y actualizar" if os.name == "nt" else "Instalar ahora", install_now, "primary"))
            elif rpm:
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
        self.show_page(dialog)

    def download_update(self, url, path, tag):
        self.submit("update", f"Actualización {tag}",
                    lambda entry: self.run_update_download(entry, url, path, tag),
                    lambda: self.download_update(url, path, tag))

    def run_update_download(self, entry, url, path, tag):
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
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
                instalar_actualizacion.mark_verified(path, tag)
            except (OSError, ValueError, KeyError, actualizaciones.requests.RequestException) as error:
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
        if instalar_actualizacion.is_verified(path):
            def install_now():
                dialog.destroy()
                self.install_update(path, tag)

            box.append(button("Reiniciar y actualizar" if os.name == "nt" else "Instalar ahora", install_now, "primary"))
        box.append(button("Abrir carpeta", lambda: motor.open_folder(path.parent)))

        def copy_command():
            dialog.get_clipboard().set(f"sudo dnf install {shlex.quote(str(path.absolute()))}")
            copy.set_label("Comando copiado")

        if os.name != "nt":
            copy = button("Copiar comando de instalación", copy_command)
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
            if error:  # a failed check keeps what was known (a pending update must not vanish)
                if manual:
                    self.status.set_text(error)
                return
            self.available_release = release
            self.update_home()
            self.release_note.set_text(f"Actualizar a {release[0]}" if release else "Al día")
            if release:
                self.release_card.add_css_class("update")
                if self.preferences.get("auto_update") and release[1]:
                    self.auto_download(release)
                if manual:
                    self.status.set_text(f"Nueva versión de Nova · {release[0]}")
                    self.release_details()
            else:
                self.release_card.remove_css_class("update")
                if manual:
                    self.status.set_text(error or "Ya tenés la última versión.")

        def worker():
            try:
                release = actualizaciones.check(repo, self.preferences.get("beta", False))
            except (OSError, ValueError, KeyError, actualizaciones.requests.RequestException) as error:
                GLib.idle_add(finish, None, str(error))
            else:
                GLib.idle_add(finish, release, None)

        threading.Thread(target=worker, daemon=True).start()

    # ---- automatic updates: download in the background, install with one click

    def staged_update(self):
        """(path, tag) of a verified installer already waiting for the available release, else None."""
        staged = getattr(self, "update_staged", None)
        release = getattr(self, "available_release", None)
        if staged and release and staged[1] == release[0] and instalar_actualizacion.is_verified(staged[0]):
            return staged
        return None

    def auto_download(self, release):
        tag, url = release[0], release[1]
        if getattr(self, "auto_downloading", False) or self.staged_update():
            return
        try:
            path = instalar_actualizacion.staged_path(url)
        except ValueError:
            return
        self.auto_downloading = True

        def worker():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if not instalar_actualizacion.is_verified(path):
                    instalar_actualizacion.clean()
                    actualizaciones.download(url, path)
                    instalar_actualizacion.mark_verified(path, tag)
                instalar_actualizacion.clean(path)
            except (OSError, ValueError, KeyError, actualizaciones.requests.RequestException):
                GLib.idle_add(self._auto_done, None, tag)  # quietly: a manual update still works
                return
            GLib.idle_add(self._auto_done, path, tag)

        threading.Thread(target=worker, daemon=True).start()

    def _auto_done(self, path, tag):
        self.auto_downloading = False
        if path:
            self.update_staged = (path, tag)
            self.release_note.set_text(f"Listo para instalar · {tag}")
            self.status.set_text(f"Nova {tag} está descargada y verificada. Tocá la versión abajo a la izquierda para instalarla.")
        return False

    def install_update(self, path, tag):
        if self.busy or self.parallel or self.servers_block_close():
            self.status.set_text("Terminá lo que Nova está haciendo (descargas, juego o servidores) antes de actualizar.")
            return
        if os.name == "nt":
            try:
                instalar_actualizacion.apply(path)
            except (OSError, ValueError) as error:
                self.status.set_text(f"No se pudo iniciar el instalador: {error}")
                return
            self.status.set_text("Actualizando Nova… se va a cerrar y abrir sola.")
            GLib.timeout_add(400, lambda: (self.quit(), False)[1])
            return
        self.status.set_text(f"Instalando Nova {tag}… autorizá en la ventana del sistema.")

        def worker():
            try:
                result = instalar_actualizacion.apply(path)
            except (OSError, ValueError, subprocess_timeout()) as error:
                GLib.idle_add(self._install_done, False, f"No se pudo instalar: {error}")
                return
            ok = result.returncode == 0
            GLib.idle_add(self._install_done, ok, "" if ok else instalar_actualizacion.failure_text(result))

        threading.Thread(target=worker, daemon=True).start()

    def _install_done(self, ok, message):
        if not ok:
            self.status.set_text(message)
            return False
        self.status.set_text("Nova se actualizó. Abriendo la versión nueva…")
        instalar_actualizacion.relaunch()
        GLib.timeout_add(600, lambda: (self.quit(), False)[1])
        return False


def subprocess_timeout():
    import subprocess
    return subprocess.TimeoutExpired

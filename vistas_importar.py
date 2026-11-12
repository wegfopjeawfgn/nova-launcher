"""Nova window: importar."""
import os
from pathlib import Path
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk

import biblioteca
import catalogo
import motor
import respaldos
from widgets import label


class ImportarMixin:
    def browse_packs(self):
        if not self.busy:
            biblioteca.Browser(self, None, None, "modpack")

    def load_versions(self):
        try:
            entries = motor.versions()
        except (OSError, ValueError):
            return
        GLib.idle_add(setattr, self, "versions", entries)

    def choose_prism(self):
        if self.busy:
            return
        picker = Gtk.FileChooserNative(title="Elegir carpeta de la instancia de Prism",
                                       transient_for=self.window,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)

        def selected(_, response):
            file = picker.get_file() if response == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            picker.destroy()
            if not path:
                return
            source = Path(path)
            try:
                name, version, loader, _, game = respaldos.prism_details(source)
                worlds = sum(1 for _ in (game / "saves").glob("*/level.dat"))
            except (OSError, KeyError, TypeError, ValueError) as error:
                self.status.set_text(f"No se pudo leer la instancia de Prism: {error}")
                return
            dialog = Gtk.Dialog(title="Revisar instancia de Prism", transient_for=self.window, modal=True)
            dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
            dialog.add_button("Importar", Gtk.ResponseType.OK).add_css_class("primary")
            box = dialog.get_content_area()
            box.add_css_class("menu")
            box.append(label(name, "subheading"))
            box.append(label(f"Minecraft {version} · {motor.LOADERS[loader]} · {worlds} mundos", "muted"))

            def confirm(_, response):
                dialog.destroy()
                if response != Gtk.ResponseType.OK:
                    return

                def task():
                    folder = respaldos.import_prism(source, self.preferences["memory"])
                    GLib.idle_add(setattr, self, "selected", folder)

                self.background_file("Copiando instancia de Prism…", task, "Instancia importada.")

            dialog.connect("response", confirm)
            dialog.present()

        picker.connect("response", selected)
        picker.show()

    def browse(self):
        if not self.busy:
            biblioteca.Browser(self, self.selected, self.instances.get(self.selected))

    def import_pack(self, extension):
        if self.busy:
            return
        format_name = "Modrinth" if extension == "mrpack" else "Nova o CurseForge"
        picker = Gtk.FileChooserNative(title=f"Importar {format_name} (.{extension})",
                                       transient_for=self.window, action=Gtk.FileChooserAction.OPEN)
        file_filter = Gtk.FileFilter(name=f"{format_name} (*.{extension})")
        pattern = "".join(f"[{letter}{letter.upper()}]" for letter in extension)
        file_filter.add_pattern(f"*.{pattern}")
        picker.add_filter(file_filter)
        all_files = Gtk.FileFilter(name="Todos los archivos")
        all_files.add_pattern("*")
        picker.add_filter(all_files)
        picker.set_filter(file_filter)

        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog.get_file().get_path()
                if path:
                    dialog.destroy()
                    if Path(path).suffix.lower() != f".{extension}":
                        self.status.set_text(f"Elegí un archivo .{extension} para importar desde {format_name}.")
                    else:
                        self.preview_pack(path)
                    return
            dialog.destroy()

        picker.connect("response", selected)
        picker.show()

    def preview_pack(self, path):
        try:
            name, version, loader, needs_key = catalogo.pack_summary(path)
        except (OSError, ValueError, KeyError, TypeError, catalogo.zipfile.BadZipFile) as exc:
            self.status.set_text(f"No se pudo leer el modpack: {exc}")
            return
        dialog = Gtk.Dialog(title="Revisar modpack", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Continuar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        title = label(name[:100], "subheading")
        title.set_wrap(True)
        box.append(title)
        box.append(label(f"Minecraft {version} · {loader}", "muted"))

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                if needs_key and not os.environ.get("CURSEFORGE_API_KEY"):
                    self.import_curseforge(path)
                else:
                    self.import_local(path)

        dialog.connect("response", respond)
        dialog.present()

    def import_curseforge(self, path):
        dialog = Gtk.Dialog(title="Importar ZIP de CurseForge", transient_for=self.window,
                            modal=True, default_width=440)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Importar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        hint = label("Si el ZIP referencia archivos externos, ingresá tu clave de API de CurseForge. "
                     "Si ya incluye todo el contenido, dejá el campo vacío.", "muted")
        hint.set_wrap(True)
        box.append(hint)
        entry = Gtk.PasswordEntry(placeholder_text="Clave de API de CurseForge")
        box.append(entry)
        entry.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))

        def respond(_, response):
            key = entry.get_text().strip()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.import_local(path, key)

        dialog.connect("response", respond)
        dialog.present()

    def import_local(self, path, api_key="", manual_dir=None):
        if self.busy:
            return
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
        entry = self.history.start("import", f"Importar {Path(path).name}")
        self.retries[entry] = lambda: self.import_local(path, api_key, manual_dir)
        self.set_download_progress("Importando modpack…")
        self.refresh()
        memory = self.preferences["memory"]

        def finish(folder, message, manual=False):
            self.cancel_download = None
            self.record(entry, None if folder else message, cancel, message)
            self.set_download_progress(message)
            if folder:
                self.selected = folder
            self.finished(message)
            if not folder and not cancel.is_set():
                dialog = Gtk.Dialog(title="Importación interrumpida", transient_for=self.window, modal=True)
                dialog.add_button("Cerrar", Gtk.ResponseType.CANCEL)
                dialog.add_button("Reintentar", Gtk.ResponseType.OK)
                if manual:
                    dialog.add_button("Elegir carpeta con archivos", Gtk.ResponseType.APPLY)
                box = dialog.get_content_area()
                box.add_css_class("menu")
                error = label(message, "form-error")
                error.set_wrap(True)
                error.set_max_width_chars(60)
                box.append(error)

                def respond(_, response):
                    dialog.destroy()
                    if response == Gtk.ResponseType.OK:
                        self.import_local(path, api_key, manual_dir)
                    elif response == Gtk.ResponseType.APPLY:
                        picker = Gtk.FileChooserNative(title="Elegir carpeta con los archivos de CurseForge",
                                                       transient_for=self.window,
                                                       action=Gtk.FileChooserAction.SELECT_FOLDER)

                        def selected(_, response):
                            file = picker.get_file() if response == Gtk.ResponseType.ACCEPT else None
                            directory = file.get_path() if file else None
                            picker.destroy()
                            if directory:
                                self.import_local(path, api_key, Path(directory))

                        picker.connect("response", selected)
                        picker.show()

                dialog.connect("response", respond)
                dialog.present()

        def progress(message):
            if cancel.is_set():
                raise InterruptedError("Importación cancelada.")
            GLib.idle_add(self.set_download_progress, message)

        def worker():
            try:
                folder = catalogo.import_pack(path, memory, api_key, manual_dir=manual_dir, progress=progress)
            except InterruptedError:
                GLib.idle_add(finish, None, "Importación cancelada. Los archivos verificados se conservaron.")
            except Exception as exc:
                GLib.idle_add(finish, None, f"No se pudo importar: {exc}",
                              isinstance(exc, catalogo.ManualPackFile))
            else:
                GLib.idle_add(finish, folder, "Modpack importado.")

        threading.Thread(target=worker, daemon=True).start()

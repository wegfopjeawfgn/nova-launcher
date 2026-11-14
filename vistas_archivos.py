"""Nova window: añadir contenido desde archivos del equipo (mods, texturas, shaders, paquetes de datos, modpacks)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango

import errores
import importar_archivos as importar
from widgets import label

PICKER = {
    None: ("Mods, texturas, shaders y modpacks", ("jar", "zip", "mrpack")),
    "mod": ("Mods (.jar)", ("jar",)),
    "shader": ("Shaders (.zip)", ("zip",)),
    "resourcepack": ("Texturas (.zip)", ("zip",)),
}
TITLES = {None: "Importar desde el equipo", "mod": "Importar mods", "shader": "Importar shaders",
          "resourcepack": "Importar texturas"}


class ArchivosMixin:
    def import_files(self, paths=None, *, category=None, folder=None, parent=None, after=None):
        """Entry point for the button, the menu, Ctrl+O and drag and drop."""
        if self.busy:
            self.status.set_text("Esperá a que termine la operación actual para importar archivos.")
            return
        if paths:
            self.review_files(paths, folder, parent, after)
        else:
            self.pick_files(category, folder, parent, after)

    def pick_files(self, category, folder, parent, after):
        description, suffixes = PICKER.get(category, PICKER[None])
        picker = Gtk.FileChooserNative(title=TITLES.get(category, TITLES[None]),
                                       transient_for=parent or self.window, action=Gtk.FileChooserAction.OPEN)
        picker.set_select_multiple(True)
        wanted = Gtk.FileFilter(name=description)
        for suffix in suffixes:
            wanted.add_suffix(suffix)
        picker.add_filter(wanted)
        everything = Gtk.FileFilter(name="Todos los archivos")
        everything.add_pattern("*")
        picker.add_filter(everything)
        picker.set_filter(wanted)

        def selected(dialog, response):
            files = dialog.get_files() if response == Gtk.ResponseType.ACCEPT else None
            paths = [files.get_item(index).get_path() for index in range(files.get_n_items())] if files else []
            dialog.destroy()
            paths = [path for path in paths if path]
            if paths:
                self.review_files(paths, folder, parent, after)

        picker.connect("response", selected)
        picker.show()

    def review_files(self, paths, folder, parent, after):
        self.status.set_text("Revisando archivos…")

        def worker():
            try:
                items = importar.inspect_many(paths)
            except Exception as error:  # a file that cannot be read must not close the window
                errores.record(error, "vistas_archivos.review")
                GLib.idle_add(self.status.set_text, f"No se pudieron revisar los archivos: {error}")
                return
            GLib.idle_add(self.show_import_review, items, folder, parent, after)

        threading.Thread(target=worker, daemon=True).start()

    def show_import_review(self, items, folder, parent, after):
        self.status.set_text("Listo")
        if len(items) == 1 and items[0].kind == "modpack" and items[0].ok:
            self.preview_pack(str(items[0].path))  # a lone modpack follows the existing import flow
            return
        folder = folder or self.selected
        loose = [item for item in items if item.kind != "modpack"]
        if folder is None and any(item.ok for item in loose):
            self.status.set_text("Creá o elegí una instancia antes de añadirle contenido.")
            return
        dialog = Gtk.Dialog(title="Revisar archivos", transient_for=parent or self.window, modal=True,
                            default_width=580)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        accept = dialog.add_button("Importar", Gtk.ResponseType.OK)
        accept.add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(12)

        state = {"folder": folder}
        names = list(self.instances)
        chooser = None
        if folder is not None and len(names) > 1:
            header = Gtk.Box(spacing=10)
            header.append(label("Instalar en", "muted"))
            chooser = Gtk.DropDown.new_from_strings([self.instances[name]["name"] for name in names])
            chooser.set_selected(names.index(folder) if folder in names else 0)
            chooser.set_hexpand(True)
            header.append(chooser)
            box.append(header)
        elif folder is not None:
            box.append(label(f"Se añadirá a «{self.instances[folder]['name']}»", "muted"))

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                    max_content_height=360, min_content_height=80)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["import-list"])
        scroll.set_child(rows)
        box.append(scroll)
        summary = label("", "muted")
        box.append(summary)

        entries = []  # (item, check, warning_label, world_picker)
        mixed = len(items) > 1
        for item in items:
            installable = item.ok and not (item.kind == "modpack")
            row = Gtk.Box(spacing=10, css_classes=["import-row"])
            check = Gtk.CheckButton(active=installable, sensitive=installable)
            check.set_valign(Gtk.Align.START)
            check.update_property([Gtk.AccessibleProperty.LABEL], [f"Importar {item.path.name}"])
            row.append(check)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
            title = label(item.title or item.path.name, "catalog-title")
            title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            title.set_xalign(0)
            text.append(title)
            kind = importar.KIND_NAMES.get(item.kind, "Archivo")
            parts = [kind, item.detail, importar.human_size(item.size) if item.size else ""]
            meta = label(" · ".join(part for part in parts if part), "muted")
            meta.set_xalign(0)
            meta.set_wrap(True)
            text.append(meta)
            note = label("", "import-note")
            note.set_visible(False)
            note.set_xalign(0)
            note.set_wrap(True)
            note.set_max_width_chars(60)
            text.append(note)
            if item.problem:
                note.set_text(item.problem)
                note.set_visible(True)
                note.add_css_class("form-error")
            elif item.kind == "modpack" and mixed:
                note.set_text("Los modpacks se importan por separado: arrastrá este archivo solo.")
                note.set_visible(True)
                note.add_css_class("form-error")
            row.append(text)
            world_picker = None
            if installable and item.kind == "datapack":
                world_picker = Gtk.DropDown.new_from_strings([""])
                world_picker.set_valign(Gtk.Align.START)
                row.append(world_picker)
            rows.append(row)
            entries.append((item, check, note, world_picker))

        def instance_of():
            return names[chooser.get_selected()] if chooser is not None else state["folder"]

        def refresh_rows(*_):
            target = instance_of()
            instance = self.instances.get(target, {}) if target is not None else {}
            for item, check, note, world_picker in entries:
                if item.problem or item.kind == "modpack":
                    continue
                note.remove_css_class("form-error")
                note.set_text(importar.warning(item, instance))
                note.set_visible(bool(note.get_text()))
                if world_picker is not None:
                    available = importar.worlds(target)
                    world_picker.set_model(Gtk.StringList.new(available or ["Sin mundos"]))
                    world_picker.set_sensitive(bool(available))
                    check.set_sensitive(bool(available))
                    if not available:
                        check.set_active(False)
                        note.set_text("Esta instancia todavía no tiene mundos para instalar el paquete de datos.")
                        note.set_visible(True)
            update_count()

        def chosen():
            return [(item, world_picker) for item, check, _, world_picker in entries
                    if check.get_active() and check.get_sensitive()]

        def update_count(*_):
            count = len(chosen())
            accept.set_sensitive(count > 0)
            accept.set_label("Importar 1 archivo" if count == 1 else f"Importar {count} archivos" if count else "Importar")
            problems = sum(1 for item, *_ in entries if item.problem)
            summary.set_text((f"{problems} archivos se omiten: no se reconocen o no son compatibles." if problems != 1
                              else "1 archivo se omite: no se reconoce o no es compatible.") if problems else "")

        for _, check, _, _ in entries:
            check.connect("toggled", update_count)
        if chooser is not None:
            chooser.connect("notify::selected", refresh_rows)
        refresh_rows()

        def respond(_, response):
            jobs, target = [], instance_of()
            if response == Gtk.ResponseType.OK:
                for item, world_picker in chosen():
                    world = None
                    if world_picker is not None:
                        selected = world_picker.get_selected_item()
                        world = selected.get_string() if selected else None
                    jobs.append((item, world))
            dialog.destroy()
            if jobs and target is not None:
                self.run_file_import(target, jobs, after)

        dialog.connect("response", respond)
        dialog.present()

    def run_file_import(self, folder, jobs, after=None):
        name = self.instances[folder]["name"]
        self.busy = True
        self.refresh()
        total = len(jobs)

        def worker():
            added, skipped, failed = 0, 0, []
            for number, (item, world) in enumerate(jobs, 1):
                GLib.idle_add(self.status.set_text, f"Copiando {number}/{total} · {item.path.name}")
                try:
                    target, _ = importar.install(folder, item, world)
                except (OSError, RuntimeError, ValueError) as error:
                    failed.append(f"{item.path.name}: {error}")
                except Exception as error:
                    errores.record(error, "vistas_archivos.worker")
                    failed.append(f"{item.path.name}: {error}")
                else:
                    if target is None:
                        skipped += 1
                    else:
                        added += 1
            parts = []
            if added:
                parts.append(f"{added} archivo{'s' if added != 1 else ''} añadido{'s' if added != 1 else ''} a «{name}»")
            if skipped:
                parts.append(f"{skipped} ya estaba{'n' if skipped != 1 else ''} instalado{'s' if skipped != 1 else ''}")
            if failed:
                parts.append(f"{len(failed)} falló · {failed[0]}")
            GLib.idle_add(self.finish_file_import, " · ".join(parts) or "No se importó nada.", after)

        threading.Thread(target=worker, daemon=True).start()

    def finish_file_import(self, message, after):
        self.finished(message)
        if after:
            after()

    # ---- Drag and drop onto the main window ----

    def setup_drop(self, window, hint):
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)

        def entered(*_):
            hint.set_visible(True)
            return Gdk.DragAction.COPY

        def left(*_):
            hint.set_visible(False)

        def dropped(_, value, *_rest):
            hint.set_visible(False)
            paths = [file.get_path() for file in value.get_files() if file.get_path()]
            if paths:
                self.import_files(paths)
            return bool(paths)

        target.connect("enter", entered)
        target.connect("leave", left)
        target.connect("drop", dropped)
        window.add_controller(target)

    @staticmethod
    def drop_hint():
        hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["drop-hint"],
                       halign=Gtk.Align.FILL, valign=Gtk.Align.FILL, visible=False, can_target=False)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER,
                        valign=Gtk.Align.CENTER, vexpand=True, css_classes=["drop-card"])
        inner.append(label("Soltá los archivos para importarlos", "drop-title"))
        inner.append(label("Mods, texturas, shaders, paquetes de datos o un modpack", "muted"))
        hint.append(inner)
        return hint

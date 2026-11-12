"""Nova window: respaldos."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk, Pango

import motor
import respaldos
from widgets import label, button, feature_button


class RespaldosMixin:
    def show_backups(self):
        dialog = Gtk.Window(title="Respaldos", transient_for=self.window, modal=True,
                            default_width=540, default_height=350)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label("Respaldos de instancias", "subheading"))
        hint = label("Restaurar crea una instancia separada con los mundos, mods y ajustes del respaldo.", "muted")
        hint.set_wrap(True)
        content.append(hint)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        scroller.set_child(rows)
        content.append(scroller)
        paths = sorted((motor.ROOT / "backups").glob("*/backup.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths:
            info = motor.read(path, {})
            instance = motor.read(path.parent / "instance.json", {})
            if not instance.get("name"):
                continue
            when = info.get("created", "")[:16].replace("T", " ")
            rows.append(feature_button(instance["name"], f"{when} · Restaurar como instancia nueva",
                        lambda folder=path.parent: self.restore_backup(dialog, folder)))
        if rows.get_first_child() is None:
            rows.append(label("Todavía no tenés respaldos. Creá uno desde el panel de una instancia.", "muted"))
            rows.get_first_child().set_wrap(True)
        dialog.set_child(content)
        self.show_page(dialog)

    def restore_backup(self, dialog, folder):
        dialog.destroy()
        self.copy_instance(folder, "restore")

    def export_instance(self, folder):
        dialog = Gtk.Dialog(title="Exportar instancia", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar archivo", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        format_choice = Gtk.ComboBoxText()
        format_choice.append("zip", "ZIP · Configuración y mundos opcionales")
        format_choice.append("mrpack", "Modrinth (.mrpack) · Con referencias de descarga")
        format_choice.set_active_id("zip")
        box.append(format_choice)
        info = label("El .mrpack incluye referencias para los archivos activos que coinciden "
                     "con Modrinth. Los archivos sin coincidencia se omiten.", "muted")
        info.set_wrap(True)
        info.set_max_width_chars(48)
        box.append(info)
        worlds = Gtk.CheckButton(label="Incluir mis mundos")
        box.append(worlds)

        def respond(_, response):
            extension = format_choice.get_active_id()
            include_worlds = worlds.get_active()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.save_file("Exportar instancia", f"instancia-nova.{extension}", lambda path:
                               self.background_file("Exportando instancia…",
                                   lambda: respaldos.export_instance(folder, path, include_worlds),
                                   f"Instancia exportada en {path}."))

        dialog.connect("response", respond)
        dialog.present()

    def show_java(self, folder, instance):
        dialog = Gtk.Window(title="Java y memoria", transient_for=self.window, modal=True, default_width=500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Java y memoria", "subheading"))
        box.append(label(f"RAM asignada · {instance['memory']} GB", "form-label"))
        status = label("Comprobando Java…", "muted")
        status.set_wrap(True)
        status.set_selectable(True)
        box.append(status)

        def reset():
            try:
                with motor.instance_lock(folder):
                    settings = motor.read(folder / "instance.json", {})
                    settings.update(java="", memory=self.preferences["memory"])
                    motor.save(folder / "instance.json", settings)
            except (OSError, RuntimeError) as error:
                status.set_text(str(error))
                return
            dialog.destroy()
            self.refresh()
            self.status.set_text("La instancia usa el Java y la memoria predeterminados de Nova.")

        box.append(button("Usar valores predeterminados de Nova", reset))
        dialog.set_child(box)
        self.show_page(dialog)
        settings = {**instance, "java": instance["java"] or self.preferences["java"]}

        def worker():
            try:
                executable, required, found = motor.java_report(settings)
                lines = [executable]
                if required:
                    lines.append(f"Minecraft requiere Java {required}.")
                if found:
                    lines.append(f"Java detectado · {found}")
                if found and required and found < required:
                    lines.append("Este Java es demasiado antiguo para la instancia.")
            except (OSError, ValueError, KeyError, motor.subprocess.SubprocessError) as error:
                lines = [f"No se pudo comprobar Java: {error}"]
            GLib.idle_add(status.set_text, "\n".join(lines))

        threading.Thread(target=worker, daemon=True).start()

    def repair_instance(self, folder, instance):
        settings = {**instance, "java": instance["java"] or self.preferences["java"]}

        def task():
            with motor.instance_lock(folder):
                motor.prepare(settings, lambda message: GLib.idle_add(self.status.set_text, message), repair=True)

        self.background_file("Verificando la instalación…", task, "Instalación revisada.")

    def show_worlds(self, folder):
        dialog = Gtk.Window(title="Mundos", transient_for=self.window, modal=True,
                            default_width=520, default_height=400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label(f"Mundos de {self.instances[folder]['name']}", "subheading"))
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.set_child(rows)
        box.append(scroll)
        status = label("", "muted")
        status.set_wrap(True)
        box.append(status)

        def render():
            while child := rows.get_first_child():
                rows.remove(child)
            for backup in (False, True):
                paths = respaldos.worlds(folder, backups=backup)
                if not paths:
                    continue
                rows.append(label("Respaldos" if backup else "Mundos guardados", "form-label"))
                for path in paths:
                    row = Gtk.Box(spacing=8, css_classes=["catalog-row"])
                    title = label(path.name)
                    title.set_ellipsize(Pango.EllipsizeMode.END)
                    title.set_hexpand(True)
                    row.append(title)
                    row.append(button("Restaurar copia" if backup else "Respaldar",
                                      lambda path=path, restore=backup: copy_world(path, restore)))
                    rows.append(row)
            if not rows.get_first_child():
                rows.append(label("Todavía no hay mundos guardados.", "muted"))

        def copy_world(path, restore):
            rows.set_sensitive(False)
            status.set_text("Copiando mundo…")

            def finish(message):
                status.set_text(message)
                render()
                rows.set_sensitive(True)

            def worker():
                try:
                    target = respaldos.copy_world(folder, path, restore=restore)
                except (OSError, ValueError, RuntimeError) as error:
                    GLib.idle_add(finish, f"No se pudo copiar el mundo: {error}")
                else:
                    GLib.idle_add(finish, f"Copia guardada como «{target.name}».")

            threading.Thread(target=worker, daemon=True).start()

        render()
        dialog.set_child(box)
        self.show_page(dialog)

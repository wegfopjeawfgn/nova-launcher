"""Nova window: respaldos."""
from datetime import datetime, timedelta
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk, Pango

import errores
import motor
import respaldos
from progreso import size_text
from widgets import label, button


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
        backups = respaldos.list_backups()
        for item in backups:
            rows.append(self.backup_card(dialog, item))
        if not backups:
            rows.append(label("Todavía no tenés respaldos. Creá uno desde el panel de una instancia.", "muted"))
            rows.get_first_child().set_wrap(True)
        dialog.set_child(content)
        self.show_page(dialog)

    def backup_card(self, dialog, item):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["job"])
        line = Gtk.Box(spacing=10)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=2)
        info.append(label(item["name"], "job-title"))
        when = item["created"][:16].replace("T", " ")
        details = [when, size_text(item["size"]) if item["size"] else "tamaño desconocido",
                   f"{item['worlds']} mundo(s)", f"{item['mods']} mod(s)"]
        if item["auto"]:
            details.append("automático")
        info.append(label(" · ".join(details), "muted"))
        line.append(info)
        state = Gtk.Label(label="Sin verificar", valign=Gtk.Align.CENTER, css_classes=["state"])
        line.append(state)
        check = button("Verificar", lambda: verify())
        line.append(check)
        line.append(button("Restaurar", lambda: self.restore_backup(dialog, item["folder"]), "quiet-button"))
        card.append(line)
        detail = label("", "muted")
        detail.set_wrap(True)
        detail.set_visible(False)
        card.append(detail)

        def verify():
            check.set_sensitive(False)
            state.set_text("Verificando…")

            def worker():
                outcome = respaldos.verify_backup(item["folder"])
                GLib.idle_add(done, *outcome)

            def done(result, problems):
                check.set_sensitive(True)
                for name in ("state-ok", "state-error", "state-warning"):
                    state.remove_css_class(name)
                if result == "ok":
                    state.set_text("Íntegro")
                    state.add_css_class("state-ok")
                elif result == "dañado":
                    state.set_text("Dañado")
                    state.add_css_class("state-error")
                    detail.set_text("; ".join(problems[:4]) + (" …" if len(problems) > 4 else ""))
                    detail.set_visible(True)
                else:
                    state.set_text("Sin suma de control")
                    state.add_css_class("state-warning")
                    detail.set_text("Es un respaldo anterior a la versión 1.4.0: no se puede comprobar su integridad.")
                    detail.set_visible(True)

            threading.Thread(target=worker, daemon=True).start()

        return card

    def auto_backup(self):
        """Once per start: back up instances that have none newer than the chosen number of days."""
        days = self.preferences.get("auto_backup_days", 0)
        if not isinstance(days, int) or days <= 0 or self.busy or self.parallel:
            return False
        limit = (datetime.now().astimezone() - timedelta(days=days)).isoformat(timespec="minutes")
        newest = {}
        for item in respaldos.list_backups():
            newest[item["source"]] = max(newest.get(item["source"], ""), item["created"])
        due = [folder for folder in self.instances if newest.get(folder.name, "") < limit]
        if not due:
            return False

        def worker():
            for folder in due:
                try:
                    respaldos.copy_instance(folder, "backup", auto=True)
                except (OSError, ValueError, RuntimeError) as error:
                    errores.record(error, "vistas_respaldos.auto_backup")
                else:
                    GLib.idle_add(self.status.set_text, f"Copia automática de «{self.instances[folder]['name']}» lista.")

        threading.Thread(target=worker, daemon=True).start()
        return False

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

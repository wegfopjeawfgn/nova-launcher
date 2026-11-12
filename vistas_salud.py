"""Nova window: instance health page (Smart Mods analysis and Nova Repair diagnosis)."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import errores
import modanalisis
import reparacion
from widgets import label, button

SEVERITY_LABEL = {"confirmado": "Confirmado", "posible": "Posible", "aviso": "Aviso",
                  "error": "Error", "warning": "Atención", "info": "Info"}
SEVERITY_CLASS = {"confirmado": "state-error", "error": "state-error", "posible": "state-warning",
                  "warning": "state-warning", "aviso": "state-info", "info": "state-info"}


class SaludMixin:
    def confirm(self, title, text, accept, on_accept, danger=False):
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        control = dialog.add_button(accept, Gtk.ResponseType.OK)
        control.add_css_class("danger" if danger else "primary")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.add_css_class("menu")
        message = label(text)
        message.set_wrap(True)
        message.set_max_width_chars(56)
        box.append(message)

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                on_accept()

        dialog.connect("response", respond)
        dialog.present()

    def show_health(self, folder=None):
        folder = folder or self.selected
        if folder is None or folder not in self.instances:
            self.status.set_text("Elegí una instancia para analizarla.")
            return
        instance = dict(self.instances[folder])
        page = Gtk.Window(title="Salud de la instancia")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label(instance["name"], "subheading"))
        hint = label("Nova lee los metadatos de cada mod y revisa la instalación. Solo avisa de problemas que puede "
                     "comprobar; no cambia nada sin que lo confirmes.", "muted")
        hint.set_wrap(True)
        content.append(hint)
        top = Gtk.Box(spacing=10)
        summary = label("Analizando…", "muted")
        summary.set_hexpand(True)
        top.append(summary)
        top.append(button("Volver a analizar", lambda: analyze()))
        content.append(top)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller.set_child(results)
        content.append(scroller)
        page.set_child(content)
        token = [0]

        def card(item, kind):
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["job"])
            line = Gtk.Box(spacing=10)
            name = item["mod"] if kind == "mod" else item["title"]
            title = item["title"] if kind == "mod" else None
            heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, spacing=2)
            heading.append(label(str(name), "job-title"))
            if title:
                heading.append(label(title, "muted"))
            line.append(heading)
            line.append(Gtk.Label(label=SEVERITY_LABEL[item["severity"]], valign=Gtk.Align.CENTER,
                                  css_classes=["state", SEVERITY_CLASS[item["severity"]]]))
            body.append(line)
            for text in ((item["reason"] if kind == "mod" else item["meaning"]),
                         (None if kind == "mod" else "Consecuencia: " + item["consequence"]),
                         "Solución: " + item["fix"]):
                if text:
                    note = label(text, "muted")
                    note.set_wrap(True)
                    note.set_selectable(True)
                    body.append(note)
            action = item.get("action")
            if action == "disable":
                body.append(button(f"Desactivar {item['file']}", lambda: disable(item), "quiet-button"))
            elif action == "reset_settings":
                body.append(button("Corregir ajustes", lambda: reset(), "quiet-button"))
            return body

        def disable(item):
            def run():
                try:
                    modanalisis.disable(folder / "game" / "mods" / item["file"])
                except (OSError, ValueError) as error:
                    self.status.set_text(f"No se pudo desactivar el mod: {error}")
                else:
                    self.status.set_text(f"{item['file']} se desactivó. Podés reactivarlo quitando «.disabled».")
                analyze()

            self.confirm("Desactivar mod", f"Se renombrará «{item['file']}» a «{item['file']}.disabled». "
                         "No se borra nada y podés volver a activarlo.", "Desactivar", run)

        def reset():
            def run():
                try:
                    changes = reparacion.apply("reset_settings", folder)
                except (OSError, ValueError) as error:
                    self.status.set_text(f"No se pudo corregir: {error}")
                else:
                    self.refresh()
                    self.status.set_text("Ajustes corregidos · " + "; ".join(changes) +
                                         ". Se guardó una copia como instance.json.bak-…")
                analyze()

            self.confirm("Corregir ajustes", "Nova restablecerá solo los valores inválidos de RAM y argumentos "
                         "de Java. Antes guarda una copia de instance.json.", "Corregir", run)

        def render(mine, mods, repairs, failure):
            if mine != token[0]:
                return
            while (child := results.get_first_child()):
                results.remove(child)
            if failure:
                summary.set_text(f"No se pudo analizar: {failure}")
                return
            problems = [item for item in repairs if item["severity"] != "info"]
            confirmed = [item for item in mods if item["severity"] == "confirmado"]
            summary.set_text(f"{len(confirmed)} problema(s) confirmado(s) en mods · "
                             f"{len(problems)} en la instalación" if (confirmed or problems)
                             else "Todo en orden: no se encontraron problemas comprobables.")
            for title, items, kind in (("Instalación", repairs, "repair"), ("Mods", mods, "mod")):
                if items:
                    results.append(label(title, "section-title"))
                    for item in items:
                        results.append(card(item, kind))

        def analyze():
            token[0] += 1
            mine = token[0]
            summary.set_text("Analizando…")

            def worker():
                try:
                    mods = modanalisis.analyze(folder / "game" / "mods", instance)
                    repairs = reparacion.diagnose(folder, instance)
                except Exception as error:  # a damaged instance must never crash the page
                    errores.record(error, "vistas_salud.worker")
                    GLib.idle_add(render, mine, [], [], str(error))
                else:
                    GLib.idle_add(render, mine, mods, repairs, None)

            threading.Thread(target=worker, daemon=True).start()

        analyze()
        self.show_page(page)

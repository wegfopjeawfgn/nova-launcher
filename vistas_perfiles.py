"""Nova window: instance templates and portable profiles."""
import json
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import errores
import modanalisis
import motor
import plantillas
import reparacion
from widgets import label, feature_button


class PerfilesMixin:
    def show_templates(self):
        page = Gtk.Window(title="Plantillas")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        content.append(label("Empezar desde una plantilla", "subheading"))
        hint = label("La plantilla solo completa el formulario con ajustes razonables. Podés cambiarlo todo "
                     "antes de crear la instancia.", "muted")
        hint.set_wrap(True)
        content.append(hint)
        for key, template in plantillas.TEMPLATES.items():
            content.append(feature_button(template["title"], template["detail"],
                                          lambda key=key: self.use_template(key)))
        page.set_child(content)
        self.show_page(page)

    def use_template(self, key):
        preset = plantillas.apply_template(key, ram_mb=reparacion.physical_memory_mb())
        preset["name"] = plantillas.TEMPLATES[key]["title"]
        self.leave_page()
        self.instance_form(None, preset=preset)

    def export_profile(self, folder):
        instance = self.instances[folder]
        mods = []
        try:
            for jar in sorted((folder / "game" / "mods").glob("*.jar")):
                try:
                    for meta in modanalisis.read_mod(jar)["metadata"][:1]:
                        mods.append((meta["id"], meta["name"], meta["version"]))
                except (OSError, ValueError, KeyError, modanalisis.zipfile.BadZipFile):
                    continue
        except OSError:
            pass
        profile = plantillas.export_profile(instance, mods)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in instance["name"]).strip() or "perfil"

        def save(path):
            try:
                path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as error:
                self.status.set_text(f"No se pudo guardar el perfil: {error}")
            else:
                self.status.set_text(f"Perfil guardado en {path.name}. No incluye mundos, mods ni la ruta de Java.")

        self.save_file("Exportar perfil", f"{safe}.nova-profile.json", save)

    def import_profile(self):
        picker = Gtk.FileChooserNative(title="Importar perfil de Nova", transient_for=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        profiles = Gtk.FileFilter()
        profiles.set_name("Perfiles de Nova (*.json)")
        profiles.add_pattern("*.json")
        picker.add_filter(profiles)

        def chosen(dialog, response):
            file = dialog.get_file() if response == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            dialog.destroy()
            if not path:
                return
            try:
                profile = plantillas.read_profile(Path(path))
            except ValueError as error:
                self.status.set_text(str(error))
                return
            self.review_profile(profile)

        picker.connect("response", chosen)
        picker.show()

    def review_profile(self, profile):
        text = "Se va a abrir el formulario de una instancia nueva con estos valores:\n\n" + \
               "\n".join(plantillas.describe_profile(profile))
        if profile["mods"]:
            text += "\n\nMods del perfil original: " + ", ".join(m["name"] or m["id"] for m in profile["mods"][:12])
            text += " …" if len(profile["mods"]) > 12 else ""
        preset = {key: profile[key] for key in ("version", "loader", "loader_version", "memory", "jvm_args",
                                                "resolution", "notes") if profile[key] != ""}
        preset["name"] = profile["name"]
        self.confirm("Revisar perfil", text, "Continuar", lambda: self.instance_form(None, preset=preset))

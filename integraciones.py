"""Optional client integrations for an individual Nova instance."""
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading

from gi.repository import GLib, Gtk

import catalogo
import motor


def ensure_mod(folder, instance, slug, marker):
    files = tuple((folder / "game" / "mods").glob("*"))
    if any(marker in path.name.lower() and path.name.endswith(".jar") for path in files):
        return
    if any(marker in path.name.lower() and path.name.endswith(".jar.disabled") for path in files):
        raise ValueError("Activá el mod de integración desde Mods → Instalados.")
    versions = catalogo.releases(slug, "mod", instance)
    if not versions:
        raise ValueError(f"No hay una versión compatible de {slug} para esta instancia.")
    catalogo.install_content(folder, instance, "mod", versions[0])


def equip(folder, instance, player, png):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", player):
        raise ValueError("Elegí un perfil offline para equipar la skin.")
    ensure_mod(folder, instance, "customskinloader", "customskinloader")
    with motor.instance_lock(folder):
        directory = folder / "game" / "CustomSkinLoader"
        target = directory / "LocalSkin" / "skins" / f"{player}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        config = directory / "CustomSkinLoader.json"
        data = motor.read(config, {})
        sources = data.get("loadlist") or []
        local = next((source for source in sources if source.get("name") == "LocalSkin"), None)
        if local is None:
            local = {"name": "LocalSkin", "type": "Legacy", "checkPNG": False,
                     "skin": "LocalSkin/skins/{USERNAME}.png", "model": "auto"}
        else:
            local = {**local, "skin": "LocalSkin/skins/{USERNAME}.png"}
        data["loadlist"] = [local, *(source for source in sources if source.get("name") != "LocalSkin")]
        with NamedTemporaryFile(dir=target.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(png)
        try:
            motor.save(config, data)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def apply_colors(folder, instance):
    ensure_mod(folder, instance, "dark-loading-screen", "dark-loading-screen")
    with motor.instance_lock(folder):
        config = folder / "game" / "config" / "dark-loading-screen.json"
        data = motor.read(config, {})
        motor.save(config, {**data, "background": "101022", "bar": "bb94f5",
                            "barBackground": "211b35", "border": "594475", "logo": "eadbff"})
        if instance["version"] == "1.21.11" and instance["loader"] == "fabric":
            motor.save(folder / "nova-loading.json", {"logo": True})


def run(app, parent, title, task, success):
    dialog = Gtk.Window(title=title, transient_for=parent, modal=True, resizable=False)
    dialog.connect("close-request", lambda _: True)
    content = Gtk.Box(spacing=12, css_classes=["menu"])
    spinner = Gtk.Spinner(spinning=True)
    content.append(spinner)
    message = Gtk.Label(label="Preparando la instancia…", xalign=0, wrap=True, max_width_chars=52)
    content.append(message)
    dialog.set_child(content)

    def finish(error):
        dialog.destroy()
        app.status.set_text(error or success)
        app.refresh()

    def worker():
        try:
            task()
        except Exception as error:
            GLib.idle_add(finish, f"No se pudo completar: {error}")
        else:
            GLib.idle_add(finish, None)

    dialog.present()
    threading.Thread(target=worker, daemon=True).start()

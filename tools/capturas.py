#!/usr/bin/env python3
"""Render Nova Launcher with made-up demo data and save screenshots as PNG.

It never touches your real launcher data: everything lives in a temporary XDG_DATA_HOME.
No network, no account. Used to keep the website screenshots in sync with the app.

    python3 tools/capturas.py SALIDA            # writes SALIDA/<name>.png for every scene
    python3 tools/capturas.py SALIDA principal  # only the named scenes
    NOVA_CAPTURA_TEMA=light python3 tools/capturas.py SALIDA
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(tempfile.mkdtemp(prefix="nova-capturas-"))
os.environ["XDG_DATA_HOME"] = str(DATA)
os.environ.setdefault("GTK_A11Y", "none")
sys.path.insert(0, str(ROOT))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk  # noqa: E402

FABRIC_MODS = ("Sodium", "Lithium", "Iris Shaders", "Mod Menu", "Fabric API", "Xaero's Minimap", "Sound Physics")
FAKE_INSTANCES = (
    ("Supervivencia", "1.21.11", "fabric", "0.19.3", 4, 6, 42_300, 1),
    ("Create Nova", "1.21.1", "neoforge", "21.1.231", 8, 14, 15_400, 2),
    ("Servidor de amigos", "1.20.1", "forge", "47.3.0", 6, 5, 7_900, 3),
    ("Vanilla limpio", "1.21.4", "vanilla", "", 3, 0, 900, 4),
)


def write_zip(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def build_demo():
    root = DATA / "nova-launcher"
    library = {"selected": "", "recent": {}, "playtime": {}, "favorites": []}
    now = time.time()
    for number, (name, version, loader, loader_version, memory, mods, seconds, artwork) in enumerate(FAKE_INSTANCES):
        folder = root / "instances" / f"demo{number}"
        (folder / "game").mkdir(parents=True)
        (folder / "instance.json").write_text(json.dumps({
            "version": version, "loader": loader, "loader_version": loader_version, "java": "", "jvm_args": "",
            "memory_min": 0, "name": name, "memory": memory, "artwork": artwork, "pack": False, "cover": "",
            "notes": "", "resolution": "default"}), encoding="utf-8")
        for index in range(mods):
            title = FABRIC_MODS[index % len(FABRIC_MODS)].lower().replace(" ", "-").replace("'", "")
            write_zip(folder / "game" / "mods" / f"{title}-{index}.jar", {"fabric.mod.json": "{}"})
        if number == 0:
            write_zip(folder / "game" / "shaderpacks" / "BSL v8.2.zip", {"shaders/final.fsh": "x"})
            write_zip(folder / "game" / "resourcepacks" / "Faithful 64x.zip", {"pack.mcmeta": "{}", "assets/a": "x"})
            write_zip(folder / "game" / "resourcepacks" / "Bare Bones.zip", {"pack.mcmeta": "{}", "assets/a": "x"})
        library["recent"][folder.name] = now - number * 86_400
        library["playtime"][folder.name] = seconds
    library["selected"] = "demo0"
    library["favorites"] = ["demo0"]
    (root / "library.json").write_text(json.dumps(library), encoding="utf-8")
    (root / "accounts.json").write_text(json.dumps({"active": "Alex", "profiles": ["Alex"]}), encoding="utf-8")
    theme = os.environ.get("NOVA_CAPTURA_TEMA", "dark")
    (root / "settings.json").write_text(json.dumps({"theme": theme, "memory": 4}), encoding="utf-8")


def demo_downloads():
    """Files to import, with believable sizes (random bytes are stored, not compressed)."""
    folder = DATA / "descargas"
    folder.mkdir(parents=True, exist_ok=True)

    def make(name, files, megabytes):
        with zipfile.ZipFile(folder / name, "w", zipfile.ZIP_STORED) as archive:
            for entry, data in files.items():
                archive.writestr(entry, data)
            archive.writestr("data.bin", os.urandom(int(megabytes * 1024 * 1024)))

    make("sodium-fabric-0.6.1.jar", {"fabric.mod.json": json.dumps(
        {"id": "sodium", "name": "Sodium", "version": "0.6.1"})}, 1.3)
    make("iris-1.8.jar", {"fabric.mod.json": json.dumps({"id": "iris", "name": "Iris Shaders", "version": "1.8.0"})}, 2.9)
    make("create-1.21.1.jar", {"META-INF/neoforge.mods.toml": 'displayName="Create"\nversion="6.0.1"\n'}, 18.4)
    make("Complementary Reimagined.zip", {"shaders/final.fsh": "x"}, 2.2)
    make("Faithful 64x.zip", {"pack.mcmeta": json.dumps({"pack": {"description": "Faithful 64x"}}),
                              "assets/minecraft/a.png": "x"}, 38.5)
    make("libreria-comun.jar", {"com/example/Util.class": "x"}, 0.4)
    (folder / "notas.txt").write_text("hola", encoding="utf-8")
    return sorted(folder.iterdir())


def snapshot(window, path):
    width, height = window.get_width(), window.get_height()
    paintable = Gtk.WidgetPaintable.new(window)
    shot = Gtk.Snapshot()
    paintable.snapshot(shot, width, height)
    node = shot.to_node()
    texture = window.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, width, height))
    texture.save_to_png(str(path))
    print("capturada", path)


def main():
    out = Path(sys.argv[1]).resolve()
    wanted = set(sys.argv[2:])
    out.mkdir(parents=True, exist_ok=True)
    build_demo()
    import nova

    app = nova.Nova()
    app.check_release = lambda: None
    nova.motor.versions = lambda: []
    state = {"index": 0, "popover": None}
    scenes = scene_list(app, state)
    scenes = [scene for scene in scenes if not wanted or scene[0] in wanted]

    def step():
        if state["index"] >= len(scenes):
            app.quit()
            return False
        name, prepare, wait = scenes[state["index"]]
        state["index"] += 1
        prepare()

        def shoot():
            target = app.window
            dialog = next((w for w in Gtk.Window.list_toplevels()
                           if w is not app.window and w.get_visible() and w.get_transient_for() is app.window), None)
            if name == "menu" and state["popover"] is not None:
                dialog = state["popover"]
                dialog.destroy = lambda: None
            snapshot(dialog or target, out / f"{name}.png")
            if name == "soltar":
                app.window.get_child().get_last_child().set_visible(False)
            if dialog:
                dialog.destroy()
            GLib.timeout_add(300, step)
            return False

        GLib.timeout_add(wait, shoot)
        return False

    def start(*_):
        def resize():
            width = int(os.environ.get("NOVA_CAPTURA_ANCHO", "1280"))
            height = int(os.environ.get("NOVA_CAPTURA_ALTO", "820"))
            app.window.set_default_size(width, height)
            GLib.timeout_add(1800, step)
            return False

        GLib.timeout_add(1200, resize)

    app.connect("activate", start)
    app.run([])


def scene_list(app, state):
    def nothing():
        pass

    def contents(kind):
        def run():
            import biblioteca
            folder = app.selected
            if kind == "instalado":
                biblioteca.open_installed(app, folder)
        return run

    def add():
        app.add_instance()

    def review():
        import importar_archivos
        paths = demo_downloads()
        app.show_import_review(importar_archivos.inspect_many(paths), app.selected, None, None)

    def mods():
        import biblioteca
        biblioteca.open_installed(app, app.selected, "mod")

    def importing():
        app.add_instance(import_only=True)

    def edit():
        app.instance_form(app.selected)

    def new():
        app.instance_form(None)

    def menu():
        app.leave_page()
        hero = app.details.get_first_child()
        walk = [hero]
        found = None
        while walk and not found:
            widget = walk.pop()
            if isinstance(widget, Gtk.MenuButton):
                found = widget
            child = widget.get_first_child()
            while child:
                walk.append(child)
                child = child.get_next_sibling()
        if found:
            found.popup()
            state["popover"] = found.get_popover()

    def page(name):
        def run():
            app.leave_page()
            getattr(app, name)()
        return run

    def health():
        app.leave_page()
        app.show_health(app.selected)

    def drop():
        hint = app.window.get_child().get_last_child()
        hint.set_visible(True)

    def tall():
        app.window.set_default_size(1280, 1180)

    return [
        ("principal", nothing, 400),
        ("biblioteca", tall, 900),
        ("soltar", drop, 400),
        ("salud", health, 1500),
        ("plantillas", page("show_templates"), 900),
        ("estadisticas", page("show_statistics"), 900),
        ("respaldos", page("show_backups"), 900),
        ("almacenamiento", page("show_storage"), 900),
        ("editar", edit, 900),
        ("nueva-instancia", new, 700),
        ("menu", menu, 900),
        ("revisar", review, 900),
        ("mods", mods, 700),
        ("nueva", add, 700),
        ("importar", importing, 700),
    ]


if __name__ == "__main__":
    main()

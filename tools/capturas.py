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

if Path("/usr/share/nova-launcher/vendor").is_dir():   # the sign-in library lives here when Nova runs from a source folder
    sys.path.append("/usr/share/nova-launcher/vendor")
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gio, GLib, Graphene, Gtk  # noqa: E402

FABRIC_MODS = ("Sodium", "Lithium", "Iris Shaders", "Mod Menu", "Fabric API", "Xaero's Minimap", "Sound Physics")
FAKE_INSTANCES = (
    ("Supervivencia", "1.21.11", "fabric", "0.19.3", 4, 6, 42_300, 1, "java"),
    ("Create Nova", "1.21.1", "neoforge", "21.1.231", 8, 14, 15_400, 2, "java"),
    ("Servidor de amigos", "1.20.1", "forge", "47.3.0", 6, 5, 7_900, 3, "java"),
    ("Vanilla limpio", "1.21.4", "vanilla", "", 3, 0, 900, 4, "java"),
    ("Prueba en Rust", "1.21.11", "vanilla", "", 4, 0, 5_400, 0, "pomme"),
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
    for number, (name, version, loader, loader_version, memory, mods, seconds, artwork, client) in enumerate(FAKE_INSTANCES):
        folder = root / "instances" / f"demo{number}"
        (folder / "game").mkdir(parents=True)
        (folder / "instance.json").write_text(json.dumps({
            "version": version, "loader": loader, "loader_version": loader_version, "java": "", "jvm_args": "",
            "memory_min": 0, "name": name, "memory": memory, "artwork": artwork, "pack": False, "cover": "", "client": client,
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
    # Independent instance: without this a running Nova Launcher would receive the "activate" instead.
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    app.check_release = lambda: None
    app.ask_usage = lambda: False  # the first-run prompt would cover every shot
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
        app.page_stack.set_transition_duration(0)   # a window that is not in front draws no animation frames
        try:
            prepare()
        except Exception:  # keep going: one broken scene must not stop the others
            import traceback
            traceback.print_exc()

        def shoot():
            target = app.window
            dialog = next((w for w in Gtk.Window.list_toplevels()
                           if w is not app.window and w.get_visible() and w.get_transient_for() is app.window), None)
            if name == "menu" and state["popover"] is not None:
                dialog = state["popover"]
                dialog.destroy = lambda: None
            app.window.present()   # a window that is not in front may not draw its frames
            try:
                snapshot(dialog or target, out / f"{name}.png")
            except TypeError:  # the window had not been drawn yet: wait a moment and try again, up to three times
                state["tries"] = state.get("tries", 0) + 1
                if state["tries"] < 4:
                    GLib.timeout_add(1500, shoot)
                    return False
                print("no se pudo capturar", name)
            state["tries"] = 0
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



def find_widget(root, test):
    walk = [root]
    while walk:
        widget = walk.pop(0)
        if test(widget):
            return widget
        child = widget.get_first_child()
        while child:
            walk.append(child)
            child = child.get_next_sibling()
    return None


def no_animations(root):
    """Every Gtk.Stack under ``root`` switches at once: a window that is not in front draws no animation frames."""
    walk = [root]
    while walk:
        widget = walk.pop()
        if isinstance(widget, Gtk.Stack):
            widget.set_transition_duration(0)
        child = widget.get_first_child()
        while child:
            walk.append(child)
            child = child.get_next_sibling()


def local_demo():
    """A made-up local server (no download) so the Mi servidor screens have something to show."""
    import servidor_local as sl
    sid = "0123456789ab"
    path = sl.folder(sid)
    (path / "plugins").mkdir(parents=True, exist_ok=True)
    (path / "world").mkdir(exist_ok=True)
    (path / "plugins" / "EssentialsX.jar").write_bytes(b"x" * 2_400_000)
    (path / "plugins" / "WorldEdit.jar").write_bytes(b"x" * 4_100_000)
    (path / "plugins" / "config.yml").write_text("spawn: true\n")
    (path / "plugins" / "Dynmap.jar.disabled").write_bytes(b"x" * 9_800_000)
    (path / "plugins" / "Vault").mkdir(exist_ok=True)
    (path / "server.properties").write_text("motd=Los pibes - Nova Launcher\nserver-port=25565\ngamemode=survival\ndifficulty=normal\nmax-players=10\n")
    sl.write_eula(path)
    sl.save({"id": sid, "name": "Los pibes", "kind": "paper", "version": "1.21.11", "memory": 4, "port": 25565,
             "java_component": "java-runtime-delta", "java_major": 21, "created": 1, "eula": True})
    runner = sl.runner(sid)
    runner.lines.clear()
    runner.lines.extend(["[Nova] Encendiendo «Los pibes»…", "[10:32:01 INFO]: Starting minecraft server version 1.21.11",
                         "[10:32:04 INFO]: Loading properties", "[10:32:09 INFO]: Done (7.842s)! For help, type \"help\"",
                         "[10:33:12 INFO]: Alex joined the game", "> whitelist add Sofi", "[10:33:20 INFO]: Added Sofi to the whitelist"])
    runner.state = "running"
    runner.pid, runner.started_at, runner.online = os.getpid(), time.time() - 8100, {"Alex", "Sofi", "Mati"}
    (path / "ops.json").write_text('[{"uuid": "1", "name": "Alex", "level": 4, "bypassesPlayerLimit": false}]')
    (path / "whitelist.json").write_text('[{"uuid": "2", "name": "Sofi"}, {"uuid": "3", "name": "Mati"}, {"uuid": "4", "name": "Alex"}]')
    (path / "banned-players.json").write_text('[{"uuid": "5", "name": "Troll99", "created": "x", "source": "Nova", "expires": "forever", "reason": "x"}]')
    import zipfile
    (path / "backups").mkdir(exist_ok=True)
    for index, name in enumerate(("auto-2026-11-15-120000.zip", "auto-2026-11-15-060000.zip", "mundo-2026-11-14-221500.zip", "antes-2026-11-14-190000.zip")):
        with zipfile.ZipFile(path / "backups" / name, "w") as archive:
            archive.writestr("world/level.dat", "x" * (900_000 + index * 150_000))
        os.utime(path / "backups" / name, (time.time() - 3600 * (index * 7 + 1),) * 2)
    return sid


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

    def pomme():
        app.leave_page()
        app.selected = DATA / "nova-launcher" / "instances" / "demo4"
        app.refresh()

    def pomme_download():
        pomme()
        app.confirm_pomme_install()

    def drop():
        hint = app.window.get_child().get_last_child()
        hint.set_visible(True)

    def modrinth():
        import biblioteca
        biblioteca.Browser(app, app.selected, app.instances.get(app.selected), "mod")

    def modpacks():
        import biblioteca
        biblioteca.Browser(app, None, None, "modpack")

    def local_list():
        local_demo()
        app.leave_page()
        app.show_local_servers()

    def local_detail(tab=0, folder=None, tall=False, source=None):
        def run():
            if tall:
                app.window.set_default_size(1280, 1100)
            local_demo()
            app.leave_page()
            app.show_local_servers()
            window = app.current_page[1]
            no_animations(window)
            opener = find_widget(window, lambda w: isinstance(w, Gtk.Button) and w.get_label() == "Abrir")
            opener.emit("clicked")
            no_animations(window)
            section = ("Consola", "Estado", "Jugadores", "Archivos", "Plugins", "Respaldos", "Amigos", "Ajustes")[tab]
            find_widget(window, lambda w: isinstance(w, Gtk.Button) and w.get_label() == section).emit("clicked")
            if source:   # switch the catalog to another source, as a person would with the selector
                chooser = find_widget(window, lambda w: isinstance(w, Gtk.ComboBoxText) and w.get_active_id() == "modrinth")
                chooser.set_active_id(source)
            if folder:
                go = find_widget(window, lambda w: isinstance(w, Gtk.Button) and w.get_label() == folder)
                go.emit("clicked")
        return run

    def local_import():
        app.leave_page()
        demo = DATA / "viejo" / "Mi servidor viejo"
        (demo / "world").mkdir(parents=True, exist_ok=True)
        (demo / "paper-1.21.11-132.jar").write_bytes(b"PK" + b"x" * 5000)
        (demo / "world" / "level.dat").write_bytes(b"x" * 3_000_000)
        (demo / "version_history.json").write_text('{"currentVersion": "git-Paper-132 (MC: 1.21.11)"}')
        (demo / "server.properties").write_text("server-port=25570\n")
        app.import_local_server(app.window, lambda sid: None).inspect_folder(str(demo))

    def local_create():
        app.leave_page()
        app.create_local_server(app.window, lambda sid: None)

    def tall():
        app.window.set_default_size(1280, 1180)

    return [
        ("juegos", app.show_games, 500),
        ("roblox", lambda: app.choose_game("roblox", save=False), 4000),
        ("roblox-amigos", lambda: (app.choose_game("roblox", save=False), app.roblox_open_tab("fun-with-friends")), 4000),
        ("principal", lambda: app.choose_game("minecraft", save=False), 400),
        ("biblioteca", tall, 900),
        ("soltar", drop, 400),
        ("pomme", pomme, 700),
        ("pomme-descarga", pomme_download, 900),
        ("salud", health, 1500),
        ("plantillas", page("show_templates"), 900),
        ("estadisticas", page("show_statistics"), 900),
        ("respaldos", page("show_backups"), 900),
        ("almacenamiento", page("show_storage"), 900),
        ("editar", edit, 900),
        ("nueva-instancia", new, 700),
        ("menu", menu, 900),
        ("revisar", review, 900),
        ("modrinth", modrinth, 5000),
        ("modpacks", modpacks, 5000),
        ("servidor-lista", local_list, 900),
        ("servidor-consola", local_detail(0), 900),
        ("servidor-ajustes", local_detail(7), 2500),
        ("servidor-archivos", local_detail(3), 2500),
        ("servidor-catalogo", local_detail(4), 6000),
        ("servidor-amigos", local_detail(6), 2500),
        ("servidor-estado", local_detail(1), 4500),
        ("servidor-jugadores", local_detail(2), 2500),
        ("servidor-respaldos", local_detail(5), 2500),
        ("servidor-importar", local_import, 2500),
        ("v-estado", local_detail(1, tall=True), 4500),
        ("v-jugadores", local_detail(2, tall=True), 2500),
        ("v-respaldos", local_detail(5, tall=True), 2500),
        ("v-ajustes", local_detail(7, tall=True), 2500),
        ("v-hangar", local_detail(4, tall=True, source="hangar"), 7000),
        ("servidor-crear", local_create, 3500),
        ("mods", mods, 700),
        ("nueva", add, 700),
        ("importar", importing, 700),
    ]


if __name__ == "__main__":
    main()

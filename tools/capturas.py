#!/usr/bin/env python3
"""Render Nova Launcher with made-up demo data and save screenshots as PNG.

It never touches your real launcher data: everything lives in a temporary XDG_DATA_HOME.
No network, no account. Used to keep the website screenshots in sync with the app.

    python3 tools/capturas.py SALIDA            # writes SALIDA/<name>.png for every scene
    python3 tools/capturas.py SALIDA principal  # only the named scenes
    NOVA_CAPTURA_TEMA=light python3 tools/capturas.py SALIDA
    NOVA_CAPTURA_IDIOMA=en python3 tools/capturas.py SALIDA
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
    (root / "settings.json").write_text(json.dumps({"theme": theme, "memory": 4, "language": os.environ.get("NOVA_CAPTURA_IDIOMA", "es")}), encoding="utf-8")


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
    sl.local_address = lambda port: f"192.168.1.20:{port}"  # an example: never publish the real address of this PC
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

    def instance_folder():
        return DATA / "nova-launcher" / "instances" / "demo0"

    def health_java():
        """Instance whose chosen Java no longer exists: the real finding and its one-click fix."""
        config = instance_folder() / "instance.json"
        data = json.loads(config.read_text(encoding="utf-8"))
        data["java"] = "/opt/jdk-17-viejo/bin/java"
        config.write_text(json.dumps(data), encoding="utf-8")
        app.refresh()
        app.leave_page()
        app.show_health(instance_folder())

    def failure(log_text, report_text=""):
        def run():
            import consola
            app.choose_game("minecraft", save=False)
            game = instance_folder() / "game"
            if report_text:
                (game / "crash-reports").mkdir(parents=True, exist_ok=True)
                (game / "crash-reports" / "crash-2026-11-20_10.00.00-client.txt").write_text(report_text, encoding="utf-8")
            cause = consola.analyze(log_text, game)
            app.status.set_text(consola.failure_message(1, cause))
            app.failure_log.set_visible(True)
            app.failure_action = (instance_folder(), cause["action"]) if cause["action"] else None
            app.failure_fix.set_visible(bool(cause["action"]))
        return run

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

    def signed():
        app.roblox_person = {"id": 156, "name": "alex_demo", "display": "Alex", "picture": ""}
        app.roblox_loaded = False

    def roblox_friends_scene():
        signed()
        people = [(156, "builderman", "builderman"), (1, "Roblox", "Roblox")]
        app.preferences = {**app.preferences, "roblox_friend_list": [{"id": i, "name": n, "display": d} for i, n, d in people]}
        app.choose_game("roblox", save=False)
        app.roblox_open_tab("top-trending")
        app.roblox_render_friends()
        GLib.timeout_add(3600, lambda: app.roblox_scroll.get_vadjustment().set_value(0) or False)  # the shot is taken at 4 s

    def roblox_paid_scene():
        signed()
        app.choose_game("roblox", save=False)
        app.roblox_open_tab("fun-with-friends")
        GLib.timeout_add(2500, lambda: app.roblox_scroll.get_vadjustment().set_value(app.roblox_scroll.get_vadjustment().get_upper()) or False)

    def roblox_login_scene():
        app.roblox_person = None
        app.choose_game("roblox", save=False)

    def roblox_guide_scene():
        roblox_login_scene()
        app.roblox_client_guide(lambda: None)

    def roblox_servers_scene():
        signed()
        app.choose_game("roblox", save=False)
        GLib.timeout_add(1500, lambda: app.roblox_servers({"place": 920587237, "name": "Adopt Me!", "universe": None}) or False)

    def settings_scene(top=False):
        app.choose_game("minecraft", save=False)
        app.global_settings()

        def bottom():
            def walk(widget):
                if isinstance(widget, Gtk.ScrolledWindow):
                    adj = widget.get_vadjustment()
                    adj.set_value(0 if top else adj.get_upper())
                child = widget.get_first_child()
                while child:
                    walk(child)
                    child = child.get_next_sibling()
            if app.current_page:
                walk(app.current_page[1])
            return False
        GLib.timeout_add(1200, bottom)

    def update_card_scene():
        app.choose_game("minecraft", save=False)
        app.release_note.set_text("Listo para instalar · v1.14.0")
        app.release_card.add_css_class("update")
        app.leave_page()

    def skins_scene():
        import skinlib
        app.choose_game("minecraft", save=False)
        app.leave_page()
        app.open_skins()
        editor = app.current_page and getattr(app.current_page[0], "editor", None)
        import skins as skins_module
        for obj in __import__("gc").get_objects():
            if isinstance(obj, skins_module.Editor):
                editor = obj
        # three made-up skins so the library, the thumbnails and the 3D view have something to show
        def dress(body, legs, hair):
            pixels = skinlib.seed()
            for part, rgb in ((1, body), (2, body), (3, body), (4, legs), (5, legs)):
                for side in range(6):
                    u, v, w, h = skinlib.face(part, side)
                    for y in range(v, v + h):
                        for x in range(u, u + w):
                            pixels[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4] = bytes((*rgb, 255))
            for side in range(6):
                u, v, w, h = skinlib.face(0, side, overlay=True)
                for y in range(v, v + h):
                    for x in range(u, u + w):
                        if side in (1, 2, 3, 4) or y < v + 3:
                            pixels[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4] = bytes((*hair, 255))
            return pixels
        demo = (("Caballero azul", (52, 101, 190), (40, 48, 90), (60, 40, 30)),
                ("Mago violeta", (133, 91, 201), (64, 50, 110), (210, 210, 220)),
                ("Explorador", (96, 140, 70), (92, 70, 48), (120, 80, 40)))
        for name, body, legs, hair in demo:
            editor.pixels[:] = dress(body, legs, hair)
            editor.write(editor.library / editor.profile / f"{name}.png")
        editor.open_file(editor.library / editor.profile / "Caballero azul.png", library=True)
        editor.yaw = 0.62
        editor.invalidate()
        import os
        if os.environ.get("NOVA_SKIN_TEST"):
            def drive():
                zoom, left, top = editor.geometry(editor.canvas.get_width(), editor.canvas.get_height())
                def at(col, row):
                    return left + col * zoom + zoom / 2, top + row * zoom + zoom / 2
                out = []
                before = bytes(editor.pixels)
                editor.pick_tool("pencil"); editor.color.set_rgba(editor.rgba("#ff0000"))
                editor.stroke_begin(None, *at(10, 10)); editor.apply_at(*at(12, 10)); editor.stroke_end()
                idx = lambda c, r: (r * 64 + c) * 4
                out.append(("pencil", bytes(editor.pixels[idx(10, 10):idx(10, 10) + 4]), bytes(editor.pixels[idx(11, 10):idx(11, 10) + 4])))
                out.append(("history", len(editor.history), editor.dirty))
                editor.undo(); out.append(("undo", bytes(editor.pixels) == before))
                editor.redo(); out.append(("redo", bytes(editor.pixels) != before))
                editor.pick_tool("eraser"); editor.stroke_begin(None, *at(10, 10)); editor.stroke_end()
                out.append(("erase-base-kept", editor.pixels[idx(10, 10) + 3]))
                editor.stroke_begin(None, *at(40, 10)); editor.stroke_end()
                out.append(("erase-overlay", editor.pixels[idx(40, 10) + 3]))
                editor.pick_tool("fill"); editor.stroke_begin(None, *at(20, 20)); editor.stroke_end()
                out.append(("fill", bytes(editor.pixels[idx(21, 21):idx(21, 21) + 4])))
                editor.mirror_button.set_active(True); editor.pick_tool("pencil")
                editor.stroke_begin(None, *at(9, 9)); editor.stroke_end()
                other = skinlib.mirror_texel(9, 9)
                out.append(("mirror", bytes(editor.pixels[idx(*other):idx(*other) + 4])))
                editor.set_slim(True); out.append(("slim", editor.slim))
                from pathlib import Path
                target = editor.library / editor.profile / "Prueba skin.png"
                out.append(("save", editor.write(target), target.is_file(), editor.dirty, editor.current == target))
                out.append(("rows", [r.path.name for r in iter(lambda r=[editor.rows.get_first_child()]: r.__setitem__(0, r[0].get_next_sibling()) or r[0], None)] if False else target.name))
                before_open = bytes(editor.pixels)
                editor.pick_tool("pencil"); editor.stroke_begin(None, *at(11, 11)); editor.stroke_end()
                out.append(("dirty-after-edit", editor.dirty))
                out.append(("reopen", editor.open_file(target, library=True), bytes(editor.pixels) == before_open, editor.dirty, editor.slim))
                target.unlink()
                editor.spin(0.6); editor.face_front()
                print("SKINTEST", out)
                return False
            GLib.timeout_add(800, drive)

    def launching_scene():
        app.choose_game("minecraft", save=False)
        app.leave_page()
        folder = app.selected
        instance = dict(app.instances[folder])
        app.launch_screen_show(folder, instance, app.profile or "Alex")
        app.launch_screen_update("Descargando recursos de Minecraft…")
        app.launch_view.set_opacity(1.0)
        import os
        if os.environ.get("NOVA_LAUNCH_TEST"):
            out = []

            def step(n):
                if n == 0:
                    app.launch_screen_update("Iniciando Minecraft…")
                    out.append(("iniciando", app.launch_step))
                elif n == 1:
                    app.launch_screen_started(False)
                    out.append(("abierto", app.launch_step, app.launch_view.get_visible()))
                elif n == 2:
                    out.append(("tras-1.4s", app.launch_view.get_visible()))
                    app.launch_screen_show(folder, instance, "Alex")
                    app.launch_screen_update("Descargando recursos de Minecraft…")
                    app.launch_screen_finished(True, "Minecraft terminó con código 1.")
                    out.append(("fallo", app.launch_failed, app.launch_log.get_visible(), app.launch_view.get_visible()))
                    app.launch_screen_hide()
                    app.preferences = {**app.preferences, "launch_screen": False}
                    app.launch_screen_show(folder, instance, "Alex")
                    out.append(("desactivada", app.launch_view.get_visible()))
                    print("LAUNCHTEST", out)
                    return False
                GLib.timeout_add(1700 if n == 1 else 100, step, n + 1)
                return False
            GLib.timeout_add(300, step, 0)

    def roblox_favs():
        signed()
        games = app.roblox_data.get("top-trending", [])
        app.preferences = {**app.preferences, "roblox_favs": games[:6], "roblox_recent": games[6:12]}
        app.choose_game("roblox", save=False)
        app.roblox_open_tab("favs")

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
        ("juegos", app.show_games, 3500),
        ("roblox", lambda: (signed(), app.choose_game("roblox", save=False)), 4000),
        ("roblox-favoritos", roblox_favs, 4000),
        ("roblox-amigos", roblox_friends_scene, 4000),
        ("roblox-sesion", roblox_login_scene, 4000),
        ("lanzando", launching_scene, 2500),
        ("skins", skins_scene, 2500),
        ("ajustes-nova", settings_scene, 2500),
        ("ajustes-idioma", lambda: settings_scene(True), 2500),
        ("actualizacion", update_card_scene, 1200),
        ("roblox-servidores", roblox_servers_scene, 5000),
        ("roblox-guia", roblox_guide_scene, 3000),
        ("roblox-pago", roblox_paid_scene, 5000),
        ("principal", lambda: app.choose_game("minecraft", save=False), 400),
        ("biblioteca", tall, 900),
        ("soltar", drop, 400),
        ("pomme", pomme, 700),
        ("pomme-descarga", pomme_download, 900),
        ("salud", health, 1500),
        ("salud-java", health_java, 1500),
        ("fallo-java", failure("java.lang.UnsupportedClassVersionError: class file version 65.0"), 900),
        ("fallo-mod", failure("net.fabricmc.loader: Mixin apply failed", "---- Minecraft Crash Report ----\nDescription: Mod initialization failed\n\nSuspected Mods: \n\tSodium (sodium)\n"), 900),
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

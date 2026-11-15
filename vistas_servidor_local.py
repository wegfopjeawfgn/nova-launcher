"""Nova window: Mi servidor, servidores de Minecraft Java en este equipo (crear, encender, consola, ajustes, archivos)."""
from pathlib import Path
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gio, Gtk, Pango

import errores
import motor
import servidor_local as sl
import tunel_playit as tp
from widgets import button, label

STATES = {"stopped": "Apagado", "starting": "Encendiendo…", "running": "Encendido", "stopping": "Apagando…"}
GAMEMODES = (("survival", "Supervivencia"), ("creative", "Creativo"), ("adventure", "Aventura"), ("spectator", "Espectador"))
DIFFICULTIES = (("peaceful", "Pacífico"), ("easy", "Fácil"), ("normal", "Normal"), ("hard", "Difícil"))
QUICK = (("Mundo", "world"), ("Configuración", "config"), ("Registros", "logs"))


def icon(name):
    """A bundled Nova icon when there is one (the system theme may not have it), else the theme's."""
    bundled = Path(__file__).resolve().parent / "icons" / f"{name}.svg"
    return Gtk.Image.new_from_file(str(bundled)) if bundled.is_file() else Gtk.Image.new_from_icon_name(name)


def Path_suffix(name):
    return "." + name.lower().rsplit(".", 1)[-1] if "." in name else ""


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def chip(state):
    widget = Gtk.Label(label=STATES[state], css_classes=["chip"] + (["chip-accent"] if state == "running" else []))
    return widget


def local_notice(short=False):
    """Visible reminder that these servers run on this computer, not in the cloud."""
    box = Gtk.Box(spacing=10, css_classes=["catalog-row"])
    box.append(icon("network-server-symbolic"))
    text = label("Servidor local: corre en tu computadora, no en la nube. Si la apagás o cerrás Nova, se apaga."
                 if short else
                 "Estos servidores son locales: corren en tu computadora, no en la nube. Solo están disponibles mientras tu PC esté "
                 "encendida y el servidor prendido, y gastan memoria y procesador mientras juegan. Tus amigos entran por tu red "
                 "o por un túnel; no hay alojamiento de Nova.", "muted")
    text.set_wrap(True)
    text.set_hexpand(True)
    box.append(text)
    return box


class ServidorLocalMixin:
    # ------------------------------------------------------------ pantalla principal
    def show_local_servers(self):
        dialog = Gtk.Window(title="Mi servidor", transient_for=self.window, modal=True, default_width=860, default_height=620)
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        dialog.set_child(stack)
        cleanups = []
        state = {"current": None}

        def on_close(_):
            for cleanup in cleanups:
                cleanup()
            return False

        dialog.connect("close-request", on_close)

        def refresh_list():
            while child := list_rows.get_first_child():
                list_rows.remove(child)
            servers = sl.all_servers()
            if not servers:
                empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["catalog-row"])
                empty.append(label("Todavía no tenés servidores", "form-label"))
                text = label("Creá un servidor para jugar con tus amigos. Corre en tu computadora: mientras esté encendida, "
                             "entran en tu red local o por un túnel.", "muted")
                text.set_wrap(True)
                empty.append(text)
                list_rows.append(empty)
            for meta in servers:
                runner = sl.RUNNERS.get(meta["id"])
                current = runner.state if runner else "stopped"
                row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
                title = label(meta["name"], "form-label")
                title.set_ellipsize(Pango.EllipsizeMode.END)
                info.append(title)
                info.append(label(f"{sl.KINDS[meta['kind']]} · {meta['version']} · puerto {meta['port']} · {meta['memory']} GB", "muted"))
                row.append(info)
                row.append(chip(current))
                if current == "stopped":
                    row.append(button("Encender", lambda sid=meta["id"]: start(sid), "primary"))
                elif current in ("starting", "running"):
                    row.append(button("Apagar", lambda sid=meta["id"]: sl.runner(sid).stop()))
                row.append(button("Abrir", lambda sid=meta["id"]: open_detail(sid)))
                list_rows.append(row)

        def start(sid):
            runner = sl.runner(sid)
            meta = sl.load(sid)
            if meta and not sl.eula_accepted(sl.folder(sid)):
                self.ask_eula(dialog, meta, lambda: start(sid))
                return
            feedback.set_text("Encendiendo… la primera vez puede tardar mientras se prepara el mundo.")

            def worker():
                try:
                    runner.start(status=lambda text: GLib.idle_add(feedback.set_text, text))
                except Exception as error:
                    GLib.idle_add(feedback.set_text, f"No se pudo encender: {error}")
                else:
                    GLib.idle_add(feedback.set_text, "")

            threading.Thread(target=worker, daemon=True).start()

        def watch(sid):
            runner = sl.runner(sid)

            def listener(kind, payload):
                if kind in ("state", "error"):
                    GLib.idle_add(refresh_all)
            runner.listeners.append(listener)
            cleanups.append(lambda: runner.listeners.remove(listener) if listener in runner.listeners else None)

        def refresh_all():
            if state["current"] is None:
                refresh_list()
            return False

        # ---- lista
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        header = Gtk.Box(spacing=10)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        titles.append(label("Mi servidor", "subheading"))
        titles.append(label("Servidores de Minecraft Java que corren en este equipo. Gratis y sin cuentas.", "muted"))
        header.append(titles)
        header.append(button("Crear servidor", lambda: self.create_local_server(dialog, lambda sid: (watch(sid), refresh_list())), "primary"))
        page.append(header)
        page.append(local_notice())
        feedback = label("", "muted")
        feedback.set_wrap(True)
        page.append(feedback)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        list_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.set_child(list_rows)
        page.append(scroll)
        stack.add_named(page, "list")
        for meta in sl.all_servers():
            watch(meta["id"])

        # ---- detalle
        def open_detail(sid):
            meta = sl.load(sid)
            if meta is None:
                refresh_list()
                return
            old = stack.get_child_by_name("detail")
            if old:
                stack.remove(old)
            state["current"] = sid
            view, teardown = self.local_server_detail(dialog, sid, back=lambda: close_detail(teardown))
            cleanups.append(teardown)
            stack.add_named(view, "detail")
            stack.set_visible_child_name("detail")

        def close_detail(teardown):
            teardown()
            state["current"] = None
            stack.set_visible_child_name("list")
            refresh_list()

        refresh_list()
        self.show_page(dialog)

    # ------------------------------------------------------------ EULA
    def ask_eula(self, parent, meta, then):
        dialog = Gtk.Dialog(title="EULA de Mojang", transient_for=parent, modal=True, default_width=460)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Acepto, encender", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        box.append(label("Para encender el servidor aceptá el EULA", "subheading"))
        text = label("Mojang exige aceptar su contrato de usuario final para correr un servidor. Nova no lo acepta por vos: "
                     "leelo y, si estás de acuerdo, tocá «Acepto».", "muted")
        text.set_wrap(True)
        box.append(text)
        link = Gtk.LinkButton.new_with_label(sl.EULA_URL, "Leer el EULA de Minecraft")
        link.set_halign(Gtk.Align.START)
        box.append(link)

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                try:
                    sl.write_eula(sl.folder(meta["id"]))
                    sl.save({**meta, "eula": True})
                except OSError as error:
                    self.status.set_text(f"No se pudo guardar el EULA: {error}")
                    return
                then()

        dialog.connect("response", respond)
        dialog.present()

    # ------------------------------------------------------------ crear
    def create_local_server(self, parent, created):
        dialog = Gtk.Dialog(title="Crear servidor", transient_for=parent, modal=True, default_width=500)
        cancel = dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        make = dialog.add_button("Crear servidor", Gtk.ResponseType.NONE)
        make.add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(8)
        box.append(label("Crear servidor", "subheading"))
        box.append(label("Nombre", "form-label"))
        name = Gtk.Entry(placeholder_text="Los pibes", text="Mi servidor")
        box.append(name)
        box.append(label("Tipo", "form-label"))
        kind = Gtk.ComboBoxText()
        for key, title in sl.KINDS.items():
            kind.append(key, title)
        kind.set_active_id("paper")
        box.append(kind)
        hints = {"paper": "Paper es rápido y acepta plugins: lo más usado para jugar con amigos.",
                 "fabric": "Fabric es liviano y acepta mods modernos.",
                 "forge": "Forge acepta mods y modpacks clásicos. Crearlo tarda unos minutos: ejecuta su instalador.",
                 "vanilla": "Vanilla es el servidor oficial de Mojang, sin mods ni plugins."}
        hint = label(hints["paper"] + " El servidor es local: corre en tu computadora.", "opt-hint")
        hint.set_wrap(True)
        box.append(hint)
        box.append(label("Versión de Minecraft", "form-label"))
        version = Gtk.ComboBoxText()
        version.append("", "Cargando versiones…")
        version.set_active(0)
        box.append(version)
        box.append(label("Memoria (GB)", "form-label"))
        memory = Gtk.SpinButton.new_with_range(1, 32, 1)
        memory.set_value(4)
        box.append(memory)
        box.append(label("Puerto", "form-label"))
        used = {meta.get("port") for meta in sl.all_servers()}
        port_value = next(p for p in range(25565, 25665) if p not in used and sl.free_port(p))
        port = Gtk.SpinButton.new_with_range(1024, 65535, 1)
        port.set_value(port_value)
        box.append(port)
        eula = Gtk.CheckButton(label="Acepto el EULA de Mojang")
        box.append(eula)
        link = Gtk.LinkButton.new_with_label(sl.EULA_URL, "Leer el EULA de Minecraft")
        link.set_halign(Gtk.Align.START)
        box.append(link)
        progress = label("", "muted")
        progress.set_wrap(True)
        box.append(progress)
        error = label("", "form-error")
        error.set_wrap(True)
        box.append(error)
        working = {"on": False}

        loading = {"token": 0}

        def versions(chosen_kind, token):
            try:
                found = sl.release_versions(chosen_kind)
            except Exception as problem:
                GLib.idle_add(error.set_text, f"No se pudieron cargar las versiones: {problem}")
                return
            GLib.idle_add(fill, found, token)

        def fill(found, token):
            if token != loading["token"]:
                return  # the type changed while this list was loading
            version.remove_all()
            for item in found[:60]:
                version.append(item, item)
            version.set_active(0)

        def kind_changed(*_):
            loading["token"] += 1
            error.set_text("")
            hint.set_text(hints.get(kind.get_active_id(), "") + " El servidor es local: corre en tu computadora.")
            version.remove_all()
            version.append("", "Cargando versiones…")
            version.set_active(0)
            threading.Thread(target=versions, args=(kind.get_active_id(), loading["token"]), daemon=True).start()

        def run(_):
            if working["on"]:
                return
            chosen = version.get_active_id()
            if not chosen:
                error.set_text("Esperá a que carguen las versiones.")
                return
            try:
                sl.check_new(name.get_text(), kind.get_active_id(), chosen, memory.get_value_as_int(), port.get_value_as_int())
            except ValueError as problem:
                error.set_text(str(problem))
                return
            if not sl.free_port(port.get_value_as_int()):
                error.set_text("Ese puerto ya está en uso en este equipo. Elegí otro.")
                return
            error.set_text("")
            working["on"] = True
            make.set_sensitive(False)

            def worker():
                try:
                    meta = sl.create(name.get_text(), kind.get_active_id(), chosen, memory.get_value_as_int(),
                                     port.get_value_as_int(), eula=eula.get_active(),
                                     status=lambda text: GLib.idle_add(progress.set_text, text),
                                     progress=lambda done, total: GLib.idle_add(
                                         progress.set_text, f"Descargando el servidor… {done * 100 // total}%" if total else
                                         f"Descargando el servidor… {human_size(done)}"))
                except Exception as problem:
                    if not isinstance(problem, (OSError, ValueError, RuntimeError)):
                        errores.record(problem, "vistas_servidor_local.create")
                    GLib.idle_add(failed, str(problem))
                else:
                    GLib.idle_add(done, meta)

            threading.Thread(target=worker, daemon=True).start()

        def failed(text):
            working["on"] = False
            make.set_sensitive(True)
            progress.set_text("")
            error.set_text(f"No se pudo crear el servidor: {text}")

        def done(meta):
            dialog.destroy()
            created(meta["id"])
            self.status.set_text(f"Servidor «{meta['name']}» creado." + ("" if meta.get("eula") else " Aceptá el EULA al encenderlo."))

        make.connect("clicked", run)
        cancel.connect("clicked", lambda _: None if working["on"] else dialog.destroy())
        dialog.connect("close-request", lambda _: working["on"])
        kind.connect("changed", kind_changed)
        kind_changed()
        dialog.present()

    # ------------------------------------------------------------ detalle de un servidor
    def local_server_detail(self, parent, sid, back):
        meta = sl.load(sid)
        path = sl.folder(sid)
        runner = sl.runner(sid)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"], vexpand=True)
        subs = []

        def teardown():
            for listener in subs:
                if listener in runner.listeners:
                    runner.listeners.remove(listener)
            subs.clear()

        # ---- cabecera: nombre, estado y acciones en una sola fila
        top = Gtk.Box(spacing=8)
        top.append(button("‹ Servidores", back, "quiet-button"))
        title = label(meta["name"], "subheading")
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        top.append(title)
        state_slot = Gtk.Box()
        top.append(state_slot)
        message = label("", "muted")
        message.set_wrap(True)
        message.set_visible(False)
        message.connect("notify::label", lambda w, _p: w.set_visible(bool(w.get_label())))
        b_start = button("Encender", lambda: do_start(), "primary")
        b_stop = button("Apagar", lambda: runner.stop())
        b_restart = button("Reiniciar", lambda: do_restart())
        b_play = button("Jugar con Nova", lambda: play(sl.read_properties(path).get("server-port", meta["port"])), "primary")
        more = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Más acciones")
        more.update_property([Gtk.AccessibleProperty.LABEL], ["Más acciones del servidor"])
        more_pop = Gtk.Popover()
        more_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
        more_pop.set_child(more_box)
        more.set_popover(more_pop)
        more_box.append(button("Abrir carpeta del servidor", lambda: (more_pop.popdown(), motor.open_folder(path))))
        b_delete = button("Eliminar servidor…", lambda: (more_pop.popdown(), do_delete()), "danger")
        more_box.append(b_delete)
        for widget in (b_start, b_stop, b_restart, b_play, more):
            top.append(widget)
        root.append(top)

        # ---- tarjeta de información: aviso de servidor local y direcciones
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["catalog-row"])
        notice = Gtk.Box(spacing=8)
        notice.append(icon("network-server-symbolic"))
        notice.append(label("Servidor local · corre en tu computadora: si la apagás o cerrás Nova, se apaga.", "muted"))
        info.append(notice)
        addr_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.append(addr_slot)
        root.append(info)
        root.append(message)

        def say(text):
            GLib.idle_add(message.set_text, text)

        def do_start():
            current = sl.load(sid) or meta
            if not sl.eula_accepted(path):
                self.ask_eula(parent, current, do_start)
                return
            message.set_text("Encendiendo… la primera vez puede tardar mientras se prepara el mundo.")

            def worker():
                try:
                    runner.start(status=say)
                except Exception as error:
                    say(f"No se pudo encender: {error}")
                else:
                    say("")
            threading.Thread(target=worker, daemon=True).start()

        def do_restart():
            try:
                runner.restart()
                message.set_text("Reiniciando…")
            except Exception as error:
                message.set_text(f"No se pudo reiniciar: {error}")

        def do_delete():
            if runner.state != "stopped":
                message.set_text("Apagá el servidor antes de eliminarlo.")
                return
            confirm = Gtk.Dialog(title="Eliminar servidor", transient_for=parent, modal=True, default_width=440)
            confirm.add_button("Cancelar", Gtk.ResponseType.CANCEL)
            confirm.add_button("Eliminar para siempre", Gtk.ResponseType.OK).add_css_class("danger")
            area = confirm.get_content_area()
            area.add_css_class("menu")
            area.set_spacing(8)
            area.append(label(f"¿Eliminar «{meta['name']}»?", "subheading"))
            size = label(f"Se borran el mundo, los mods o plugins y todos los archivos ({human_size(sl.folder_size(path))}). "
                         "No se puede deshacer.", "muted")
            size.set_wrap(True)
            area.append(size)

            def respond(_, response):
                confirm.destroy()
                if response != Gtk.ResponseType.OK:
                    return
                try:
                    sl.delete(sid)
                except (OSError, RuntimeError, ValueError) as error:
                    message.set_text(f"No se pudo eliminar: {error}")
                    return
                self.status.set_text(f"Servidor «{meta['name']}» eliminado.")
                back()

            confirm.connect("response", respond)
            confirm.present()

        def build_addresses():
            while child := addr_slot.get_first_child():
                addr_slot.remove(child)
            current = sl.load(sid) or meta
            port = sl.read_properties(path).get("server-port", current["port"])
            line = Gtk.Box(spacing=10)
            for caption, target in (("En este equipo", f"localhost:{port}"), ("En tu red", sl.local_address(port))):
                line.append(label(caption, "muted"))
                value = label(target, "form-label")
                value.set_selectable(True)
                line.append(value)
                line.append(button("Copiar", lambda t=target: (Gdk.Display.get_default().get_clipboard().set(t), message.set_text(f"Copiado: {t}")), "quiet-button"))
            addr_slot.append(line)
            public = (sl.load(sid) or meta).get("tunnel_address")
            if public:
                net = Gtk.Box(spacing=10)
                net.append(label("Por internet", "muted"))
                shown = label(public, "form-label")
                shown.set_selectable(True)
                net.append(shown)
                net.append(button("Copiar", lambda t=public: (Gdk.Display.get_default().get_clipboard().set(t), message.set_text(f"Copiado: {t}")), "quiet-button"))
                net.append(Gtk.Label(label="Túnel encendido" if tp.AGENT.running else "Túnel apagado", css_classes=["chip"] + (["chip-accent"] if tp.AGENT.running else [])))
                addr_slot.append(net)
            else:
                note = label("Para entrar desde otra red usá la sección «Amigos» (túnel) o abrí el puerto en tu router.", "opt-hint")
                note.set_wrap(True)
                addr_slot.append(note)

        def play(port):
            current = sl.load(sid) or meta
            instance = self.instances.get(self.selected) if self.selected else None
            if runner.state != "running":
                message.set_text("Encendé el servidor y esperá a que diga «Encendido».")
                return
            if not instance or instance["version"] != current["version"]:
                have = instance["version"] if instance else "ninguna"
                message.set_text(f"Elegí una instancia de Minecraft {current['version']} (la elegida es {have}). "
                                 "Si el servidor es Fabric, que tenga los mismos mods.")
                return
            self.leave_page()
            self.play(f"localhost:{port}")

        # ---- navegación por secciones (cada una se desplaza por su cuenta)
        pages = Gtk.Stack(vexpand=True, hexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=150)
        nav = Gtk.Box(spacing=4, css_classes=["seg"])
        seg = {}

        def show(key):
            pages.set_visible_child_name(key)
            loader = getattr(pages.get_child_by_name(key), "load_once", None)
            if loader:
                pages.get_child_by_name(key).load_once = None
                loader()
            for name, widget in seg.items():
                (widget.add_css_class if name == key else widget.remove_css_class)("seg-active")

        sections = (("console", "Consola", self.local_console_tab(runner, subs, message)),
                    ("settings", "Ajustes", self.local_settings_tab(sid, runner, message, build_addresses, title)),
                    ("files", "Archivos", self.local_files_tab(parent, sid, message)))
        catalog_text = "Plugins" if meta["kind"] == "paper" else "Mods" if sl.catalog_available(meta) else "Catálogo"
        sections += (("catalog", catalog_text, self.local_catalog_tab(sid, runner, message)),
                     ("friends", "Amigos", self.local_tunnel_tab(sid, runner, message, build_addresses, subs)))
        for key, text, widget in sections:
            pages.add_named(widget, key)
            seg[key] = button(text, lambda k=key: show(k), "seg-button")
            nav.append(seg[key])
        root.append(nav)
        root.append(pages)
        show("console")

        def sync(*_):
            current = runner.state
            while child := state_slot.get_first_child():
                state_slot.remove(child)
            state_slot.append(chip(current))
            b_start.set_visible(current == "stopped")
            b_stop.set_visible(current in ("starting", "running"))
            b_restart.set_visible(current in ("starting", "running"))
            b_play.set_visible(current == "running")
            b_delete.set_sensitive(current == "stopped")
            return False

        def listener(kind, payload):
            if kind == "state":
                GLib.idle_add(sync)
            elif kind == "error":
                say(f"No se pudo reiniciar: {payload}")

        runner.listeners.append(listener)
        subs.append(listener)
        build_addresses()
        sync()
        return root, teardown

    # ---- consola
    def local_console_tab(self, runner, subs, message):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, cursor_visible=False,
                            left_margin=8, right_margin=8, top_margin=6, bottom_margin=6)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(view)
        box.append(scroll)
        buffer = view.get_buffer()
        buffer.set_text("\n".join(runner.lines) + ("\n" if runner.lines else ""))
        pending = []
        lock = threading.Lock()

        def flush():
            with lock:
                lines, pending[:] = list(pending), []
            if lines:
                bottom = scroll.get_vadjustment()
                at_end = bottom.get_value() + bottom.get_page_size() >= bottom.get_upper() - 40
                buffer.insert(buffer.get_end_iter(), "\n".join(lines) + "\n")
                extra = buffer.get_line_count() - 3000
                if extra > 0:
                    buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(extra))
                if at_end:
                    GLib.idle_add(lambda: bottom.set_value(bottom.get_upper()))
            return False

        def listener(kind, payload):
            if kind == "line":
                with lock:
                    pending.append(payload)
                    first = len(pending) == 1
                if first:
                    GLib.timeout_add(120, flush)

        runner.listeners.append(listener)
        subs.append(listener)
        GLib.idle_add(lambda: scroll.get_vadjustment().set_value(scroll.get_vadjustment().get_upper()))
        row = Gtk.Box(spacing=8)
        entry = Gtk.Entry(hexpand=True, placeholder_text="Comando, por ejemplo: whitelist add Amigo  ·  op Amigo  ·  say Hola")
        entry.update_property([Gtk.AccessibleProperty.LABEL], ["Comando del servidor"])

        def send(*_):
            text = entry.get_text()
            if not text.strip():
                return
            try:
                runner.send(text)
            except RuntimeError as error:
                message.set_text(str(error))
                return
            runner.lines.append(f"> {text.strip()}")
            with lock:
                pending.append(f"> {text.strip()}")
            GLib.timeout_add(50, flush)
            entry.set_text("")

        entry.connect("activate", send)
        row.append(entry)
        row.append(button("Enviar", send))
        row.append(button("Copiar registro", lambda: Gdk.Display.get_default().get_clipboard().set("\n".join(runner.lines)), "quiet-button"))
        box.append(row)
        return box

    # ---- ajustes
    def local_settings_tab(self, sid, runner, message, rebuild, title):
        meta = sl.load(sid)
        path = sl.folder(sid)
        props = sl.read_properties(path)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, margin_end=6)
        scroll.set_child(grid)
        outer.append(scroll)

        def card(heading, column, row, rows=1):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["catalog-row"], valign=Gtk.Align.START)
            box.append(label(heading, "settings-heading"))
            grid.attach(box, column, row, 1, rows)
            return box

        def field(box, text, widget, hint=None):
            """Label on the left, control on the right (stacked for wide controls like text entries)."""
            row = Gtk.Box(spacing=12)
            caption = label(text, "form-label")
            caption.set_hexpand(True)
            caption.set_wrap(True)
            row.append(caption)
            widget.set_halign(Gtk.Align.END)
            row.append(widget)
            box.append(row)
            if hint:
                note = label(hint, "opt-hint")
                note.set_wrap(True)
                box.append(note)

        def wide(box, text, widget):
            box.append(label(text, "form-label"))
            box.append(widget)

        general = card("General", 0, 0)
        name = Gtk.Entry(text=meta["name"])
        wide(general, "Nombre", name)
        motd = Gtk.Entry(text=props.get("motd", ""))
        wide(general, "Mensaje en la lista de servidores", motd)
        memory = Gtk.SpinButton.new_with_range(1, 64, 1)
        memory.set_value(meta["memory"])
        field(general, "Memoria (GB)", memory)
        port = Gtk.SpinButton.new_with_range(1024, 65535, 1)
        port.set_value(int(props.get("server-port", meta["port"])))
        field(general, "Puerto", port, "Si lo cambiás, tus amigos tienen que usar el puerto nuevo.")

        game = card("Juego", 1, 0)
        mode = Gtk.ComboBoxText()
        for key, text in GAMEMODES:
            mode.append(key, text)
        mode.set_active_id(props.get("gamemode", "survival") if props.get("gamemode") in dict(GAMEMODES) else "survival")
        field(game, "Modo de juego", mode)
        difficulty = Gtk.ComboBoxText()
        for key, text in DIFFICULTIES:
            difficulty.append(key, text)
        difficulty.set_active_id(props.get("difficulty", "easy") if props.get("difficulty") in dict(DIFFICULTIES) else "easy")
        field(game, "Dificultad", difficulty)
        players = Gtk.SpinButton.new_with_range(1, 1000, 1)
        players.set_value(int(props.get("max-players", 20)) if props.get("max-players", "20").isdigit() else 20)
        field(game, "Máximo de jugadores", players)
        distance = Gtk.SpinButton.new_with_range(2, 32, 1)
        distance.set_value(int(props.get("view-distance", 10)) if props.get("view-distance", "10").isdigit() else 10)
        field(game, "Distancia de visión", distance, "En chunks. Más alta se ve mejor y gasta más memoria.")

        rules = card("Reglas y seguridad", 0, 1, 2)
        switches = {}
        for key, text, hint, default in (
                ("pvp", "PvP", "Los jugadores pueden pelear entre sí.", "true"),
                ("white-list", "Lista blanca", "Solo entran los que agregues con «whitelist add nombre» en la consola.", "false"),
                ("online-mode", "Solo cuentas originales de Minecraft", "Si lo apagás, entra cualquiera con cualquier nombre. No lo hagas si el servidor es público.", "true")):
            control = Gtk.Switch(active=props.get(key, default) == "true", valign=Gtk.Align.CENTER)
            control.update_property([Gtk.AccessibleProperty.LABEL], [text])
            switches[key] = control
            field(rules, text, control, hint)
        eula = card("EULA de Mojang", 1, 1)
        accepted = sl.eula_accepted(path)
        note = label("Aceptado." if accepted else "Todavía no lo aceptaste: se te pide al encender el servidor.", "opt-hint")
        note.set_wrap(True)
        eula.append(note)
        link = Gtk.LinkButton.new_with_label(sl.EULA_URL, "Leer el EULA de Minecraft")
        link.set_halign(Gtk.Align.START)
        eula.append(link)

        # barra de guardado fija: siempre a la vista, sin tener que desplazarse
        bar = Gtk.Box(spacing=10, css_classes=["catalog-row"])
        error = label("", "form-error")
        error.set_wrap(True)
        error.set_hexpand(True)
        bar.append(error)

        def save(*_):
            try:
                new_name = name.get_text().strip()
                if not 1 <= len(new_name) <= 60:
                    raise ValueError("Poné un nombre de hasta 60 caracteres.")
                others = {m["port"] for m in sl.all_servers() if m["id"] != sid}
                if port.get_value_as_int() in others:
                    raise ValueError("Otro servidor de Nova ya usa ese puerto.")
                sl.write_properties(path, {
                    "motd": motd.get_text(), "server-port": str(port.get_value_as_int()), "query.port": str(port.get_value_as_int()),
                    "gamemode": mode.get_active_id(), "difficulty": difficulty.get_active_id(),
                    "max-players": str(players.get_value_as_int()), "view-distance": str(distance.get_value_as_int()),
                    **{key: "true" if control.get_active() else "false" for key, control in switches.items()}})
                sl.save({**sl.load(sid), "name": new_name, "memory": memory.get_value_as_int(), "port": port.get_value_as_int()})
            except (OSError, ValueError) as problem:
                error.set_text(str(problem))
                return
            error.set_text("")
            title.set_text(new_name)
            rebuild()
            message.set_text("Ajustes guardados." + (" Se aplican al reiniciar el servidor." if runner.state != "stopped" else ""))

        bar.append(button("Guardar ajustes", save, "primary"))
        outer.append(bar)
        return outer

    # ---- catálogo de mods y plugins
    def local_catalog_tab(self, sid, runner, message):
        meta = sl.load(sid)
        base = sl.folder(sid)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        if not sl.catalog_available(meta):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["catalog-row"])
            card.append(label("Un servidor Vanilla no admite mods ni plugins", "form-label"))
            text = label("Creá un servidor Paper (plugins), Fabric o Forge (mods) para usar el catálogo.", "muted")
            text.set_wrap(True)
            card.append(text)
            box.append(card)
            return box
        noun = "plugins" if meta["kind"] == "paper" else "mods"
        head = Gtk.Box(spacing=8)
        search = Gtk.SearchEntry(placeholder_text=f"Buscar {noun} en Modrinth", hexpand=True)
        search.update_property([Gtk.AccessibleProperty.LABEL], [f"Buscar {noun}"])
        head.append(search)
        head.append(button("Buscar", lambda: run(0)))
        box.append(head)
        info = label(f"Solo se muestran {noun} compatibles con Minecraft {meta['version']} y {sl.KINDS[meta['kind']].split(' ')[0]}. "
                     "Los descarga Nova desde Modrinth y comprueba su SHA-512.", "opt-hint")
        info.set_wrap(True)
        box.append(info)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.set_child(rows)
        box.append(scroll)
        foot = Gtk.Box(spacing=8)
        count = label("", "muted")
        count.set_hexpand(True)
        foot.append(count)
        more = button("Cargar más", lambda: run(state["offset"], append=True), "quiet-button")
        more.set_visible(False)
        foot.append(more)
        box.append(foot)
        state = {"offset": 0, "busy": False, "token": 0}

        def downloads(n):
            return f"{n / 1_000_000:.1f} M" if n >= 1_000_000 else f"{n / 1000:.0f} mil" if n >= 10_000 else str(n)

        def render(hits, append):
            if not append:
                while old := rows.get_first_child():
                    rows.remove(old)
            installed = sl.catalog_installed(base)
            if not hits and not append:
                rows.append(label("No se encontró nada compatible. Probá con otra búsqueda.", "muted"))
            for hit in hits:
                rows.append(build_row(hit, hit["project_id"] in installed))

        def build_row(hit, is_installed):
            row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
            title = label(hit["title"], "form-label")
            title.set_ellipsize(Pango.EllipsizeMode.END)
            text.append(title)
            description = label(hit["description"], "muted")
            description.set_ellipsize(Pango.EllipsizeMode.END)
            description.set_tooltip_text(hit["description"])
            text.append(description)
            row.append(text)
            row.append(label(f"{downloads(hit['downloads'])} descargas", "muted"))
            if is_installed:
                row.append(Gtk.Label(label="Instalado", css_classes=["chip", "chip-accent"]))
                row.append(button("Quitar", lambda h=hit: remove(h), "quiet-button"))
            else:
                row.append(button("Instalar", lambda h=hit, r=row: install(h, r), "primary"))
            return row

        def run(offset, append=False):
            if state["busy"]:
                return
            state["busy"] = True
            state["token"] += 1
            token = state["token"]
            count.set_text("Buscando…")
            query = search.get_text()

            def worker():
                try:
                    result = sl.catalog_search(meta, query, offset=offset)
                except Exception as error:
                    GLib.idle_add(finish, None, str(error), append, offset, token)
                else:
                    GLib.idle_add(finish, result, "", append, offset, token)
            threading.Thread(target=worker, daemon=True).start()

        def finish(result, problem, append, offset, token):
            state["busy"] = False
            if token != state["token"]:
                return
            if result is None:
                count.set_text(f"No se pudo buscar: {problem}")
                return
            render(result["hits"], append)
            state["offset"] = offset + len(result["hits"])
            more.set_visible(state["offset"] < result["total"])
            count.set_text(f"{state['offset']} de {result['total']} resultados")

        def install(hit, row):
            for child_button in (row.get_last_child(),):
                child_button.set_sensitive(False)
                child_button.set_label("Instalando…")

            def worker():
                try:
                    installed = sl.catalog_install(base, sl.load(sid) or meta, hit["project_id"], title=hit["title"])
                except Exception as error:
                    GLib.idle_add(done, f"No se pudo instalar «{hit['title']}»: {error}", row, hit, False)
                else:
                    extra = [name for name in installed[1:]]
                    text = f"Instalado «{hit['title']}»" + (f" y sus dependencias ({', '.join(extra)})" if extra else "")
                    GLib.idle_add(done, text + ". Reiniciá el servidor para cargarlo.", row, hit, True)
            threading.Thread(target=worker, daemon=True).start()

        def done(text, row, hit, ok):
            message.set_text(text)
            parent = row.get_parent()
            if parent is None:
                return
            replacement = build_row(hit, ok)
            parent.insert_child_after(replacement, row)
            parent.remove(row)

        def remove(hit):
            try:
                sl.catalog_remove(base, sl.load(sid) or meta, hit["project_id"])
            except (OSError, ValueError) as error:
                message.set_text(str(error))
                return
            message.set_text(f"«{hit['title']}» quitado. Reiniciá el servidor para aplicarlo.")
            run(0)

        search.connect("activate", lambda _: run(0))
        search.connect("search-changed", lambda _: None)
        box.load_once = lambda: run(0)
        return box

    # ---- amigos: túnel con playit.gg
    def local_tunnel_tab(self, sid, runner, message, rebuild, subs):
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8, margin_end=6)
        scroll.set_child(box)
        state = {"busy": False}

        def card(heading):
            block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["catalog-row"])
            block.append(label(heading, "settings-heading"))
            box.append(block)
            return block

        def text(block, value, style="muted"):
            widget = label(value, style)
            widget.set_wrap(True)
            block.append(widget)
            return widget

        def open_url(url):
            Gio.AppInfo.launch_default_for_uri(url, None)

        def note(value):
            GLib.idle_add(message.set_text, value)

        def render():
            for undo in cleanup:
                undo()
            cleanup.clear()
            while old := box.get_first_child():
                box.remove(old)
            intro = card("Entrar desde otra red")
            text(intro, "Sin esto, solo entran personas que estén en tu misma red (WiFi o cable). Con un túnel, tus amigos entran "
                        "desde cualquier lugar por una dirección pública, sin abrir puertos en tu router.")
            external = card("Servicio externo: playit.gg")
            text(external, "El túnel lo da playit.gg, un servicio gratuito que no es de Nova ni de Mojang: tiene sus propias condiciones, "
                           "límites y política de privacidad, y puede cambiarlas. El tráfico de tus amigos pasa por sus servidores. "
                           "Nova usa su agente oficial (código abierto), comprueba su SHA-256 y se cierra junto con Nova.")
            link = Gtk.LinkButton.new_with_label(tp.SITE, "Ver playit.gg")
            link.set_halign(Gtk.Align.START)
            external.append(link)
            if tp.supported() is None:
                manual = card("En este sistema")
                text(manual, "El túnel integrado funciona por ahora solo en Linux de 64 bits. Podés usar playit.gg a mano: instalás su "
                             "programa, creás un túnel «Minecraft Java» hacia localhost:25565 y pasás la dirección a tus amigos.")
                return
            if tp.installed() is None:
                step = card("Paso 1 · Descargar el agente")
                consent = Gtk.CheckButton(label="Entiendo que playit.gg es un servicio externo con sus propias condiciones")
                step.append(consent)
                progress = text(step, "", "muted")
                go = button("Descargar el agente de playit", lambda: download(consent, go, progress), "primary")
                go.set_halign(Gtk.Align.START)
                go.set_sensitive(False)
                consent.connect("toggled", lambda c: go.set_sensitive(c.get_active() and not state["busy"]))
                step.append(go)
                return
            if not tp.has_secret():
                step = card("Paso 2 · Vincular tu cuenta de playit")
                text(step, "Se abre playit.gg en tu navegador para que inicies sesión (o crees una cuenta gratis) y apruebes a Nova. "
                           "Tu contraseña nunca pasa por Nova.")
                info = text(step, "", "opt-hint")
                go = button("Vincular en el navegador", lambda: link_account(go, info), "primary")
                go.set_halign(Gtk.Align.START)
                step.append(go)
                return
            running = Gtk.Box(spacing=12, css_classes=["opt-row"])
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            col.append(label("Túnel", "form-label"))
            status = label("Encendido: tus amigos pueden entrar." if tp.AGENT.running else "Apagado.", "opt-hint")
            col.append(status)
            running.append(col)
            toggle = Gtk.Switch(active=tp.AGENT.running, valign=Gtk.Align.CENTER)
            toggle.update_property([Gtk.AccessibleProperty.LABEL], ["Encender el túnel"])
            running.append(toggle)
            panel = card("Paso 3 · Encender el túnel")
            panel.append(running)

            def switched(widget, _state):
                if widget.get_active() and not tp.AGENT.running:
                    try:
                        tp.AGENT.start()
                    except (OSError, RuntimeError) as error:
                        message.set_text(str(error))
                        widget.set_active(False)
                        return True
                elif not widget.get_active() and tp.AGENT.running:
                    threading.Thread(target=tp.AGENT.stop, daemon=True).start()
                GLib.timeout_add(600, lambda: (rebuild(), render(), False)[2])
                return False

            toggle.connect("state-set", switched)
            view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, cursor_visible=False, height_request=90,
                                left_margin=6, top_margin=4)
            view.get_buffer().set_text("\n".join(list(tp.AGENT.lines)[-30:]))
            holder = Gtk.ScrolledWindow(min_content_height=90)
            holder.set_child(view)
            panel.append(holder)
            create = card("Paso 4 · Crear el túnel y guardar su dirección")
            current = (sl.load(sid) or {}).get("port", 25565)
            port = sl.read_properties(sl.folder(sid)).get("server-port", current)
            text(create, f"En tu panel de playit creá un túnel de tipo «Minecraft Java» (TCP) hacia 127.0.0.1 puerto {port}. "
                         "Playit te da una dirección (por ejemplo algo.joinmc.link): pegala acá para tenerla a mano.")
            create.append(button("Abrir mi panel de playit", lambda: open_url(tp.TUNNELS_URL), "quiet-button"))
            row = Gtk.Box(spacing=8)
            entry = Gtk.Entry(hexpand=True, placeholder_text="algo.joinmc.link", text=(sl.load(sid) or {}).get("tunnel_address", ""))
            entry.update_property([Gtk.AccessibleProperty.LABEL], ["Dirección pública del túnel"])
            row.append(entry)
            error = label("", "form-error")

            def save_address(*_):
                value = entry.get_text().strip()
                clean = tp.valid_address(value) if value else ""
                if clean is None:
                    error.set_text("Pegá solo la dirección, sin http:// ni espacios (por ejemplo algo.joinmc.link o algo.gl.at.ply.gg:12345).")
                    return
                error.set_text("")
                try:
                    meta = {**(sl.load(sid) or {})}
                    if clean:
                        meta["tunnel_address"] = clean
                    else:
                        meta.pop("tunnel_address", None)
                    sl.save(meta)
                except OSError as problem:
                    error.set_text(str(problem))
                    return
                rebuild()
                message.set_text("Dirección guardada." if clean else "Dirección quitada.")

            entry.connect("activate", save_address)
            row.append(button("Guardar", save_address, "primary"))
            create.append(row)
            create.append(error)
            account = card("Cuenta")
            account.append(button("Desvincular mi cuenta de playit", lambda: unlink(), "danger"))

            def on_agent(kind, payload):
                if kind == "line":
                    GLib.idle_add(lambda: (view.get_buffer().insert(view.get_buffer().get_end_iter(), payload + "\n"), False)[1])
            tp.AGENT.listeners.append(on_agent)
            cleanup.append(lambda: tp.AGENT.listeners.remove(on_agent) if on_agent in tp.AGENT.listeners else None)

        def unlink():
            threading.Thread(target=tp.AGENT.stop, daemon=True).start()
            tp.forget_account()
            render()
            message.set_text("Cuenta de playit desvinculada de este equipo.")

        def download(consent, go, progress):
            if state["busy"] or not consent.get_active():
                return
            state["busy"] = True
            go.set_sensitive(False)
            progress.set_text("Descargando el agente de playit…")

            def worker():
                try:
                    tp.install(lambda done, total: GLib.idle_add(progress.set_text, f"Descargando el agente de playit… {done * 100 // total}%"))
                except Exception as error:
                    state["busy"] = False
                    GLib.idle_add(progress.set_text, f"No se pudo descargar: {error}")
                    GLib.idle_add(go.set_sensitive, True)
                else:
                    state["busy"] = False
                    GLib.idle_add(render)
            threading.Thread(target=worker, daemon=True).start()

        def link_account(go, info):
            if state["busy"]:
                return
            state["busy"] = True
            go.set_sensitive(False)
            info.set_text("Preparando…")

            def worker():
                try:
                    code, url = tp.claim_start()
                except tp.ClaimError as error:
                    state["busy"] = False
                    GLib.idle_add(info.set_text, str(error))
                    GLib.idle_add(go.set_sensitive, True)
                    return
                GLib.idle_add(open_url, url)
                GLib.idle_add(info.set_text, f"Se abrió {url} en tu navegador. Iniciá sesión y aprobá a Nova; esperando… "
                                             "(si no se abrió, copiá ese enlace.)")
                try:
                    tp.claim_finish(code)
                except tp.ClaimError as error:
                    state["busy"] = False
                    GLib.idle_add(info.set_text, str(error))
                    GLib.idle_add(go.set_sensitive, True)
                    return
                state["busy"] = False
                GLib.idle_add(render)
                note("Cuenta de playit vinculada.")
            threading.Thread(target=worker, daemon=True).start()

        cleanup = []
        scroll.connect("destroy", lambda *_: [fn() for fn in cleanup])
        render()
        return scroll

    # ---- archivos
    def local_files_tab(self, parent, sid, message):
        meta = sl.load(sid)
        base = sl.folder(sid)
        runner = sl.runner(sid)
        here = {"path": "", "sort": "name", "filter": "", "picked": set()}
        MAX_ROWS = 400
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)

        # migas de pan + acciones
        top = Gtk.Box(spacing=8)
        crumbs = Gtk.Box(spacing=2, hexpand=True)
        top.append(crumbs)
        top.append(button("Agregar archivos", lambda: pick(), "primary"))
        top.append(button("Nueva carpeta", lambda: new_folder()))
        more = Gtk.MenuButton(label="Más", tooltip_text="Más acciones")
        pop = Gtk.Popover()
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
        pop.set_child(menu)
        more.set_popover(pop)
        menu.append(button("Respaldar el mundo", lambda: (pop.popdown(), backup())))
        menu.append(button("Abrir esta carpeta en el explorador",
                           lambda: (pop.popdown(), motor.open_folder(sl.safe_path(base, here["path"])))))
        menu.append(button("Recargar", lambda: (pop.popdown(), render())))
        top.append(more)
        box.append(top)

        # filtro, orden y atajos
        tools = Gtk.Box(spacing=8)
        search = Gtk.SearchEntry(placeholder_text="Filtrar por nombre", hexpand=True)
        search.update_property([Gtk.AccessibleProperty.LABEL], ["Filtrar archivos"])
        order = Gtk.ComboBoxText()
        for key, text in (("name", "Nombre"), ("size", "Tamaño"), ("date", "Fecha")):
            order.append(key, "Ordenar: " + text)
        order.set_active_id("name")
        tools.append(search)
        tools.append(order)
        box.append(tools)
        quick = Gtk.Box(spacing=6)
        quick.append(label("Ir a:", "muted"))
        shortcuts = [("Inicio", "")]
        if sl.UPLOAD_DIRS[meta["kind"]]:
            shortcuts.append(("Mods" if meta["kind"] == "fabric" else "Plugins", sl.UPLOAD_DIRS[meta["kind"]]))
        shortcuts += [("Mundo", "world"), ("Configuración", "config"), ("Registros", "logs"), ("Respaldos", "backups")]
        for text, target in shortcuts:
            quick.append(button(text, lambda t=target: go(t, create=t in ("mods", "plugins", "config")), "quiet-button"))
        box.append(quick)

        # barra de selección
        selection = Gtk.Box(spacing=8, css_classes=["catalog-row"])
        picked_label = label("", "form-label")
        picked_label.set_hexpand(True)
        selection.append(picked_label)
        selection.append(button("Guardar copia en…", lambda: export_picked(), "quiet-button"))
        selection.append(button("Eliminar", lambda: delete_picked(), "danger"))
        selection.append(button("Quitar selección", lambda: (here["picked"].clear(), render()), "quiet-button"))
        selection.set_visible(False)
        box.append(selection)

        # lista
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll.set_child(rows)
        box.append(scroll)
        footer = Gtk.Box(spacing=8)
        count = label("", "muted")
        count.set_hexpand(True)
        footer.append(count)
        footer.append(label("Arrastrá archivos acá para agregarlos a esta carpeta.", "opt-hint"))
        box.append(footer)

        def kind_icon(entry):
            if entry["dir"]:
                return "folder-symbolic"
            suffix = entry["name"].lower().rsplit(".", 1)[-1] if "." in entry["name"] else ""
            if entry["name"].lower().endswith(".jar.disabled") or suffix in ("jar", "zip", "gz", "tar"):
                return "package-x-generic-symbolic"
            if suffix in ("png", "jpg", "jpeg", "gif", "webp"):
                return "image-x-generic-symbolic"
            return "text-x-generic-symbolic"

        def editable(name):
            return Path_suffix(name) in sl.TEXT_SUFFIXES or name in ("ops.json", "whitelist.json", "banned-players.json")

        def child(name):
            return f"{here['path']}/{name}" if here["path"] else name

        def go(relative, create=False):
            try:
                target = sl.safe_path(base, relative)
                if create and not target.exists():
                    target.mkdir(parents=True)
                if not target.is_dir():
                    message.set_text("Esa carpeta todavía no existe: aparece cuando el servidor la crea.")
                    return
            except (OSError, ValueError) as error:
                message.set_text(str(error))
                return
            here["path"] = relative
            here["picked"].clear()
            render()

        def render_crumbs():
            while old := crumbs.get_first_child():
                crumbs.remove(old)
            parts = [part for part in here["path"].split("/") if part]
            crumbs.append(button("Servidor", lambda: go(""), "quiet-button"))
            for index, part in enumerate(parts):
                crumbs.append(label("›", "muted"))
                target = "/".join(parts[:index + 1])
                crumbs.append(button(part, lambda t=target: go(t), "quiet-button"))

        def render():
            while old := rows.get_first_child():
                rows.remove(old)
            render_crumbs()
            try:
                entries = sl.list_dir(base, here["path"])
            except (OSError, ValueError) as error:
                rows.append(label(f"No se pudo leer la carpeta: {error}", "form-error"))
                return
            total = len(entries)
            term = here["filter"].casefold()
            if term:
                entries = [e for e in entries if term in e["name"].casefold()]
            key = {"name": lambda e: e["name"].casefold(), "size": lambda e: -e["size"], "date": lambda e: -e["modified"]}[here["sort"]]
            entries.sort(key=lambda e: (not e["dir"], key(e)))
            names = {e["name"] for e in entries}
            here["picked"] &= names
            if not entries:
                rows.append(label("No hay nada que coincida con el filtro." if term else "Carpeta vacía. Arrastrá archivos acá o usá «Agregar archivos».", "muted"))
            for entry in entries[:MAX_ROWS]:
                rows.append(build_row(entry))
            shown = min(len(entries), MAX_ROWS)
            size = sum(e["size"] for e in entries if not e["dir"])
            count.set_text(f"{shown} de {total} elementos" + (" (usá el filtro para ver el resto)" if len(entries) > MAX_ROWS else "")
                           + f" · {human_size(size)} en archivos")
            update_selection()

        def update_selection():
            n = len(here["picked"])
            selection.set_visible(n > 0)
            picked_label.set_text(f"{n} seleccionado{'s' if n != 1 else ''}")

        def build_row(entry):
            name = entry["name"]
            full = child(name)
            row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
            check = Gtk.CheckButton(active=name in here["picked"])
            check.update_property([Gtk.AccessibleProperty.LABEL], [f"Seleccionar {name}"])
            check.connect("toggled", lambda c, n=name: (here["picked"].add(n) if c.get_active() else here["picked"].discard(n), update_selection()))
            row.append(check)
            row.append(icon(kind_icon(entry)))
            title = label(name, "form-label")
            title.set_hexpand(True)
            title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            title.set_tooltip_text(name)
            row.append(title)
            if name.endswith(".jar.disabled"):
                row.append(Gtk.Label(label="Desactivado", css_classes=["chip"]))
            row.append(label("" if entry["dir"] else human_size(entry["size"]), "muted"))
            row.append(label(time.strftime("%d/%m/%Y %H:%M", time.localtime(entry["modified"])), "muted"))
            if entry["dir"]:
                row.append(button("Abrir", lambda f=full: go(f)))
            elif editable(name):
                row.append(button("Editar", lambda f=full: edit(f)))
            menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text=f"Acciones de {name}")
            popover = Gtk.Popover()
            options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
            popover.set_child(options)
            menu_button.set_popover(popover)

            def item(text, action, style=None):
                options.append(button(text, lambda: (popover.popdown(), action()), style))
            if name.endswith(".jar"):
                item("Desactivar", lambda: toggle(full, False))
            elif name.endswith(".jar.disabled"):
                item("Activar", lambda: toggle(full, True))
            item("Renombrar", lambda: rename(full, name))
            item("Guardar copia en…", lambda: export_to([name]))
            item("Eliminar", lambda: delete([name]), "danger")
            row.append(menu_button)
            return row

        def after(text):
            message.set_text(text)
            render()

        def pick():
            picker = Gtk.FileChooserNative(title="Agregar archivos al servidor", transient_for=parent, action=Gtk.FileChooserAction.OPEN)
            picker.set_select_multiple(True)

            def chosen(dialog, response):
                files = dialog.get_files() if response == Gtk.ResponseType.ACCEPT else None
                paths = [files.get_item(i).get_path() for i in range(files.get_n_items())] if files else []
                dialog.destroy()
                add([p for p in paths if p])

            picker.connect("response", chosen)
            picker.show()

        def add(paths):
            if not paths:
                return False
            try:
                added = sl.add_files(base, here["path"], paths)
            except (OSError, ValueError) as error:
                message.set_text(f"No se pudieron agregar: {error}")
                return False
            after(f"Agregado: {', '.join(added[:3])}" + ("…" if len(added) > 3 else "")
                  + (". Reiniciá el servidor para que cargue lo nuevo." if runner.state == "running" and here["path"] in ("mods", "plugins") else "."))
            return True

        def toggle(full, enable):
            try:
                result = sl.set_enabled(base, full, enable)
            except (OSError, ValueError) as error:
                message.set_text(str(error))
                return
            after(f"«{result}» {'activado' if enable else 'desactivado'}." + (" Reiniciá el servidor para aplicarlo." if runner.state != "stopped" else ""))

        def export_to(names):
            picker = Gtk.FileChooserNative(title="Elegí dónde guardar la copia", transient_for=parent,
                                           action=Gtk.FileChooserAction.SELECT_FOLDER)

            def chosen(dialog, response):
                file = dialog.get_file() if response == Gtk.ResponseType.ACCEPT else None
                destination = file.get_path() if file else None
                dialog.destroy()
                if not destination:
                    return
                try:
                    for name in names:
                        sl.export(base, child(name), destination)
                except (OSError, ValueError) as error:
                    message.set_text(f"No se pudo copiar: {error}")
                    return
                message.set_text(f"Copiado en {destination}.")

            picker.connect("response", chosen)
            picker.show()

        def export_picked():
            export_to(sorted(here["picked"]))

        def ask(title_text, detail, initial, ok_text, then):
            dialog = Gtk.Dialog(title=title_text, transient_for=parent, modal=True, default_width=400)
            dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
            dialog.add_button(ok_text, Gtk.ResponseType.OK).add_css_class("primary")
            area = dialog.get_content_area()
            area.add_css_class("menu")
            area.set_spacing(8)
            area.append(label(detail, "form-label"))
            entry = Gtk.Entry(text=initial, activates_default=True)
            area.append(entry)
            dialog.set_default_response(Gtk.ResponseType.OK)

            def respond(_, response):
                value = entry.get_text().strip()
                dialog.destroy()
                if response == Gtk.ResponseType.OK and value:
                    try:
                        then(value)
                    except (OSError, ValueError) as error:
                        message.set_text(str(error))
                        return
                    render()

            dialog.connect("response", respond)
            dialog.present()

        def new_folder():
            ask("Nueva carpeta", "Nombre de la carpeta", "", "Crear", lambda value: sl.make_dir(base, here["path"], value))

        def rename(full, current):
            ask("Renombrar", f"Nuevo nombre para «{current}»", current, "Renombrar", lambda value: sl.rename(base, full, value))

        def delete(names):
            dialog = Gtk.Dialog(title="Eliminar", transient_for=parent, modal=True, default_width=420)
            dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
            dialog.add_button("Eliminar", Gtk.ResponseType.OK).add_css_class("danger")
            area = dialog.get_content_area()
            area.add_css_class("menu")
            area.set_spacing(8)
            area.append(label(f"¿Eliminar «{names[0]}»?" if len(names) == 1 else f"¿Eliminar {len(names)} elementos?", "subheading"))
            warn = label("Si es una carpeta, se borra todo lo que tiene adentro. No se puede deshacer.", "muted")
            warn.set_wrap(True)
            area.append(warn)

            def respond(_, response):
                dialog.destroy()
                if response != Gtk.ResponseType.OK:
                    return
                failed = []
                for name in names:
                    try:
                        sl.remove(base, child(name))
                    except (OSError, ValueError) as error:
                        failed.append(f"{name}: {error}")
                here["picked"].clear()
                after(f"No se pudo eliminar {failed[0]}" if failed else
                      f"«{names[0]}» eliminado." if len(names) == 1 else f"{len(names)} elementos eliminados.")

            dialog.connect("response", respond)
            dialog.present()

        def delete_picked():
            if here["picked"]:
                delete(sorted(here["picked"]))

        def backup():
            message.set_text("Creando el respaldo del mundo…")

            def worker():
                try:
                    if runner.state == "running":
                        runner.send("save-all flush")
                        time.sleep(3)
                    target = sl.backup_world(base)
                except (OSError, ValueError, RuntimeError) as error:
                    GLib.idle_add(message.set_text, f"No se pudo respaldar: {error}")
                    return
                GLib.idle_add(after, f"Respaldo creado: backups/{target.name} ({human_size(target.stat().st_size)}).")

            threading.Thread(target=worker, daemon=True).start()

        def edit(full):
            try:
                text = sl.read_text(base, full)
            except (OSError, ValueError) as error:
                message.set_text(str(error))
                return
            dialog = Gtk.Window(title=f"Editar {full}", transient_for=parent, modal=True, default_width=760, default_height=540)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["menu"])
            inner.append(label(full, "form-label"))
            view = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.NONE, left_margin=8, top_margin=6, bottom_margin=6)
            view.get_buffer().set_text(text)
            scroller = Gtk.ScrolledWindow(vexpand=True)
            scroller.set_child(view)
            inner.append(scroller)
            inner.append(label("Si el servidor está encendido, reinicialo para que lea los cambios.", "opt-hint"))
            feedback = label("", "form-error")
            inner.append(feedback)
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)

            def save():
                buffer = view.get_buffer()
                try:
                    sl.write_text(base, full, buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))
                except (OSError, ValueError) as error:
                    feedback.set_text(str(error))
                    return
                dialog.destroy()
                after(f"«{full}» guardado.")

            buttons.append(button("Cancelar", dialog.destroy))
            buttons.append(button("Guardar", save, "primary"))
            inner.append(buttons)
            dialog.set_child(inner)
            dialog.present()

        def filter_changed(entry):
            here["filter"] = entry.get_text()
            render()

        def sort_changed(combo):
            here["sort"] = combo.get_active_id() or "name"
            render()

        search.connect("search-changed", filter_changed)
        order.connect("changed", sort_changed)
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", lambda _t, value, *_r: add([f.get_path() for f in value.get_files() if f.get_path()]))
        scroll.add_controller(target)
        render()
        return box

    # ------------------------------------------------------------ cerrar Nova con servidores encendidos
    def servers_block_close(self):
        active = sl.running()
        if not active:
            return False
        dialog = Gtk.Dialog(title="Hay servidores encendidos", transient_for=self.window, modal=True, default_width=440)
        dialog.add_button("Seguir en Nova", Gtk.ResponseType.CANCEL)
        dialog.add_button("Apagar y cerrar", Gtk.ResponseType.OK).add_css_class("primary")
        area = dialog.get_content_area()
        area.add_css_class("menu")
        area.set_spacing(8)
        area.append(label("Si cerrás Nova se apagan tus servidores", "subheading"))
        text = label("Nova los apaga con calma (guardando el mundo) antes de cerrar.", "muted")
        text.set_wrap(True)
        area.append(text)

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.status.set_text("Apagando servidores…")

                def worker():
                    sl.stop_all()
                    GLib.idle_add(self.window.close)
                threading.Thread(target=worker, daemon=True).start()

        dialog.connect("response", respond)
        dialog.present()
        return True

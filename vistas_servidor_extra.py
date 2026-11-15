"""Nova window: secciones Estado, Jugadores y Respaldos de «Mi servidor», y la tarjeta para actualizar la versión."""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk, Pango

import motor
import servidor_gestion as sg
import servidor_local as sl
from vistas_servidor_local import human_size
from widgets import button, label

KIND_NAMES = {"auto": "Automático", "mundo": "Manual", "antes": "Antes de un cambio"}


def duration(seconds):
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} d {hours} h"
    return f"{hours} h {minutes} min" if hours else f"{minutes} min" if minutes else "menos de un minuto"


class ServidorExtraMixin:
    # ------------------------------------------------------------ pequeñas piezas
    @staticmethod
    def _card(box, heading):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["catalog-row"], valign=Gtk.Align.START)
        card.append(label(heading, "settings-heading"))
        box.append(card)
        return card

    @staticmethod
    def _confirm(parent, heading, detail, ok_text, then, danger=False):
        dialog = Gtk.Dialog(title=heading, transient_for=parent, modal=True, default_width=460)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button(ok_text, Gtk.ResponseType.OK).add_css_class("danger" if danger else "primary")
        area = dialog.get_content_area()
        area.add_css_class("menu")
        area.set_spacing(8)
        area.append(label(heading, "subheading"))
        text = label(detail, "muted")
        text.set_wrap(True)
        area.append(text)

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                then()

        dialog.connect("response", respond)
        dialog.present()

    @staticmethod
    def _worker(run, done, failed):
        """Run ``run()`` off the interface thread; ``done(result)`` or ``failed(text)`` come back on it."""
        def target():
            try:
                result = run()
            except Exception as error:
                GLib.idle_add(failed, str(error))
            else:
                GLib.idle_add(done, result)
        threading.Thread(target=target, daemon=True).start()

    # ------------------------------------------------------------ Estado
    def local_status_tab(self, sid, runner, subs):
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, margin_top=8, margin_end=6)
        scroll.set_child(grid)
        sampler = sg.Sampler()
        cells = {}

        def card(name, heading, column, row):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["catalog-row"], valign=Gtk.Align.START)
            box.append(label(heading, "settings-heading"))
            big = label("—", "subheading")
            big.set_wrap(True)
            box.append(big)
            bar = Gtk.ProgressBar(visible=False)
            box.append(bar)
            note = label("", "opt-hint")
            note.set_wrap(True)
            box.append(note)
            grid.attach(box, column, row, 1, 1)
            cells[name] = (big, bar, note)

        card("state", "Estado", 0, 0)
        card("players", "Jugadores", 1, 0)
        card("memory", "Memoria", 0, 1)
        card("cpu", "Procesador", 1, 1)
        card("disk", "Disco", 0, 2)
        card("net", "Conexión", 1, 2)
        busy = {"on": False}

        def show(data):
            busy["on"] = False
            state = data["state"]
            big, bar, note = cells["state"]
            big.set_text({"stopped": "Apagado", "starting": "Encendiendo…", "running": "Encendido", "stopping": "Apagando…"}[state])
            note.set_text((f"Hace {duration(data['uptime'])}. " if data["uptime"] is not None else "")
                          + ("Reconectado: se ve el estado pero no se mandan comandos." if data["adopted"] else ""))
            big, bar, note = cells["players"]
            big.set_text(f"{len(data['players'])} de {data['max_players']}" if state == "running" else "—")
            note.set_text(", ".join(data["players"]) if data["players"] else ("Nadie conectado." if state == "running" else "El servidor está apagado."))
            big, bar, note = cells["memory"]
            if data["memory"] is not None:
                big.set_text(f"{human_size(data['memory'])} de {human_size(data['memory_limit'])}")
                bar.set_visible(True)
                bar.set_fraction(min(1.0, data["memory"] / data["memory_limit"]))
                note.set_text("Memoria que usa el proceso. Si se llena seguido, subí la memoria en Ajustes.")
            else:
                big.set_text("—")
                bar.set_visible(False)
                note.set_text(f"Asignada: {human_size(data['memory_limit'])}.")
            big, bar, note = cells["cpu"]
            if data["cpu"] is not None:
                big.set_text(f"{data['cpu']:.0f} %")
                bar.set_visible(True)
                bar.set_fraction(data["cpu"] / 100)
                note.set_text("Del total de tu procesador.")
            else:
                big.set_text("—")
                bar.set_visible(False)
                note.set_text("Se mide mientras el servidor está encendido." if state == "stopped" else "Midiendo…")
            big, bar, note = cells["disk"]
            big.set_text(f"Mundo: {human_size(data['world'])}")
            note.set_text(f"Todo el servidor: {human_size(data['total'])}." if data["total"] is not None else "El total se calcula con el servidor apagado.")
            big, bar, note = cells["net"]
            big.set_text(f"Puerto {data['port']}")
            note.set_text("Tus amigos usan este puerto en la dirección del servidor.")

        def tick():
            if scroll.get_root() is None:
                return False   # the screen was closed: stop measuring
            if scroll.get_mapped() and not busy["on"]:
                busy["on"] = True
                self._worker(lambda: sg.status(sid, sampler), show, lambda text: busy.update(on=False))
            return True

        GLib.timeout_add_seconds(2, tick)
        scroll.on_show = lambda: tick()
        return scroll

    # ------------------------------------------------------------ Jugadores
    def local_players_tab(self, sid, runner, message):
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8, margin_end=6)
        scroll.set_child(box)
        slots = {}

        def person_list(kind, heading, hint, add_text, remove_text, remove_all_kinds=True):
            card = self._card(box, heading)
            note = label(hint, "opt-hint")
            note.set_wrap(True)
            card.append(note)
            rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.append(rows)
            slots[kind] = rows
            line = Gtk.Box(spacing=8)
            entry = Gtk.Entry(hexpand=True, placeholder_text="Nombre del jugador")
            entry.update_property([Gtk.AccessibleProperty.LABEL], [f"Jugador para {heading}"])
            line.append(entry)
            line.append(button(add_text, lambda k=kind, e=entry: change(k, e.get_text().strip(), True, e), "primary"))
            card.append(line)
            return remove_text

        online_card = self._card(box, "Conectados ahora")
        online_note = label("", "opt-hint")
        online_note.set_wrap(True)
        online_card.append(online_note)
        online_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        online_card.append(online_rows)
        online_card.append(button("Actualizar", lambda: ask_list(), "quiet-button"))
        removers = {"ops": "Quitar permisos", "whitelist": "Quitar", "bans": "Perdonar"}
        person_list("ops", "Operadores", "Pueden usar todos los comandos del servidor. Dalo solo a quien confíes.", "Hacer operador", "Quitar permisos")
        person_list("whitelist", "Lista blanca", "Si la activás en Ajustes, solo entran los que estén acá.", "Agregar", "Quitar")
        person_list("bans", "Baneados", "No pueden entrar al servidor.", "Banear", "Perdonar")

        def render_list(kind):
            rows = slots[kind]
            while old := rows.get_first_child():
                rows.remove(old)
            entries = sg.read_players(sid, kind)
            if not entries:
                rows.append(label("Nadie por ahora.", "muted"))
            for item in entries:
                row = Gtk.Box(spacing=8)
                row.append(label(item["name"], "form-label"))
                row.get_first_child().set_hexpand(True)
                row.append(button(removers[kind], lambda k=kind, n=item["name"]: change(k, n, False, None), "quiet-button"))
                rows.append(row)

        def render_online():
            while old := online_rows.get_first_child():
                online_rows.remove(old)
            running = runner.state == "running"
            if runner.adopted and running:
                online_note.set_text("Este servidor siguió encendido cuando Nova se cerró: se ven los jugadores del registro, pero no se puede expulsar a nadie.")
            else:
                online_note.set_text("" if running else "El servidor está apagado.")
            for name in sorted(runner.online) if running else []:
                row = Gtk.Box(spacing=8)
                row.append(label(name, "form-label"))
                row.get_first_child().set_hexpand(True)
                kick_button = button("Expulsar", lambda n=name: act(lambda: sg.kick(sid, n), f"«{n}» expulsado."), "quiet-button")
                kick_button.set_sensitive(not runner.adopted)
                row.append(kick_button)
                online_rows.append(row)
            if running and not runner.online:
                online_rows.append(label("Nadie conectado.", "muted"))

        def refresh():
            for kind in ("ops", "whitelist", "bans"):
                render_list(kind)
            render_online()
            return False

        def act(run, ok_text):
            def failed(text):
                message.set_text(text)
            self._worker(run, lambda _r: (message.set_text(ok_text), GLib.timeout_add(1500, refresh)), failed)

        def ask_list():
            try:
                sg.refresh_online(sid)
            except RuntimeError as error:
                message.set_text(str(error))
            GLib.timeout_add(1200, refresh)

        def change(kind, name, add, entry):
            if add and not name:
                message.set_text("Escribí el nombre del jugador.")
                return
            verbs = {("ops", True): "ahora es operador", ("ops", False): "ya no es operador", ("whitelist", True): "agregado a la lista blanca",
                     ("whitelist", False): "quitado de la lista blanca", ("bans", True): "baneado", ("bans", False): "perdonado"}

            def run():
                return sg.change_player(sid, kind, name, add)

            def done(how):
                message.set_text(f"«{name}» {verbs[(kind, add)]}." + (" Se aplicó en el servidor encendido." if how == "comando" else ""))
                if entry is not None:
                    entry.set_text("")
                GLib.timeout_add(1500 if how == "comando" else 100, refresh)

            self._worker(run, done, lambda text: message.set_text(text))

        def listener(kind, payload):
            if kind in ("state", "line"):
                if kind == "state" or "joined the game" in str(payload) or "left the game" in str(payload) or "players online" in str(payload):
                    GLib.idle_add(refresh)
        runner.listeners.append(listener)
        scroll.connect("destroy", lambda *_: runner.listeners.remove(listener) if listener in runner.listeners else None)
        scroll.on_show = refresh
        refresh()
        return scroll

    # ------------------------------------------------------------ Respaldos
    def local_backups_tab(self, sid, runner, message, parent):
        meta = sl.load(sid)
        base = sl.folder(sid)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8, margin_end=6)
        scroll.set_child(box)
        settings = sg.backup_settings(meta)

        auto = self._card(box, "Respaldos automáticos")
        hint = label("Con el servidor encendido, Nova guarda el mundo y lo copia cada cierto tiempo. Los respaldos manuales nunca se borran solos.", "opt-hint")
        hint.set_wrap(True)
        auto.append(hint)
        switch = Gtk.Switch(active=settings["hours"] > 0, valign=Gtk.Align.CENTER)
        switch.update_property([Gtk.AccessibleProperty.LABEL], ["Respaldos automáticos"])
        hours = Gtk.SpinButton.new_with_range(1, sg.MAX_HOURS, 1)
        hours.set_value(settings["hours"] or 6)
        keep = Gtk.SpinButton.new_with_range(1, 50, 1)
        keep.set_value(settings["keep"])
        stop_switch = Gtk.Switch(active=settings["on_stop"], valign=Gtk.Align.CENTER)
        stop_switch.update_property([Gtk.AccessibleProperty.LABEL], ["Respaldar al apagar"])
        for text, widget in (("Activados", switch), ("Cada (horas)", hours), ("Guardar los últimos", keep), ("Respaldar también al apagar", stop_switch)):
            line = Gtk.Box(spacing=12)
            caption = label(text, "form-label")
            caption.set_hexpand(True)
            line.append(caption)
            widget.set_halign(Gtk.Align.END)
            line.append(widget)
            auto.append(line)

        def save_settings():
            try:
                current = sl.load(sid) or meta
                sl.save({**current, "backup_hours": hours.get_value_as_int() if switch.get_active() else 0,
                         "backup_keep": keep.get_value_as_int(), "backup_on_stop": stop_switch.get_active()})
            except OSError as error:
                message.set_text(f"No se pudo guardar: {error}")
                return
            message.set_text("Respaldos automáticos " + (f"activados cada {hours.get_value_as_int()} h." if switch.get_active() else "desactivados."))

        auto.append(button("Guardar", save_settings, "primary"))

        actions = self._card(box, "Respaldos")
        bar = Gtk.Box(spacing=8)
        bar.append(button("Crear respaldo ahora", lambda: make(), "primary"))
        bar.append(button("Abrir carpeta de respaldos", lambda: (base / sg.BACKUPS).mkdir(exist_ok=True) or motor.open_folder(base / sg.BACKUPS), "quiet-button"))
        actions.append(bar)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        actions.append(rows)

        def render():
            while old := rows.get_first_child():
                rows.remove(old)
            found = sg.list_backups(sid)
            if not found:
                rows.append(label("Todavía no hay respaldos.", "muted"))
            for item in found:
                row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
                name = label(item["name"], "form-label")
                name.set_hexpand(True)
                name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                row.append(name)
                row.append(Gtk.Label(label=KIND_NAMES.get(item["kind"], "Manual"), css_classes=["chip"]))
                row.append(label(human_size(item["size"]), "muted"))
                row.append(label(time.strftime("%d/%m/%Y %H:%M", time.localtime(item["modified"])), "muted"))
                row.append(button("Restaurar", lambda n=item["name"]: restore(n)))
                row.append(button("Eliminar", lambda n=item["name"]: remove(n), "danger"))
                rows.append(row)
            return False

        def make():
            message.set_text("Creando el respaldo…")
            self._worker(lambda: sg.create_backup(sid), lambda path: (message.set_text(f"Respaldo creado: {path.name} ({human_size(path.stat().st_size)})."), render()),
                         lambda text: message.set_text(f"No se pudo respaldar: {text}"))

        def restore(name):
            if runner.state != "stopped":
                message.set_text("Apagá el servidor antes de restaurar un respaldo.")
                return

            def go():
                message.set_text("Restaurando…")
                self._worker(lambda: sg.restore_backup(sid, name),
                             lambda r: (message.set_text(f"Mundo restaurado desde {name}." + (f" El mundo anterior quedó en {r['safety']}." if r["safety"] else "")), render()),
                             lambda text: message.set_text(f"No se pudo restaurar: {text}"))
            self._confirm(parent, "¿Restaurar este respaldo?",
                          f"El mundo vuelve a como estaba en {name}. Antes, Nova guarda una copia del mundo actual, así que podés deshacerlo.", "Restaurar", go)

        def remove(name):
            def go():
                try:
                    sg.delete_backup(sid, name)
                except (OSError, ValueError) as error:
                    message.set_text(str(error))
                    return
                message.set_text(f"«{name}» eliminado.")
                render()
            self._confirm(parent, "¿Eliminar este respaldo?", f"Se borra {name}. No se puede deshacer.", "Eliminar", go, danger=True)

        scroll.on_show = render
        render()
        return scroll

    # ------------------------------------------------------------ Actualizar la versión
    def local_version_card(self, sid, runner, message, parent, container, row_title):
        """Card for the settings screen: what is installed, look for updates and update."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["catalog-row"], valign=Gtk.Align.START)
        card.append(label("Versión del servidor", "settings-heading"))
        current = label("", "form-label")
        card.append(current)
        result = label("", "opt-hint")
        result.set_wrap(True)
        card.append(result)
        choice = Gtk.ComboBoxText(visible=False)
        card.append(choice)
        controls = Gtk.Box(spacing=8)
        check_button = button("Buscar actualizaciones", lambda: check(), "quiet-button")
        update_build = button("Actualizar a la última compilación", lambda: update(None), "primary")
        update_version = button("Actualizar a esa versión", lambda: update(choice.get_active_id()), "primary")
        for widget in (check_button, update_build, update_version):
            controls.append(widget)
        update_build.set_visible(False)
        update_version.set_visible(False)
        card.append(controls)
        warn = label("Se hace un respaldo del mundo antes. No se puede volver a una versión anterior de Minecraft.", "opt-hint")
        warn.set_wrap(True)
        card.append(warn)
        container(card)

        def describe():
            meta = sl.load(sid)
            current.set_text(f"{sl.KINDS[meta['kind']]} · Minecraft {meta['version']}" + (f" · compilación {meta['build']}" if meta.get("build") and meta["kind"] != "vanilla" and len(str(meta["build"])) < 20 else ""))

        def check():
            if runner.state != "stopped":
                result.set_text("Apagá el servidor para actualizarlo.")
                return
            check_button.set_sensitive(False)
            result.set_text("Buscando…")

            def done(data):
                check_button.set_sensitive(True)
                lines = []
                update_build.set_visible(bool(data["build"]))
                if data["build"]:
                    lines.append("Hay una compilación más nueva para esta versión de Minecraft.")
                elif data["build"] is False:
                    lines.append("Esta versión de Minecraft ya está en su última compilación.")
                else:
                    lines.append("No se puede saber si hay una compilación nueva (el servidor se creó con una versión vieja de Nova); podés reinstalarla igual.")
                    update_build.set_visible(True)
                choice.remove_all()
                for version in data["versions"][:15]:
                    choice.append(version, version)
                choice.set_visible(bool(data["versions"]))
                update_version.set_visible(bool(data["versions"]))
                if data["versions"]:
                    choice.set_active(0)
                    lines.append(f"Hay versiones de Minecraft más nuevas: la última es {data['versions'][0]}. Los plugins o mods pueden necesitar actualizarse.")
                result.set_text(" ".join(lines))

            self._worker(lambda: sg.check_update(sl.load(sid)), done, lambda text: (check_button.set_sensitive(True), result.set_text(f"No se pudo buscar: {text}")))

        def update(version):
            if runner.state != "stopped":
                result.set_text("Apagá el servidor para actualizarlo.")
                return
            target = version or sl.load(sid)["version"]

            def go():
                for widget in (check_button, update_build, update_version):
                    widget.set_sensitive(False)
                result.set_text("Actualizando…")

                def done(info):
                    for widget in (check_button, update_build, update_version):
                        widget.set_sensitive(True)
                        widget.set_visible(widget is check_button)
                    choice.set_visible(False)
                    describe()
                    row_title(sl.load(sid)["name"])
                    text = f"Actualizado a Minecraft {info['to']}." + (f" Respaldo del mundo: {info['backup']}." if info["backup"] else "")
                    if info["changed_version"] and info["extensions"]:
                        text += f" Revisá que tus {info['extensions']} plugins o mods funcionen en la versión nueva."
                    result.set_text(text)
                    message.set_text(text)

                def failed(text):
                    for widget in (check_button, update_build, update_version):
                        widget.set_sensitive(True)
                    result.set_text(f"No se pudo actualizar: {text}")

                self._worker(lambda: sg.update_server(sid, version, status=lambda t: GLib.idle_add(result.set_text, t),
                                                      progress=lambda d, t: GLib.idle_add(result.set_text, f"Descargando… {d * 100 // t}%" if t else "Descargando…")),
                             done, failed)

            self._confirm(parent, "¿Actualizar el servidor?",
                          f"Se actualiza a Minecraft {target}. Antes se hace un respaldo del mundo. Si cambia la versión de Minecraft, no se puede volver atrás y "
                          "los plugins o mods pueden necesitar actualizarse.", "Actualizar", go)

        describe()
        return card

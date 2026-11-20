"""Nova Launcher desktop window for GTK 4."""
import hashlib
import os
from pathlib import Path
import re
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gio, Gtk, Pango

import errores
import actualizaciones
import atajos
import biblioteca
import consola
import historial
import integraciones
import motor
import pantalla_carga
import estadisticas
import i18n
import inicio
import reparacion
import respaldos
import servidor_gestion
import servidor_local
import tiempo
import uso
import widgets
from widgets import (resolution_field, instance_art, hero_art, enter, label, button, feature_button,
                     content_tile, stat_tile, default_cover, HERE)
from vistas_cuentas import CuentasMixin
from vistas_paginas import PaginasMixin
from vistas_juegos import JuegosMixin
from vistas_lanzamiento import LanzamientoMixin
from vistas_salud import SaludMixin
from vistas_java import java_picker
from vistas_perfiles import PerfilesMixin
from vistas_curseforge import CurseForgeMixin
from vistas_estadisticas import EstadisticasMixin
from vistas_importar import ImportarMixin
from vistas_archivos import ArchivosMixin
from vistas_pomme import PommeMixin
from vistas_servidores import ServidoresMixin
from vistas_servidor_local import ServidorLocalMixin
from vistas_servidor_extra import ServidorExtraMixin
from vistas_descargas import DescargasMixin
from vistas_sesiones import SesionesMixin
from vistas_actualizar import ActualizarMixin
from vistas_respaldos import RespaldosMixin


class Nova(
    PaginasMixin,
    JuegosMixin,
    LanzamientoMixin,
    SaludMixin,
    PerfilesMixin,
    CurseForgeMixin,
    EstadisticasMixin,
    CuentasMixin,
    ImportarMixin,
    ArchivosMixin,
    PommeMixin,
    ServidoresMixin,
    ServidorLocalMixin,
    ServidorExtraMixin,
    DescargasMixin,
    SesionesMixin,
    ActualizarMixin,
    RespaldosMixin,
    Gtk.Application,
):
    def __init__(self):
        super().__init__(application_id="io.nova.launcher",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option("jugar", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             "Iniciar una instancia por su identificador", "ID")
        self.window = None
        self.selected = None
        self.busy = False
        self.parallel = False
        self.running = None
        self.second_session = None
        self.download_progress = "Sin descargas recientes."
        self.cancel_download = None
        self.download_view = None
        self.history = historial.History(motor.ROOT / "downloads-history.json")
        self.retries = {}
        self.queue = []
        self.history_view = None
        self.launch_stage = ""
        self.versions = []
        self.microsoft = None
        self.microsoft_active = False

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        self.activate()
        target = options.get("jugar")
        if target:
            GLib.timeout_add(600, self.play_from_shortcut, target)
        return 0

    def play_from_shortcut(self, instance_id):
        folder = motor.ROOT / "instances" / instance_id
        if not atajos.valid_instance_id(instance_id) or folder not in getattr(self, "instances", {}):
            self.status.set_text("El atajo apunta a una instancia que ya no existe.")
        elif self.busy or self.parallel:
            self.status.set_text("Nova está ocupada. Esperá a que termine la operación actual.")
        else:
            self.choose_game("minecraft", save=False)
            self.selected = folder
            self.refresh()
            self.play()
        return False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_path(str(HERE / "nova.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
        )
        self.light_provider = Gtk.CssProvider()
        self.light_provider.load_from_path(str(HERE / "nova-light.css"))
        self.light_active = False
        self.window = Gtk.ApplicationWindow(application=self, title="Nova Launcher",
                                            default_width=1150, default_height=730)
        self.window.add_css_class("nova-main")
        self.window.set_icon_name("io.nova.launcher")
        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        keys.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>f"),
            Gtk.CallbackAction.new(lambda *_: self.library_query.grab_focus()),
        ))
        keys.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>o"),
            Gtk.CallbackAction.new(lambda *_: self.import_files()),
        ))
        keys.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("Escape"),
            Gtk.CallbackAction.new(lambda *_: self.current_page is not None and self.leave_page()),
        ))
        self.window.add_controller(keys)
        self.window.connect("close-request", lambda _: self.busy or self.parallel or self.servers_block_close())
        accounts = motor.read(motor.ROOT / "accounts.json", {"active": "", "profiles": []})
        self.preferences = {
            "memory": 4, "java": "", "resolution": "default", "console": False,
            "compact": False, "alphabetical": False, "launch_behavior": "keep", "launch_screen": True, "beta": False, "auto_backup_days": 0, "theme": "dark", "language": "es",
            **motor.read(motor.ROOT / "settings.json", {}),
        }
        i18n.set_language(self.preferences.get("language", "es"))
        i18n.install_gtk()
        self.apply_speed()
        self.release_repo = actualizaciones.repository(
            motor.read(HERE / "canal.json", {}).get("repository", "")
        )
        self.checking_release = False
        self.library = motor.read(motor.ROOT / "library.json", {})
        last = self.library.get("selected")
        if isinstance(last, str) and Path(last).name == last:
            self.selected = motor.ROOT / "instances" / last
        self.profile = accounts["active"]
        self.profiles = accounts["profiles"]
        import credenciales
        self.microsoft = credenciales.load_session()
        import nova_cuenta
        self.nova_account = nova_cuenta.load()
        titlebar = Gtk.HeaderBar(decoration_layout=":minimize,maximize,close")
        titlebar.add_css_class("nova-titlebar")
        self.library_query = Gtk.SearchEntry(placeholder_text="Buscar instancias", width_chars=34,
                                             max_width_chars=34, css_classes=["top-search"])
        titlebar.set_title_widget(self.library_query)
        identity = Gtk.Box(spacing=8)
        logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(HERE / "nova-logo.svg"), 24, 24, True)
        identity.append(Gtk.Image.new_from_pixbuf(logo))
        identity.append(label("Nova Launcher", "brand"))
        titlebar.pack_start(identity)
        switch = Gtk.Box(margin_start=3, margin_end=3, margin_top=3, margin_bottom=3)
        self.game_switch = {}
        for key, name in (("minecraft", "Minecraft"), ("roblox", "Roblox")):
            tab = button(name, lambda k=key: self.switch_game(k), "seg-button")
            self.game_switch[key] = tab
            switch.append(tab)
        self.switch_pill = Gtk.Box(css_classes=["seg-pill"], halign=Gtk.Align.START, valign=Gtk.Align.CENTER,
                                   can_target=False)
        # the pill is the base layer and the buttons sit on top of it
        pill_frame = Gtk.Overlay(valign=Gtk.Align.CENTER, css_classes=["seg", "game-switch"], child=self.switch_pill)
        pill_frame.add_overlay(switch)
        pill_frame.set_measure_overlay(switch, True)
        self.switch_box = pill_frame
        self.pill_now = None
        titlebar.pack_start(pill_frame)
        self.accounts = Gtk.MenuButton(css_classes=["account-switcher"])
        titlebar.pack_end(self.accounts)
        self.window.set_titlebar(titlebar)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame = Gtk.Overlay()
        frame.set_child(outer)
        drop_hint = self.drop_hint()
        self.frame_overlay = frame
        frame.add_overlay(drop_hint)
        self.setup_launch_screen(frame)
        self.window.set_child(frame)
        self.setup_drop(self.window, drop_hint)
        shell = Gtk.Box(vexpand=True)
        outer.append(shell)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["sidebar"])
        nav_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        propagate_natural_width=True)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.nav_box = nav
        nav_scroll.set_child(nav)
        sidebar.append(nav_scroll)
        self.nav_items = []

        def add(box, title, icon, action, active=False):
            item = self.nav_button(title, icon, action, active=active)
            self.nav_items.append(item)
            box.append(item)

        nav.append(label(i18n.tr("BIBLIOTECA"), "nav-caption"))
        add(nav, "Instancias", "view-grid-symbolic",
            lambda: (self.leave_page(), scroll.get_vadjustment().set_value(0)), True)
        add(nav, "Novedades", "package-x-generic-symbolic", self.show_news)
        nav.append(label(i18n.tr("DESCUBRIR"), "nav-caption"))
        add(nav, "Explorar", "system-search-symbolic", self.browse)
        add(nav, "CurseForge", "system-search-symbolic", self.show_curseforge)
        add(nav, "Modpacks", "package-x-generic-symbolic", self.browse_packs)
        add(nav, "Importar", "document-open-symbolic", lambda: self.add_instance(import_only=True))
        nav.append(label(i18n.tr("HERRAMIENTAS"), "nav-caption"))
        add(nav, "Skins", "applications-graphics-symbolic", self.open_skins)
        add(nav, "Servidores", "network-server-symbolic", self.open_servers)
        add(nav, "Mi servidor", "network-server-symbolic", self.show_local_servers)
        # The rarely used pages hide behind one row; it opens by itself when one of them is on screen.
        self.more_revealer = Gtk.Revealer(transition_type=Gtk.StackTransitionType.SLIDE_DOWN, transition_duration=widgets.ms(240))
        more = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.more_items = []
        for title, icon, action in (("Respaldos", "document-open-symbolic", self.show_backups),
                                    ("Sesiones", "media-playback-start-symbolic", self.show_sessions),
                                    ("Descargas", "folder-download-symbolic", self.show_downloads),
                                    ("Almacenamiento", "drive-harddisk-symbolic", self.show_storage),
                                    ("Estadísticas", "applications-graphics-symbolic", self.show_statistics)):
            add(more, title, icon, action)
            self.more_items.append(self.nav_items[-1])
        self.more_revealer.set_child(more)
        self.more_toggle = button("", lambda: self.more_revealer.set_reveal_child(not self.more_revealer.get_reveal_child()),
                                  "nav-button")
        toggle_row = Gtk.Box(spacing=10)
        toggle_row.append(Gtk.Image.new_from_icon_name("view-more-symbolic"))
        toggle_row.append(label(i18n.tr("Más")))
        self.more_toggle.set_child(toggle_row)
        self.more_toggle.update_property([Gtk.AccessibleProperty.LABEL], [i18n.tr("Más herramientas")])
        nav.append(self.more_toggle)
        nav.append(self.more_revealer)
        # One card: version and update state on the left, settings gear on the right.
        self.release_card = Gtk.Box(spacing=4, css_classes=["me-card"])
        info = Gtk.Box(spacing=10)
        logo_tile = Gtk.Box(css_classes=["me-logo"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        logo_tile.append(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(HERE / "nova-logo.svg"), 20, 20, True)))
        logo_tile.get_first_child().set_hexpand(True)
        info.append(logo_tile)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        texts.append(label(f"Nova {actualizaciones.VERSION}", "me-title"))
        self.release_note = label("Al día", "me-note")
        texts.append(self.release_note)
        info.append(texts)
        self.release_button = button("", self.release_details, "me-main")
        self.release_button.set_child(info)
        self.release_button.set_hexpand(True)
        self.release_button.update_property([Gtk.AccessibleProperty.LABEL], ["Versión de Nova y actualizaciones"])
        self.release_card.append(self.release_button)
        gear = button("", self.global_settings, "me-gear")
        gear.set_child(Gtk.Image.new_from_icon_name("emblem-system-symbolic"))
        gear.set_tooltip_text("Ajustes")
        gear.update_property([Gtk.AccessibleProperty.LABEL], ["Ajustes"])
        gear.set_valign(Gtk.Align.CENTER)
        self.release_card.append(gear)
        footer = self.release_card
        sidebar.append(footer)
        self.sidebar = sidebar
        sidebar.set_hexpand(False)  # the footer card expands; the sidebar must not
        shell.append(sidebar)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        panel = Gtk.Box(hexpand=True, css_classes=["content-panel"])
        panel.set_overflow(Gtk.Overflow.HIDDEN)
        panel.append(self.setup_pages(scroll))
        shell.append(panel)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        main.add_css_class("main")
        scroll.set_child(main)
        library_header = Gtk.Box(spacing=10)
        title_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        title_group.append(label("Mis instancias", "heading"))
        self.library_count = label("", "muted")
        title_group.append(self.library_count)
        library_header.append(title_group)
        library_header.append(self.header_button("Importar", "document-open-symbolic",
                                                 lambda: self.add_instance(import_only=True)))
        library_header.append(self.header_button("Nueva instancia", "list-add-symbolic",
                                                 self.add_instance, "primary"))
        main.append(library_header)
        self.home_cards = {}
        home = Gtk.Box(spacing=0, homogeneous=False, css_classes=["home-strip"])
        for key, action in (("last", lambda: self.select(self.last_played) if self.last_played else None),
                            ("downloads", self.show_downloads),
                            ("account", lambda: self.accounts.popup()),
                            ("nova", self.release_details)):
            card = Gtk.Button(css_classes=["home-card"])
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = label("", "home-title")
            text = label("", "home-text")
            text.set_ellipsize(Pango.EllipsizeMode.END)
            inner.append(title)
            inner.append(text)
            card.set_child(inner)
            card.set_hexpand(True)
            card.connect("clicked", lambda _, run=action: run())
            home.append(card)
            self.home_cards[key] = (card, title, text)
        self.last_played = None
        main.append(home)
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main.append(self.details)
        self.library_filter = Gtk.ComboBoxText()
        for key, title in (("all", "Todas"), ("favorites", "Favoritas"), ("recent", "Jugadas recientemente")):
            self.library_filter.append(key, title)
        self.library_filter.set_active_id("all")
        section = Gtk.Box(spacing=10)
        section.append(label("Tus instancias", "section-title"))
        section.append(Gtk.Box(hexpand=True))
        section.append(self.library_filter)
        main.append(section)
        self.cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                 min_children_per_line=2, homogeneous=True, column_spacing=14, row_spacing=14)
        main.append(self.cards)
        self.compact = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        main.append(self.compact)
        self.instance_rows = {}
        self.expanded_folder = None
        self.library_layout = None
        self.status = label("Listo", "muted")
        self.status.set_wrap(True)
        self.status.set_hexpand(True)
        statusbar = Gtk.Box(spacing=10, css_classes=["statusbar"])
        statusbar.append(self.status)
        self.queue_label = label("", "muted")
        statusbar.append(self.queue_label)
        self.failure_log = button("Ver registro", lambda: consola.open_console(self.window, self.failed_log),
                                  "quiet-button")
        self.failure_log.set_visible(False)
        statusbar.append(self.failure_log)
        self.failure_fix = button("Corregir", self.fix_failure, "quiet-button")
        self.failure_fix.set_visible(False)
        self.failure_action = None
        statusbar.append(self.failure_fix)
        outer.append(statusbar)
        self.library_query.connect("search-changed", lambda _: self.refresh())
        self.library_filter.connect("changed", lambda _: self.refresh())
        self.update_accounts()
        if widgets.motion_enabled():
            widgets.intro_delay[0] = widgets.ms(1750)
            GLib.timeout_add(widgets.ms(3200), lambda: (widgets.intro_delay.__setitem__(0, 0), False)[1])
        self.refresh()
        self.apply_theme()
        self.setup_games()
        self.play_intro(frame, nav, [library_header, home, section])
        self.window.present()
        servidor_local.adopt_all()
        servidor_local.STOP_HOOKS.append(lambda sid: threading.Thread(target=servidor_gestion.on_stopped, args=(sid,), daemon=True).start())
        GLib.timeout_add_seconds(60, self.server_backups_tick)
        self.refresh_nova()
        GLib.timeout_add_seconds(30, self.auto_backup)
        self.versions = motor.read(motor.ROOT / "versions.json", [])
        threading.Thread(target=self.load_versions, daemon=True).start()
        if self.preferences.get("release_repo", self.release_repo):
            self.check_release()
        self.usage_count()

    def server_backups_tick(self):
        """Every minute, make the scheduled world backups of local servers that are running."""
        threading.Thread(target=servidor_gestion.auto_backups, daemon=True).start()
        return True

    def usage_count(self):
        """Ask once whether to join the anonymous usage count; if yes, send at most one ping a day."""
        if self.preferences.get("usage") is None:
            GLib.timeout_add_seconds(3, self.ask_usage)
        elif self.preferences["usage"]:
            ping = uso.due()
            if ping:
                threading.Thread(target=uso.send, args=(ping,), daemon=True).start()

    def ask_usage(self):
        dialog = Gtk.Dialog(title="Contar esta instalación", transient_for=self.window, modal=True, default_width=460)
        dialog.add_button("No, gracias", Gtk.ResponseType.CANCEL)
        dialog.add_button("Sí, contar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        box.append(label("¿Ayudás a contar cuánta gente usa Nova?", "subheading"))
        for text in ("Una vez al día Nova envía un número al azar, su versión y tu sistema (Linux o Windows). "
                     "Nada más: ni tu nombre, ni tu cuenta, ni tus instancias.",
                     "Podés cambiarlo cuando quieras en Ajustes."):
            line = label(text, "muted")
            line.set_wrap(True)
            box.append(line)

        def respond(_, response):
            dialog.destroy()
            self.set_usage(response == Gtk.ResponseType.OK)

        dialog.connect("response", respond)
        dialog.present()
        return False

    def set_usage(self, enabled):
        self.preferences = {**self.preferences, "usage": enabled}
        motor.save(motor.ROOT / "settings.json", self.preferences)
        if enabled:
            self.usage_count()
        else:
            uso.forget()

    def create_shortcut(self, folder, name):
        try:
            atajos.create(folder, name)
        except (OSError, RuntimeError, ValueError) as error:
            self.status.set_text(f"No se pudo crear el atajo: {error}")
        else:
            self.status.set_text(f"Atajo creado · buscá «{name} · Nova» en el menú de aplicaciones.")

    def copy_instance(self, folder, mode):
        def task():
            result = respaldos.copy_instance(folder, mode)
            if mode != "backup":
                GLib.idle_add(setattr, self, "selected", result)

        title, message = {
            "duplicate": ("Duplicar instancia", "Instancia duplicada."),
            "backup": ("Crear respaldo", "Respaldo guardado. Podés abrirlo desde Respaldos."),
            "restore": ("Restaurar respaldo", "Respaldo restaurado como instancia nueva."),
        }[mode]
        integraciones.run(self, self.window, title, task, message)





    def update_home(self):
        if not getattr(self, "home_cards", None):
            return
        names = {folder.name: data["name"] for folder, data in self.instances.items()}
        recent = self.library.get("recent", {})
        account = (("microsoft", self.microsoft[1]["name"]) if self.microsoft_active and self.microsoft
                   else ("offline", self.profile) if self.profile else None)
        release = getattr(self, "available_release", None)
        cards = inicio.summary(recent=recent, names=names, now=time.time(),
                               downloading=self.cancel_download is not None, queued=len(self.queue),
                               account=account, update=release[0] if release else None)
        self.last_played = None
        for item in cards:
            card, title, text = self.home_cards[item["key"]]
            title.set_text(i18n.tr(item["title"]))
            text.set_text(item["text"])
            card.update_property([Gtk.AccessibleProperty.LABEL], [f"{item['title']}: {item['text']}"])
        stamped = [(when, key) for key, when in recent.items()
                   if key in names and isinstance(when, (int, float)) and not isinstance(when, bool)]
        if stamped:
            newest = max(stamped)[1]
            self.last_played = next((f for f in self.instances if f.name == newest), None)

    def apply_speed(self):
        """Animation speed from Ajustes: soft, medium or fast. The CSS durations are rewritten, the code ones use widgets.ms()."""
        key = self.preferences.get("animations")
        widgets.speed[0] = widgets.SPEEDS.get(key, 1.0)
        if widgets.speed[0] != 1.0 or getattr(self, "speed_applied", False):
            css = widgets.scale_css((HERE / "nova.css").read_text(encoding="utf-8"))
            if hasattr(self.css_provider, "load_from_string"):  # GTK 4.12+
                self.css_provider.load_from_string(css)
            else:
                self.css_provider.load_from_data(css.encode("utf-8"))
            self.speed_applied = True
        if hasattr(self, "page_stack"):
            self.page_stack.set_transition_duration(widgets.ms(200))
            self.more_revealer.set_transition_duration(widgets.ms(240))
            for _tile, _arrow, reveal in self.instance_rows.values():
                reveal.set_transition_duration(widgets.ms(180))

    def apply_theme(self):
        light = self.preferences.get("theme") == "light"
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", not light)
        if light and not self.light_active:
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self.light_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
        elif not light and self.light_active:
            Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), self.light_provider)
        self.light_active = light

    @staticmethod
    def header_button(title, icon, action, style=None):
        content = Gtk.Box(spacing=8)
        content.append(Gtk.Image.new_from_icon_name(icon))
        content.append(label(title))
        control = button("", action, style)
        control.set_child(content)
        control.set_valign(Gtk.Align.CENTER)
        control.update_property([Gtk.AccessibleProperty.LABEL], [title])
        return control

    @staticmethod
    def nav_button(title, icon, action, active=False):
        control = button("", action, "nav-button")
        row = Gtk.Box(spacing=10)
        bundled = HERE / "icons" / f"{icon}.svg"
        icon_widget = Gtk.Image.new_from_file(str(bundled)) if bundled.is_file() else Gtk.Image.new_from_icon_name(icon)
        icon_widget.set_pixel_size(16)
        row.append(icon_widget)
        row.append(label(i18n.tr(title)))
        control.set_child(row)
        control.update_property([Gtk.AccessibleProperty.LABEL], [i18n.tr(title)])
        if active:
            control.add_css_class("nav-active")
        return control











    def form(self, title, field, value, submit, memory=None):
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        save = dialog.add_button("Guardar", Gtk.ResponseType.OK)
        save.add_css_class("primary")
        if isinstance(save.get_parent(), Gtk.Box):
            save.get_parent().set_spacing(8)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        box.append(label(field, "form-label"))
        entry = Gtk.Entry(text=value, width_chars=32, activates_default=True)
        box.append(entry)
        if memory is not None:
            entry.set_placeholder_text("Java administrado por Nova")
            box.append(label("Dejá el campo vacío para usar la versión que pide el juego.", "muted"))
            memory_row = Gtk.Box(spacing=16, css_classes=["settings-row"])
            memory_label = label("Memoria para nuevas instancias", "form-label")
            memory_label.set_hexpand(True)
            memory_row.append(memory_label)
            ram = Gtk.SpinButton.new_with_range(2, 32, 1)
            ram.set_value(memory)
            memory_row.append(ram)
            memory_row.append(label("GB", "muted"))
            box.append(memory_row)
        error = label("", "form-error")
        error.set_wrap(True)
        error.set_visible(False)
        box.append(error)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    submit(entry.get_text().strip(), ram.get_value_as_int() if memory is not None else None)
                except (OSError, ValueError) as exc:
                    error.set_text(str(exc))
                    error.set_visible(True)
                    return
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()




    def add_instance(self, *, import_only=False):
        title = "Importar" if import_only else "Nueva instancia"
        chooser = Gtk.Window(title=title, transient_for=self.window,
                             modal=True, default_width=510, resizable=False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label(title, "subheading"))
        content.append(label("Elegí qué querés importar" if import_only else
                             "Elegí cómo querés empezar", "muted"))

        def choose(action):
            chooser.destroy()
            action()

        options = (
            ("◇   Personalizada", "Elegí la versión de Minecraft y el cargador.",
             lambda: self.instance_form(None)),
            ("↓   Buscar un modpack", "Descargá un pack completo desde Modrinth.",
             self.browse_packs),
            ("Importar Modrinth (.mrpack)", "Elegí un archivo .mrpack de Modrinth.",
             lambda: self.import_pack("mrpack")),
            ("Importar ZIP", "Abrí un ZIP de CurseForge o exportado desde Nova.",
             lambda: self.import_pack("zip")),
            ("Archivos del equipo", "Mods, texturas, shaders, paquetes de datos o un modpack. "
             "También podés arrastrarlos a la ventana.", self.import_files),
        )
        options += (("Importar desde Prism Launcher", "Copiá la instancia, sus mods y sus mundos.",
                     self.choose_prism),
                    ("Desde una plantilla", "Supervivencia, PvP, rendimiento y más, con ajustes razonables.",
                     self.show_templates),
                    ("Importar un perfil de Nova", "Archivo .json exportado desde otra instancia.",
                     self.import_profile))
        # Archivos del equipo (4), Prism (5) and perfil (7) when importing; everything but the files option otherwise.
        shown = (options[4], options[5], options[7]) if import_only else options[:4] + options[5:]
        for name, detail, action in shown:
            content.append(feature_button(name, detail, lambda run=action: choose(run)))
        chooser.set_child(content)
        self.show_page(chooser)


    def edit_settings(self):
        if self.selected:
            self.instance_form(self.selected)

    def instance_form(self, folder, preset=None):
        values = self.instances[folder] if folder else {
            **motor.DEFAULTS, "name": "", "memory": self.preferences["memory"], **(preset or {}),
        }
        dialog = Gtk.Dialog(title="Editar instancia" if folder else "Nueva instancia",
                            transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.set_spacing(0)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, css_classes=["form-page"])
        form.set_halign(Gtk.Align.START)
        card_width = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)  # every section card is as wide as the widest
        scroller.set_child(form)
        box.append(scroller)
        head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        head.append(label("Editar instancia" if folder else "Nueva instancia", "subheading"))
        head.append(label("Nombre, versión, memoria y portada de esta instancia." if folder else
                          "Elegí cómo se llama y con qué versión de Minecraft juega.", "muted"))
        form.append(head)

        def section(title):
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            group.append(label(title, "form-section"))
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["form-card"])
            card_width.add_widget(card)
            group.append(card)
            form.append(group)
            return card

        def row(card, title, control, hint=None, width=None):
            line = Gtk.Box(spacing=18, css_classes=["form-row"])
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
            text.append(label(title, "form-label"))
            if hint:
                note = label(hint, "opt-hint")
                note.set_wrap(True)
                note.set_max_width_chars(46)
                text.append(note)
            line.append(text)
            if width:
                control.set_size_request(width, -1)
            control.set_halign(Gtk.Align.END)
            control.set_valign(Gtk.Align.CENTER)
            line.append(control)
            card.append(line)
            return control

        identity = section("Instancia")
        game = section("Minecraft")
        performance = section("Rendimiento")
        java_card = section("Java")

        name = row(identity, "Nombre", Gtk.Entry(text=values["name"], max_length=40, placeholder_text="Mi instancia"), width=300)
        name.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))
        notes = row(identity, "Nota", Gtk.Entry(text=values.get("notes", ""), max_length=160,
                                                 placeholder_text="Ej. Mundo cooperativo con amigos"),
                    hint="Un recordatorio corto. Se ve debajo del banner.", width=300)
        cover = values.get("cover", "")
        pending = None
        preview = instance_art({**values, "artwork": values.get("artwork", 0)}, width=192, height=108)
        cover_controls = Gtk.Box(spacing=14)
        cover_controls.append(preview)
        cover_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.CENTER)
        cover_controls.append(cover_buttons)
        row(identity, "Portada", cover_controls, hint="Se ve en la biblioteca y en el banner.")

        client = row(game, "Cliente", Gtk.ComboBoxText(), width=300,
                     hint="Pomme es no oficial y está hecho en Rust: no usa mods de Java y tiene su propio inicio de sesión.")
        client.append("java", "Java (Minecraft normal)")
        client.append("pomme", "Pomme · cliente Rust (experimental)")
        client.set_active_id("pomme" if values.get("client") == "pomme" else "java")
        versions = row(game, "Versión de Minecraft", Gtk.ComboBoxText.new_with_entry(), width=300)
        for item in self.versions:
            versions.append(item["id"], item["id"])
        if not versions.set_active_id(values["version"]):
            versions.get_child().set_text(values["version"])
        loader = row(game, "Cargador", Gtk.ComboBoxText(), hint="Fabric, Forge, NeoForge o Quilt para usar mods.",
                     width=300)
        for key, title in motor.LOADERS.items():
            loader.append(key, title)
        loader.set_active_id(values["loader"])
        build_row = Gtk.Box(spacing=8)
        builds = Gtk.ComboBoxText.new_with_entry()
        builds.set_hexpand(True)
        loader_build = builds.get_child()
        loader_build.set_text(values["loader_version"])
        loader_build.set_placeholder_text("Automática")
        build_row.append(builds)
        row(game, "Versión del cargador", build_row, hint="Opcional. Vacía, Nova elige la más reciente compatible.",
            width=300)
        build_row.set_sensitive(values["loader"] != "vanilla")

        def load_builds():
            version = versions.get_child().get_text().strip()
            loader_id = loader.get_active_id()
            lookup.set_sensitive(False)
            error.set_text("Consultando versiones del cargador…")

            def finish(entries, message):
                lookup.set_sensitive(True)
                if loader_id != loader.get_active_id() or version != versions.get_child().get_text().strip():
                    error.set_text("")
                    return
                previous = loader_build.get_text()
                builds.remove_all()
                for entry in entries:
                    builds.append(entry, entry)
                loader_build.set_text(previous)
                error.set_text(message)

            def worker():
                try:
                    from minecraft_launcher_lib.mod_loader import get_mod_loader
                    available = get_mod_loader(loader_id).get_loader_versions(version, False)
                except Exception as exc:
                    errores.record(exc, "nova.worker")
                    GLib.idle_add(finish, [], f"No se pudieron consultar las versiones: {exc}")
                else:
                    message = "Abrí la lista para elegir una versión." if available else "Sin builds compatibles."
                    GLib.idle_add(finish, available, message)

            threading.Thread(target=worker, daemon=True).start()

        lookup = button("Consultar", load_builds)
        lookup.set_tooltip_text("Buscar las versiones del cargador compatibles con esta versión de Minecraft")
        build_row.append(lookup)

        def loader_changed(_):
            builds.remove_all()
            loader_build.set_text("")
            build_row.set_sensitive(loader.get_active_id() != "vanilla")

        loader.connect("changed", loader_changed)
        fixed = folder and (values.get("pack") or (folder / "game" / "saves").exists()
                            or (folder / "game" / "mods").exists())
        if fixed:
            for widget in (versions, loader, build_row):
                widget.set_sensitive(False)
            lock_note = label("Esta instancia tiene un pack, mods o mundos: la versión y el cargador no se pueden "
                              "cambiar. Creá otra instancia si necesitás otra versión.", "form-note")
            lock_note.set_wrap(True)
            game.append(lock_note)

        memory = row(performance, "Memoria máxima", Gtk.SpinButton.new_with_range(1, 32, 1),
                     hint="En GB. Los modpacks grandes suelen pedir 6 u 8.", width=120)
        memory.set_value(values["memory"])
        memory_min = row(performance, "Memoria mínima", Gtk.SpinButton.new_with_range(0, 32, 1),
                         hint="En GB. 0 deja que Java decida.", width=120)
        memory_min.set_value(values.get("memory_min", 0))
        resolution = row(performance, "Tamaño de la ventana", resolution_field(
            values.get("resolution"), "Usar ajuste de Nova"), width=300)

        java = row(java_card, "Ruta de Java", Gtk.Entry(text=values["java"], placeholder_text="Administrado por Nova"),
                   hint="Opcional. Para usar un Java que ya tenés instalado.", width=300)
        row(java_card, "Java instalado", java_picker(java, lambda: versions.get_child().get_text().strip()),
            hint="Buscá los que ya hay en este equipo.")
        jvm_args = row(java_card, "Argumentos extra", Gtk.Entry(text=values.get("jvm_args", ""),
                                                                 placeholder_text="-XX:+UseG1GC"),
                       hint="Opcional. Para usuarios avanzados.", width=300)

        def choose_cover():
            picker = Gtk.FileChooserNative(title="Elegir portada", transient_for=dialog,
                                           action=Gtk.FileChooserAction.OPEN)
            images = Gtk.FileFilter(name="Imágenes")
            images.add_pixbuf_formats()
            picker.add_filter(images)

            def chosen(window, response):
                nonlocal pending, cover
                if response == Gtk.ResponseType.ACCEPT:
                    path = window.get_file().get_path()
                    try:
                        if not path:
                            raise ValueError("Elegí una imagen guardada en el equipo.")
                        info, width, height = GdkPixbuf.Pixbuf.get_file_info(path)
                        if not info or width * height > 40_000_000:
                            raise ValueError("Elegí una imagen válida de hasta 40 megapíxeles.")
                        pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 960, 540, True)
                        _, pending = pixels.save_to_bufferv("png", [], [])
                        cover = hashlib.sha256(pending).hexdigest() + ".png"
                        preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixels))
                        error.set_text("")
                    except (GLib.Error, OSError, ValueError) as exc:
                        error.set_text(str(exc))
                window.destroy()

            picker.connect("response", chosen)
            picker.show()

        def clear_cover():
            nonlocal pending, cover
            pending, cover = None, ""
            preview.set_paintable(default_cover(values.get("artwork", 0)))

        cover_buttons.append(button("Elegir imagen", choose_cover))
        cover_buttons.append(button("Usar la original", clear_cover, "quiet-button"))

        error = label("", "form-status")
        error.set_wrap(True)
        box.append(error)

        def submit(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    title = name.get_text().strip()
                    if not 1 <= len(title) <= 40:
                        raise ValueError("Ingresá un nombre de 1 a 40 caracteres.")
                    version = versions.get_child().get_text().strip()
                    build = loader_build.get_text().strip() if loader.get_active_id() != "vanilla" else ""
                    if any(not re.fullmatch(r"[A-Za-z0-9._+-]+", value) or value in {".", ".."}
                           for value in (version, build) if value) or not version:
                        raise ValueError("Elegí una versión válida.")
                    java_path = self.java_path(java.get_text())
                    extra_args = jvm_args.get_text().strip()
                    motor.parse_jvm_args(extra_args)
                    settings = {"version": version, "loader": loader.get_active_id(), "client": client.get_active_id(),
                                "loader_version": build, "java": java_path, "cover": cover,
                                "jvm_args": extra_args,
                                "notes": notes.get_text().strip(),
                                "resolution": resolution.get_active_id()}
                    if pending:
                        self.store_cover(cover, pending)
                    ram = memory.get_value_as_int()
                    ram_min = memory_min.get_value_as_int()
                    if ram_min > ram:
                        raise ValueError("La memoria mínima no puede superar la máxima.")
                    settings["memory_min"] = ram_min
                    if folder:
                        with motor.instance_lock(folder):
                            motor.save(folder / "instance.json", {
                                **values, **settings, "name": title, "memory": ram,
                            })
                    else:
                        self.selected = motor.create(title, ram, len(self.instances) % 3, **settings)
                    self.refresh()
                except (OSError, RuntimeError, ValueError) as exc:
                    error.set_text(str(exc))
                    return
            dialog.destroy()

        dialog.connect("response", submit)
        self.show_page(dialog)

    @staticmethod
    def store_cover(name, data):
        from tempfile import NamedTemporaryFile
        target = motor.ROOT / "covers" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return
        with NamedTemporaryFile(dir=target.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        try:
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def java_path(value):
        value = value.strip()
        if not value:
            return ""
        path = Path(value).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError("La ruta de Java debe apuntar a un ejecutable.")
        return str(path)

    def global_settings(self):
        dialog = Gtk.Dialog(title="Ajustes de Nova", transient_for=self.window, modal=True,
                            default_width=540, default_height=580)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar", Gtk.ResponseType.OK).add_css_class("primary")
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        dialog.get_content_area().append(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      css_classes=["menu", "preferences"])
        scroll.set_child(box)

        def section(title):
            heading = label(title, "form-section")
            heading.set_margin_top(10)
            box.append(heading)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["form-card"])
            box.append(card)
            return card

        def field(card, title, control, hint=None, width=None):
            line = Gtk.Box(spacing=18, css_classes=["form-row"])
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True, valign=Gtk.Align.CENTER)
            text.append(label(title, "form-label"))
            if hint:
                note = label(hint, "opt-hint")
                note.set_wrap(True)
                note.set_max_width_chars(46)
                text.append(note)
            line.append(text)
            if width:
                control.set_size_request(width, -1)
            control.set_halign(Gtk.Align.END)
            control.set_valign(Gtk.Align.CENTER)
            line.append(control)
            card.append(line)
            return control

        minecraft = section("Minecraft")
        java = field(minecraft, "Ejecutable de Java", Gtk.Entry(text=self.preferences["java"],
                     placeholder_text="Java administrado por Nova"), width=260)
        picker = java_picker(java, lambda: motor.VERSION)
        picker_row = Gtk.Box(css_classes=["form-row"])
        picker_row.append(picker)
        minecraft.append(picker_row)
        memory = Gtk.SpinButton.new_with_range(2, 32, 1)
        memory.set_value(self.preferences["memory"])
        field(minecraft, "Memoria para nuevas instancias", memory, "En GB.")
        resolution = field(minecraft, "Tamaño de ventana", resolution_field(self.preferences["resolution"],
                           "Elegido por Minecraft"), "Se usa en las instancias nuevas.")
        behavior = Gtk.ComboBoxText()
        behavior.append("keep", "Mantener Nova abierto")
        behavior.append("minimize", "Minimizar Nova hasta que se cierre Minecraft")
        if os.name != "nt":
            behavior.append("close", "Cerrar Nova")
        if not behavior.set_active_id(self.preferences["launch_behavior"]):
            behavior.set_active_id("keep")
        field(minecraft, "Al iniciar Minecraft", behavior, "El registro se guarda aunque cierres Nova.")
        toggles = {}

        def switches(card, items):
            for key, title, hint in items:
                control = Gtk.Switch(active=bool(self.preferences.get(key)))
                control.update_property([Gtk.AccessibleProperty.LABEL], [title])
                toggles[key] = control
                field(card, title, control, hint)

        library = section("Biblioteca y diagnóstico")
        switches(library, (
            ("compact", "Lista compacta", "Usarla incluso con pocas instancias."),
            ("alphabetical", "Ordenar por nombre", "Si no, se muestran en el orden de creación."),
            ("console", "Abrir la consola al iniciar", "Útil para depurar mods."),
            ("launch_screen", "Pantalla de inicio al jugar", "Muestra el avance (preparar, archivos, Java, en juego) mientras Minecraft se abre."),
            ("beta", "Versiones beta de Nova", "Pruebas anticipadas, pueden tener errores."),
            ("usage", "Contar esta instalación", "Envía una vez al día un número al azar, la versión y el sistema. Nada más."),
        ))
        backups = section("Respaldos")
        backup_days = Gtk.SpinButton.new_with_range(0, 90, 1)
        backup_days.set_value(self.preferences.get("auto_backup_days", 0))
        field(backups, "Copia automática cada cuántos días", backup_days,
              "0 la apaga. Se hace al abrir Nova para las instancias sin respaldo reciente y no borra respaldos viejos.")
        look = section("Idioma y apariencia")
        language = Gtk.ComboBoxText()
        for code in i18n.available():
            language.append(code, {"es": "Español", "en": "English"}.get(code, code))
        language.set_active_id(self.preferences.get("language", "es"))
        field(look, "Idioma", language, "Se aplica al reiniciar Nova. Los textos sin traducción siguen en español.")
        theme = Gtk.ComboBoxText()
        theme.append("dark", "Oscuro")
        theme.append("light", "Claro")
        theme.set_active_id(self.preferences.get("theme", "dark") if self.preferences.get("theme") in ("dark", "light")
                            else "dark")
        field(look, "Apariencia", theme)
        animations = Gtk.ComboBoxText()
        for key, title in (("soft", "Lentas y suaves"), ("medium", "Normales"), ("fast", "Rápidas"), ("off", "Apagadas")):
            animations.append(key, title)
        animations.set_active_id(self.preferences.get("animations") if self.preferences.get("animations") in widgets.SPEEDS
                                 else "medium")
        field(look, "Animaciones", animations, "Lentas: más fluidas. Rápidas: casi instantáneas. Apagadas: sin movimiento. Si tu sistema tiene las animaciones apagadas, no se nota ningún cambio.")
        updates = section("Actualizaciones")
        repo = field(updates, "Repositorio público de GitHub", Gtk.Entry(
            text=self.preferences.get("release_repo", self.release_repo), placeholder_text="usuario/repositorio"), width=260)
        switches(updates, (("auto_update", "Actualizar Nova en segundo plano",
                            "Descarga y verifica (SHA-256) las versiones nuevas mientras usás Nova. Instalarlas es un clic: no instala nada solo."),))
        help_card = section("Ayuda")
        field(help_card, "Reporte de errores", button("Copiar", lambda: (
            dialog.get_clipboard().set(errores.report()),
            self.status.set_text("Reporte copiado. Pegalo en la página de reportes de GitHub."))),
            "Copia los datos útiles para pegarlos en la página de reportes.")
        field(help_card, "Página de reportes", button("Abrir", lambda: Gio.AppInfo.launch_default_for_uri(errores.ISSUES_URL, None)))
        error = label("", "form-error")
        error.set_wrap(True)
        box.append(error)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    settings = {**self.preferences, "java": self.java_path(java.get_text()),
                                "memory": memory.get_value_as_int(), "resolution": resolution.get_active_id(),
                                "release_repo": actualizaciones.repository(repo.get_text()),
                                "launch_behavior": behavior.get_active_id(),
                                "auto_backup_days": backup_days.get_value_as_int(),
                                "theme": theme.get_active_id(),
                                "animations": animations.get_active_id() or "medium",
                                "language": language.get_active_id() or "es",
                                **{key: control.get_active() for key, control in toggles.items()}}
                    motor.save(motor.ROOT / "settings.json", settings)
                    self.preferences = settings
                    if not settings["usage"]:
                        uso.forget()
                    self.apply_theme()
                    self.apply_speed()
                    self.refresh()
                    self.check_release()
                except (OSError, ValueError) as exc:
                    error.set_text(str(exc))
                    return
            dialog.destroy()

        dialog.connect("response", respond)
        self.show_page(dialog)






    def refresh(self):
        self.instances = {
            config.parent: {**motor.DEFAULTS, **motor.read(config, {})}
            for config in sorted((motor.ROOT / "instances").glob("*/instance.json"))
        }
        favorites = self.library.get("favorites", [])
        recent = self.library.get("recent", {})
        mode = self.library_filter.get_active_id()
        query = self.library_query.get_text().strip().casefold()
        visible = {folder: entry for folder, entry in self.instances.items()
                   if query in entry["name"].casefold()
                   and (mode != "favorites" or folder.name in favorites)
                   and (mode != "recent" or folder.name in recent)}
        if mode == "recent":
            visible = dict(sorted(visible.items(), key=lambda item: recent[item[0].name], reverse=True))
        elif self.preferences["alphabetical"]:
            visible = dict(sorted(visible.items(), key=lambda item: item[1]["name"].casefold()))
        self.visible_instances = visible
        count = len(visible)
        played = tiempo.total(self.library)
        self.library_count.set_text(i18n.tr("1 instancia" if count == 1 else f"{count} instancias")
                                    + (i18n.tr(f" · {tiempo.short(played)} jugadas") if played else ""))
        if self.selected not in visible:
            self.selected = next((folder for folder in visible
                                  if folder.name == self.library.get("selected")), next(iter(visible), None))
        compact = bool(self.visible_instances) and (len(self.visible_instances) > 12
                                         or (self.preferences["compact"] and len(self.visible_instances) > 3))
        layout = (compact, tuple((folder, instance["name"], instance["version"], instance["loader"],
                                  instance["artwork"], instance.get("cover"))
                                 for folder, instance in self.visible_instances.items()))
        if layout != self.library_layout:
            for container in (self.cards, self.compact):
                while child := container.get_first_child():
                    container.remove(child)
            self.instance_rows.clear()
            self.expanded_folder = None
            self.library_layout = layout
            self.cards.set_visible(bool(self.visible_instances) and not compact)
            self.details.set_visible(not compact)
            self.compact.set_visible(compact)
            if compact:
                for folder, instance in self.visible_instances.items():
                    self.add_compact_instance(folder, instance)
            else:
                self.render_cards()
        if compact:
            already_open = self.expanded_folder == self.selected
            self.expand_instance(self.selected, animate=False)
            if already_open:
                self.render_details(self.instance_rows[self.selected][2].get_child())
            for key, (_, _, reveal) in self.instance_rows.items():
                if key != self.selected:
                    reveal.set_child(None)
        else:
            for child, folder in zip(self.cards, self.visible_instances):
                tile = child.get_child()
                if folder == self.selected:
                    tile.add_css_class("selected")
                else:
                    tile.remove_css_class("selected")
            self.render_details(self.details)
        self.update_home()

    def render_cards(self):
        for index, (folder, instance) in enumerate(self.visible_instances.items()):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            artwork = instance_art(instance, -1, 104)
            card.append(artwork)
            title = label(instance["name"], "card-label")
            title.set_ellipsize(Pango.EllipsizeMode.END)
            card.append(title)
            played = tiempo.of(self.library, folder.name)
            meta = f"{instance['version']} · {'Pomme' if instance.get('client') == 'pomme' else motor.LOADERS[instance['loader']]}"
            card.append(label(meta + (f" · {tiempo.short(played)}" if played else ""), "card-meta"))
            tile = button("", lambda selected=folder: self.select(selected), "card")
            tile.set_child(card)
            tile.update_property([Gtk.AccessibleProperty.LABEL], [instance["name"]])
            if folder == self.selected:
                tile.add_css_class("selected")
            if not self.library_query.get_text().strip():  # typing in the search must not replay the entrance
                enter(tile, min(index, 12) * 45)  # stagger: decorative, never blocks clicks
            self.cards.append(tile)
        create = button("", self.add_instance, "card-new")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER,
                          valign=Gtk.Align.CENTER)
        content.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        content.append(label("Nueva instancia"))
        create.set_child(content)
        create.update_property([Gtk.AccessibleProperty.LABEL], ["Nueva instancia"])
        if not self.library_query.get_text().strip():
            enter(create, min(len(self.visible_instances), 12) * 45)
        self.cards.append(create)

    def add_compact_instance(self, folder, instance):
        row = Gtk.Box(spacing=10)
        artwork = instance_art(instance, 48, 34)
        row.append(artwork)
        name = label(instance["name"], "compact-name")
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)
        row.append(label(f"{instance['version']} · {'Pomme' if instance.get('client') == 'pomme' else motor.LOADERS[instance['loader']]}", "muted"))
        arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        row.append(arrow)
        tile = button("", lambda: self.select(folder), "compact-instance")
        tile.set_child(row)
        tile.update_property([Gtk.AccessibleProperty.LABEL], [instance["name"]])
        reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                             transition_duration=widgets.ms(180))
        item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        item.append(tile)
        item.append(reveal)
        self.compact.append(item)
        self.instance_rows[folder] = tile, arrow, reveal

        def release_details(widget, _):
            if not widget.get_child_revealed() and not widget.get_reveal_child():
                widget.set_child(None)

        reveal.connect("notify::child-revealed", release_details)

    def expand_instance(self, folder, *, animate=True):
        if self.expanded_folder == folder:
            return
        animate = animate and Gtk.Settings.get_default().get_property("gtk-enable-animations")
        previous = self.expanded_folder
        self.expanded_folder = folder
        if previous is not None:
            tile, arrow, reveal = self.instance_rows[previous]
            tile.remove_css_class("selected")
            arrow.set_from_icon_name("pan-end-symbolic")
            tile.update_state([Gtk.AccessibleState.EXPANDED], [0])
            if reveal.get_child():
                reveal.get_child().set_sensitive(False)
            if not animate:
                reveal.set_transition_duration(0)
            reveal.set_reveal_child(False)
            if not animate:
                reveal.set_transition_duration(widgets.ms(180))

        tile, arrow, reveal = self.instance_rows[folder]
        tile.add_css_class("selected")
        arrow.set_from_icon_name("pan-down-symbolic")
        tile.update_state([Gtk.AccessibleState.EXPANDED], [1])
        details = reveal.get_child()
        if details is None:
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                              css_classes=["details", "inline-details"])
            self.render_details(details)
            reveal.set_child(details)
        details.set_sensitive(True)
        if not animate:
            reveal.set_transition_duration(0)
        reveal.set_reveal_child(True)
        if not animate:
            reveal.set_transition_duration(widgets.ms(180))

    def render_details(self, details):
        details.remove_css_class("empty-state")
        while child := details.get_first_child():
            details.remove(child)
        if self.selected is None:
            if self.instances:
                details.append(label("No hay instancias para este filtro.", "subheading"))
                return
            details.add_css_class("empty-state")
            details.append(label("Tu biblioteca está vacía", "subheading"))
            hint = label("Creá una instancia de Minecraft Java o importá un modpack.", "muted")
            hint.set_wrap(True)
            details.append(hint)
            actions = Gtk.Box(spacing=8)
            actions.append(button("Crear mi primera instancia", self.add_instance, "primary"))
            actions.append(button("Importar un modpack", lambda: self.add_instance(import_only=True)))
            details.append(actions)
            return
        instance = self.instances[self.selected]
        folder = self.selected
        hero = Gtk.Overlay(css_classes=["hero"])
        hero.set_overflow(Gtk.Overflow.HIDDEN)
        hero.set_child(hero_art(instance))
        hero.add_overlay(Gtk.Box(css_classes=["hero-shade"]))
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, valign=Gtk.Align.END,
                          halign=Gtk.Align.START, css_classes=["hero-content"])
        hero.add_overlay(content)
        if folder.name in self.library.get("favorites", []):
            content.append(Gtk.Label(label="★ Favorita", halign=Gtk.Align.START, css_classes=["chip", "chip-accent"]))
        name = label(instance["name"], "hero-title")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_tooltip_text(instance["name"])
        content.append(name)
        chips = Gtk.Box(spacing=6)
        loader_name = motor.LOADERS[instance["loader"]]
        played = tiempo.of(self.library, folder.name)
        for text, accent in ((instance["version"], True),
                             ("Pomme · Rust" if instance.get("client") == "pomme"
                              else f"{loader_name} {instance['loader_version']}".strip(), False),
                             (f"{instance['memory']} GB", False),
                             (f"⏱ {tiempo.short(played)}", False)):
            chips.append(Gtk.Label(label=text, css_classes=["chip", "chip-accent"] if accent else ["chip"]))
        content.append(chips)
        actions = Gtk.Box(spacing=8, css_classes=["hero-actions"])
        play = button("", self.play, "primary")
        play.add_css_class("play-button")
        if self.launch_stage:
            play.add_css_class("launching")
        play_content = Gtk.Box(spacing=8)
        play_content.append(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        self.play_label = label(self.launch_stage or "Jugar")
        play_content.append(self.play_label)
        play.set_child(play_content)
        play.update_property([Gtk.AccessibleProperty.LABEL], ["Jugar"])
        play.set_sensitive(not self.busy and not self.parallel)
        actions.append(play)
        actions.append(button("Editar", self.edit_settings))
        actions.append(button("Servidores", lambda: self.open_servers(folder)))
        more = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Más acciones")
        more.update_property([Gtk.AccessibleProperty.LABEL], ["Más acciones"])
        popover = Gtk.Popover()
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["action-menu"])
        # The list is long: keep it inside the window and let it scroll instead of running off the screen.
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                      max_content_height=420, min_content_width=270)
        scroller.set_child(menu)
        popover.set_child(scroller)
        popover.connect("show", lambda *_: scroller.set_max_content_height(
            max(220, min(560, self.window.get_height() - 190))))
        more.set_popover(popover)
        actions.append(more)
        content.append(actions)
        details.append(hero)
        if getattr(self, "hero_folder", None) != folder:  # typing in the search rebuilds the hero: only animate a new one
            enter(hero)
        self.hero_folder = folder
        if instance.get("client") == "pomme":
            about = label("Pomme es un cliente aparte: no usa los mods, shaders ni texturas de Java de esta instancia. "
                          "Se inicia con Jugar y tiene su propio inicio de sesión.", "muted")
            about.set_wrap(True)
            details.append(about)
        else:
            details.append(label("Contenido", "section-title"))
            tiles = Gtk.Box(spacing=12, homogeneous=True)
            for category, title in (("mod", "Mods"), ("shader", "Shaders"), ("resourcepack", "Texturas")):
                count = len(biblioteca.content_files(folder, category))
                tile = content_tile(
                    title, count,
                    lambda kind=category: biblioteca.open_installed(self, folder, kind),
                    lambda kind=category: biblioteca.Browser(self, folder, instance, kind),
                    lambda kind=category: self.import_files(category=kind, folder=folder))
                tile.set_sensitive(not self.busy)
                tiles.append(tile)
            tiles.append(stat_tile("Tiempo jugado", tiempo.short(played)))
            details.append(tiles)
        if instance.get("notes"):
            note = label(instance["notes"], "muted")
            note.set_wrap(True)
            details.append(note)

        def group(title):
            if menu.get_first_child() is not None:
                menu.append(Gtk.Separator(css_classes=["menu-separator"]))
            menu.append(label(title, "menu-caption"))

        def add_item(control):
            child = control.get_child()
            if isinstance(child, Gtk.Label):  # left-aligned, like a menu
                child.set_xalign(0)
                child.set_hexpand(True)
            menu.append(control)

        def add_action(title, action, style=None):
            def activate():
                popover.popdown()
                action()
            control = button(title, activate, style)
            control.set_sensitive(not self.busy)
            add_item(control)

        favorite = folder.name in self.library.get("favorites", [])
        group("JUGAR")
        add_action("Quitar de favoritas" if favorite else "Marcar como favorita",
                   lambda: self.toggle_favorite(folder))
        if instance.get("client") == "pomme":
            add_action("Actualizar o reinstalar Pomme", self.install_pomme)
        alternate = button("Jugar con otra cuenta", lambda: (popover.popdown(), self.play_parallel(folder)))
        alternate.set_sensitive(not self.parallel and (not self.busy or
                                (self.running and self.running[0] == folder)))
        add_item(alternate)
        add_action("Jugar con cuenta offline", lambda: self.play(offline=True))
        group("CONTENIDO")
        add_action("Salud y mods", lambda: self.show_health(folder))
        add_action("Contenido instalado", lambda: biblioteca.open_installed(self, folder))
        add_action("Importar archivos del equipo", lambda: self.import_files(folder=folder))
        add_action("Mundos", lambda: self.show_worlds(folder))
        add_action("Java y memoria", lambda: self.show_java(folder, instance))
        add_action("Ver registro", lambda: self.open_log(folder))
        add_action("Abrir carpeta", lambda: motor.open_folder(folder))
        group("INSTANCIA")
        add_action("Duplicar instancia", lambda: self.copy_instance(folder, "duplicate"))
        add_action("Crear respaldo", lambda: self.copy_instance(folder, "backup"))
        add_action("Exportar instancia", lambda: self.export_instance(folder))
        add_action("Exportar perfil", lambda: self.export_profile(folder))
        if os.name != "nt" and not Path("/.flatpak-info").exists():  # a sandbox cannot export launchers
            add_action("Crear atajo en el menú", lambda: self.create_shortcut(folder, instance["name"]))
        add_action("Reparar instalación", lambda: self.repair_instance(folder, instance))
        if instance["loader"] in ("fabric", "quilt"):
            full_branding = pantalla_carga.logo_supported(instance)
            if pantalla_carga.status(folder) == "on":
                add_action("Quitar pantalla de carga Nova", lambda: integraciones.run(
                    self, self.window, "Pantalla de carga",
                    lambda: integraciones.remove_colors(folder),
                    "Listo: la pantalla de carga vuelve a como estaba antes de Nova."
                ))
            else:
                title = "Pantalla de carga Nova" if full_branding else "Colores Nova en la carga"
                add_action(title, lambda: integraciones.run(
                    self, self.window, "Pantalla de carga",
                    lambda: integraciones.apply_colors(folder, instance),
                    "Pantalla Nova preparada para el próximo inicio de Minecraft." if full_branding else
                    "Colores de Nova aplicados. Se ven al iniciar Minecraft."
                ))
        menu.append(Gtk.Separator(css_classes=["menu-separator"]))
        add_action("Eliminar instancia", lambda: self.remove_instance(folder, instance["name"]), "danger")

    def save_file(self, title, filename, action):
        picker = Gtk.FileChooserNative(title=title, transient_for=self.window,
                                       action=Gtk.FileChooserAction.SAVE)
        picker.set_current_name(filename)

        def respond(dialog, response):
            file = dialog.get_file() if response == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            dialog.destroy()
            if path:
                action(Path(path))

        picker.connect("response", respond)
        picker.show()

    def background_file(self, message, task, success, *, after_save=None):
        if self.busy:
            return
        self.busy = True
        self.status.set_text(message)
        self.refresh()

        def saved():
            self.finished(success)
            if after_save:
                after_save()

        def worker():
            try:
                task()
            except Exception as exc:
                errores.record(exc, "nova.worker")
                GLib.idle_add(self.finished, f"No se pudo completar: {exc}")
            else:
                GLib.idle_add(saved)

        threading.Thread(target=worker, daemon=True).start()





    def remove_instance(self, folder, name):
        if self.parallel:
            self.status.set_text("Cerrá la segunda sesión antes de eliminar instancias.")
            return
        dialog = Gtk.Dialog(title="Eliminar instancia", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Mover a la Papelera", Gtk.ResponseType.OK).add_css_class("danger")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.add_css_class("menu")
        message = label(f"«{name}» se moverá a la Papelera junto con sus mundos, mods y ajustes.")
        message.set_wrap(True)
        message.set_max_width_chars(48)
        box.append(message)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    with motor.instance_lock(folder):
                        Gio.File.new_for_path(str(folder)).trash(None)
                except (GLib.Error, OSError, RuntimeError) as error:
                    self.status.set_text(f"No se pudo eliminar la instancia: {error}")
                else:
                    atajos.remove(folder)
                    self.status.set_text(f"«{name}» se movió a la Papelera.")
                    self.refresh()
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()

    def open_log(self, folder):
        consola.open_console(self.window, folder / "minecraft.log")

    def select(self, folder):
        if self.selected == folder:
            return
        self.selected = folder
        self.library["selected"] = folder.name
        self.save_library()
        if folder in self.instance_rows:
            self.expand_instance(folder)
        else:
            self.refresh()









    def save_library(self):
        try:
            motor.save(motor.ROOT / "library.json", self.library)
        except OSError as error:
            self.status.set_text(f"No se pudo guardar la biblioteca: {error}")

    def toggle_favorite(self, folder):
        favorites = self.library.setdefault("favorites", [])
        if folder.name in favorites:
            favorites.remove(folder.name)
        else:
            favorites.append(folder.name)
        self.save_library()
        self.refresh()

    def play(self, server=None, *, offline=False):
        if self.busy or self.parallel or self.selected is None:
            return
        if self.instances[self.selected].get("client") == "pomme":
            self.play_pomme()
            return
        if not self.profile and (offline or not self.microsoft_active):
            self.edit_profile(after_save=lambda: self.play(server, offline=offline))
            self.status.set_text("Elegí el nombre con el que querés jugar.")
            return
        folder = self.selected
        profile = self.profile
        microsoft = self.microsoft if self.microsoft_active and not offline else None
        instance = dict(self.instances[folder])
        instance["java"] = instance["java"] or self.preferences["java"]
        if instance.get("resolution", "default") == "default":
            instance["resolution"] = self.preferences["resolution"]
        behavior = self.preferences["launch_behavior"]
        if os.name == "nt" and behavior == "close" or behavior == "close" and servidor_local.running():
            behavior = "minimize"  # closing Nova would leave a running server without control
        if self.preferences["console"] and behavior != "close":
            self.open_log(folder)
        self.busy = True
        self.failure_log.set_visible(False)
        self.failure_fix.set_visible(False)
        self.launch_stage = "Preparando…"
        self.status.set_text("Preparando Minecraft…")
        self.refresh()
        if behavior != "close":
            self.launch_screen_show(folder, instance, microsoft[1]["name"] if microsoft else profile)

        minimized = False
        failure_fix = []
        began = []
        clicked = time.monotonic()
        wall = []

        def started(player):
            nonlocal minimized
            began.append(time.monotonic())
            wall.append(time.time())
            self.running = folder, player, server
            self.library["selected"] = folder.name
            self.library.setdefault("recent", {})[folder.name] = time.time()
            self.save_library()
            if behavior == "close" and not self.parallel:
                self.quit()
                return
            if behavior == "minimize":
                self.window.minimize()
                minimized = True
            self.refresh()
            self.launch_screen_started(minimized)

        def finish(message, failed):
            self.running = None
            self.launch_stage = ""
            if began:
                seconds = time.monotonic() - began[0]
                tiempo.add(self.library, folder.name, seconds)
                self.save_library()
                estadisticas.record_session(folder.name, started_at=wall[0], seconds=seconds,
                                            launch_seconds=began[0] - clicked, ok=not failed)
            self.finished(message)
            self.failed_log = folder / "minecraft.log"
            self.failure_log.set_visible(failed)
            self.failure_action = (folder, failure_fix[0]) if failed and failure_fix else None
            self.failure_fix.set_visible(bool(self.failure_action))
            self.launch_screen_finished(failed, message)
            if minimized:
                self.window.unminimize()
                self.window.present()

        def show_stage(message):
            self.status.set_text(message)
            self.launch_screen_update(message)
            self.launch_stage = ("Descargando…" if message.startswith("Descargando") else
                                 "En juego" if message.startswith("Minecraft abierto") else
                                 "Iniciando…" if message.startswith("Iniciando") else "Preparando…")
            if self.selected == folder:
                self.play_label.set_text(self.launch_stage)

        def worker():
            def status(message):
                GLib.idle_add(show_stage, message)
            try:
                failed = False
                session = None
                if microsoft:
                    status("Verificando la cuenta de Microsoft…")
                    import cuentas
                    session = cuentas.refresh(*microsoft)
                if session:
                    GLib.idle_add(self.store_session, microsoft, session)
                result = motor.launch(
                    folder, profile, instance, status, session=session,
                    on_started=lambda: GLib.idle_add(started, session["name"] if session else profile),
                    detach=behavior == "close", server=server, offline=offline,
                )
                message = "Minecraft cerrado."
                if result != 0:
                    failed = True
                    try:
                        cause = consola.analyze(consola.read_log(folder / "minecraft.log"), folder / "game")
                    except OSError:
                        cause = {"advice": "", "mod": "", "action": None}
                    if cause["action"]:
                        failure_fix.append(cause["action"])
                    message = consola.failure_message(result, cause)
            except Exception as exc:
                errores.record(exc, "nova.worker")
                GLib.idle_add(self.finished, f"No se pudo completar: {exc}")
            else:
                GLib.idle_add(saved)

        threading.Thread(target=worker, daemon=True).start()





    def remove_instance(self, folder, name):
        if self.parallel:
            self.status.set_text("Cerrá la segunda sesión antes de eliminar instancias.")
            return
        dialog = Gtk.Dialog(title="Eliminar instancia", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Mover a la Papelera", Gtk.ResponseType.OK).add_css_class("danger")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.add_css_class("menu")
        message = label(f"«{name}» se moverá a la Papelera junto con sus mundos, mods y ajustes.")
        message.set_wrap(True)
        message.set_max_width_chars(48)
        box.append(message)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    with motor.instance_lock(folder):
                        Gio.File.new_for_path(str(folder)).trash(None)
                except (GLib.Error, OSError, RuntimeError) as error:
                    self.status.set_text(f"No se pudo eliminar la instancia: {error}")
                else:
                    atajos.remove(folder)
                    self.status.set_text(f"«{name}» se movió a la Papelera.")
                    self.refresh()
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()

    def open_log(self, folder):
        consola.open_console(self.window, folder / "minecraft.log")

    def select(self, folder):
        if self.selected == folder:
            return
        self.selected = folder
        self.library["selected"] = folder.name
        self.save_library()
        if folder in self.instance_rows:
            self.expand_instance(folder)
        else:
            self.refresh()









    def save_library(self):
        try:
            motor.save(motor.ROOT / "library.json", self.library)
        except OSError as error:
            self.status.set_text(f"No se pudo guardar la biblioteca: {error}")

    def toggle_favorite(self, folder):
        favorites = self.library.setdefault("favorites", [])
        if folder.name in favorites:
            favorites.remove(folder.name)
        else:
            favorites.append(folder.name)
        self.save_library()
        self.refresh()

    def play(self, server=None, *, offline=False):
        if self.busy or self.parallel or self.selected is None:
            return
        if self.instances[self.selected].get("client") == "pomme":
            self.play_pomme()
            return
        if not self.profile and (offline or not self.microsoft_active):
            self.edit_profile(after_save=lambda: self.play(server, offline=offline))
            self.status.set_text("Elegí el nombre con el que querés jugar.")
            return
        folder = self.selected
        profile = self.profile
        microsoft = self.microsoft if self.microsoft_active and not offline else None
        instance = dict(self.instances[folder])
        instance["java"] = instance["java"] or self.preferences["java"]
        if instance.get("resolution", "default") == "default":
            instance["resolution"] = self.preferences["resolution"]
        behavior = self.preferences["launch_behavior"]
        if os.name == "nt" and behavior == "close" or behavior == "close" and servidor_local.running():
            behavior = "minimize"  # closing Nova would leave a running server without control
        if self.preferences["console"] and behavior != "close":
            self.open_log(folder)
        self.busy = True
        self.failure_log.set_visible(False)
        self.failure_fix.set_visible(False)
        self.launch_stage = "Preparando…"
        self.status.set_text("Preparando Minecraft…")
        self.refresh()
        if behavior != "close":
            self.launch_screen_show(folder, instance, microsoft[1]["name"] if microsoft else profile)

        minimized = False
        failure_fix = []
        began = []
        clicked = time.monotonic()
        wall = []

        def started(player):
            nonlocal minimized
            began.append(time.monotonic())
            wall.append(time.time())
            self.running = folder, player, server
            self.library["selected"] = folder.name
            self.library.setdefault("recent", {})[folder.name] = time.time()
            self.save_library()
            if behavior == "close" and not self.parallel:
                self.quit()
                return
            if behavior == "minimize":
                self.window.minimize()
                minimized = True
            self.refresh()
            self.launch_screen_started(minimized)

        def finish(message, failed):
            self.running = None
            self.launch_stage = ""
            if began:
                seconds = time.monotonic() - began[0]
                tiempo.add(self.library, folder.name, seconds)
                self.save_library()
                estadisticas.record_session(folder.name, started_at=wall[0], seconds=seconds,
                                            launch_seconds=began[0] - clicked, ok=not failed)
            self.finished(message)
            self.failed_log = folder / "minecraft.log"
            self.failure_log.set_visible(failed)
            self.failure_action = (folder, failure_fix[0]) if failed and failure_fix else None
            self.failure_fix.set_visible(bool(self.failure_action))
            self.launch_screen_finished(failed, message)
            if minimized:
                self.window.unminimize()
                self.window.present()

        def show_stage(message):
            self.status.set_text(message)
            self.launch_screen_update(message)
            self.launch_stage = ("Descargando…" if message.startswith("Descargando") else
                                 "En juego" if message.startswith("Minecraft abierto") else
                                 "Iniciando…" if message.startswith("Iniciando") else "Preparando…")
            if self.selected == folder:
                self.play_label.set_text(self.launch_stage)

        def worker():
            def status(message):
                GLib.idle_add(show_stage, message)
            try:
                failed = False
                session = None
                if microsoft:
                    status("Verificando la cuenta de Microsoft…")
                    import cuentas
                    session = cuentas.refresh(*microsoft)
                if session:
                    GLib.idle_add(self.store_session, microsoft, session)
                result = motor.launch(
                    folder, profile, instance, status, session=session,
                    on_started=lambda: GLib.idle_add(started, session["name"] if session else profile),
                    detach=behavior == "close", server=server, offline=offline,
                )
                message = "Minecraft cerrado."
                if result != 0:
                    failed = True
                    try:
                        cause = consola.analyze(consola.read_log(folder / "minecraft.log"), folder / "game")
                    except OSError:
                        cause = {"advice": "", "mod": "", "action": None}
                    if cause["action"]:
                        failure_fix.append(cause["action"])
                    message = (f"Minecraft terminó con código {result}. "
                               f"{cause['advice'] or 'Abrí Ver registro para ver los detalles.'}"
                               + (f" Sospechoso: {cause['mod']}." if cause["mod"] else ""))
            except Exception as exc:
                errores.record(exc, "nova.worker")
                failed = True
                message = f"Error al iniciar Minecraft: {exc}"
            GLib.idle_add(finish, message, failed)

        threading.Thread(target=worker, daemon=True).start()

    def fix_failure(self):
        if not self.failure_action:
            return
        folder, action = self.failure_action
        title, text = (("Usar el Java de Nova", "Se vaciará la ruta de Java de esta instancia para que Nova use el compatible. Antes guarda una copia de instance.json.")
                       if action == "use_nova_java" else
                       ("Corregir ajustes", "Nova restablecerá solo los valores inválidos de RAM y argumentos de Java. Antes guarda una copia de instance.json."))

        def run():
            try:
                changes = reparacion.apply(action, folder)
            except (OSError, ValueError) as error:
                self.status.set_text(f"No se pudo corregir: {error}")
                return
            self.refresh()
            self.failure_fix.set_visible(False)
            self.failure_action = None
            self.status.set_text("Corregido · " + ("; ".join(changes) or "no había nada que cambiar") + ". Probá jugar de nuevo.")

        self.confirm(title, text, "Corregir", run)

    def store_session(self, previous, session):
        if self.microsoft is previous:
            self.microsoft = (previous[0], session)
            import credenciales
            credenciales.save_session(previous[0], session)

    def finished(self, message):
        self.busy = False
        self.status.set_text(message)
        self.refresh()
        GLib.idle_add(self.run_queue)


if __name__ == "__main__":
    sys.exit(Nova().run(sys.argv))

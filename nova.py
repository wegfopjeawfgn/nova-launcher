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
import estadisticas
import i18n
import respaldos
import tiempo
from widgets import resolution_field, instance_art, hero_art, enter, label, button, feature_button, HERE
from vistas_cuentas import CuentasMixin
from vistas_paginas import PaginasMixin
from vistas_salud import SaludMixin
from vistas_perfiles import PerfilesMixin
from vistas_curseforge import CurseForgeMixin
from vistas_estadisticas import EstadisticasMixin
from vistas_importar import ImportarMixin
from vistas_servidores import ServidoresMixin
from vistas_descargas import DescargasMixin
from vistas_sesiones import SesionesMixin
from vistas_actualizar import ActualizarMixin
from vistas_respaldos import RespaldosMixin


class Nova(
    PaginasMixin,
    SaludMixin,
    PerfilesMixin,
    CurseForgeMixin,
    EstadisticasMixin,
    CuentasMixin,
    ImportarMixin,
    ServidoresMixin,
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
            self.selected = folder
            self.refresh()
            self.play()
        return False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(HERE / "nova.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
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
            Gtk.ShortcutTrigger.parse_string("Escape"),
            Gtk.CallbackAction.new(lambda *_: self.current_page is not None and self.leave_page()),
        ))
        self.window.add_controller(keys)
        self.window.connect("close-request", lambda _: self.busy or self.parallel)
        accounts = motor.read(motor.ROOT / "accounts.json", {"active": "", "profiles": []})
        self.preferences = {
            "memory": 4, "java": "", "resolution": "default", "console": False,
            "compact": False, "alphabetical": False, "launch_behavior": "keep", "beta": False, "auto_backup_days": 0, "theme": "dark", "language": "es",
            **motor.read(motor.ROOT / "settings.json", {}),
        }
        i18n.set_language(self.preferences.get("language", "es"))
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
        self.accounts = Gtk.MenuButton(css_classes=["account-switcher"])
        titlebar.pack_end(self.accounts)
        self.window.set_titlebar(titlebar)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.set_child(outer)
        shell = Gtk.Box(vexpand=True)
        outer.append(shell)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["sidebar"])
        nav_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        propagate_natural_width=True)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.nav_box = nav
        nav_scroll.set_child(nav)
        sidebar.append(nav_scroll)
        nav.append(label(i18n.tr("BIBLIOTECA"), "nav-caption"))
        nav.append(self.nav_button("Instancias", "view-grid-symbolic",
                                   lambda: (self.leave_page(), scroll.get_vadjustment().set_value(0)), active=True))
        nav.append(self.nav_button("Nueva instancia", "list-add-symbolic", self.add_instance))
        nav.append(self.nav_button("Novedades", "package-x-generic-symbolic", self.show_news))
        nav.append(label(i18n.tr("DESCUBRIR"), "nav-caption"))
        nav.append(self.nav_button("Explorar", "system-search-symbolic", self.browse))
        nav.append(self.nav_button("CurseForge", "system-search-symbolic", self.show_curseforge))
        nav.append(self.nav_button("Modpacks", "package-x-generic-symbolic", self.browse_packs))
        nav.append(self.nav_button("Importar pack", "document-open-symbolic",
                                   lambda: self.add_instance(import_only=True)))
        nav.append(label(i18n.tr("HERRAMIENTAS"), "nav-caption"))
        nav.append(self.nav_button("Skins", "applications-graphics-symbolic", self.open_skins))
        nav.append(self.nav_button("Servidores", "network-server-symbolic", self.open_servers))
        nav.append(self.nav_button("Respaldos", "document-open-symbolic", self.show_backups))
        nav.append(self.nav_button("Sesiones", "media-playback-start-symbolic", self.show_sessions))
        nav.append(self.nav_button("Descargas", "folder-download-symbolic", self.show_downloads))
        nav.append(self.nav_button("Almacenamiento", "drive-harddisk-symbolic", self.show_storage))
        nav.append(self.nav_button("Estadísticas", "applications-graphics-symbolic", self.show_statistics))
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
        sidebar.set_hexpand(False)  # the footer card expands; the sidebar must not
        shell.append(sidebar)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        shell.append(self.setup_pages(scroll))
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
        outer.append(statusbar)
        self.library_query.connect("search-changed", lambda _: self.refresh())
        self.library_filter.connect("changed", lambda _: self.refresh())
        self.update_accounts()
        self.refresh()
        self.apply_theme()
        self.window.present()
        GLib.timeout_add_seconds(30, self.auto_backup)
        self.versions = motor.read(motor.ROOT / "versions.json", [])
        threading.Thread(target=self.load_versions, daemon=True).start()
        if self.preferences.get("release_repo", self.release_repo):
            self.check_release()



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
        title = "Importar modpack" if import_only else "Nueva instancia"
        chooser = Gtk.Window(title=title, transient_for=self.window,
                             modal=True, default_width=510, resizable=False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label(title, "subheading"))
        content.append(label("Elegí el formato del archivo" if import_only else
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
        )
        options += (("Importar desde Prism Launcher", "Copiá la instancia, sus mods y sus mundos.",
                     self.choose_prism),
                    ("Desde una plantilla", "Supervivencia, PvP, rendimiento y más, con ajustes razonables.",
                     self.show_templates),
                    ("Importar un perfil de Nova", "Archivo .json exportado desde otra instancia.",
                     self.import_profile))
        shown = options[2:4] + options[6:] if import_only else options
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
        box.add_css_class("menu")
        box.set_spacing(8)

        tabs = Gtk.Notebook()
        box.append(tabs)
        general = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["menu"])
        appearance = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        tabs.append_page(general, Gtk.Label(label="Juego"))
        tabs.append_page(appearance, Gtk.Label(label="Portada y notas"))

        def game_field(title, widget):
            general.append(label(title))
            general.append(widget)
            return widget

        name = game_field("Nombre", Gtk.Entry(text=values["name"], width_chars=43))
        versions = game_field("Versión de Minecraft", Gtk.ComboBoxText.new_with_entry())
        for item in self.versions:
            versions.append(item["id"], item["id"])
        if not versions.set_active_id(values["version"]):
            versions.get_child().set_text(values["version"])
        loader = game_field("Cargador", Gtk.ComboBoxText())
        for key, title in motor.LOADERS.items():
            loader.append(key, title)
        loader.set_active_id(values["loader"])
        build_row = game_field("Versión del cargador (opcional)", Gtk.Box(spacing=8))
        builds = Gtk.ComboBoxText.new_with_entry()
        builds.set_hexpand(True)
        loader_build = builds.get_child()
        loader_build.set_text(values["loader_version"])
        loader_build.set_placeholder_text("Automática si se deja vacía")
        build_row.append(builds)
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

        lookup = button("Consultar builds", load_builds)
        build_row.append(lookup)

        def loader_changed(_):
            builds.remove_all()
            loader_build.set_text("")
            build_row.set_sensitive(loader.get_active_id() != "vanilla")

        loader.connect("changed", loader_changed)
        memory = game_field("Memoria máxima (GB)", Gtk.SpinButton.new_with_range(1, 32, 1))
        memory.set_value(values["memory"])
        java = game_field("Ruta de Java para esta instancia (opcional)", Gtk.Entry(text=values["java"]))
        jvm_args = game_field("Argumentos extra de Java (opcional)",
                              Gtk.Entry(text=values.get("jvm_args", ""),
                                        placeholder_text="-XX:+UseG1GC -Xms1G"))
        fixed = folder and (values.get("pack") or (folder / "game" / "saves").exists()
                            or (folder / "game" / "mods").exists())
        if fixed:
            for widget in (versions, loader, build_row):
                widget.set_sensitive(False)
            general.append(label("Esta instancia contiene un pack, mods o mundos.", "muted"))
        resolution = game_field("Tamaño de la ventana", resolution_field(
            values.get("resolution"), "Usar ajuste de Nova"
        ))
        cover = values.get("cover", "")
        pending = None
        cover_frame = instance_art({**values, "artwork": values.get("artwork", 0)}, height=135)
        preview = cover_frame.get_last_child()
        appearance.append(cover_frame)
        cover_buttons = Gtk.Box(spacing=8)
        appearance.append(cover_buttons)
        notes = Gtk.Entry(text=values.get("notes", ""), max_length=160,
                          placeholder_text="Ej. Mundo cooperativo con amigos")
        appearance.append(label("Nota de la instancia", "form-label"))
        appearance.append(notes)

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
            preview.set_paintable(None)

        cover_buttons.append(button("Elegir imagen", choose_cover))
        cover_buttons.append(button("Usar portada original", clear_cover))

        error = label("", "muted")
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
                    settings = {"version": version, "loader": loader.get_active_id(),
                                "loader_version": build, "java": java_path, "cover": cover,
                                "jvm_args": extra_args,
                                "notes": notes.get_text().strip(),
                                "resolution": resolution.get_active_id()}
                    if pending:
                        self.store_cover(cover, pending)
                    ram = memory.get_value_as_int()
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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      css_classes=["menu", "preferences"])
        scroll.set_child(box)
        box.append(label("Minecraft", "settings-heading"))
        box.append(label("Ejecutable de Java", "form-label"))
        java = Gtk.Entry(text=self.preferences["java"], placeholder_text="Java administrado por Nova")
        box.append(java)
        memory = Gtk.SpinButton.new_with_range(2, 32, 1)
        memory.set_value(self.preferences["memory"])
        resolution = resolution_field(self.preferences["resolution"], "Elegido por Minecraft")
        box.append(label("Memoria para nuevas instancias (GB)", "form-label"))
        box.append(memory)
        box.append(label("Tamaño de ventana predeterminado", "form-label"))
        box.append(resolution)
        box.append(label("Al iniciar Minecraft", "settings-heading"))
        behavior = Gtk.ComboBoxText()
        behavior.append("keep", "Mantener Nova abierto")
        behavior.append("minimize", "Minimizar Nova hasta que se cierre Minecraft")
        if os.name != "nt":
            behavior.append("close", "Cerrar Nova")
        if not behavior.set_active_id(self.preferences["launch_behavior"]):
            behavior.set_active_id("keep")
        box.append(behavior)
        hint = label("El registro de Minecraft se guarda aunque cierres Nova.", "muted")
        hint.set_wrap(True)
        box.append(hint)
        box.append(label("Biblioteca y diagnóstico", "settings-heading"))
        toggles = {}
        for key, title, hint in (
            ("compact", "Lista compacta", "Usarla incluso con pocas instancias."),
            ("alphabetical", "Ordenar por nombre", "Si no, se muestran en el orden de creación."),
            ("console", "Abrir la consola al iniciar", "Útil para depurar mods."),
            ("beta", "Versiones beta de Nova", "Pruebas anticipadas, pueden tener errores."),
        ):
            control = Gtk.Switch(active=self.preferences[key], valign=Gtk.Align.CENTER)
            control.update_property([Gtk.AccessibleProperty.LABEL], [title])
            toggles[key] = control
            row = Gtk.Box(spacing=12, css_classes=["opt-row"])
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            text.append(label(title, "form-label"))
            text.append(label(hint, "opt-hint"))
            row.append(text)
            row.append(control)
            box.append(row)
        box.append(label("Respaldos", "settings-heading"))
        box.append(label("Copia automática cada cuántos días (0 = apagada)", "form-label"))
        backup_days = Gtk.SpinButton.new_with_range(0, 90, 1)
        backup_days.set_value(self.preferences.get("auto_backup_days", 0))
        box.append(backup_days)
        box.append(label("Se hace una vez al abrir Nova para las instancias sin respaldo reciente. "
                         "No borra respaldos viejos.", "opt-hint"))
        box.append(label("Idioma", "settings-heading"))
        language = Gtk.ComboBoxText()
        for code in i18n.available():
            language.append(code, {"es": "Español", "en": "English"}.get(code, code))
        language.set_active_id(self.preferences.get("language", "es"))
        box.append(language)
        box.append(label("Se aplica al reiniciar Nova. Los textos sin traducción siguen en español.", "opt-hint"))
        box.append(label("Apariencia", "settings-heading"))
        theme = Gtk.ComboBoxText()
        theme.append("dark", "Oscuro")
        theme.append("light", "Claro")
        theme.set_active_id(self.preferences.get("theme", "dark") if self.preferences.get("theme") in ("dark", "light")
                            else "dark")
        box.append(theme)
        box.append(label("Actualizaciones", "settings-heading"))
        box.append(label("Repositorio público de GitHub", "form-label"))
        repo = Gtk.Entry(text=self.preferences.get("release_repo", self.release_repo),
                         placeholder_text="usuario/repositorio")
        box.append(repo)
        box.append(label("Ayuda", "settings-heading"))
        box.append(button("Copiar reporte de errores", lambda: (
            dialog.get_clipboard().set(errores.report()),
            self.status.set_text("Reporte copiado. Pegalo en la página de reportes de GitHub."))))
        box.append(button("Abrir página de reportes", lambda: Gio.AppInfo.launch_default_for_uri(errores.ISSUES_URL, None)))
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
                                "language": language.get_active_id() or "es",
                                **{key: control.get_active() for key, control in toggles.items()}}
                    motor.save(motor.ROOT / "settings.json", settings)
                    self.preferences = settings
                    self.apply_theme()
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
        self.library_count.set_text(("1 instancia" if count == 1 else f"{count} instancias")
                                    + (f" · {tiempo.short(played)} jugadas" if played else ""))
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

    def render_cards(self):
        for index, (folder, instance) in enumerate(self.visible_instances.items()):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            artwork = instance_art(instance, -1, 104)
            card.append(artwork)
            title = label(instance["name"], "card-label")
            title.set_ellipsize(Pango.EllipsizeMode.END)
            card.append(title)
            played = tiempo.of(self.library, folder.name)
            meta = f"{instance['version']} · {motor.LOADERS[instance['loader']]}"
            card.append(label(meta + (f" · {tiempo.short(played)}" if played else ""), "card-meta"))
            tile = button("", lambda selected=folder: self.select(selected), "card")
            tile.set_child(card)
            tile.update_property([Gtk.AccessibleProperty.LABEL], [instance["name"]])
            if folder == self.selected:
                tile.add_css_class("selected")
            enter(tile, index * 45)  # stagger: decorative, never blocks clicks
            self.cards.append(tile)
        create = button("", self.add_instance, "card-new")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER,
                          valign=Gtk.Align.CENTER)
        content.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        content.append(label("Nueva instancia"))
        create.set_child(content)
        create.update_property([Gtk.AccessibleProperty.LABEL], ["Nueva instancia"])
        enter(create, len(self.visible_instances) * 45)
        self.cards.append(create)

    def add_compact_instance(self, folder, instance):
        row = Gtk.Box(spacing=10)
        artwork = instance_art(instance, 48, 34)
        row.append(artwork)
        name = label(instance["name"], "compact-name")
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)
        row.append(label(f"{instance['version']} · {motor.LOADERS[instance['loader']]}", "muted"))
        arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic")
        row.append(arrow)
        tile = button("", lambda: self.select(folder), "compact-instance")
        tile.set_child(row)
        tile.update_property([Gtk.AccessibleProperty.LABEL], [instance["name"]])
        reveal = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
                             transition_duration=180)
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
                reveal.set_transition_duration(180)

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
            reveal.set_transition_duration(180)

    def render_details(self, details):
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
                             (f"{loader_name} {instance['loader_version']}".strip(), False),
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
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
        popover.set_child(menu)
        more.set_popover(popover)
        actions.append(more)
        content.append(actions)
        details.append(hero)
        enter(hero)
        tiles = Gtk.Box(spacing=12, homogeneous=True)
        for category, title in (("mod", "Mods"), ("shader", "Shaders"), ("resourcepack", "Texturas")):
            count = len(biblioteca.content_files(folder, category))
            tile = feature_button(title, "1 instalado" if count == 1 else f"{count} instalados",
                                  lambda kind=category: biblioteca.Browser(self, folder, instance, kind))
            tile.set_sensitive(not self.busy)
            tiles.append(tile)
        tile = feature_button("Tiempo jugado", tiempo.short(played), lambda: None)
        tile.add_css_class("stat")
        tile.set_can_target(False)
        tile.set_focusable(False)
        tiles.append(tile)
        details.append(tiles)
        if instance.get("notes"):
            note = label(instance["notes"], "muted")
            note.set_wrap(True)
            details.append(note)

        def add_action(title, action, style=None):
            def activate():
                popover.popdown()
                action()
            control = button(title, activate, style)
            control.set_sensitive(not self.busy)
            menu.append(control)

        favorite = folder.name in self.library.get("favorites", [])
        add_action("Quitar de favoritas" if favorite else "Marcar como favorita",
                   lambda: self.toggle_favorite(folder))
        alternate = button("Jugar con otra cuenta", lambda: (popover.popdown(), self.play_parallel(folder)))
        alternate.set_sensitive(not self.parallel and (not self.busy or
                                (self.running and self.running[0] == folder)))
        menu.append(alternate)
        add_action("Salud y mods", lambda: self.show_health(folder))
        add_action("Exportar perfil", lambda: self.export_profile(folder))
        add_action("Ver registro", lambda: self.open_log(folder))
        add_action("Abrir carpeta", lambda: motor.open_folder(folder))
        add_action("Contenido instalado", lambda: biblioteca.open_installed(self, folder))
        add_action("Duplicar instancia", lambda: self.copy_instance(folder, "duplicate"))
        if os.name != "nt" and not Path("/.flatpak-info").exists():  # a sandbox cannot export launchers
            add_action("Crear atajo en el menú", lambda: self.create_shortcut(folder, instance["name"]))
        add_action("Crear respaldo", lambda: self.copy_instance(folder, "backup"))
        add_action("Mundos", lambda: self.show_worlds(folder))
        add_action("Jugar sin conexión", lambda: self.play(offline=True))
        add_action("Reparar instalación", lambda: self.repair_instance(folder, instance))
        add_action("Java y memoria", lambda: self.show_java(folder, instance))
        add_action("Exportar instancia", lambda: self.export_instance(folder))
        if instance["loader"] in ("fabric", "quilt"):
            full_branding = instance["version"] == "1.21.11" and instance["loader"] == "fabric"
            title = "Pantalla de carga Nova" if full_branding else "Colores Nova en la carga"
            add_action(title, lambda: integraciones.run(
                self, self.window, "Colores de carga",
                lambda: integraciones.apply_colors(folder, instance),
                "Pantalla Nova preparada para el próximo inicio." if full_branding else
                "Colores aplicados. Se ven al iniciar Minecraft."
            ))
        menu.append(Gtk.Separator())
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
        if self.instance_rows:
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
        if os.name == "nt" and behavior == "close":
            behavior = "minimize"
        if self.preferences["console"] and behavior != "close":
            self.open_log(folder)
        self.busy = True
        self.failure_log.set_visible(False)
        self.launch_stage = "Preparando…"
        self.status.set_text("Preparando Minecraft…")
        self.refresh()

        minimized = False
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
            if minimized:
                self.window.unminimize()
                self.window.present()

        def show_stage(message):
            self.status.set_text(message)
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
                        diagnosis = consola.diagnose(consola.read_log(folder / "minecraft.log"))
                    except OSError:
                        diagnosis = ""
                    message = (f"Minecraft terminó con código {result}. "
                               f"{diagnosis or 'Abrí Ver registro para ver los detalles.'}")
            except Exception as exc:
                errores.record(exc, "nova.worker")
                failed = True
                message = f"Error al iniciar Minecraft: {exc}"
            GLib.idle_add(finish, message, failed)

        threading.Thread(target=worker, daemon=True).start()

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

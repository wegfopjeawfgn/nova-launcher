"""Nova Launcher desktop window for GTK 4."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

import actualizaciones
import biblioteca
import integraciones
import consola
import catalogo
import motor
import respaldos

HERE = Path(__file__).resolve().parent
RESOLUTIONS = ("854x480", "1280x720", "1600x900", "1920x1080", "2560x1440")


def resolution_field(value, automatic):
    combo = Gtk.ComboBoxText()
    combo.append("default", automatic)
    for size in RESOLUTIONS:
        combo.append(size, size.replace("x", " × "))
    combo.set_active_id(value if value in RESOLUTIONS else "default")
    return combo


@lru_cache(maxsize=24)
def cover_texture(path, width, height):
    pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), width, height, True)
    return Gdk.Texture.new_for_pixbuf(pixels)


def instance_art(instance, width=-1, height=145):
    frame = Gtk.Overlay(width_request=width, height_request=height)
    background = Gtk.Box(css_classes=[f"art{instance['artwork']}"])
    frame.set_child(background)
    picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER,
                          css_classes=["instance-cover"])
    frame.add_overlay(picture)
    cover = instance.get("cover", "")
    if re.fullmatch(r"[a-f0-9]{64}\.png", cover):
        path = motor.ROOT / "covers" / cover
        if path.is_file():
            try:
                picture.set_paintable(cover_texture(path, width * 2 if width > 0 else 768, height * 2))
            except GLib.Error:
                pass
    return frame


def label(value, style=None):
    widget = Gtk.Label(label=value, xalign=0)
    if style:
        widget.add_css_class(style)
    return widget


def button(value, action, style=None):
    widget = Gtk.Button(label=value)
    widget.connect("clicked", lambda _: action())
    if style:
        widget.add_css_class(style)
    return widget


def feature_button(title, detail, action):
    tile = button("", action, "feature")
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    content.append(label(title, "feature-title"))
    description = label(detail, "muted")
    description.set_wrap(True)
    content.append(description)
    tile.set_child(content)
    tile.update_property([Gtk.AccessibleProperty.LABEL], [title])
    return tile


class Nova(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.nova.launcher")
        self.window = None
        self.selected = None
        self.busy = False
        self.versions = []
        self.microsoft = None
        self.microsoft_active = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(HERE / "nova.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
        )
        self.window = Gtk.ApplicationWindow(application=self, title="Nova Launcher",
                                            default_width=1150, default_height=730)
        self.window.add_css_class("nova-main")
        self.window.set_icon_name("io.nova.launcher")
        self.window.connect("close-request", lambda _: self.busy)
        accounts = motor.read(motor.ROOT / "accounts.json", {"active": "", "profiles": []})
        self.preferences = {
            "memory": 4, "java": "", "resolution": "default", "console": False,
            "compact": False, "alphabetical": False, "launch_behavior": "keep",
            **motor.read(motor.ROOT / "settings.json", {}),
        }
        self.release_repo = actualizaciones.repository(
            motor.read(HERE / "canal.json", {}).get("repository", "")
        )
        self.checking_release = False
        self.profile = accounts["active"]
        self.profiles = accounts["profiles"]
        titlebar = Gtk.HeaderBar()
        titlebar.set_title_widget(Gtk.Label())
        identity = Gtk.Box(spacing=8)
        logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(HERE / "nova-logo.svg"), 24, 24, True)
        identity.append(Gtk.Image.new_from_pixbuf(logo))
        identity.append(label("Nova Launcher", "brand"))
        titlebar.pack_start(identity)
        self.accounts = Gtk.MenuButton()
        titlebar.pack_end(self.accounts)
        self.window.set_titlebar(titlebar)
        shell = Gtk.Box()
        self.window.set_child(shell)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        nav.add_css_class("sidebar")
        nav.append(label("BIBLIOTECA", "nav-caption"))
        nav.append(self.nav_button("Instancias", "view-grid-symbolic",
                                   lambda: scroll.get_vadjustment().set_value(0), active=True))
        nav.append(self.nav_button("Nueva instancia", "list-add-symbolic", self.add_instance))
        nav.append(label("MODRINTH", "nav-caption"))
        nav.append(self.nav_button("Explorar", "system-search-symbolic", self.browse))
        nav.append(self.nav_button("Modpacks", "package-x-generic-symbolic", self.browse_packs))
        nav.append(self.nav_button("Importar pack", "document-open-symbolic", self.import_pack))
        nav.append(self.nav_button("Skins", "applications-graphics-symbolic", self.open_skins))
        nav.append(self.nav_button("Respaldos", "document-open-symbolic", self.show_backups))
        nav.append(Gtk.Box(vexpand=True))
        self.release_button = button(f"Nova {actualizaciones.VERSION}", self.release_details)
        nav.append(self.release_button)
        nav.append(self.nav_button("Ajustes", "preferences-system-symbolic", self.global_settings))
        shell.append(nav)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        shell.append(scroll)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
        main.add_css_class("main")
        scroll.set_child(main)
        main.append(label("Mis instancias", "heading"))
        new = button("+   Nueva instancia", self.add_instance, "primary")
        new.set_halign(Gtk.Align.START)
        main.append(new)
        self.cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3,
                                 homogeneous=True, column_spacing=12, row_spacing=12)
        main.append(self.cards)
        self.compact = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        main.append(self.compact)
        self.instance_rows = {}
        self.expanded_folder = None
        self.library_layout = None
        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.details.add_css_class("details")
        main.append(self.details)
        self.status = label("Listo", "muted")
        self.status.set_wrap(True)
        main.append(self.status)
        self.update_accounts()
        self.refresh()
        self.window.present()
        self.versions = motor.read(motor.ROOT / "versions.json", [])
        threading.Thread(target=self.load_versions, daemon=True).start()
        if self.preferences.get("release_repo", self.release_repo):
            self.check_release()

    def show_backups(self):
        dialog = Gtk.Window(title="Respaldos", transient_for=self.window, modal=True,
                            default_width=540, default_height=350)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label("Respaldos de instancias", "subheading"))
        hint = label("Restaurar crea una instancia separada con los mundos, mods y ajustes del respaldo.", "muted")
        hint.set_wrap(True)
        content.append(hint)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        scroller.set_child(rows)
        content.append(scroller)
        paths = sorted((motor.ROOT / "backups").glob("*/backup.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths:
            info = motor.read(path, {})
            instance = motor.read(path.parent / "instance.json", {})
            if not instance.get("name"):
                continue
            when = info.get("created", "")[:16].replace("T", " ")
            rows.append(feature_button(instance["name"], f"{when} · Restaurar como instancia nueva",
                        lambda folder=path.parent: self.restore_backup(dialog, folder)))
        if rows.get_first_child() is None:
            rows.append(label("Todavía no tenés respaldos. Creá uno desde el panel de una instancia.", "muted"))
            rows.get_first_child().set_wrap(True)
        dialog.set_child(content)
        dialog.present()

    def restore_backup(self, dialog, folder):
        dialog.destroy()
        self.copy_instance(folder, "restore")

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

    def release_details(self):
        dialog = Gtk.Window(title="Versiones de Nova", transient_for=self.window, modal=True,
                            default_width=440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        box.append(label(f"Nova Launcher {actualizaciones.VERSION}", "subheading"))
        notice = label("Launcher de terceros para Minecraft Java Edition. Sin afiliación con Mojang o Microsoft.",
                       "muted")
        notice.set_wrap(True)
        box.append(notice)
        release = getattr(self, "available_release", None)
        if release:
            tag, rpm, page = release
            box.append(label(f"Nueva versión disponible · {tag}", "form-label"))
            if rpm:
                box.append(Gtk.LinkButton(uri=rpm, label="Descargar RPM para Fedora"))
            box.append(Gtk.LinkButton(uri=page, label="Ver cambios en GitHub"))
        box.append(button("Buscar actualizaciones", lambda: (dialog.destroy(), self.check_release(manual=True))))
        dialog.set_child(box)
        dialog.present()

    def check_release(self, manual=False):
        if self.checking_release:
            return
        repo = self.preferences.get("release_repo", self.release_repo)
        self.checking_release = True
        if manual:
            self.status.set_text("Consultando GitHub…")

        def finish(release, error):
            self.checking_release = False
            if repo != self.preferences.get("release_repo", self.release_repo):
                self.check_release(manual)
                return
            self.available_release = release
            self.release_button.set_label(f"Actualizar a {release[0]}" if release
                                          else f"Nova {actualizaciones.VERSION}")
            if release:
                self.release_button.add_css_class("primary")
                if manual:
                    self.status.set_text(f"Nueva versión de Nova · {release[0]}")
                    self.release_details()
            else:
                self.release_button.remove_css_class("primary")
                if manual:
                    self.status.set_text(error or "Ya tenés la última versión.")

        def worker():
            try:
                release = actualizaciones.check(repo)
            except Exception as error:
                GLib.idle_add(finish, None, str(error))
            else:
                GLib.idle_add(finish, release, None)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def nav_button(title, icon, action, active=False):
        control = button("", action, "nav-button")
        row = Gtk.Box(spacing=10)
        bundled = HERE / "icons" / f"{icon}.svg"
        icon_widget = Gtk.Image.new_from_file(str(bundled)) if bundled.is_file() else Gtk.Image.new_from_icon_name(icon)
        row.append(icon_widget)
        row.append(label(title))
        control.set_child(row)
        control.update_property([Gtk.AccessibleProperty.LABEL], [title])
        if active:
            control.add_css_class("nav-active")
        return control

    def browse_packs(self):
        if not self.busy:
            biblioteca.Browser(self, None, None, "modpack")

    def load_versions(self):
        try:
            entries = motor.versions()
        except (OSError, ValueError):
            return
        GLib.idle_add(setattr, self, "versions", entries)

    def update_accounts(self):
        name = self.microsoft[1]["name"] if self.microsoft_active else self.profile
        self.accounts.set_label(f"◈  {name or 'Cuentas'}")
        popover = Gtk.Popover()
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        options.add_css_class("menu")
        options.append(label("Cuentas", "subheading"))
        if name:
            options.append(button("Ver mi perfil", self.show_profile))
        for profile in self.profiles:
            style = "primary" if profile == self.profile and not self.microsoft_active else None
            options.append(button(f"{profile}    ·    Offline",
                                  lambda name=profile: self.select_profile(name), style))
        if self.microsoft:
            options.append(button(f"{self.microsoft[1]['name']}    ·    Microsoft", self.select_microsoft,
                                  "primary" if self.microsoft_active else None))
            options.append(button("Desconectar Microsoft", self.disconnect_microsoft))
        else:
            options.append(button("+  Conectar Microsoft", self.connect_microsoft))
        options.append(button("+  Agregar cuenta offline", self.edit_profile))
        popover.set_child(options)
        self.accounts.set_popover(popover)

    def show_profile(self):
        self.accounts.popdown()
        online = self.microsoft_active
        name = self.microsoft[1]["name"] if online else self.profile
        dialog = Gtk.Window(title="Mi perfil", transient_for=self.window, modal=True,
                            default_width=420)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        box.append(label(name, "subheading"))
        box.append(label("Microsoft · Sesión activa" if online else "Perfil offline · Guardado en este equipo",
                         "muted"))
        count = sum(1 for _ in (motor.ROOT / "skins" / name).glob("*.png"))
        box.append(label(f"{count} skins guardadas · {len(self.profiles)} perfiles offline"))
        box.append(button("Copiar nombre", lambda: dialog.get_clipboard().set(name)))
        box.append(button("Abrir mis skins", lambda: (dialog.destroy(), self.open_skins())))
        box.append(button("Cambiar de cuenta", lambda: (dialog.destroy(), self.accounts.popup())))
        dialog.set_child(box)
        dialog.present()

    def open_skins(self):
        from skins import Editor
        Editor(self)

    def connect_microsoft(self):
        import cuentas
        cuentas.connect(self)

    def use_microsoft(self, client_id, session):
        self.microsoft = (client_id, session)
        self.select_microsoft()
        self.status.set_text(f"Cuenta Microsoft conectada · {session['name']}")

    def select_microsoft(self):
        self.accounts.popdown()
        self.microsoft_active = True
        self.update_accounts()

    def disconnect_microsoft(self):
        self.accounts.popdown()
        self.microsoft = None
        self.microsoft_active = False
        self.update_accounts()

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

    def edit_profile(self, after_save=None):
        self.accounts.popdown()

        def submit(name, _):
            if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
                raise ValueError("Usá entre 3 y 16 letras, números o guiones bajos.")
            profiles = self.profiles if name in self.profiles else [*self.profiles, name]
            self.save_accounts(name, profiles)
            if after_save:
                GLib.idle_add(after_save)

        self.form("Cuenta offline", "Nombre de jugador", "", submit)

    def save_accounts(self, name, profiles):
        motor.save(motor.ROOT / "accounts.json", {"active": name, "profiles": profiles})
        self.profile = name
        self.microsoft_active = False
        self.profiles = profiles
        self.update_accounts()

    def select_profile(self, name):
        self.accounts.popdown()
        try:
            self.save_accounts(name, self.profiles)
        except OSError as exc:
            self.status.set_text(str(exc))

    def add_instance(self):
        chooser = Gtk.Window(title="Nueva instancia", transient_for=self.window,
                             modal=True, default_width=510, resizable=False)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label("Nueva instancia", "subheading"))
        content.append(label("Elegí cómo querés empezar", "muted"))

        def choose(action):
            chooser.destroy()
            action()

        for title, detail, action in (
            ("◇   Personalizada", "Elegí la versión de Minecraft y el cargador.",
             lambda: self.instance_form(None)),
            ("↓   Buscar un modpack", "Descargá un pack completo desde Modrinth.",
             self.browse_packs),
            ("＋   Importar un archivo", "Importá un .mrpack de Modrinth o un ZIP de CurseForge.",
             self.import_pack),
        ):
            content.append(feature_button(title, detail, lambda run=action: choose(run)))
        chooser.set_child(content)
        chooser.present()

    def edit_settings(self):
        if self.selected:
            self.instance_form(self.selected)

    def instance_form(self, folder):
        values = self.instances[folder] if folder else {
            **motor.DEFAULTS, "name": "", "memory": self.preferences["memory"],
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
                    settings = {"version": version, "loader": loader.get_active_id(),
                                "loader_version": build, "java": java_path, "cover": cover,
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
        dialog.present()

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
                            default_width=500)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        box.append(label("Minecraft", "subheading"))
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
        box.append(label("Al iniciar Minecraft", "subheading"))
        behavior = Gtk.ComboBoxText()
        behavior.append("keep", "Mantener Nova abierto")
        behavior.append("minimize", "Minimizar Nova hasta que se cierre Minecraft")
        behavior.append("close", "Cerrar Nova")
        if not behavior.set_active_id(self.preferences["launch_behavior"]):
            behavior.set_active_id("keep")
        box.append(behavior)
        hint = label("El registro de Minecraft se guarda aunque cierres Nova.", "muted")
        hint.set_wrap(True)
        box.append(hint)
        box.append(label("Biblioteca y diagnóstico", "subheading"))
        toggles = {}
        for key, title in (
            ("compact", "Usar lista compacta incluso con una o dos instancias"),
            ("alphabetical", "Ordenar instancias por nombre"),
            ("console", "Abrir la consola al iniciar Minecraft"),
        ):
            control = Gtk.CheckButton(label=title, active=self.preferences[key])
            toggles[key] = control
            box.append(control)
        box.append(label("Actualizaciones", "subheading"))
        box.append(label("Repositorio público de GitHub", "form-label"))
        repo = Gtk.Entry(text=self.preferences.get("release_repo", self.release_repo),
                         placeholder_text="usuario/repositorio")
        box.append(repo)
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
                                **{key: control.get_active() for key, control in toggles.items()}}
                    motor.save(motor.ROOT / "settings.json", settings)
                    self.preferences = settings
                    self.refresh()
                    self.check_release()
                except (OSError, ValueError) as exc:
                    error.set_text(str(exc))
                    return
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()

    def browse(self):
        if not self.busy:
            biblioteca.Browser(self, self.selected, self.instances.get(self.selected))

    def import_pack(self):
        if self.busy:
            return
        picker = Gtk.FileChooserNative(title="Importar modpack", transient_for=self.window,
                                       action=Gtk.FileChooserAction.OPEN)
        filters = Gtk.FileFilter(name="Modpacks de Modrinth y CurseForge")
        filters.add_suffix("mrpack")
        filters.add_suffix("zip")
        picker.add_filter(filters)

        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog.get_file().get_path()
                if path:
                    dialog.destroy()
                    if Path(path).suffix.lower() == ".zip" and not os.environ.get("CURSEFORGE_API_KEY"):
                        self.import_curseforge(path)
                    else:
                        self.import_local(path)
                    return
            dialog.destroy()

        picker.connect("response", selected)
        picker.show()

    def import_curseforge(self, path):
        dialog = Gtk.Dialog(title="Importar ZIP de CurseForge", transient_for=self.window,
                            modal=True, default_width=440)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Importar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(10)
        hint = label("Si el ZIP referencia archivos externos, ingresá tu clave de API de CurseForge. "
                     "Si ya incluye todo el contenido, dejá el campo vacío.", "muted")
        hint.set_wrap(True)
        box.append(hint)
        entry = Gtk.PasswordEntry(placeholder_text="Clave de API de CurseForge")
        box.append(entry)
        entry.connect("activate", lambda _: dialog.response(Gtk.ResponseType.OK))

        def respond(_, response):
            key = entry.get_text().strip()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.import_local(path, key)

        dialog.connect("response", respond)
        dialog.present()

    def import_local(self, path, api_key=""):
        if self.busy:
            return
        self.busy = True
        self.status.set_text("Importando modpack…")
        self.refresh()
        memory = self.preferences["memory"]

        def finish(folder, message):
            if folder:
                self.selected = folder
            self.finished(message)

        def worker():
            try:
                folder = catalogo.import_pack(path, memory, api_key)
            except Exception as exc:
                GLib.idle_add(finish, None, f"No se pudo importar: {exc}")
            else:
                GLib.idle_add(finish, folder, "Modpack importado.")

        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        self.instances = {
            config.parent: {**motor.DEFAULTS, **motor.read(config, {})}
            for config in sorted((motor.ROOT / "instances").glob("*/instance.json"))
        }
        if self.selected not in self.instances:
            self.selected = next(iter(self.instances), None)
        if self.preferences["alphabetical"]:
            self.instances = dict(sorted(self.instances.items(), key=lambda item: item[1]["name"].casefold()))
        compact = bool(self.instances) and (len(self.instances) > 2 or self.preferences["compact"])
        layout = (compact, tuple((folder, instance["name"], instance["version"], instance["loader"],
                                  instance["artwork"], instance.get("cover"))
                                 for folder, instance in self.instances.items()))
        if layout != self.library_layout:
            for container in (self.cards, self.compact):
                while child := container.get_first_child():
                    container.remove(child)
            self.instance_rows.clear()
            self.expanded_folder = None
            self.library_layout = layout
            self.cards.set_visible(not compact)
            self.details.set_visible(not compact)
            self.compact.set_visible(compact)
            if compact:
                for folder, instance in self.instances.items():
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
            for child, folder in zip(self.cards, self.instances):
                tile = child.get_child()
                if folder == self.selected:
                    tile.add_css_class("selected")
                else:
                    tile.remove_css_class("selected")
            self.render_details(self.details)

    def render_cards(self):
        for folder, instance in self.instances.items():
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            artwork = instance_art(instance)
            card.append(artwork)
            title = label("◇  " + instance["name"], "card-label")
            title.set_ellipsize(Pango.EllipsizeMode.END)
            card.append(title)
            card.append(label(f"{instance['version']} · {motor.LOADERS[instance['loader']]}", "card-meta"))
            tile = button("", lambda selected=folder: self.select(selected), "card")
            tile.set_child(card)
            if folder == self.selected:
                tile.add_css_class("selected")
            self.cards.append(tile)

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
            details.append(label("Creá una instancia para empezar.", "subheading"))
            details.append(label("Minecraft Java · Vanilla y loaders", "muted"))
            return
        instance = self.instances[self.selected]
        summary = Gtk.Box(spacing=16)
        artwork = instance_art(instance, 120, 104)
        summary.append(artwork)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        summary.append(info)
        row = Gtk.Box(spacing=10)
        name = label(instance["name"], "subheading")
        name.set_hexpand(True)
        row.append(name)
        play = button("▶   Jugar", self.play, "primary")
        play.set_sensitive(not self.busy)
        row.append(play)
        info.append(row)
        info.append(label("Minecraft Java", "muted"))
        info.append(label(
            f"{instance['version']}  ·  {motor.LOADERS[instance['loader']]} {instance['loader_version']}"
            f"  ·  {instance['memory']} GB",
            "muted",
        ))
        details.append(summary)
        if instance.get("notes"):
            note = label(instance["notes"], "muted")
            note.set_wrap(True)
            details.append(note)
        folder = self.selected
        details.append(label("Contenido de la instancia", "feature-title"))
        shortcuts = Gtk.Box(spacing=10, homogeneous=True)
        for category, title in (
            ("mod", "◇  Mods"),
            ("shader", "✦  Shaders"),
            ("resourcepack", "▦  Texturas"),
        ):
            count = len(biblioteca.content_files(folder, category))
            detail = "1 instalado" if count == 1 else f"{count} instalados"
            shortcut = feature_button(title, detail, lambda kind=category: biblioteca.Browser(
                self, folder, instance, kind
            ))
            shortcut.set_sensitive(not self.busy)
            shortcuts.append(shortcut)
        details.append(shortcuts)
        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8,
                              row_spacing=8, max_children_per_line=5,
                              css_classes=["instance-actions"])
        actions.append(button("Abrir carpeta", lambda: subprocess.Popen(["xdg-open", str(folder)])))
        actions.append(button("Editar instancia", self.edit_settings))
        actions.append(button("Duplicar", lambda: self.copy_instance(folder, "duplicate")))
        actions.append(button("Crear respaldo", lambda: self.copy_instance(folder, "backup")))
        actions.append(button("Contenido instalado", lambda: biblioteca.open_installed(self, folder)))
        actions.append(button("Ver registro", lambda: self.open_log(folder)))
        remove = button("Eliminar instancia", lambda: self.remove_instance(folder, instance["name"]),
                        "danger")
        remove.set_sensitive(not self.busy)
        actions.append(remove)
        details.append(actions)
        if instance["loader"] in ("fabric", "quilt"):
            full_branding = instance["version"] == "1.21.11" and instance["loader"] == "fabric"
            title = "Pantalla de carga Nova" if full_branding else "Colores Nova en la carga"
            theme = button(title, lambda: integraciones.run(
                self, self.window, "Colores de carga",
                lambda: integraciones.apply_colors(folder, instance),
                "Pantalla Nova preparada para el próximo inicio." if full_branding else
                "Colores aplicados. Se ven al iniciar Minecraft."
            ))
            theme.set_sensitive(not self.busy)
            theme.set_halign(Gtk.Align.START)
            details.append(theme)

    def remove_instance(self, folder, name):
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
        if self.instance_rows:
            self.expand_instance(folder)
        else:
            self.refresh()

    def play(self):
        if self.busy:
            return
        if not self.profile and not self.microsoft_active:
            self.edit_profile(after_save=self.play)
            self.status.set_text("Elegí el nombre con el que querés jugar.")
            return
        folder = self.selected
        profile = self.profile
        microsoft = self.microsoft if self.microsoft_active else None
        instance = dict(self.instances[folder])
        instance["java"] = instance["java"] or self.preferences["java"]
        if instance.get("resolution", "default") == "default":
            instance["resolution"] = self.preferences["resolution"]
        behavior = self.preferences["launch_behavior"]
        if self.preferences["console"] and behavior != "close":
            self.open_log(folder)
        self.busy = True
        self.status.set_text("Preparando Minecraft…")
        self.refresh()

        minimized = False

        def started():
            nonlocal minimized
            if behavior == "close":
                self.quit()
            elif behavior == "minimize":
                self.window.minimize()
                minimized = True

        def finish(message):
            self.finished(message)
            if minimized:
                self.window.unminimize()
                self.window.present()

        def worker():
            def status(message):
                GLib.idle_add(self.status.set_text, message)
            try:
                session = None
                if microsoft:
                    import cuentas
                    session = cuentas.refresh(*microsoft)
                if session:
                    GLib.idle_add(self.store_session, microsoft, session)
                result = motor.launch(
                    folder, profile, instance, status, session=session,
                    on_started=(lambda: GLib.idle_add(started)) if behavior in {"close", "minimize"} else None,
                    detach=behavior == "close",
                )
                message = ("Minecraft cerrado." if result == 0 else
                           f"Minecraft terminó con código {result}. Consultá {folder / 'minecraft.log'}")
            except Exception as exc:
                message = f"Error al iniciar Minecraft: {exc}"
            GLib.idle_add(finish, message)

        threading.Thread(target=worker, daemon=True).start()

    def store_session(self, previous, session):
        if self.microsoft is previous:
            self.microsoft = (previous[0], session)

    def finished(self, message):
        self.busy = False
        self.status.set_text(message)
        self.refresh()


if __name__ == "__main__":
    sys.exit(Nova().run(sys.argv))

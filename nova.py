"""Nova Launcher desktop window for GTK 4."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
from tempfile import TemporaryDirectory
import time
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
import servidores

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
        self.parallel = False
        self.running = None
        self.second_session = None
        self.download_progress = "Sin descargas recientes."
        self.cancel_download = None
        self.download_view = None
        self.launch_stage = ""
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
        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        keys.add_shortcut(Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("<Control>f"),
            Gtk.CallbackAction.new(lambda *_: self.library_query.grab_focus()),
        ))
        self.window.add_controller(keys)
        self.window.connect("close-request", lambda _: self.busy or self.parallel)
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
        self.library = motor.read(motor.ROOT / "library.json", {})
        last = self.library.get("selected")
        if isinstance(last, str) and Path(last).name == last:
            self.selected = motor.ROOT / "instances" / last
        self.profile = accounts["active"]
        self.profiles = accounts["profiles"]
        titlebar = Gtk.HeaderBar(decoration_layout=":minimize,maximize,close")
        titlebar.add_css_class("nova-titlebar")
        titlebar.set_title_widget(Gtk.Label())
        identity = Gtk.Box(spacing=8)
        logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(HERE / "nova-logo.svg"), 24, 24, True)
        identity.append(Gtk.Image.new_from_pixbuf(logo))
        identity.append(label("Nova Launcher", "brand"))
        titlebar.pack_start(identity)
        self.accounts = Gtk.MenuButton(css_classes=["account-switcher"])
        titlebar.pack_end(self.accounts)
        self.window.set_titlebar(titlebar)
        shell = Gtk.Box()
        self.window.set_child(shell)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["sidebar"])
        nav_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        propagate_natural_width=True)
        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        nav_scroll.set_child(nav)
        sidebar.append(nav_scroll)
        nav.append(label("BIBLIOTECA", "nav-caption"))
        nav.append(self.nav_button("Instancias", "view-grid-symbolic",
                                   lambda: scroll.get_vadjustment().set_value(0), active=True))
        nav.append(self.nav_button("Nueva instancia", "list-add-symbolic", self.add_instance))
        nav.append(label("DESCUBRIR", "nav-caption"))
        nav.append(self.nav_button("Explorar", "system-search-symbolic", self.browse))
        nav.append(self.nav_button("Modpacks", "package-x-generic-symbolic", self.browse_packs))
        nav.append(self.nav_button("Importar pack", "document-open-symbolic",
                                   lambda: self.add_instance(import_only=True)))
        nav.append(label("HERRAMIENTAS", "nav-caption"))
        nav.append(self.nav_button("Skins", "applications-graphics-symbolic", self.open_skins))
        nav.append(self.nav_button("Servidores", "network-server-symbolic", self.open_servers))
        nav.append(self.nav_button("Respaldos", "document-open-symbolic", self.show_backups))
        nav.append(self.nav_button("Sesiones", "media-playback-start-symbolic", self.show_sessions))
        nav.append(self.nav_button("Descargas", "folder-download-symbolic", self.show_downloads))
        nav.append(self.nav_button("Almacenamiento", "drive-harddisk-symbolic", self.show_storage))
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["sidebar-footer"])
        footer.append(self.nav_button("Ajustes", "preferences-system-symbolic", self.global_settings))
        self.release_button = button(f"Nova {actualizaciones.VERSION}", self.release_details, "version-button")
        footer.append(self.release_button)
        sidebar.append(footer)
        shell.append(sidebar)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        shell.append(scroll)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
        main.add_css_class("main")
        scroll.set_child(main)
        library_header = Gtk.Box(spacing=16)
        title_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        title_group.append(label("Mis instancias", "heading"))
        self.library_count = label("", "muted")
        title_group.append(self.library_count)
        library_header.append(title_group)
        new = button("", self.add_instance, "primary")
        new.set_child(Gtk.Box(spacing=8))
        new.get_child().append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        new.get_child().append(label("Nueva instancia"))
        new.update_property([Gtk.AccessibleProperty.LABEL], ["Nueva instancia"])
        new.set_valign(Gtk.Align.CENTER)
        library_header.append(new)
        main.append(library_header)
        library_controls = Gtk.Box(spacing=8)
        self.library_query = Gtk.SearchEntry(hexpand=True, placeholder_text="Buscar instancias")
        self.library_filter = Gtk.ComboBoxText()
        for key, title in (("all", "Todas"), ("favorites", "Favoritas"), ("recent", "Jugadas recientemente")):
            self.library_filter.append(key, title)
        self.library_filter.set_active_id("all")
        library_controls.append(self.library_query)
        library_controls.append(self.library_filter)
        main.append(library_controls)
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
        self.status.add_css_class("status-line")
        status_row = Gtk.Box(spacing=8)
        self.status.set_hexpand(True)
        status_row.append(self.status)
        self.failure_log = button("Ver registro", lambda: consola.open_console(self.window, self.failed_log))
        self.failure_log.set_visible(False)
        status_row.append(self.failure_log)
        main.append(status_row)
        self.library_query.connect("search-changed", lambda _: self.refresh())
        self.library_filter.connect("changed", lambda _: self.refresh())
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
        box.append(label(f"Versión instalada · Nova {actualizaciones.VERSION}", "subheading"))
        notice = label("Launcher de terceros para Minecraft Java Edition. Sin afiliación con Mojang o Microsoft.",
                       "muted")
        notice.set_wrap(True)
        box.append(notice)
        release = getattr(self, "available_release", None)
        if release:
            tag, rpm, page, notes = release
            box.append(label(f"Nueva versión disponible · {tag}", "form-label"))
            if rpm:
                def save_update():
                    dialog.destroy()
                    self.save_file("Guardar actualización de Nova", rpm.rsplit("/", 1)[-1],
                                   lambda path: self.download_update(rpm, path, tag))

                box.append(button("Descargar instalador de Windows" if os.name == "nt" else
                                  "Descargar RPM para Fedora", save_update, "primary"))
            if notes:
                changelog = Gtk.TextView(editable=False, cursor_visible=False,
                                         wrap_mode=Gtk.WrapMode.WORD_CHAR)
                changelog.get_buffer().set_text(notes)
                scroll = Gtk.ScrolledWindow(min_content_height=120, max_content_height=220,
                                            propagate_natural_height=True)
                scroll.set_child(changelog)
                box.append(scroll)
            box.append(Gtk.LinkButton(uri=page, label="Ver cambios en GitHub"))
        box.append(button("Buscar actualizaciones", lambda: (dialog.destroy(), self.check_release(manual=True))))
        dialog.set_child(box)
        dialog.present()

    def download_update(self, url, path, tag):
        if self.busy or self.cancel_download:
            return
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
        self.set_download_progress("Descargando actualización…")
        self.refresh()

        def progress(message):
            if cancel.is_set():
                raise InterruptedError("Descarga cancelada.")
            GLib.idle_add(self.set_download_progress, message)

        def finish(error):
            self.cancel_download = None
            message = error or "Actualización lista para instalar."
            self.set_download_progress(message)
            self.finished(message)
            if not error:
                self.update_ready(path, tag)

        def worker():
            try:
                actualizaciones.download(url, path, progress=progress)
            except Exception as error:
                GLib.idle_add(finish, f"No se descargó la actualización: {error}")
            else:
                GLib.idle_add(finish, None)

        threading.Thread(target=worker, daemon=True).start()

    def update_ready(self, path, tag):
        dialog = Gtk.Window(title="Actualización de Nova", transient_for=self.window, modal=True,
                            default_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label(f"{tag} · Lista para instalar", "subheading"))
        box.append(label(f"Versión instalada · {actualizaciones.VERSION}", "muted"))
        box.append(label("Ejecutá el instalador y volvé a abrir Nova." if os.name == "nt" else
                         "Instalá el RPM y volvé a abrir Nova.", "muted"))
        box.append(button("Abrir carpeta", lambda: motor.open_folder(path.parent)))

        def copy_command():
            dialog.get_clipboard().set(f"sudo dnf install {shlex.quote(str(path.absolute()))}")
            copy.set_label("Comando copiado")

        if os.name != "nt":
            copy = button("Copiar comando de instalación", copy_command, "primary")
            box.append(copy)
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
        icon_widget.set_pixel_size(16)
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
        account = Gtk.Box(spacing=8)
        account.append(Gtk.Image.new_from_icon_name("avatar-default-symbolic"))
        account.append(label(name or "Cuentas"))
        account.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self.accounts.set_child(account)
        self.accounts.update_property([Gtk.AccessibleProperty.LABEL],
                                      [f"Cuentas · {name}" if name else "Cuentas"])
        popover = Gtk.Popover()
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        options.add_css_class("menu")
        options.append(label("Cuentas", "subheading"))
        if name:
            options.append(button("Ver mi perfil", self.show_profile))
        if self.profiles:
            profiles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        max_content_height=230, propagate_natural_height=True,
                                        propagate_natural_width=True)
            scroll.set_child(profiles)
            options.append(scroll)
            for profile in self.profiles:
                style = "primary" if profile == self.profile and not self.microsoft_active else None
                row = Gtk.Box(spacing=6)
                select = button(f"{profile} · Offline", lambda name=profile: self.select_profile(name), style)
                select.set_hexpand(True)
                row.append(select)
                remove = button("Quitar", lambda name=profile: self.confirm_remove_profile(name), "quiet-button")
                remove.update_property([Gtk.AccessibleProperty.LABEL], [f"Quitar perfil {profile}"])
                row.append(remove)
                profiles.append(row)
        if self.microsoft:
            options.append(button(f"{self.microsoft[1]['name']}    ·    Microsoft", self.select_microsoft,
                                  "primary" if self.microsoft_active else None))
            options.append(button("Quitar cuenta Microsoft", self.disconnect_microsoft, "quiet-button"))
        else:
            options.append(button("+  Conectar Microsoft", self.connect_microsoft))
        options.append(button("+  Agregar cuenta offline", self.edit_profile))
        popover.set_child(options)
        self.accounts.set_popover(popover)

    def confirm_remove_profile(self, profile):
        self.accounts.popdown()
        dialog = Gtk.Dialog(title="Quitar perfil offline", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Quitar perfil", Gtk.ResponseType.OK).add_css_class("danger")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.add_css_class("menu")
        message = label(f"¿Querés quitar «{profile}» de la lista de cuentas de Nova?")
        message.set_wrap(True)
        box.append(message)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                try:
                    remaining = [name for name in self.profiles if name != profile]
                    active = self.profile if self.profile in remaining else next(iter(remaining), "")
                    motor.save(motor.ROOT / "accounts.json", {"active": active, "profiles": remaining})
                except OSError as error:
                    message.set_text(f"No se pudo quitar el perfil: {error}")
                    return
                self.profiles = remaining
                self.profile = active
                self.update_accounts()
                self.status.set_text(f"Perfil offline «{profile}» quitado.")
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()

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
                     self.choose_prism),)
        for name, detail, action in options[2:4] if import_only else options:
            content.append(feature_button(name, detail, lambda run=action: choose(run)))
        chooser.set_child(content)
        chooser.present()

    def choose_prism(self):
        if self.busy:
            return
        picker = Gtk.FileChooserNative(title="Elegir carpeta de la instancia de Prism",
                                       transient_for=self.window,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)

        def selected(_, response):
            file = picker.get_file() if response == Gtk.ResponseType.ACCEPT else None
            path = file.get_path() if file else None
            picker.destroy()
            if not path:
                return
            source = Path(path)
            try:
                name, version, loader, _, game = respaldos.prism_details(source)
                worlds = sum(1 for _ in (game / "saves").glob("*/level.dat"))
            except (OSError, KeyError, TypeError, ValueError) as error:
                self.status.set_text(f"No se pudo leer la instancia de Prism: {error}")
                return
            dialog = Gtk.Dialog(title="Revisar instancia de Prism", transient_for=self.window, modal=True)
            dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
            dialog.add_button("Importar", Gtk.ResponseType.OK).add_css_class("primary")
            box = dialog.get_content_area()
            box.add_css_class("menu")
            box.append(label(name, "subheading"))
            box.append(label(f"Minecraft {version} · {motor.LOADERS[loader]} · {worlds} mundos", "muted"))

            def confirm(_, response):
                dialog.destroy()
                if response != Gtk.ResponseType.OK:
                    return

                def task():
                    folder = respaldos.import_prism(source, self.preferences["memory"])
                    GLib.idle_add(setattr, self, "selected", folder)

                self.background_file("Copiando instancia de Prism…", task, "Instancia importada.")

            dialog.connect("response", confirm)
            dialog.present()

        picker.connect("response", selected)
        picker.show()

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
        for key, title in (
            ("compact", "Usar lista compacta incluso con una o dos instancias"),
            ("alphabetical", "Ordenar instancias por nombre"),
            ("console", "Abrir la consola al iniciar Minecraft"),
        ):
            control = Gtk.CheckButton(label=title, active=self.preferences[key])
            toggles[key] = control
            box.append(control)
        box.append(label("Actualizaciones", "settings-heading"))
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

    def import_pack(self, extension):
        if self.busy:
            return
        format_name = "Modrinth" if extension == "mrpack" else "Nova o CurseForge"
        picker = Gtk.FileChooserNative(title=f"Importar {format_name} (.{extension})",
                                       transient_for=self.window, action=Gtk.FileChooserAction.OPEN)
        file_filter = Gtk.FileFilter(name=f"{format_name} (*.{extension})")
        pattern = "".join(f"[{letter}{letter.upper()}]" for letter in extension)
        file_filter.add_pattern(f"*.{pattern}")
        picker.add_filter(file_filter)
        all_files = Gtk.FileFilter(name="Todos los archivos")
        all_files.add_pattern("*")
        picker.add_filter(all_files)
        picker.set_filter(file_filter)

        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog.get_file().get_path()
                if path:
                    dialog.destroy()
                    if Path(path).suffix.lower() != f".{extension}":
                        self.status.set_text(f"Elegí un archivo .{extension} para importar desde {format_name}.")
                    else:
                        self.preview_pack(path)
                    return
            dialog.destroy()

        picker.connect("response", selected)
        picker.show()

    def preview_pack(self, path):
        try:
            name, version, loader, needs_key = catalogo.pack_summary(path)
        except (OSError, ValueError, KeyError, TypeError, catalogo.zipfile.BadZipFile) as exc:
            self.status.set_text(f"No se pudo leer el modpack: {exc}")
            return
        dialog = Gtk.Dialog(title="Revisar modpack", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Continuar", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        title = label(name[:100], "subheading")
        title.set_wrap(True)
        box.append(title)
        box.append(label(f"Minecraft {version} · {loader}", "muted"))

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                if needs_key and not os.environ.get("CURSEFORGE_API_KEY"):
                    self.import_curseforge(path)
                else:
                    self.import_local(path)

        dialog.connect("response", respond)
        dialog.present()

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

    def import_local(self, path, api_key="", manual_dir=None):
        if self.busy:
            return
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
        self.set_download_progress("Importando modpack…")
        self.refresh()
        memory = self.preferences["memory"]

        def finish(folder, message, manual=False):
            self.cancel_download = None
            self.set_download_progress(message)
            if folder:
                self.selected = folder
            self.finished(message)
            if not folder and not cancel.is_set():
                dialog = Gtk.Dialog(title="Importación interrumpida", transient_for=self.window, modal=True)
                dialog.add_button("Cerrar", Gtk.ResponseType.CANCEL)
                dialog.add_button("Reintentar", Gtk.ResponseType.OK)
                if manual:
                    dialog.add_button("Elegir carpeta con archivos", Gtk.ResponseType.APPLY)
                box = dialog.get_content_area()
                box.add_css_class("menu")
                error = label(message, "form-error")
                error.set_wrap(True)
                error.set_max_width_chars(60)
                box.append(error)

                def respond(_, response):
                    dialog.destroy()
                    if response == Gtk.ResponseType.OK:
                        self.import_local(path, api_key, manual_dir)
                    elif response == Gtk.ResponseType.APPLY:
                        picker = Gtk.FileChooserNative(title="Elegir carpeta con los archivos de CurseForge",
                                                       transient_for=self.window,
                                                       action=Gtk.FileChooserAction.SELECT_FOLDER)

                        def selected(_, response):
                            file = picker.get_file() if response == Gtk.ResponseType.ACCEPT else None
                            directory = file.get_path() if file else None
                            picker.destroy()
                            if directory:
                                self.import_local(path, api_key, Path(directory))

                        picker.connect("response", selected)
                        picker.show()

                dialog.connect("response", respond)
                dialog.present()

        def progress(message):
            if cancel.is_set():
                raise InterruptedError("Importación cancelada.")
            GLib.idle_add(self.set_download_progress, message)

        def worker():
            try:
                folder = catalogo.import_pack(path, memory, api_key, manual_dir=manual_dir, progress=progress)
            except InterruptedError:
                GLib.idle_add(finish, None, "Importación cancelada. Los archivos verificados se conservaron.")
            except Exception as exc:
                GLib.idle_add(finish, None, f"No se pudo importar: {exc}",
                              isinstance(exc, catalogo.ManualPackFile))
            else:
                GLib.idle_add(finish, folder, "Modpack importado.")

        threading.Thread(target=worker, daemon=True).start()

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
        self.library_count.set_text("1 instancia" if count == 1 else f"{count} instancias")
        if self.selected not in visible:
            self.selected = next((folder for folder in visible
                                  if folder.name == self.library.get("selected")), next(iter(visible), None))
        compact = bool(self.visible_instances) and (len(self.visible_instances) > 2 or self.preferences["compact"])
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
        for folder, instance in self.visible_instances.items():
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            artwork = instance_art(instance)
            card.append(artwork)
            title = label(instance["name"], "card-label")
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
        summary = Gtk.Box(spacing=16)
        artwork = instance_art(instance, 120, 104)
        summary.append(artwork)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        summary.append(info)
        row = Gtk.Box(spacing=10)
        name = label(instance["name"], "subheading")
        name.set_hexpand(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_tooltip_text(instance["name"])
        row.append(name)
        play = button("", self.play, "primary")
        play_content = Gtk.Box(spacing=8)
        play_content.append(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        self.play_label = label(self.launch_stage or "Jugar")
        play_content.append(self.play_label)
        play.set_child(play_content)
        play.update_property([Gtk.AccessibleProperty.LABEL], ["Jugar"])
        play.set_sensitive(not self.busy and not self.parallel)
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
            ("mod", "Mods"),
            ("shader", "Shaders"),
            ("resourcepack", "Texturas"),
        ):
            count = len(biblioteca.content_files(folder, category))
            detail = "1 instalado" if count == 1 else f"{count} instalados"
            shortcut = feature_button(title, detail, lambda kind=category: biblioteca.Browser(
                self, folder, instance, kind
            ))
            shortcut.set_sensitive(not self.busy)
            shortcuts.append(shortcut)
        details.append(shortcuts)
        actions = Gtk.Box(spacing=8, css_classes=["instance-toolbar"])
        actions.append(button("Editar instancia", self.edit_settings))
        actions.append(button("Ver registro", lambda: self.open_log(folder)))
        actions.append(button("Servidores", lambda: self.open_servers(folder)))
        more = Gtk.MenuButton(label="Más acciones")
        popover = Gtk.Popover()
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
        popover.set_child(menu)
        more.set_popover(popover)
        actions.append(more)
        details.append(actions)

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
        add_action("Abrir carpeta", lambda: motor.open_folder(folder))
        add_action("Contenido instalado", lambda: biblioteca.open_installed(self, folder))
        add_action("Duplicar instancia", lambda: self.copy_instance(folder, "duplicate"))
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
                GLib.idle_add(self.finished, f"No se pudo completar: {exc}")
            else:
                GLib.idle_add(saved)

        threading.Thread(target=worker, daemon=True).start()

    def export_instance(self, folder):
        dialog = Gtk.Dialog(title="Exportar instancia", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar archivo", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        format_choice = Gtk.ComboBoxText()
        format_choice.append("zip", "ZIP · Configuración y mundos opcionales")
        format_choice.append("mrpack", "Modrinth (.mrpack) · Con referencias de descarga")
        format_choice.set_active_id("zip")
        box.append(format_choice)
        info = label("El .mrpack incluye referencias para los archivos activos que coinciden "
                     "con Modrinth. Los archivos sin coincidencia se omiten.", "muted")
        info.set_wrap(True)
        info.set_max_width_chars(48)
        box.append(info)
        worlds = Gtk.CheckButton(label="Incluir mis mundos")
        box.append(worlds)

        def respond(_, response):
            extension = format_choice.get_active_id()
            include_worlds = worlds.get_active()
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                self.save_file("Exportar instancia", f"instancia-nova.{extension}", lambda path:
                               self.background_file("Exportando instancia…",
                                   lambda: respaldos.export_instance(folder, path, include_worlds),
                                   f"Instancia exportada en {path}."))

        dialog.connect("response", respond)
        dialog.present()

    def show_java(self, folder, instance):
        dialog = Gtk.Window(title="Java y memoria", transient_for=self.window, modal=True, default_width=500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Java y memoria", "subheading"))
        box.append(label(f"RAM asignada · {instance['memory']} GB", "form-label"))
        status = label("Comprobando Java…", "muted")
        status.set_wrap(True)
        status.set_selectable(True)
        box.append(status)

        def reset():
            try:
                with motor.instance_lock(folder):
                    settings = motor.read(folder / "instance.json", {})
                    settings.update(java="", memory=self.preferences["memory"])
                    motor.save(folder / "instance.json", settings)
            except (OSError, RuntimeError) as error:
                status.set_text(str(error))
                return
            dialog.destroy()
            self.refresh()
            self.status.set_text("La instancia usa el Java y la memoria predeterminados de Nova.")

        box.append(button("Usar valores predeterminados de Nova", reset))
        dialog.set_child(box)
        dialog.present()
        settings = {**instance, "java": instance["java"] or self.preferences["java"]}

        def worker():
            try:
                executable, required, found = motor.java_report(settings)
                lines = [executable]
                if required:
                    lines.append(f"Minecraft requiere Java {required}.")
                if found:
                    lines.append(f"Java detectado · {found}")
                if found and required and found < required:
                    lines.append("Este Java es demasiado antiguo para la instancia.")
            except Exception as error:
                lines = [f"No se pudo comprobar Java: {error}"]
            GLib.idle_add(status.set_text, "\n".join(lines))

        threading.Thread(target=worker, daemon=True).start()

    def repair_instance(self, folder, instance):
        settings = {**instance, "java": instance["java"] or self.preferences["java"]}

        def task():
            with motor.instance_lock(folder):
                motor.prepare(settings, lambda message: GLib.idle_add(self.status.set_text, message), repair=True)

        self.background_file("Verificando la instalación…", task, "Instalación revisada.")

    def show_worlds(self, folder):
        dialog = Gtk.Window(title="Mundos", transient_for=self.window, modal=True,
                            default_width=520, default_height=400)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label(f"Mundos de {self.instances[folder]['name']}", "subheading"))
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.set_child(rows)
        box.append(scroll)
        status = label("", "muted")
        status.set_wrap(True)
        box.append(status)

        def render():
            while child := rows.get_first_child():
                rows.remove(child)
            for backup in (False, True):
                paths = respaldos.worlds(folder, backups=backup)
                if not paths:
                    continue
                rows.append(label("Respaldos" if backup else "Mundos guardados", "form-label"))
                for path in paths:
                    row = Gtk.Box(spacing=8, css_classes=["catalog-row"])
                    title = label(path.name)
                    title.set_ellipsize(Pango.EllipsizeMode.END)
                    title.set_hexpand(True)
                    row.append(title)
                    row.append(button("Restaurar copia" if backup else "Respaldar",
                                      lambda path=path, restore=backup: copy_world(path, restore)))
                    rows.append(row)
            if not rows.get_first_child():
                rows.append(label("Todavía no hay mundos guardados.", "muted"))

        def copy_world(path, restore):
            rows.set_sensitive(False)
            status.set_text("Copiando mundo…")

            def finish(message):
                status.set_text(message)
                render()
                rows.set_sensitive(True)

            def worker():
                try:
                    target = respaldos.copy_world(folder, path, restore=restore)
                except (OSError, ValueError, RuntimeError) as error:
                    GLib.idle_add(finish, f"No se pudo copiar el mundo: {error}")
                else:
                    GLib.idle_add(finish, f"Copia guardada como «{target.name}».")

            threading.Thread(target=worker, daemon=True).start()

        render()
        dialog.set_child(box)
        dialog.present()

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

    def open_servers(self, folder=None):
        folder = folder or self.selected
        if folder is None:
            self.status.set_text("Elegí una instancia para ver sus servidores.")
            return
        if self.busy:
            return
        dialog = Gtk.Window(title="Servidores", transient_for=self.window, modal=True,
                            default_width=560, default_height=410)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label(self.instances[folder]["name"], "subheading"))
        box.append(label("Servidores de esta instancia", "muted"))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll.set_child(rows)
        box.append(scroll)
        address = Gtk.Entry(placeholder_text="ejemplo.net:25565", hexpand=True)
        address.update_property([Gtk.AccessibleProperty.LABEL], ["Dirección del servidor"])
        name = Gtk.Entry(placeholder_text="Nombre opcional", hexpand=True)
        name.update_property([Gtk.AccessibleProperty.LABEL], ["Nombre del servidor"])
        form = Gtk.Box(spacing=8)
        form.append(name)
        form.append(address)
        form.append(button("Guardar", lambda: add_server()))
        box.append(form)
        feedback = label("", "muted")
        feedback.set_wrap(True)
        box.append(feedback)
        path = folder / "nova-servers.json"
        preferences_path = folder / "server-preferences.json"
        editing = None

        def join(target):
            try:
                servidores.address_parts(target)
            except ValueError as error:
                feedback.set_text(str(error))
                return
            dialog.destroy()
            self.select(folder)
            self.play(target)

        def populate():
            while child := rows.get_first_child():
                rows.remove(child)
            try:
                saved = servidores.saved_servers(folder / "game" / "servers.dat")
            except (OSError, ValueError, EOFError) as error:
                saved = []
                feedback.set_text(f"No se pudo leer la lista de Minecraft: {error}")
            extra = motor.read(path, {})
            preferences = motor.read(preferences_path, {})
            hidden = set(preferences.get("hidden", []))
            favorites = set(preferences.get("favorites", []))
            servers = {target.casefold(): (title, target) for title, target in saved}
            servers.update({target.casefold(): (title, target) for target, title in extra.items()})
            for title, target in sorted(servers.values(),
                                        key=lambda entry: (entry[1].casefold() not in favorites,
                                                           entry[0].casefold())):
                key = target.casefold()
                if key in hidden:
                    continue
                row = Gtk.Box(spacing=8, css_classes=["catalog-row"])
                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
                for value, style in ((title, "form-label"), (target, "muted")):
                    text = label(value, style)
                    text.set_ellipsize(Pango.EllipsizeMode.END)
                    info.append(text)
                row.append(info)
                menu = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text="Acciones del servidor")
                popover = Gtk.Popover()
                options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["action-menu"])
                popover.set_child(options)
                menu.set_popover(popover)
                options.append(button("Editar", lambda title=title, target=target, popover=popover:
                                      (popover.popdown(), edit_server(title, target))))
                options.append(button("Quitar de favoritos" if key in favorites else "Marcar como favorito",
                                      lambda key=key, popover=popover:
                                      (popover.popdown(), change_preference("favorites", key))))
                options.append(button("Quitar de Nova", lambda key=key, popover=popover:
                                      (popover.popdown(), change_preference("hidden", key))))
                row.append(menu)
                row.append(button("Entrar", lambda target=target: join(target), "primary"))
                rows.append(row)
            if not rows.get_first_child():
                rows.append(label("Agregá un servidor para entrar desde Nova.", "muted"))

        def edit_server(title, target):
            nonlocal editing
            editing = target.casefold()
            name.set_text(title)
            address.set_text(target)
            address.grab_focus()
            feedback.set_text("Editá los datos y presioná Guardar.")

        def change_preference(field, key):
            try:
                with motor.instance_lock(folder):
                    preferences = motor.read(preferences_path, {})
                    values = set(preferences.get(field, []))
                    values.symmetric_difference_update({key})
                    preferences[field] = sorted(values)
                    motor.save(preferences_path, preferences)
            except (OSError, RuntimeError) as error:
                feedback.set_text(str(error))
                return
            populate()

        def add_server():
            nonlocal editing
            target = address.get_text().strip()
            try:
                servidores.address_parts(target)
                with motor.instance_lock(folder):
                    extra = motor.read(path, {})
                    key = target.casefold()
                    extra = {address: title for address, title in extra.items()
                             if address.casefold() not in {key, editing}}
                    extra[target] = name.get_text().strip()[:80] or target
                    preferences = motor.read(preferences_path, {})
                    hidden = set(preferences.get("hidden", []))
                    hidden.discard(key)
                    if editing and editing != key:
                        hidden.add(editing)
                        favorites = set(preferences.get("favorites", []))
                        if editing in favorites:
                            favorites.remove(editing)
                            favorites.add(key)
                            preferences["favorites"] = sorted(favorites)
                    preferences["hidden"] = sorted(hidden)
                    motor.save(path, extra)
                    motor.save(preferences_path, preferences)
            except (OSError, ValueError, RuntimeError) as error:
                feedback.set_text(str(error))
                return
            editing = None
            address.set_text("")
            name.set_text("")
            feedback.set_text("Servidor guardado en Nova.")
            populate()

        address.connect("activate", lambda _: add_server())
        populate()
        dialog.set_child(box)
        dialog.present()

    def set_download_progress(self, message):
        self.download_progress = message
        self.status.set_text(message)
        if self.download_view:
            text, cancel = self.download_view
            text.set_text(message)
            cancel.set_sensitive(self.cancel_download is not None)

    def show_downloads(self):
        dialog = Gtk.Window(title="Descargas", transient_for=self.window, modal=False, default_width=440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Centro de descargas", "subheading"))
        text = label(self.download_progress, "muted")
        text.set_wrap(True)
        box.append(text)

        def cancel_current():
            if self.cancel_download:
                self.cancel_download.set()
                text.set_text("Cancelando al terminar el archivo actual…")
                control.set_sensitive(False)

        control = button("Cancelar descarga", cancel_current)
        control.set_sensitive(self.cancel_download is not None)
        box.append(control)
        self.download_view = text, control

        def closed(*_):
            if self.download_view and self.download_view[0] is text:
                self.download_view = None
            return False

        dialog.connect("close-request", closed)
        dialog.set_child(box)
        dialog.present()

    def show_storage(self):
        dialog = Gtk.Window(title="Almacenamiento", transient_for=self.window, modal=True, default_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Almacenamiento de Nova", "subheading"))
        usage = label("Calculando…", "muted")
        usage.set_wrap(True)
        box.append(usage)
        cache = motor.ROOT / "pack-cache"

        def calculate():
            lines = []
            for name, directory in (("Instancias", "instances"), ("Respaldos", "backups"),
                                    ("Minecraft y Java", "minecraft"), ("Caché de modpacks", "pack-cache")):
                total = 0
                for root, _, files in os.walk(motor.ROOT / directory, followlinks=False):
                    for name_in_dir in files:
                        path = Path(root) / name_in_dir
                        try:
                            if not path.is_symlink():
                                total += path.stat().st_size
                        except OSError:
                            continue
                lines.append(f"{name} · {total / 1024**2:,.1f} MiB")
            GLib.idle_add(usage.set_text, "\n".join(lines))

        def clear():
            dialog.destroy()

            def task():
                with motor.file_lock(motor.ROOT / ".pack-cache.lock", blocking=True):
                    if cache.exists():
                        Gio.File.new_for_path(str(cache)).trash(None)

            self.background_file("Moviendo caché a la Papelera…", task, "Caché de modpacks limpiada.")

        remove = button("Mover la caché de modpacks a la Papelera", clear, "danger")
        remove.set_sensitive(cache.is_dir() and not self.busy)
        box.append(remove)
        dialog.set_child(box)
        dialog.present()
        threading.Thread(target=calculate, daemon=True).start()

    def show_sessions(self):
        dialog = Gtk.Window(title="Sesiones de juego", transient_for=self.window, modal=True,
                            default_width=500)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        box.append(label("Sesiones de juego", "subheading"))
        sessions = []
        if self.running:
            folder, player, server = self.running
            sessions.append((folder, player, server, folder, "Sesión principal"))
        if self.second_session:
            folder, player, isolated = self.second_session
            sessions.append((folder, player, None, isolated, "Segunda sesión"))
        for folder, player, server, storage, title in sessions:
            box.append(label(f"{self.instances[folder]['name']} · {player}", "form-label"))
            box.append(label(f"{title} · {server or 'Sin servidor seleccionado'}", "muted"))
            actions = Gtk.Box(spacing=8)
            actions.append(button("Ver registro", lambda path=storage: self.open_log(path)))
            actions.append(button("Abrir mundos", lambda path=storage: motor.open_folder(path / "game")))
            box.append(actions)
        if not sessions:
            box.append(label("No hay sesiones activas abiertas desde esta ventana.", "muted"))
        dialog.set_child(box)
        dialog.present()

    def play_parallel(self, folder):
        if self.parallel or (self.busy and (not self.running or self.running[0] != folder)):
            return
        dialog = Gtk.Dialog(title="Jugar con otra cuenta", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        play = dialog.add_button("Jugar", Gtk.ResponseType.OK)
        play.add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        hint = label("La segunda cuenta offline usa los mods y ajustes de la instancia. "
                     "Sus mundos se guardan por separado.", "muted")
        hint.set_wrap(True)
        hint.set_max_width_chars(52)
        box.append(hint)
        profile = Gtk.ComboBoxText()
        active = {self.profile.casefold()}
        if self.running:
            active.add(self.running[1].casefold())
        if self.microsoft_active and self.microsoft:
            active.add(self.microsoft[1].get("name", "").casefold())
        for player in self.profiles:
            if player.casefold() not in active:
                profile.append_text(player)
        profile.set_active(0)
        play.set_sensitive(profile.get_active() >= 0)
        if profile.get_active() < 0:
            box.append(label("Creá otro perfil offline en el menú de cuentas.", "muted"))
        box.append(profile)

        def respond(_, response):
            player = profile.get_active_text()
            dialog.destroy()
            if response == Gtk.ResponseType.OK and player:
                self.start_parallel(folder, player)

        dialog.connect("response", respond)
        dialog.present()

    def start_parallel(self, folder, player):
        if (self.parallel or folder not in self.instances
                or not re.fullmatch(r"[A-Za-z0-9_]{3,16}", player)):
            return
        self.parallel = True
        self.failure_log.set_visible(False)
        self.status.set_text(f"Preparando la segunda sesión · {player}…")
        self.refresh()
        instance = dict(self.instances[folder])
        instance["java"] = instance["java"] or self.preferences["java"]
        if instance.get("resolution", "default") == "default":
            instance["resolution"] = self.preferences["resolution"]
        isolated = folder / "sessions" / player.casefold()
        log_path = isolated / "minecraft.log"
        self.second_session = folder, player, isolated

        def finish(message, failed):
            self.parallel = False
            self.second_session = None
            self.status.set_text(message)
            self.refresh()
            if failed:
                self.failure_log.set_visible(True)
                self.failed_log = log_path

        def worker():
            try:
                isolated.mkdir(parents=True, exist_ok=True)
                with motor.instance_lock(isolated) as lock, TemporaryDirectory(dir=isolated) as temporary:
                    game = isolated / "game"
                    game.mkdir(exist_ok=True)
                    source = folder / "game"
                    for name in ("mods", "config", "defaultconfigs", "resourcepacks", "shaderpacks",
                                 "scripts", "kubejs"):
                        item = source / name
                        staged = Path(temporary) / name
                        target = game / name
                        if item.is_dir() and not item.is_symlink():
                            shutil.copytree(item, staged, ignore=lambda directory, names: [
                                child for child in names if (Path(directory) / child).is_symlink()])
                        if target.is_dir() and not target.is_symlink():
                            shutil.rmtree(target)
                        else:
                            target.unlink(missing_ok=True)
                        if staged.exists():
                            staged.rename(target)
                    for name in ("options.txt", "servers.dat"):
                        item = source / name
                        target = game / name
                        if item.is_file() and not item.is_symlink() and not target.exists():
                            shutil.copy2(item, target)
                    result = motor.launch(folder, player, instance,
                                          lambda text: GLib.idle_add(self.status.set_text, text),
                                          game=game, log_path=log_path, held_lock=lock)
                message = f"Sesión de {player} cerrada" + (f" · código {result}" if result else ".")
                GLib.idle_add(finish, message, result != 0)
            except Exception as error:
                GLib.idle_add(finish, f"No se pudo abrir la segunda sesión: {error}", True)

        threading.Thread(target=worker, daemon=True).start()

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

        def started(player):
            nonlocal minimized
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
                failed = True
                message = f"Error al iniciar Minecraft: {exc}"
            GLib.idle_add(finish, message, failed)

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

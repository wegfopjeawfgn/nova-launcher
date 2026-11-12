"""Nova window: cuentas."""
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk

import motor
from widgets import label, button


class CuentasMixin:
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
        import credenciales
        credenciales.save_session(client_id, session)
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
        import credenciales
        credenciales.clear_session()
        self.update_accounts()

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

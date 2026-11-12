"""Nova window: servidores."""


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Pango

import motor
import servidores
from widgets import label, button


class ServidoresMixin:
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

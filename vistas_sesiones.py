"""Nova window: sesiones."""
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk

import errores
import motor
from widgets import label, button


class SesionesMixin:
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
                errores.record(error, "vistas_sesiones.worker")
                GLib.idle_add(finish, f"No se pudo abrir la segunda sesión: {error}", True)

        threading.Thread(target=worker, daemon=True).start()

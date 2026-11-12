"""Nova window: search and install mods through the official CurseForge API."""
from pathlib import Path
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gio, Gtk, Pango

import catalogo
import credenciales
import curseforge
import errores
import motor
import progreso
from widgets import label, button


class CurseForgeMixin:
    def show_curseforge(self):
        folder = self.selected
        instance = self.instances.get(folder) if folder else None
        page = Gtk.Window(title="CurseForge")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["menu"])
        content.append(label("Buscar en CurseForge", "subheading"))
        scope = (f"{instance['name']} · {instance['version']} · {motor.LOADERS[instance['loader']]}"
                 if instance else "Elegí una instancia para instalar mods.")
        content.append(label(scope, "muted"))
        note = label("Usa la API oficial de CurseForge con tu clave personal. Solo se pueden instalar desde Nova "
                     "los mods que permiten descargas de terceros; el resto se abre en la web. Las dependencias "
                     "no se instalan solas.", "opt-hint")
        note.set_wrap(True)
        content.append(note)
        key_row = Gtk.Box(spacing=8)
        key_entry = Gtk.PasswordEntry(placeholder_text="Clave de API de CurseForge", hexpand=True,
                                      show_peek_icon=True)
        key_entry.update_property([Gtk.AccessibleProperty.LABEL], ["Clave de API de CurseForge"])
        key_row.append(key_entry)
        key_row.append(button("Guardar clave", lambda: save_key()))
        key_row.append(button("Quitar", lambda: remove_key(), "quiet-button"))
        content.append(key_row)
        search_row = Gtk.Box(spacing=8)
        query = Gtk.SearchEntry(placeholder_text="Buscar mods", hexpand=True)
        search_row.append(query)
        search_row.append(button("Buscar", lambda: run_search()))
        content.append(search_row)
        feedback = label("", "muted")
        feedback.set_wrap(True)
        content.append(feedback)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller.set_child(rows)
        content.append(scroller)
        page.set_child(content)
        token = [0]

        def refresh_key_state():
            key_entry.set_visible(not credenciales.load_api_key())
            if credenciales.load_api_key():
                feedback.set_text("Clave guardada. Escribí qué mod buscar.")

        def save_key():
            value = key_entry.get_text().strip()
            if not curseforge.api_key_ok(value):
                feedback.set_text("La clave no tiene un formato válido.")
                return
            try:
                credenciales.save_api_key(value)
            except OSError as error:
                feedback.set_text(f"No se pudo guardar la clave: {error}")
                return
            key_entry.set_text("")
            refresh_key_state()

        def remove_key():
            credenciales.clear_api_key()
            key_entry.set_visible(True)
            feedback.set_text("La clave se quitó de esta computadora.")

        def render(mine, found, failure):
            if mine != token[0]:
                return
            while (child := rows.get_first_child()):
                rows.remove(child)
            if failure:
                feedback.set_text(failure)
                return
            feedback.set_text(f"{found['total']} resultado(s)." if found["results"] else "Sin resultados.")
            for item in found["results"]:
                rows.append(card(item))

        def card(item):
            row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
            title = label(item["name"], "form-label")
            title.set_ellipsize(Pango.EllipsizeMode.END)
            info.append(title)
            summary = label(item["summary"], "muted")
            summary.set_wrap(True)
            summary.set_lines(2)
            summary.set_ellipsize(Pango.EllipsizeMode.END)
            info.append(summary)
            info.append(label(f"{item['author']} · {item['downloads']:,} descargas".replace(",", "."), "opt-hint"))
            row.append(info)
            if item["url"]:
                row.append(button("Abrir en la web", lambda: Gio.AppInfo.launch_default_for_uri(item["url"], None),
                                  "quiet-button"))
            if instance:
                row.append(button("Instalar", lambda: install(item), "primary"))
            return row

        def run_search():
            key = credenciales.load_api_key()
            text = query.get_text().strip()
            if not key:
                feedback.set_text("Guardá tu clave de API para buscar.")
                return
            if not text:
                return
            token[0] += 1
            mine = token[0]
            feedback.set_text("Buscando…")

            def worker():
                try:
                    found = curseforge.search(key, text, game_version=instance["version"] if instance else None,
                                              loader=instance["loader"] if instance else None)
                except curseforge.CurseForgeError as error:
                    GLib.idle_add(render, mine, None, str(error))
                else:
                    GLib.idle_add(render, mine, found, None)

            threading.Thread(target=worker, daemon=True).start()

        def install(item):
            key = credenciales.load_api_key()
            if not key or not instance:
                return
            self.submit("curseforge", f"CurseForge · {item['name']}",
                        lambda entry: self.run_curseforge_install(entry, key, item, folder, instance),
                        lambda: install(item))
            feedback.set_text(f"«{item['name']}» se agregó a Descargas.")

        query.connect("activate", lambda _: run_search())
        refresh_key_state()
        self.show_page(page)

    def run_curseforge_install(self, entry, key, item, folder, instance):
        self.busy = True
        cancel = threading.Event()
        self.cancel_download = cancel
        self.set_download_progress(f"Preparando {item['name']}…")
        self.refresh()

        def progress(received, total, elapsed, resumed):
            if cancel.is_set():
                raise InterruptedError("Descarga cancelada.")
            GLib.idle_add(self.set_download_progress, f"Descargando {item['name']} · "
                          + progreso.describe(received, total, elapsed, resumed_from=resumed))

        def finish(error):
            self.cancel_download = None
            message = error or f"«{item['name']}» instalado."
            self.record(entry, error, cancel, message)
            self.set_download_progress(message)
            self.finished(message)

        def worker():
            try:
                file = curseforge.latest_file(key, item["id"], game_version=instance["version"],
                                              loader=instance["loader"])
                if not file:
                    raise ValueError("No hay un archivo compatible con esta instancia.")
                if not curseforge.safe_download(file):
                    raise ValueError("Este mod no permite descargas de terceros: abrilo en CurseForge.")
                name = file["file_name"]
                if name != Path(name).name or not name.lower().endswith(".jar"):
                    raise ValueError("El nombre del archivo no es válido.")
                destination = folder / "game" / "mods"
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / name
                if target.exists() or target.with_name(name + ".disabled").exists():
                    raise ValueError(f"Ya existe {name} en la instancia.")
                catalogo.fetch_file(file["download_url"], target, file["sha1"].lower(), algorithm="sha1",
                                    size=file["size"], progress=progress)
            except InterruptedError:
                GLib.idle_add(finish, "Descarga cancelada.")
            except (curseforge.CurseForgeError, OSError, ValueError, KeyError,
                    catalogo.requests.RequestException) as error:
                errores.record(error, "vistas_curseforge.worker")
                GLib.idle_add(finish, f"No se pudo instalar: {error}")
            else:
                GLib.idle_add(finish, None)

        threading.Thread(target=worker, daemon=True).start()

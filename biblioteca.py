"""GTK windows for browsing and installing Modrinth content."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
from pathlib import Path
import threading

import requests
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

import errores
import catalogo
import motor

TYPES = {"mod": "Mods", "modpack": "Modpacks", "shader": "Shaders",
         "resourcepack": "Paquetes de recursos"}


ARTWORK = ThreadPoolExecutor(max_workers=4)
MAX_ARTWORK_BYTES = 2_000_000


@lru_cache(maxsize=48)
def artwork_thumbnail(url):
    if not url.startswith("https://cdn.modrinth.com/"):
        return None
    with requests.get(url, timeout=5, stream=True,
                      headers={"User-Agent": motor.USER_AGENT}) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > MAX_ARTWORK_BYTES:
                return None
    loader = GdkPixbuf.PixbufLoader.new()

    def scale(pixbuf_loader, width, height):
        ratio = min(1, 144 / max(width, height))
        pixbuf_loader.set_size(max(1, round(width * ratio)), max(1, round(height * ratio)))

    loader.connect("size-prepared", scale)
    try:
        loader.write(bytes(data))
    finally:
        loader.close()
    return loader.get_pixbuf()


def artwork(item):
    frame = Gtk.Overlay(width_request=72, height_request=68, valign=Gtk.Align.CENTER)
    frame.add_css_class("catalog-art")
    placeholder = Gtk.Label(label="◇", css_classes=["feature-title"])
    frame.set_child(placeholder)
    picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER)
    frame.add_overlay(picture)
    url = item.get("featured_gallery") or item.get("icon_url")

    def show(thumbnail):
        if frame.get_root() is not None:
            try:
                picture.set_paintable(Gdk.Texture.new_for_pixbuf(thumbnail))
                placeholder.set_visible(False)
            except GLib.Error:
                pass

    def loaded(future):
        try:
            thumbnail = future.result()
        except (requests.RequestException, GLib.Error):
            return
        if thumbnail:
            GLib.idle_add(show, thumbnail)

    if url:
        ARTWORK.submit(artwork_thumbnail, url).add_done_callback(loaded)
    return frame


@lru_cache(maxsize=2048)
def content_hash(path, size, modified, changed):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha512").hexdigest()


def installed_projects(folder, category, project_ids):
    files = {path.name: path for path in content_files(folder, category)}
    projects = {}
    for project, entry in motor.read(folder / "downloads.json", {}).items():
        if entry["category"] != category:
            continue
        name = entry["file"]
        if files.pop(name, None):
            projects[project] = "Instalado"
        elif category == "mod" and files.pop(name + ".disabled", None):
            projects[project] = "Instalado · desactivado"
    if project_ids <= projects.keys():
        return projects
    hashes = {}
    for path in files.values():
        try:
            stat = path.stat()
            digest = content_hash(path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        except OSError:
            continue
        disabled = category == "mod" and path.name.lower().endswith(".disabled")
        hashes[digest] = hashes.get(digest, False) or not disabled
    try:
        for digest, version in catalogo.versions_by_hash(hashes).items():
            project = version["project_id"]
            state = "Instalado" if hashes[digest] else "Instalado · desactivado"
            if projects.get(project) != "Instalado":
                projects[project] = state
    except (requests.RequestException, ValueError):
        pass
    return projects


class Browser:
    def __init__(self, app, folder, instance, category=None):
        self.app = app
        self.folder = folder
        self.instance = instance
        self.fixed_category = category
        self.busy = False
        title = f"{TYPES[category]} en Modrinth" if category else "Explorar Modrinth"
        self.dialog = Gtk.Window(title=title, transient_for=app.window, modal=True,
                                 default_width=840, default_height=620)
        self.dialog.connect("close-request", lambda _: self.busy)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.add_css_class("menu")
        self.dialog.set_child(box)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["subheading"]))
        scope = (f"{instance['name']}  ·  {instance['version']}  ·  {motor.LOADERS[instance['loader']]}"
                 if instance else "Cada modpack crea una instancia con su versión y cargador.")
        box.append(Gtk.Label(label=scope, xalign=0, css_classes=["muted"]))
        self.controls = Gtk.Box(spacing=8)
        self.category = Gtk.ComboBoxText()
        for key, title in TYPES.items():
            self.category.append(key, title)
        self.category.set_active_id(category or (
            "mod" if instance and instance["loader"] != "vanilla" else "modpack"
        ))
        if category is None:
            self.category.connect("changed", lambda _: self.search())
            self.controls.append(self.category)
        self.query = Gtk.SearchEntry(hexpand=True, placeholder_text="Buscar en Modrinth")
        self.query.connect("activate", lambda _: self.search())
        self.controls.append(self.query)
        self.controls.append(self.button("Buscar", self.search))
        downloads = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        downloads.append(self.controls)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.set_child(self.results)
        downloads.append(scroll)
        footer = Gtk.Box(spacing=10, css_classes=["catalog-footer"])
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        footer.append(self.spinner)
        self.status = Gtk.Label(xalign=0, wrap=True, hexpand=True, css_classes=["muted"])
        footer.append(self.status)
        self.cancel = self.button("Cancelar descarga", self.cancel_install)
        self.cancel.set_visible(False)
        footer.append(self.cancel)
        downloads.append(footer)
        if folder and category in catalogo.DESTINATIONS:
            stack = Gtk.Stack(vexpand=True)
            switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.START)
            stack.add_titled(downloads, "downloads", "Descargar")
            installed, refresh = installed_view(app, folder, category)
            stack.add_titled(installed, "installed", "Instalados")
            def changed(*_):
                if stack.get_visible_child_name() == "installed":
                    refresh()
                else:
                    self.search(self.results_offset)

            stack.connect("notify::visible-child-name", changed)
            self.refresh_installed = refresh
            box.append(switcher)
            box.append(stack)
        else:
            self.refresh_installed = None
            box.append(downloads)
        self.results_offset = 0
        self.dialog.present()
        self.search()

    @staticmethod
    def button(title, action, primary=False):
        widget = Gtk.Button(label=title)
        widget.connect("clicked", lambda _: action())
        if primary:
            widget.add_css_class("primary")
        return widget

    def run(self, message, task, success, *, failure=None):
        if self.busy:
            return
        self.busy = True
        self.spinner.set_visible(True)
        self.spinner.start()
        self.controls.set_sensitive(False)
        self.results.set_sensitive(False)
        self.status.set_text(message)

        def finish(result, error):
            self.busy = False
            self.spinner.stop()
            self.spinner.set_visible(False)
            self.controls.set_sensitive(True)
            self.results.set_sensitive(True)
            if error:
                self.status.set_text(f"No se pudo completar: {error}")
                if failure:
                    failure(error)
            else:
                success(result)

        def worker():
            try:
                result = task()
            except Exception as error:
                errores.record(error, "biblioteca.worker")
                GLib.idle_add(finish, None, str(error))
            else:
                GLib.idle_add(finish, result, None)

        threading.Thread(target=worker, daemon=True).start()

    def clear(self):
        while child := self.results.get_first_child():
            self.results.remove(child)

    def search(self, offset=0):
        if self.busy:
            return
        self.results_offset = offset
        category = self.category.get_active_id()
        query = self.query.get_text().strip()
        self.clear()
        if category != "modpack" and not self.instance:
            self.status.set_text("Seleccioná una instancia para descargar este tipo de contenido.")
            return
        if category == "mod" and self.instance["loader"] == "vanilla":
            self.status.set_text("Elegí Fabric, Forge, NeoForge o Quilt en los ajustes de la instancia.")
            return
        if category == "shader":
            self.status.set_text("Para activar shaders necesitás un mod compatible, como Iris.")
        def task():
            page = catalogo.search(query, category, self.instance, offset)
            if category == "modpack":
                installed = {instance["modrinth_pack"]: "Instalado"
                             for instance in instances if instance.get("modrinth_pack")}
            else:
                installed = installed_projects(self.folder, category,
                                               {item["project_id"] for item in page["hits"]})
            return page, installed

        instances = list(self.app.instances.values())
        self.run("Buscando…", task,
                 lambda result: self.show_results(*result, category, offset))

    def show_results(self, page, installed, category, offset):
        self.status.set_text(f"{page['total_hits']} resultados")
        if category == "shader":
            self.status.set_text(f"{page['total_hits']} resultados · Activá los shaders desde un mod compatible.")
        if not page["hits"]:
            self.results.append(Gtk.Label(label="Probá con otro nombre o término de búsqueda.",
                                          xalign=0, css_classes=["muted"]))
        for item in page["hits"]:
            row = Gtk.Box(spacing=10, css_classes=["catalog-row"])
            row.append(artwork(item))
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
            text.append(Gtk.Label(label=item["title"], xalign=0, css_classes=["catalog-title"], wrap=True))
            text.append(Gtk.Label(label=item["description"], xalign=0, wrap=True, css_classes=["muted"]))
            row.append(text)
            actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, valign=Gtk.Align.CENTER)
            state = installed.get(item["project_id"])
            if state:
                actions.append(Gtk.Label(label=state, css_classes=["muted"]))
            elif category != "modpack":
                actions.append(self.button("↓ Instalar", lambda entry=item: self.pick(
                    entry, category, quick=True
                ), primary=True))
            if not state or category == "modpack":
                actions.append(self.button("Elegir versión" if category == "modpack" else "Versiones",
                                           lambda entry=item: self.pick(entry, category)))
            row.append(actions)
            self.results.append(row)
        navigation = Gtk.Box(spacing=8)
        if offset:
            navigation.append(self.button("Anterior", lambda: self.search(max(0, offset - 18))))
        if offset + 18 < page["total_hits"]:
            navigation.append(self.button("Siguiente", lambda: self.search(offset + 18)))
        self.results.append(navigation)

    def pick(self, item, category, quick=False):
        def show(versions):
            if not versions:
                self.status.set_text("No encontramos publicaciones compatibles.")
                return
            if quick:
                stable = next((version for version in versions if version["version_type"] == "release"), None)
                if stable:
                    self.install(category, stable)
                    return
            self.clear()
            self.results.append(Gtk.Label(label=item["title"], xalign=0, css_classes=["subheading"]))
            versions_box = Gtk.ComboBoxText()
            for version in versions:
                caption = f"{version['version_number']} · {', '.join(version['game_versions'][:4])}"
                if category == "modpack":
                    caption += f" · {', '.join(version['loaders'])}"
                versions_box.append(version["id"], caption)
            versions_box.set_active(0)
            by_id = {version["id"]: version for version in versions}
            self.results.append(versions_box)
            self.results.append(self.button("Instalar", lambda: self.install(
                category, by_id[versions_box.get_active_id()]
            ), primary=True))
            self.results.append(self.button("Volver a resultados", self.search))
            self.status.set_text("Elegí una publicación. Los modpacks se instalan en una instancia nueva."
                                 if category == "modpack" else
                                 "Elegí una publicación para la instancia seleccionada.")

        self.run("Buscando versiones…", lambda: catalogo.releases(
            item["project_id"], category, self.instance
        ), show)

    def cancel_install(self):
        if self.app.cancel_download:
            self.app.cancel_download.set()
            self.cancel.set_sensitive(False)

    def install(self, category, release):
        if self.busy or self.app.cancel_download:
            return
        cancel = threading.Event()
        self.app.cancel_download = cancel
        self.cancel.set_visible(True)
        self.cancel.set_sensitive(True)
        self.app.set_download_progress("Descargando contenido de Modrinth…")

        def status(message):
            self.status.set_text(message)
            self.app.set_download_progress(message)

        def progress(message):
            if cancel.is_set():
                raise InterruptedError("Descarga cancelada.")
            GLib.idle_add(status, message)

        def complete(message):
            self.app.cancel_download = None
            self.app.set_download_progress(message)
            self.cancel.set_visible(False)

        def task():
            if category == "modpack":
                return catalogo.install_pack(
                    release, self.app.preferences["memory"],
                    progress=progress,
                )
            catalogo.install_content(self.folder, self.instance, category, release, progress=progress)
            return None

        def finished(folder):
            complete("Contenido de Modrinth instalado.")
            if folder:
                self.app.selected = folder
            self.app.refresh()
            if self.refresh_installed:
                self.refresh_installed()
            if folder and self.fixed_category == "modpack":
                self.app.status.set_text("Instancia creada desde el modpack.")
                self.dialog.destroy()
            else:
                self.search(self.results_offset)

        def failed(error):
            complete(f"No se completó la descarga: {error}")
            self.results.append(self.button("Reintentar descarga", lambda: self.install(category, release)))

        self.run("Descargando y verificando archivos…", task, finished, failure=failed)


def content_files(folder, category):
    subfolder, suffix = catalogo.DESTINATIONS[category]
    directory = folder / "game" / subfolder
    if not directory.is_dir():
        return []
    return sorted(
        (file for file in directory.iterdir()
         if (file.is_file() and (file.suffix.lower() == suffix
                                or (category == "mod" and file.name.lower().endswith(".jar.disabled"))))
         or (category == "resourcepack" and (file / "pack.mcmeta").is_file())),
        key=lambda file: file.name.casefold(),
    )


def installed_view(app, folder, category=None):
    view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    query = Gtk.SearchEntry(placeholder_text="Buscar contenido instalado")
    view.append(query)
    scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=280, min_content_width=475)
    view.append(scroll)
    rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    scroll.set_child(rows)
    status = Gtk.Label(xalign=0, wrap=True, css_classes=["muted"])
    view.append(status)
    database = folder / "downloads.json"
    available = {}

    def refresh():
        while child := rows.get_first_child():
            rows.remove(child)
        entries = motor.read(database, {})
        tracked = {(entry["category"], entry["file"]): project for project, entry in entries.items()}
        for kind in (category,) if category else catalogo.DESTINATIONS:
            for file in content_files(folder, kind):
                disabled = kind == "mod" and file.name.endswith(".disabled")
                project = tracked.get((kind, file.name.removesuffix(".disabled") if disabled else file.name))
                title = entries[project]["name"] if project else file.name
                if query.get_text().strip().casefold() not in f"{title} {file.name}".casefold():
                    continue
                row = Gtk.Box(spacing=8, css_classes=["catalog-row"])
                description = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
                description.append(Gtk.Label(label=title, xalign=0, wrap=True, css_classes=["catalog-title"]))
                description.append(Gtk.Label(label=f"{TYPES[kind]} · {file.name}", xalign=0,
                                             wrap=True, css_classes=["muted"]))
                row.append(description)
                if kind == "mod":
                    row.append(Browser.button("Activar" if disabled else "Desactivar",
                                              lambda path=file: toggle(path)))
                if project and project in available and entries[project]["id"] != available[project]["id"]:
                    release = available[project]
                    row.append(Browser.button("Actualizar", lambda item=release: change(
                        lambda: catalogo.install_content(folder, app.instances[folder], "mod", item, update=True),
                        "Mod actualizado. Podés volver a la versión anterior."
                    ), primary=True))
                if project and entries[project].get("rollback"):
                    row.append(Browser.button("Volver a anterior", lambda key=project: change(
                        lambda: catalogo.restore_mod(folder, key), "Versión anterior restaurada."
                    )))
                if project:
                    row.append(Browser.button("Mover a la Papelera",
                                              lambda path=file, key=project: remove(path, key)))
                rows.append(row)
        if rows.get_first_child() is None:
            rows.append(Gtk.Label(label="Sin coincidencias." if query.get_text().strip() else "Todavía no hay contenido instalado.", xalign=0,
                                  css_classes=["catalog-row"]))

    def toggle(path):
        try:
            with motor.instance_lock(folder):
                target = path.with_suffix("") if path.name.endswith(".disabled") else path.with_name(path.name + ".disabled")
                if target.exists():
                    raise ValueError(f"Ya existe {target.name}.")
                path.rename(target)
        except (OSError, RuntimeError, ValueError) as error:
            status.set_text(str(error))
            return
        status.set_text("Estado del mod actualizado.")
        app.refresh()
        refresh()

    def remove(target, project):
        try:
            with motor.instance_lock(folder):
                entries = motor.read(database, {})
                Gio.File.new_for_path(str(target)).trash(None)
                entries.pop(project, None)
                motor.save(database, entries)
        except (GLib.Error, OSError, RuntimeError) as error:
            status.set_text(str(error))
            return
        status.set_text("Archivo movido a la Papelera.")
        app.refresh()
        refresh()

    def change(task, message):
        view.set_sensitive(False)
        status.set_text("Preparando cambio…")

        def finish(error):
            view.set_sensitive(True)
            status.set_text(f"No se pudo completar: {error}" if error else message)
            app.refresh()
            refresh()

        def worker():
            try:
                task()
            except Exception as error:
                errores.record(error, "biblioteca.worker")
                GLib.idle_add(finish, str(error))
            else:
                GLib.idle_add(finish, None)

        threading.Thread(target=worker, daemon=True).start()

    def check_updates():
        instance = app.instances[folder]
        entries = motor.read(database, {})
        installed_mods = {path.name.removesuffix(".disabled") for path in content_files(folder, "mod")}
        projects = {project: entry for project, entry in entries.items()
                    if entry["category"] == "mod" and entry["file"] in installed_mods}
        if not projects:
            status.set_text("Las actualizaciones se consultan para mods descargados desde Nova.")
            return
        updates.set_sensitive(False)
        status.set_text("Buscando actualizaciones compatibles…")

        def finished(message, matches):
            available.clear()
            available.update(matches)
            batch.set_sensitive(bool(matches))
            refresh()
            updates.set_sensitive(True)
            status.set_text(message)

        def worker():
            matches = {}
            try:
                names = []
                for project, entry in projects.items():
                    versions = catalogo.releases(project, "mod", instance)
                    latest = next((v for v in versions if v["version_type"] == "release"), None)
                    current = next((v for v in versions if v["id"] == entry["id"]), None)
                    if latest and current and latest["date_published"] > current["date_published"]:
                        matches[project] = latest
                        names.append(f"{entry['name']} ({latest['version_number']})")
                message = "Actualizaciones disponibles · " + ", ".join(names) if names else "Mods al día."
            except (requests.RequestException, ValueError, KeyError):
                message = "No se pudieron consultar las actualizaciones de Modrinth."
            GLib.idle_add(finished, message, matches)

        threading.Thread(target=worker, daemon=True).start()

    def check_dependencies():
        entries = motor.read(database, {})
        active_files = {path.name for path in content_files(folder, "mod")
                        if not path.name.endswith(".disabled")}
        tracked = {project: entry for project, entry in entries.items()
                   if entry["category"] == "mod" and entry["file"] in active_files}
        if not tracked:
            status.set_text("Agregá mods desde el catálogo para revisar sus dependencias.")
            return
        dependencies.set_sensitive(False)
        status.set_text("Revisando dependencias de Modrinth…")

        def report(message):
            dependencies.set_sensitive(True)
            status.set_text(message)

        def worker():
            missing = []
            try:
                detected = installed_projects(folder, "mod", set(tracked) | {""})
                for entry in tracked.values():
                    release = catalogo.api(f"/version/{entry['id']}")
                    for dependency in release["dependencies"]:
                        if dependency["dependency_type"] != "required":
                            continue
                        project, version = dependency.get("project_id"), dependency.get("version_id")
                        if project and detected.get(project) == "Instalado":
                            if not version or project not in tracked or tracked[project]["id"] == version:
                                continue
                        if project or version:
                            missing.append(f"{entry['name']} → {dependency.get('file_name') or project or version}")
            except (requests.RequestException, ValueError, KeyError) as error:
                message = f"No se pudieron revisar las dependencias: {error}"
            else:
                message = ("Dependencias por revisar · " + ", ".join(dict.fromkeys(missing))
                           if missing else "Las dependencias identificadas están instaladas.")
            GLib.idle_add(report, message)

        threading.Thread(target=worker, daemon=True).start()

    def review_batch():
        entries = motor.read(database, {})
        pending = [(entries[key]["name"], release) for key, release in available.items()
                   if key in entries and entries[key]["id"] != release["id"]]
        if not pending:
            return
        dialog = Gtk.Dialog(title="Revisar actualizaciones", transient_for=app.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Actualizar mods", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        scroll = Gtk.ScrolledWindow(max_content_height=260, propagate_natural_height=True)
        summary = Gtk.Label(label="\n".join(f"{name} → {release['version_number']}"
                                               for name, release in pending), xalign=0, wrap=True)
        scroll.set_child(summary)
        box.append(scroll)

        def apply():
            for count, (name, release) in enumerate(pending):
                try:
                    catalogo.install_content(folder, app.instances[folder], "mod", release, update=True)
                except Exception as error:
                    errores.record(error, "biblioteca.apply")
                    raise ValueError(f"Se actualizaron {count} mods. Falló {name}: {error}") from error

        def respond(_, response):
            dialog.destroy()
            if response == Gtk.ResponseType.OK:
                change(apply, f"{len(pending)} mods actualizados. Podés revertirlos individualmente.")

        dialog.connect("response", respond)
        dialog.present()

    if category in (None, "mod"):
        actions = Gtk.Box(spacing=8)
        updates = Browser.button("Buscar actualizaciones", check_updates)
        batch = Browser.button("Revisar y actualizar", review_batch)
        batch.set_sensitive(False)
        actions.append(updates)
        actions.append(batch)
        dependencies = Browser.button("Revisar dependencias", check_dependencies)
        actions.append(dependencies)
        view.insert_child_after(actions, query)
    query.connect("search-changed", lambda _: refresh())
    refresh()
    return view, refresh


def open_installed(app, folder):
    dialog = Gtk.Dialog(title="Contenido instalado", transient_for=app.window, modal=True)
    dialog.add_button("Cerrar", Gtk.ResponseType.CLOSE)
    dialog.connect("response", lambda widget, _: widget.destroy())
    view, _ = installed_view(app, folder)
    view.add_css_class("menu")
    dialog.get_content_area().append(view)
    dialog.present()

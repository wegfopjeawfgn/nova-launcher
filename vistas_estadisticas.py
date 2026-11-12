"""Nova window: local statistics (Nova Insights) and the news page."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gio, Gtk

import actualizaciones
import errores
import estadisticas
import tiempo
from progreso import size_text
from widgets import label, button


class EstadisticasMixin:
    def show_statistics(self):
        page = Gtk.Window(title="Estadísticas")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label("Estadísticas de juego", "subheading"))
        note = label(estadisticas.describe(), "muted")
        note.set_wrap(True)
        content.append(note)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller.set_child(body)
        content.append(scroller)
        page.set_child(content)

        def card(title, lines):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["job"])
            box.append(label(title, "job-title"))
            for line in lines:
                text = label(line, "muted")
                text.set_wrap(True)
                box.append(text)
            return box

        def render():
            while (child := body.get_first_child()):
                body.remove(child)
            names = {folder.name: data["name"] for folder, data in self.instances.items()}
            data = estadisticas.summary(names)
            launch = data["average_launch"]
            body.append(card("Resumen", [
                f"Sesiones: {data['sessions']} · Tiempo total: {tiempo.short(data['total_seconds'])}",
                "Arranque promedio: " + (f"{launch:.0f} s" if launch is not None else "sin datos"),
                f"Sesiones que terminaron con error: {data['failed']}"]))
            memory = estadisticas.system_memory_mb()
            if memory["total"]:
                free = f" · disponible {size_text(memory['available'] * 1024**2)}" if memory["available"] else ""
                body.append(card("Memoria del sistema", [f"Total {size_text(memory['total'] * 1024**2)}{free}"]))
            if data["per_instance"]:
                body.append(card("Por instancia", [
                    f"{item['name']}: {tiempo.short(item['seconds'])} en {item['sessions']} sesión(es)"
                    for item in data["per_instance"][:10]]))
            if data["recent"]:
                body.append(card("Últimas sesiones", [
                    f"{item['start'][:16].replace('T', ' ')} · {names.get(item['instance'], item['instance'])} · "
                    f"{tiempo.short(item['seconds'])}" + ("" if item["ok"] else " · con error")
                    for item in data["recent"]]))
            errors = estadisticas.recent_errors()
            if errors:
                body.append(card("Errores recientes de Nova", errors))

        def clear():
            def run():
                estadisticas.clear()
                self.status.set_text("Las estadísticas locales se borraron.")
                render()

            self.confirm("Borrar estadísticas", "Se borra el historial de sesiones guardado en esta computadora. "
                         "El tiempo jugado de cada instancia no cambia.", "Borrar", run, danger=True)

        content.append(button("Borrar estadísticas locales", clear, "quiet-button"))
        render()
        self.show_page(page)

    def show_news(self):
        page = Gtk.Window(title="Novedades")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu"])
        content.append(label("Novedades de Nova", "subheading"))
        status = label("Consultando GitHub…", "muted")
        content.append(status)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroller.set_child(body)
        content.append(scroller)
        page.set_child(content)
        repo = self.preferences.get("release_repo", self.release_repo)

        def render(releases, failure):
            if failure:
                status.set_text(failure)
                return
            status.set_text("" if releases else "Todavía no hay versiones publicadas.")
            for item in releases:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["job"])
                card.append(label(f"{item['name']}  ·  {item['date']}", "job-title"))
                text = label(item["body"] or "Sin notas.", "muted")
                text.set_wrap(True)
                text.set_selectable(True)
                card.append(text)
                card.append(button("Ver en GitHub", lambda url=item["url"]: Gio.AppInfo.launch_default_for_uri(url, None),
                                   "quiet-button"))
                body.append(card)

        def worker():
            try:
                releases = actualizaciones.recent_releases(repo)
            except (OSError, ValueError, KeyError, actualizaciones.requests.RequestException) as error:
                GLib.idle_add(render, [], f"No se pudieron consultar las novedades: {error}")
            else:
                GLib.idle_add(render, releases, None)

        threading.Thread(target=worker, daemon=True).start()
        self.show_page(page)

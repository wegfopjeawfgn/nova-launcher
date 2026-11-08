"""PNG skin editor with a rotatable block preview."""
from pathlib import Path
from tempfile import TemporaryDirectory
import re

import cairo
import gi

gi.require_foreign("cairo")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

import integraciones
import motor

SIZE = 64
CANVAS = 336
OVERLAYS = ((32, 0), (16, 32), (40, 32), (48, 48), (0, 32), (0, 48))
PART_NAMES = ("Cabeza", "Torso", "Brazo derecho", "Brazo izquierdo", "Pierna derecha", "Pierna izquierda")
FACE_NAMES = ("Frente", "Costado izquierdo", "Espalda", "Costado derecho", "Arriba", "Abajo")


def face(part, side, slim=False, overlay=False):
    u, v, w, h, d, _, _ = PARTS[part]
    if overlay:
        u, v = OVERLAYS[part]
    if slim and part in (2, 3):
        w = 3
    return ((u+d,v+d,w,h), (u+d+w,v+d,d,h), (u+2*d+w,v+d,w,h),
            (u,v+d,d,h), (u+d,v,w,d), (u+d+w,v,w,d))[side]
PARTS = (
    (0, 0, 8, 8, 8, -4, 0),
    (16, 16, 8, 12, 4, -4, 8),
    (40, 16, 4, 12, 4, -8, 8),
    (32, 48, 4, 12, 4, 4, 8),
    (0, 16, 4, 12, 4, -4, 20),
    (16, 48, 4, 12, 4, 0, 20),
)


class Editor:
    def __init__(self, app):
        self.pixels = bytearray(SIZE * SIZE * 4)
        self.angle = 0
        self.app = app
        self.history = []
        self.future = []
        self.last_pixel = None
        self.sampling = False
        self.current = None
        self.seed()
        self.profile = app.microsoft[1]["name"] if app.microsoft_active else app.profile or "Borrador"
        self.library = motor.ROOT / "skins"
        self.profile_settings = self.library / self.profile / "selection.json"
        selection = motor.read(self.profile_settings, {})
        self.window = Gtk.Window(title="Editor de skins", transient_for=app.window,
                                 default_width=800, default_height=640)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu", "skin-editor"])
        self.window.set_child(root)

        header = Gtk.Box(spacing=12)
        title = Gtk.Label(label=f"Skins · {self.profile}", xalign=0, hexpand=True, css_classes=["subheading"])
        header.append(title)
        modes = Gtk.Box(css_classes=["linked"])
        easy = Gtk.ToggleButton(label="Modo fácil")
        advanced = Gtk.ToggleButton(label="Modo avanzado", group=easy)
        modes.append(easy)
        modes.append(advanced)
        header.append(modes)
        root.append(header)
        self.hint = Gtk.Label(xalign=0, wrap=True, css_classes=["muted"])
        root.append(self.hint)

        commands = Gtk.Box(spacing=8, css_classes=["skin-toolbar"])
        commands.append(self.control("Importar PNG", lambda: self.choose(False), primary=True))
        commands.append(self.control("Exportar PNG", lambda: self.choose(True)))
        commands.append(self.control("Comunidad", lambda: self.open_community(None)))
        root.append(commands)

        workspace = Gtk.Box(spacing=12)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(workspace)
        root.append(scroll)
        self.drawing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["skin-panel"])
        workspace.append(self.drawing)
        selectors = Gtk.Box(spacing=6)
        self.part = Gtk.ComboBoxText()
        for name in (*PART_NAMES, "Mapa completo"):
            self.part.append_text(name)
        self.part.set_active(0)
        self.side = Gtk.ComboBoxText()
        for name in FACE_NAMES:
            self.side.append_text(name)
        self.side.set_active(0)
        selectors.append(self.part)
        selectors.append(self.side)
        self.drawing.append(selectors)
        self.layer = Gtk.ComboBoxText()
        self.layer.append("base", "Capa base")
        self.layer.append("overlay", "Capa exterior")
        self.layer.set_active_id("base")
        self.drawing.append(self.layer)

        tools = Gtk.Box(spacing=6)
        self.color = Gtk.ColorButton()
        self.color.set_title("Color del pincel")
        self.color.set_rgba(self.rgba("#bb94f5"))
        tools.append(self.color)
        self.erase = Gtk.ToggleButton(label="Borrador")
        tools.append(self.erase)
        self.eyedropper = Gtk.ToggleButton(label="Cuentagotas", group=self.erase)
        tools.append(self.eyedropper)
        self.drawing.append(tools)
        self.canvas = Gtk.DrawingArea(content_width=CANVAS, content_height=CANVAS,
                                      halign=Gtk.Align.CENTER, css_classes=["skin-canvas"])
        self.canvas.set_draw_func(self.draw_canvas)
        self.drawing.append(self.canvas)
        drag = Gtk.GestureDrag.new()
        drag.set_button(Gdk.BUTTON_PRIMARY)
        drag.connect("drag-begin", self.begin_stroke)
        drag.connect("drag-update", self.paint_drag)
        self.canvas.add_controller(drag)
        self.part.connect("changed", self.select_face)
        self.side.connect("changed", self.select_face)
        self.layer.connect("changed", self.select_face)
        history = Gtk.Box(spacing=6)
        self.undo_button = self.control("Deshacer", self.undo)
        self.redo_button = self.control("Rehacer", self.redo)
        history.append(self.undo_button)
        history.append(self.redo_button)
        self.drawing.append(history)

        preview_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True,
                                css_classes=["skin-panel", "skin-preview"])
        preview_panel.append(Gtk.Label(label="Vista previa", xalign=0, css_classes=["form-label"]))
        self.model = Gtk.ComboBoxText()
        self.model.append("classic", "Modelo clásico")
        self.model.append("slim", "Modelo delgado")
        if not self.model.set_active_id(selection.get("model", "classic")):
            self.model.set_active_id("classic")
        preview_panel.append(self.model)
        self.preview = Gtk.DrawingArea(content_width=230, content_height=240, hexpand=True, vexpand=True)
        self.preview.set_draw_func(self.draw_model)
        preview_panel.append(self.preview)
        preview_panel.append(self.control("Girar modelo", self.rotate))
        workspace.append(preview_panel)

        library = Gtk.Box(spacing=8, css_classes=["skin-toolbar"])
        self.saved = Gtk.ComboBoxText(hexpand=True)
        self.saved.set_tooltip_text("Elegí una skin guardada")
        self.saved.update_property([Gtk.AccessibleProperty.LABEL], ["Biblioteca de skins"])
        library.append(self.saved)
        library.append(self.control("Abrir", lambda: self.select_saved(self.saved)))
        library.append(self.control("Guardar skin", lambda: self.save_dialog(None)))
        library.append(self.control("Equipar", lambda: self.equip(None), primary=True))
        root.append(library)
        self.status = Gtk.Label(xalign=0, wrap=True, css_classes=["muted", "status-line"])
        root.append(self.status)

        def toggle_mode(*_):
            visible = advanced.get_active()
            self.drawing.set_visible(visible)
            self.hint.set_text("Elegí una parte, una cara y una capa para dibujar." if visible else
                               "Importá una skin o elegí una de tu biblioteca para probarla y equiparla.")

        easy.set_active(True)
        advanced.connect("toggled", toggle_mode)
        toggle_mode()
        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        for key, action in (("<Control>z", self.undo), ("<Control><Shift>z", self.redo)):
            keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(key),
                                               Gtk.CallbackAction.new(lambda *_, action=action: (action(), True)[1])))
        self.window.add_controller(keys)
        self.redraw()
        self.refresh_library()
        selected = selection.get("file", "")
        if selected and Path(selected).name == selected:
            candidate = self.library / self.profile / selected
            if candidate.is_file():
                self.load(candidate, library=True)
        self.model.connect("changed", self.change_model)
        self.window.present()

    @staticmethod
    def control(title, action, *, primary=False):
        control = Gtk.Button(label=title, css_classes=["primary"] if primary else [])
        control.connect("clicked", lambda _: action())
        return control

    def change_model(self, _):
        try:
            motor.save(self.profile_settings, {"file": self.current.name if self.current else "",
                                               "model": self.model.get_active_id()})
        except OSError as error:
            self.status.set_text(str(error))
        self.select_face(None)

    def open_community(self, _):
        url = "https://www.planetminecraft.com/skins/"
        try:
            gi.require_version("WebKit", "6.0")
            from gi.repository import WebKit
        except (ImportError, ValueError):
            Gtk.show_uri(self.window, url, Gdk.CURRENT_TIME)
            return
        window = Gtk.Window(title="Skins de la comunidad", transient_for=self.window,
                            default_width=1000, default_height=680)
        network = WebKit.NetworkSession.new_ephemeral()
        web = WebKit.WebView(network_session=network)

        def download_started(_, download):
            temporary = TemporaryDirectory()
            path = Path(temporary.name) / "skin.png"

            def destination(item, _):
                item.set_destination(path.as_uri())
                return True

            def check_size(item, _):
                if item.get_received_data_length() > 2_000_000:
                    item.cancel()

            def finished(_):
                if path.is_file():
                    self.load(path)
                temporary.cleanup()

            def failed(_, error):
                self.status.set_text(f"No se pudo descargar la skin: {error.message}")
                temporary.cleanup()

            download.connect("decide-destination", destination)
            download.connect("received-data", check_size)
            download.connect("finished", finished)
            download.connect("failed", failed)

        network.connect("download-started", download_started)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["menu"])
        layout.append(Gtk.LinkButton(uri=url, label="Abrir en el navegador para publicar o iniciar sesión"))
        web.set_vexpand(True)
        layout.append(web)
        window.set_child(layout)
        web.load_uri(url)
        window.present()

    def equip(self, _):
        app = self.app
        folder = app.selected
        if not folder or not app.profile or app.microsoft_active or app.busy:
            self.status.set_text("Elegí una instancia cerrada y un perfil offline.")
            return
        instance = dict(app.instances[folder])
        if instance["loader"] == "vanilla":
            self.status.set_text("Esta skin necesita una instancia con un cargador de mods compatible.")
            return
        if not any(self.pixels[3::4]):
            self.status.set_text("Dibujá o importá una skin antes de equiparla.")
            return
        _, data = self.pixbuf().save_to_bufferv("png", [], [])
        player = app.profile
        integraciones.run(app, self.window, "Equipar skin offline",
                          lambda: integraciones.equip(folder, instance, player, data),
                          f"Skin equipada para {player} en {instance['name']}.")

    def pixbuf(self):
        return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(self.pixels)),
            GdkPixbuf.Colorspace.RGB, True, 8, SIZE, SIZE, SIZE * 4)

    def refresh_library(self):
        self.saved.remove_all()
        for file in sorted((self.library / self.profile).glob("*.png")):
            self.saved.append(str(file), file.stem)
        if self.saved.get_model().iter_n_children(None):
            self.saved.set_active(0)

    def select_saved(self, combo):
        path = combo.get_active_id()
        if path:
            self.load(Path(path), library=True)

    def save_dialog(self, _):
        dialog = Gtk.Dialog(title="Guardar skin", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar", Gtk.ResponseType.OK)
        entry = Gtk.Entry(placeholder_text="Nombre de la skin", margin_top=12, margin_bottom=12)
        if self.current:
            entry.set_text(self.current.stem)
        error = Gtk.Label(xalign=0, wrap=True)
        dialog.get_content_area().append(entry)
        dialog.get_content_area().append(error)

        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                name = entry.get_text().strip()
                if not re.fullmatch(r"[\w -]{1,48}", name):
                    error.set_text("Usá un nombre de hasta 48 letras, números o espacios.")
                    return
                path = self.library / self.profile / f"{name}.png"
                if path.exists() and path != self.current:
                    error.set_text("Ya hay una skin con ese nombre. Elegí otro.")
                    return
                if not self.save(path):
                    error.set_text(self.status.get_text())
                    return
                self.current = path
                self.change_model(None)
                self.refresh_library()
                self.saved.set_active_id(str(path))
            dialog.destroy()

        dialog.connect("response", respond)
        dialog.present()

    def choose(self, export):
        action = Gtk.FileChooserAction.SAVE if export else Gtk.FileChooserAction.OPEN
        chooser = Gtk.FileChooserNative(title="Exportar skin" if export else "Importar skin",
                                        transient_for=self.window, action=action)
        filters = Gtk.FileFilter(name="Imagen PNG")
        filters.add_mime_type("image/png")
        filters.add_pattern("*.[pP][nN][gG]")
        chooser.add_filter(filters)
        if export:
            chooser.set_current_name("skin.png")

        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog.get_file().get_path()
                if path:
                    if export:
                        self.save(Path(path))
                    else:
                        self.load(Path(path))
            dialog.destroy()

        chooser.connect("response", selected)
        chooser.show()

    def save(self, path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.pixbuf().savev(str(path), "png", [], [])
        except (GLib.Error, OSError) as error:
            self.status.set_text(str(error))
            return False
        self.status.set_text(f"Guardada · {path.name}")
        return True

    def load(self, path, library=False):
        try:
            format_info, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
            if not format_info or format_info.get_name() != "png" or (width, height) != (SIZE, SIZE):
                raise ValueError("Elegí una skin PNG de 64 × 64 píxeles.")
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path)).add_alpha(False, 0, 0, 0)
            pixels = pixbuf.get_pixels()
            stride = pixbuf.get_rowstride()
            self.remember()
            self.current = path if library else None
            self.pixels[:] = b"".join(pixels[y * stride:y * stride + SIZE * 4] for y in range(SIZE))
        except (GLib.Error, ValueError) as error:
            self.status.set_text(str(error))
            return
        if library:
            try:
                motor.save(self.profile_settings, {"file": path.name, "model": self.model.get_active_id()})
            except OSError as error:
                self.status.set_text(str(error))
                self.redraw()
                return
        self.status.set_text(f"Editando · {path.name}")
        self.redraw()

    def redraw(self):
        self.canvas.queue_draw()
        self.preview.queue_draw()

    def rotate(self):
        self.angle = (self.angle + 1) % 4
        self.preview.queue_draw()

    @staticmethod
    def rgba(value):
        color = Gdk.RGBA()
        color.parse(value)
        return color

    def pick_color(self, color):
        self.color.set_rgba(color)
        self.erase.set_active(False)
        self.eyedropper.set_active(False)

    def seed(self):
        palette = ((226, 168, 132), (133, 91, 201), (161, 117, 219),
                   (161, 117, 219), (64, 76, 121), (64, 76, 121))
        for part, rgb in enumerate(palette):
            for side in range(6):
                u, v, w, h = face(part, side)
                for y in range(v, v + h):
                    for x in range(u, u + w):
                        index = (y * SIZE + x) * 4
                        self.pixels[index:index + 4] = bytes((*rgb, 255))
        for x in (10, 13):
            index = (12 * SIZE + x) * 4
            self.pixels[index:index + 4] = bytes((53, 37, 65, 255))

    def remember(self):
        self.history.append((bytes(self.pixels), self.current))
        if len(self.history) > 40:
            self.history.pop(0)
        self.future.clear()

    def undo(self):
        if self.history:
            self.future.append((bytes(self.pixels), self.current))
            pixels, self.current = self.history.pop()
            self.pixels[:] = pixels
            self.redraw()
            self.status.set_text("Cambio deshecho.")

    def redo(self):
        if self.future:
            self.history.append((bytes(self.pixels), self.current))
            pixels, self.current = self.future.pop()
            self.pixels[:] = pixels
            self.redraw()
            self.status.set_text("Cambio rehecho.")

    def select_face(self, _):
        self.side.set_sensitive(self.part.get_active() < len(PARTS))
        self.layer.set_sensitive(self.part.get_active() < len(PARTS))
        if self.side.get_active() < 4:
            self.angle = self.side.get_active()
        self.redraw()

    def region(self):
        index = self.part.get_active()
        if index >= len(PARTS):
            return 0, 0, SIZE, SIZE
        return face(index, self.side.get_active(), self.model.get_active_id() == "slim",
                    self.layer.get_active_id() == "overlay")

    def canvas_geometry(self, width, height, cols, rows):
        zoom = max(1, min(width, height) // max(cols, rows))
        return zoom, (width - cols * zoom) // 2, (height - rows * zoom) // 2

    def begin_stroke(self, _, x, y):
        self.last_pixel = None
        self.sampling = self.eyedropper.get_active()
        self.paint(x, y, begin=True)

    def paint(self, x, y, *, begin=False):
        u, v, width, height = self.region()
        zoom, left, top = self.canvas_geometry(self.canvas.get_width(), self.canvas.get_height(),
                                               width, height)
        col, row = int((x - left) // zoom), int((y - top) // zoom)
        if not (0 <= col < width and 0 <= row < height):
            self.last_pixel = None
            return
        if self.sampling:
            if begin:
                index = ((v + row) * SIZE + u + col) * 4
                red, green, blue, alpha = self.pixels[index:index + 4]
                if alpha:
                    self.pick_color(self.rgba(f"#{red:02x}{green:02x}{blue:02x}"))
                    self.status.set_text("Color seleccionado.")
            return
        if begin or self.last_pixel is None:
            self.remember()
        old_col, old_row = self.last_pixel or (col, row)
        steps = max(abs(col - old_col), abs(row - old_row), 1)
        color = self.color.get_rgba()
        rgba = bytes(4) if self.erase.get_active() else bytes(
            round(component * 255) for component in (color.red, color.green, color.blue, 1)
        )
        for step in range(steps + 1):
            px = round(old_col + (col - old_col) * step / steps)
            py = round(old_row + (row - old_row) * step / steps)
            index = ((v + py) * SIZE + u + px) * 4
            self.pixels[index:index + 4] = rgba
        self.last_pixel = col, row
        self.redraw()

    def paint_drag(self, gesture, dx, dy):
        _, x, y = gesture.get_start_point()
        self.paint(x + dx, y + dy)

    def tile(self, context, x, y, u, v, fallback=None):
        index = (v * SIZE + u) * 4
        pixel = self.pixels[index:index + 4]
        if pixel[3]:
            context.set_source_rgba(*(component / 255 for component in pixel))
        elif fallback:
            context.set_source_rgb(*fallback)
        else:
            return
        context.rectangle(x, y, 1, 1)
        context.fill()

    def draw_canvas(self, _, context, width, height):
        u, v, cols, rows = self.region()
        zoom, left, top = self.canvas_geometry(width, height, cols, rows)
        context.translate(left, top)
        context.scale(zoom, zoom)
        for y in range(rows):
            for x in range(cols):
                gray = 0.19 if (x + y) % 2 else 0.26
                context.set_source_rgb(gray, gray, gray + 0.06)
                context.rectangle(x, y, 1, 1)
                context.fill()
                self.tile(context, x, y, u + x, v + y)
                if zoom >= 16:
                    context.set_source_rgba(0.1, 0.08, 0.15, 0.25)
                    context.set_line_width(1 / zoom)
                    context.rectangle(x, y, 1, 1)
                    context.stroke()

    def draw_model(self, _, context, width, height):
        scale = min(width / 27, height / 38)
        context.translate(width / 2 - scale * 2, (height - 31 * scale) / 2)
        context.scale(scale, scale)
        context.set_antialias(cairo.ANTIALIAS_NONE)
        slim = self.model.get_active_id() == "slim"
        for part in reversed(range(len(PARTS))):
            u, v, w, h, depth, x, y = PARTS[part]
            if slim and part in (2, 3):
                w = 3
                if part == 2:
                    x += 1
            if self.angle >= 2:
                x = -x - w
            front = (u + depth, u + depth + w, u + 2 * depth + w, u)[self.angle]
            face_width = w if self.angle % 2 == 0 else depth
            side = (u + depth + w, u + 2 * depth + w, u, u + depth)[self.angle]
            side_width = depth if self.angle % 2 == 0 else w
            overlay_u, overlay_v = OVERLAYS[part]
            context.save()
            context.translate(x, y)
            for col in range(face_width):
                for row in range(h):
                    self.tile(context, col, row, front + col, v + depth + row, (0.39, 0.30, 0.54))
                    self.tile(context, col, row, overlay_u + front - u + col, overlay_v + depth + row)
            context.translate(face_width, 0)
            context.transform(cairo.Matrix(0.47, -0.34, 0, 1, 0, 0))
            for col in range(side_width):
                for row in range(h):
                    self.tile(context, col, row, side + col, v + depth + row, (0.25, 0.19, 0.37))
                    self.tile(context, col, row, overlay_u + side - u + col, overlay_v + depth + row)
            context.restore()

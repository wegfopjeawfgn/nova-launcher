"""Skin editor: paint on the unfolded skin, see it in 3D, keep a library, bring a player's skin and equip it."""
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import threading

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

import integraciones
import motor
import skin3d
import skinlib
from skinlib import SIZE

SHORT_NAMES = ("Cabeza", "Torso", "Brazo D", "Brazo I", "Pierna D", "Pierna I")
PALETTE = ("#e2a884", "#c98b66", "#a56b4a", "#7a4a32", "#f4d2b8", "#ffffff", "#c8c8c8", "#8a8a8a", "#4a4a4a", "#151515",
           "#3b2a20", "#6b4b2a", "#d9b25f", "#f2e08a", "#b83232", "#f08c2e", "#5aa832", "#2f6b3a", "#3fc1c9", "#3b6fd1",
           "#26357a", "#8a4fd1", "#d95fa6", "#f5a3c7")
TOOLS = (("pencil", "Lápiz", "B"), ("eraser", "Borrar", "E"), ("picker", "Gotero", "I"), ("fill", "Relleno", "G"))
MINECRAFT_SKIN_PAGE = "https://www.minecraft.net/msaprofile/mygames/editskin"
COMMUNITY_URL = "https://www.planetminecraft.com/skins/"


def pixbuf_from_pixels(pixels, width=SIZE, height=SIZE):
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(pixels)), GdkPixbuf.Colorspace.RGB, True, 8,
                                           width, height, width * 4)


def decode_skin(data):
    """PNG bytes -> (64x64 RGBA bytearray, guessed slim). Accepts 64x64 and the old 64x32 layout."""
    if len(data) > skinlib.MAX_SKIN_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Elegí una skin PNG de 64 × 64 píxeles.")
    loader = GdkPixbuf.PixbufLoader()
    try:
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
    except GLib.Error as error:
        raise ValueError("No pude leer esa imagen como PNG.") from error
    width, height = pixbuf.get_width(), pixbuf.get_height()
    if width != SIZE or height not in (32, SIZE):
        raise ValueError(f"La skin mide {width} × {height}. Nova usa skins de 64 × 64 (o las antiguas de 64 × 32); "
                         "las de alta resolución todavía no.")
    pixbuf = pixbuf.add_alpha(False, 0, 0, 0) if not pixbuf.get_has_alpha() else pixbuf
    stride, raw = pixbuf.get_rowstride(), pixbuf.get_pixels()
    pixels = bytearray(b"".join(raw[y * stride:y * stride + SIZE * 4] for y in range(height)))
    if height == 32:
        pixels = skinlib.upgrade_legacy(pixels)
        return pixels, False
    return pixels, skinlib.guess_slim(pixels)


class Swatches(Gtk.DrawingArea):
    """A row of colour squares; clicking one picks it."""

    def __init__(self, colors, on_pick, columns=12):
        super().__init__()
        self.colors, self.on_pick, self.columns = list(colors), on_pick, columns
        self.cell, self.gap = 22, 5
        self.set_draw_func(self.draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self.pressed)
        self.add_controller(click)
        self.update_size()

    def update_size(self):
        rows = max(1, -(-len(self.colors) // self.columns))
        self.set_content_width(self.columns * (self.cell + self.gap) - self.gap)
        self.set_content_height(rows * (self.cell + self.gap) - self.gap)
        self.queue_draw()

    def set_colors(self, colors):
        self.colors = list(colors)
        self.update_size()

    def draw(self, _, cr, width, height):
        for index, value in enumerate(self.colors):
            color = Gdk.RGBA()
            color.parse(value)
            x = (index % self.columns) * (self.cell + self.gap)
            y = (index // self.columns) * (self.cell + self.gap)
            cr.set_source_rgb(color.red, color.green, color.blue)
            cr.rectangle(x, y, self.cell, self.cell)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.22)
            cr.set_line_width(1)
            cr.stroke()

    def pressed(self, _, __, x, y):
        col, row = int(x // (self.cell + self.gap)), int(y // (self.cell + self.gap))
        index = row * self.columns + col
        if 0 <= col < self.columns and 0 <= index < len(self.colors):
            self.on_pick(self.colors[index])


class Editor:
    def __init__(self, app):
        self.app = app
        self.pixels = skinlib.seed()
        self.history, self.future = [], []
        self.current = None
        self.dirty = False
        self.slim = False
        self.tool = "pencil"
        self.mirror = False
        self.recent = []
        self.yaw, self.pitch = 0.55, 0.16
        self.hover = None
        self.stroke_before = None
        self.last_texel = None
        self._surface = None
        self._preview_scheduled = False
        self.profile = app.microsoft[1]["name"] if app.microsoft_active else app.profile or "Borrador"
        self.library = motor.ROOT / "skins"
        self.profile_settings = self.library / self.profile / "selection.json"
        selection = motor.read(self.profile_settings, {})
        self.slim = selection.get("model") == "slim"
        self.window = Gtk.Window(title="Editor de skins", transient_for=app.window, default_width=980, default_height=700)
        self.window.connect("close-request", self.on_close)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["menu", "skin-editor"])
        self.window.set_child(root)
        root.append(self.build_header())
        body = Gtk.Box(spacing=12, vexpand=True)
        body.append(self.build_library())
        body.append(self.build_workspace())
        body.append(self.build_preview())
        root.append(body)
        self.status = Gtk.Label(xalign=0, wrap=True, css_classes=["muted", "status-line"])
        root.append(self.status)
        self.install_shortcuts()
        self.refresh_library()
        file = selection.get("file", "")
        if file and Path(file).name == file and (self.library / self.profile / file).is_file():
            self.open_file(self.library / self.profile / file, library=True)
        else:
            self.say("Elegí una skin de tu biblioteca, importá un PNG o pintá sobre la que está abierta.")
        self.sync_controls()
        app.show_page(self.window)

    # ------------------------------------------------------------ layout
    @staticmethod
    def control(title, action, *, primary=False, tooltip=None):
        widget = Gtk.Button(label=title, css_classes=["primary"] if primary else [])
        widget.connect("clicked", lambda _: action())
        if tooltip:
            widget.set_tooltip_text(tooltip)
        return widget

    def build_header(self):
        header = Gtk.Box(spacing=8)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        title.append(Gtk.Label(label="Skins", xalign=0, css_classes=["subheading"]))
        title.append(Gtk.Label(label=f"Perfil · {self.profile}", xalign=0, css_classes=["muted"]))
        header.append(title)
        header.append(self.control("Importar PNG", lambda: self.choose(False), tooltip="Abrir una skin de tu equipo"))
        header.append(self.control("Exportar PNG", lambda: self.choose(True), tooltip="Guardar la skin como imagen"))
        header.append(self.control("De un jugador", self.player_dialog, tooltip="Traer la skin actual de un jugador por su nombre"))
        header.append(self.control("Comunidad", self.open_community, tooltip="Buscar skins en Planet Minecraft"))
        return header

    def build_library(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["skin-panel"], width_request=190)
        panel.append(Gtk.Label(label="Mis skins", xalign=0, css_classes=["form-label"]))
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["skin-list"])
        self.rows.connect("row-selected", self.on_row)
        self.rows.update_property([Gtk.AccessibleProperty.LABEL], ["Biblioteca de skins"])
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.rows)
        panel.append(scroll)
        self.empty = Gtk.Label(label="Todavía no guardaste ninguna.", wrap=True, xalign=0, css_classes=["muted"])
        panel.append(self.empty)
        actions = Gtk.Box(spacing=6)
        actions.append(self.control("Nueva", self.new_skin, tooltip="Empezar una skin en blanco"))
        self.delete_button = self.control("Eliminar", self.delete_current, tooltip="Borrar la skin elegida de la biblioteca")
        actions.append(self.delete_button)
        panel.append(actions)
        panel.append(self.control("Guardar", self.save_clicked, primary=True, tooltip="Ctrl + S"))
        panel.append(self.control("Guardar como…", lambda: self.save_dialog(as_new=True)))
        return panel

    def build_workspace(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, css_classes=["skin-panel"])
        tools = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=6, row_spacing=6,
                            homogeneous=False)
        self.tool_buttons = {}
        group = None
        for key, name, shortcut in TOOLS:
            button = Gtk.ToggleButton(label=name, group=group, tooltip_text=f"{name} ({shortcut})", css_classes=["skin-tool"])
            group = group or button
            button.connect("toggled", lambda b, k=key: b.get_active() and self.set_tool(k))
            self.tool_buttons[key] = button
            tools.append(button)
        self.tool_buttons["pencil"].set_active(True)
        self.mirror_button = Gtk.ToggleButton(label="Simetría", tooltip_text="Pinta también el lado opuesto del cuerpo (M)", css_classes=["skin-tool"])
        self.mirror_button.connect("toggled", lambda b: setattr(self, "mirror", b.get_active()))
        tools.append(self.mirror_button)
        self.undo_button = self.control("Deshacer", self.undo, tooltip="Ctrl + Z")
        self.redo_button = self.control("Rehacer", self.redo, tooltip="Ctrl + Mayús + Z")
        for button in (self.undo_button, self.redo_button):
            button.add_css_class("skin-tool")
        tools.append(self.undo_button)
        tools.append(self.redo_button)
        panel.append(tools)

        self.canvas = Gtk.DrawingArea(content_width=256, content_height=256, hexpand=True, vexpand=True,
                                      css_classes=["skin-canvas"])
        self.canvas.set_draw_func(self.draw_canvas)
        self.canvas.set_cursor_from_name("crosshair")
        self.canvas.set_focusable(True)
        self.canvas.update_property([Gtk.AccessibleProperty.LABEL], ["Skin desplegada: hacé clic o arrastrá para pintar"])
        drag = Gtk.GestureDrag.new()
        drag.set_button(Gdk.BUTTON_PRIMARY)
        drag.connect("drag-begin", self.stroke_begin)
        drag.connect("drag-update", self.stroke_update)
        drag.connect("drag-end", self.stroke_end)
        self.canvas.add_controller(drag)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_hover)
        motion.connect("leave", self.on_leave)
        self.canvas.add_controller(motion)
        panel.append(self.canvas)
        self.where = Gtk.Label(xalign=0, css_classes=["muted"])
        panel.append(self.where)

        colors = Gtk.Box(spacing=12)
        self.palette = Swatches(PALETTE, self.set_color)
        colors.append(self.palette)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START)
        self.color = Gtk.ColorButton()
        self.color.set_title("Color del pincel")
        self.color.set_tooltip_text("Más colores")
        self.color.set_rgba(self.rgba("#8f6bd9"))
        self.color.connect("color-set", lambda b: self.set_color(self.hex(b.get_rgba()), from_button=True))
        side.append(self.color)
        colors.append(side)
        panel.append(colors)
        self.recent_row = Swatches([], self.set_color)
        self.recent_label = Gtk.Label(label="Usados hace poco", xalign=0, css_classes=["muted"])
        panel.append(self.recent_label)
        panel.append(self.recent_row)
        self.recent_label.set_visible(False)
        self.recent_row.set_visible(False)
        return panel

    def build_preview(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["skin-panel", "skin-preview"], width_request=240)
        panel.append(Gtk.Label(label="Vista previa", xalign=0, css_classes=["form-label"]))
        self.preview = Gtk.DrawingArea(content_width=200, content_height=320, hexpand=True, vexpand=True)
        self.preview.set_draw_func(self.draw_model)
        self.preview.set_cursor_from_name("grab")
        self.preview.update_property([Gtk.AccessibleProperty.LABEL], ["Vista 3D de la skin: arrastrá para girarla"])
        turn = Gtk.GestureDrag.new()
        turn.connect("drag-begin", lambda *_: setattr(self, "turn_start", (self.yaw, self.pitch)))
        turn.connect("drag-update", self.turn_update)
        self.preview.add_controller(turn)
        panel.append(self.preview)
        panel.append(Gtk.Label(label="Arrastrá para girarla", xalign=0.5, css_classes=["muted"]))
        turns = Gtk.Box(spacing=6, homogeneous=True)
        turns.append(self.control("‹", lambda: self.spin(-0.6), tooltip="Girar a la izquierda"))
        turns.append(self.control("De frente", self.face_front))
        turns.append(self.control("›", lambda: self.spin(0.6), tooltip="Girar a la derecha"))
        panel.append(turns)
        model = Gtk.Box(css_classes=["linked"], homogeneous=True)
        self.classic_button = Gtk.ToggleButton(label="Clásico", tooltip_text="Brazos de 4 píxeles (Steve)")
        self.slim_button = Gtk.ToggleButton(label="Delgado", group=self.classic_button, tooltip_text="Brazos de 3 píxeles (Alex)")
        self.classic_button.connect("toggled", lambda b: b.get_active() and self.set_slim(False))
        self.slim_button.connect("toggled", lambda b: b.get_active() and self.set_slim(True))
        model.append(self.classic_button)
        model.append(self.slim_button)
        panel.append(model)
        self.equip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["skin-equip"])
        self.equip_note = Gtk.Label(xalign=0, wrap=True, css_classes=["muted"])
        self.equip_box.append(self.equip_note)
        self.equip_button = self.control("Equipar", self.equip, primary=True, tooltip="Usar esta skin en la instancia elegida")
        self.equip_box.append(self.equip_button)
        self.official_button = self.control("Cambiar en minecraft.net", lambda: Gtk.show_uri(self.window, MINECRAFT_SKIN_PAGE, Gdk.CURRENT_TIME))
        self.equip_box.append(self.official_button)
        panel.append(self.equip_box)
        return panel

    def install_shortcuts(self):
        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.MANAGED)
        table = (("<Control>z", self.undo), ("<Control><Shift>z", self.redo), ("<Control>y", self.redo),
                 ("<Control>s", self.save_clicked), ("b", lambda: self.pick_tool("pencil")), ("e", lambda: self.pick_tool("eraser")),
                 ("i", lambda: self.pick_tool("picker")), ("g", lambda: self.pick_tool("fill")),
                 ("m", lambda: self.mirror_button.set_active(not self.mirror_button.get_active())))
        for key, action in table:
            keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(key),
                                               Gtk.CallbackAction.new(lambda *_, action=action: (action(), True)[1])))
        self.window.add_controller(keys)

    # ------------------------------------------------------------ small state helpers
    def say(self, text):
        self.status.set_text(text)

    @staticmethod
    def rgba(value):
        color = Gdk.RGBA()
        color.parse(value)
        return color

    @staticmethod
    def hex(color):
        return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (color.red, color.green, color.blue)))

    def brush(self):
        color = self.color.get_rgba()
        return tuple(round(c * 255) for c in (color.red, color.green, color.blue)) + (255,)

    def set_color(self, value, from_button=False):
        if not from_button:
            self.color.set_rgba(self.rgba(value))
        if self.tool in ("eraser", "picker"):
            self.pick_tool("pencil")

    def remember_color(self):
        value = self.hex(self.color.get_rgba())
        if value in PALETTE:
            return
        self.recent = [value] + [c for c in self.recent if c != value][:11]
        self.recent_row.set_colors(self.recent)
        self.recent_label.set_visible(True)
        self.recent_row.set_visible(True)

    def pick_tool(self, key):
        self.tool_buttons[key].set_active(True)

    def set_tool(self, key):
        self.tool = key
        if not hasattr(self, "canvas"):
            return  # the first toggle fires while the window is still being built
        self.canvas.set_cursor_from_name({"picker": "copy", "eraser": "not-allowed"}.get(key, "crosshair"))
        hints = {"pencil": "Lápiz: hacé clic o arrastrá sobre la skin.",
                 "eraser": "Borrador: solo en la capa exterior (zonas con borde punteado). La capa base no puede quedar vacía.",
                 "picker": "Cuentagotas: hacé clic sobre un color de la skin para usarlo.",
                 "fill": "Relleno: pinta de una vez los píxeles iguales y vecinos de esa cara."}
        self.say(hints[key])

    def set_slim(self, slim):
        if slim == self.slim:
            return
        self.slim = slim
        self.persist_selection()
        self.invalidate()

    def spin(self, amount):
        self.yaw += amount
        self.preview.queue_draw()

    def face_front(self):
        self.yaw, self.pitch = 0.0, 0.0
        self.preview.queue_draw()

    def turn_update(self, _, dx, dy):
        start_yaw, start_pitch = getattr(self, "turn_start", (self.yaw, self.pitch))
        self.yaw = start_yaw + dx * 0.012
        self.pitch = max(-0.5, min(0.7, start_pitch + dy * 0.006))
        self.schedule_preview()

    def schedule_preview(self):
        """The 3D view takes a few ms: while painting or turning, redraw it at most every 50 ms."""
        if not self._preview_scheduled:
            self._preview_scheduled = True
            GLib.timeout_add(50, self._flush_preview)

    def _flush_preview(self):
        self._preview_scheduled = False
        self.preview.queue_draw()
        return False

    def invalidate(self):
        self._surface = None
        self.canvas.queue_draw()
        self.schedule_preview()

    def sync_controls(self):
        self.classic_button.set_active(not self.slim)
        self.slim_button.set_active(self.slim)
        self.undo_button.set_sensitive(bool(self.history))
        self.redo_button.set_sensitive(bool(self.future))
        self.delete_button.set_sensitive(self.current is not None)
        microsoft = self.app.microsoft_active
        self.equip_button.set_visible(not microsoft)
        self.official_button.set_visible(microsoft)
        self.equip_note.set_text(self.equip_text())

    def equip_text(self):
        app = self.app
        if app.microsoft_active:
            return "Con una cuenta de Microsoft la skin se cambia en la página oficial de Minecraft. Exportá el PNG y subilo ahí."
        if not app.profile:
            return "Elegí un perfil offline para poder equipar la skin."
        folder = app.selected
        if not folder or folder not in app.instances:
            return "Elegí una instancia en la biblioteca para equiparla."
        instance = app.instances[folder]
        if instance["loader"] == "vanilla":
            return f"«{instance['name']}» es Vanilla: hace falta un cargador de mods (Fabric, Forge…) para equipar skins."
        return f"Se equipa a {app.profile} en «{instance['name']}». Nova instala el mod CustomSkinLoader si falta."

    # ------------------------------------------------------------ painting
    def geometry(self, width, height):
        zoom = max(2, min(width, height) // SIZE)
        return zoom, (width - SIZE * zoom) // 2, (height - SIZE * zoom) // 2

    def texel_at(self, x, y):
        zoom, left, top = self.geometry(self.canvas.get_width(), self.canvas.get_height())
        col, row = int((x - left) // zoom), int((y - top) // zoom)
        if x < left or y < top or not (0 <= col < SIZE and 0 <= row < SIZE):
            return None
        return col, row

    def stroke_begin(self, gesture, x, y):
        self.canvas.grab_focus()
        self.stroke_before = bytes(self.pixels)
        self.last_texel = None
        self.apply_at(x, y, first=True)

    def stroke_update(self, gesture, dx, dy):
        _, x, y = gesture.get_start_point()
        self.apply_at(x + dx, y + dy)

    def stroke_end(self, *_):
        if self.stroke_before is not None and bytes(self.pixels) != self.stroke_before:
            self.history.append((self.stroke_before, self.current))
            del self.history[:-60]
            self.future.clear()
            self.dirty = True
            if self.tool in ("pencil", "fill"):
                self.remember_color()
            self.sync_controls()
        self.stroke_before = None
        self.last_texel = None

    def apply_at(self, x, y, first=False):
        texel = self.texel_at(x, y)
        if texel is None:
            self.last_texel = None
            return
        if not skinlib.paintable(*texel, self.slim):
            if first:
                self.say("Esa zona de la imagen no se usa en el juego: pintá dentro de las caras marcadas.")
            return
        if self.tool == "picker":
            if first:
                index = (texel[1] * SIZE + texel[0]) * 4
                red, green, blue, alpha = self.pixels[index:index + 4]
                if alpha:
                    self.color.set_rgba(self.rgba(f"#{red:02x}{green:02x}{blue:02x}"))
                    self.pick_tool("pencil")
                    self.say("Color tomado de la skin.")
                else:
                    self.say("Ese píxel está vacío: no hay color para tomar.")
            return
        if self.tool == "fill":
            if first:
                changed = skinlib.flood_fill(self.pixels, *texel, self.brush(), self.slim)
                if changed and self.mirror:
                    other = skinlib.mirror_texel(*texel, self.slim)
                    if other:
                        skinlib.flood_fill(self.pixels, *other, self.brush(), self.slim)
                if changed:
                    self.invalidate()
            return
        erase = self.tool == "eraser"
        if erase and not skinlib.is_overlay(*texel, self.slim):
            if first:
                self.say("La capa base no puede quedar vacía (se vería negra en el juego). Borrá solo en la capa exterior.")
            return
        value = bytes(4) if erase else bytes(self.brush())
        old = self.last_texel or texel
        steps = max(abs(texel[0] - old[0]), abs(texel[1] - old[1]), 1)
        for step in range(steps + 1):
            point = (round(old[0] + (texel[0] - old[0]) * step / steps), round(old[1] + (texel[1] - old[1]) * step / steps))
            for target in ((point, skinlib.mirror_texel(*point, self.slim)) if self.mirror else (point,)):
                if target and skinlib.paintable(*target, self.slim) and not (erase and not skinlib.is_overlay(*target, self.slim)):
                    index = (target[1] * SIZE + target[0]) * 4
                    self.pixels[index:index + 4] = value
        self.last_texel = texel
        self.invalidate()

    def on_hover(self, _, x, y):
        texel = self.texel_at(x, y)
        found = skinlib.face_at(*texel, self.slim) if texel else None
        hover = texel if found else None
        if hover != self.hover:
            self.hover = hover
            self.canvas.queue_draw()
        if found:
            part, side, overlay, _ = found
            self.where.set_text(f"{skinlib.PART_NAMES[part]} · {skinlib.FACE_NAMES[side]} · "
                                f"{'capa exterior' if overlay else 'capa base'}")
        else:
            self.where.set_text("")

    def on_leave(self, _):
        self.hover = None
        self.where.set_text("")
        self.canvas.queue_draw()

    def undo(self):
        if self.history:
            self.future.append((bytes(self.pixels), self.current))
            pixels, self.current = self.history.pop()
            self.pixels[:] = pixels
            self.dirty = True
            self.invalidate()
            self.sync_controls()
            self.say("Cambio deshecho.")

    def redo(self):
        if self.future:
            self.history.append((bytes(self.pixels), self.current))
            pixels, self.current = self.future.pop()
            self.pixels[:] = pixels
            self.dirty = True
            self.invalidate()
            self.sync_controls()
            self.say("Cambio rehecho.")

    # ------------------------------------------------------------ drawing
    def texture_surface(self):
        if self._surface is None:
            data = bytearray(SIZE * SIZE * 4)
            for i in range(0, SIZE * SIZE * 4, 4):
                red, green, blue, alpha = self.pixels[i:i + 4]
                x, y = (i // 4) % SIZE, (i // 4) // SIZE
                if skinlib.paintable(x, y, self.slim):
                    gray = 0.20 if (x + y) % 2 else 0.27
                    base = (gray * 255, gray * 255, (gray + 0.05) * 255)
                else:
                    base = (14, 15, 20)
                a = alpha / 255
                data[i] = int(blue * a + base[2] * (1 - a))
                data[i + 1] = int(green * a + base[1] * (1 - a))
                data[i + 2] = int(red * a + base[0] * (1 - a))
                data[i + 3] = 255
            self._surface = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_ARGB32, SIZE, SIZE, SIZE * 4)
            self._surface_data = data  # cairo does not copy it: keep it alive
        return self._surface

    def draw_canvas(self, _, cr, width, height):
        zoom, left, top = self.geometry(width, height)
        cr.translate(left, top)
        cr.scale(zoom, zoom)
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        cr.set_source_surface(self.texture_surface(), 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        line = 1.0 / zoom
        cr.set_line_width(line)
        for part, side, overlay, (u, v, w, h) in skinlib.faces(self.slim):
            if overlay:
                cr.set_source_rgba(0.56, 0.84, 0.91, 0.55)
                cr.set_dash([3 * line, 2 * line])
            else:
                cr.set_source_rgba(1, 1, 1, 0.20)
                cr.set_dash([])
            cr.rectangle(u + 0.5 * line, v + 0.5 * line, w - line, h - line)
            cr.stroke()
        cr.set_dash([])
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        for part in range(len(skinlib.PARTS)):
            u, v, w, h = skinlib.face(part, 0, self.slim)
            cr.set_font_size(1.0)
            extent = cr.text_extents(SHORT_NAMES[part]).width or 1
            size = min(1.5, 0.86 * w / extent)
            cr.set_font_size(size)
            extent = cr.text_extents(SHORT_NAMES[part])
            cr.set_source_rgba(1, 1, 1, 0.5)
            cr.move_to(u + (w - extent.width) / 2 - extent.x_bearing, v + h / 2 + extent.height / 2)
            cr.show_text(SHORT_NAMES[part])
        if self.hover:
            for index, texel in enumerate((self.hover, skinlib.mirror_texel(*self.hover, self.slim) if self.mirror else None)):
                if texel:
                    cr.set_source_rgba(1, 1, 1, 0.95) if index == 0 else cr.set_source_rgba(0.56, 0.84, 0.91, 0.95)
                    cr.set_line_width(2.0 * line)
                    cr.rectangle(texel[0], texel[1], 1, 1)
                    cr.stroke()

    def draw_model(self, _, cr, width, height):
        cr.set_source_rgba(0, 0, 0, 0.18)
        cr.save()
        cr.translate(width / 2, height * 0.93)
        cr.scale(width * 0.22, height * 0.025)
        cr.arc(0, 0, 1, 0, 6.2832)
        cr.restore()
        cr.fill()
        scale = min(width / 26, height / 36)
        cr.translate(width / 2, height * 0.46)
        cr.scale(scale, scale)
        cr.set_line_width(0.55 / scale)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for corners, (red, green, blue, alpha) in skin3d.scene(self.pixels, self.yaw, self.pitch, self.slim):
            cr.move_to(*corners[0])
            for point in corners[1:]:
                cr.line_to(*point)
            cr.close_path()
            cr.set_source_rgba(red, green, blue, alpha)
            cr.fill_preserve()
            cr.stroke()

    # ------------------------------------------------------------ library
    def thumbnail(self, path):
        try:
            data = path.read_bytes()
            pixels, _ = decode_skin(data)
            icon = pixbuf_from_pixels(skinlib.head_icon(pixels), 8, 8).scale_simple(32, 32, GdkPixbuf.InterpType.NEAREST)
            return Gdk.Texture.new_for_pixbuf(icon)
        except (OSError, ValueError):
            return None

    def refresh_library(self, select=None):
        self.loading = True
        while row := self.rows.get_first_child():
            self.rows.remove(row)
        files = sorted((self.library / self.profile).glob("*.png"), key=lambda f: f.stem.lower())
        for file in files:
            row = Gtk.ListBoxRow()
            line = Gtk.Box(spacing=10, margin_top=4, margin_bottom=4, margin_start=4)
            picture = Gtk.Picture(width_request=32, height_request=32, can_shrink=False, css_classes=["skin-thumb"])
            texture = self.thumbnail(file)
            if texture:
                picture.set_paintable(texture)
            line.append(picture)
            line.append(Gtk.Label(label=file.stem, xalign=0, hexpand=True, ellipsize=3))
            row.set_child(line)
            row.path = file
            self.rows.append(row)
            if select and file == select:
                self.rows.select_row(row)
        self.empty.set_visible(not files)
        self.loading = False

    def on_row(self, _, row):
        if getattr(self, "loading", False) or row is None or row.path == self.current:
            return
        path = row.path

        def go():
            self.open_file(path, library=True)

        def stay():
            self.loading = True
            self.select_current_row()
            self.loading = False

        self.confirm_discard(go, stay)

    def select_current_row(self):
        row = self.rows.get_first_child()
        while row:
            if getattr(row, "path", None) == self.current:
                self.rows.select_row(row)
                return
            row = row.get_next_sibling()
        self.rows.unselect_all()

    def persist_selection(self):
        try:
            motor.save(self.profile_settings, {"file": self.current.name if self.current else "",
                                               "model": "slim" if self.slim else "classic"})
        except OSError as error:
            self.say(str(error))

    # ------------------------------------------------------------ opening and saving
    def confirm_discard(self, proceed, cancel=None):
        if not self.dirty:
            proceed()
            return
        alert = Gtk.AlertDialog(message="Hay cambios sin guardar",
                                detail="Si seguís, se pierden los cambios que hiciste en esta skin.")
        alert.set_buttons(["Cancelar", "Guardar y seguir", "Descartar"])
        alert.set_cancel_button(0)
        alert.set_default_button(1)

        def answered(dialog, result):
            try:
                choice = dialog.choose_finish(result)
            except GLib.Error:
                choice = 0
            if choice == 2:
                proceed()
            elif choice == 1:
                self.save_clicked(then=proceed)
            elif cancel:
                cancel()

        alert.choose(self.window, None, answered)

    def on_close(self, _):
        if self.dirty and not getattr(self, "closing", False):
            def leave():
                self.closing = True
                self.window.close()

            self.confirm_discard(leave)
            return True
        return False

    def adopt(self, pixels, *, slim=None, current=None, note=""):
        self.history.clear()
        self.future.clear()
        self.pixels[:] = pixels
        self.current = current
        self.dirty = False
        if slim is not None and slim != self.slim:
            self.slim = slim
        self.invalidate()
        self.sync_controls()
        self.say(note)

    def open_file(self, path, library=False):
        try:
            pixels, guessed = decode_skin(path.read_bytes())
        except (OSError, ValueError) as error:
            self.say(str(error))
            return False
        model = motor.read(self.profile_settings, {}).get("model") if library else None
        slim = (model == "slim") if library and model else guessed
        self.adopt(pixels, slim=slim, current=path if library else None,
                   note=f"Abierta · {path.stem}" if library else f"Importada · {path.name}. Guardala en tu biblioteca para conservarla.")
        if not library:
            self.dirty = True
        else:
            self.persist_selection()
            self.select_current_row()
        return True

    def new_skin(self):
        def go():
            self.adopt(skinlib.seed(), current=None, note="Skin nueva. Pintá y guardala con un nombre.")
            self.persist_selection()
            self.select_current_row()

        self.confirm_discard(go)

    def save_clicked(self, then=None):
        if self.current:
            return self.write(self.current, then)
        self.save_dialog(then=then)
        return False

    def write(self, path, then=None):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pixbuf_from_pixels(self.pixels).savev(str(path), "png", [], [])
        except (GLib.Error, OSError) as error:
            self.say(f"No se pudo guardar: {error}")
            return False
        self.current = path
        self.dirty = False
        self.persist_selection()
        self.refresh_library(select=path)
        self.sync_controls()
        self.say(f"Guardada · {path.stem}")
        if then:
            then()
        return True

    def save_dialog(self, as_new=False, then=None):
        dialog = Gtk.Dialog(title="Guardar skin", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar", Gtk.ResponseType.OK).add_css_class("primary")
        area = dialog.get_content_area()
        area.add_css_class("menu")
        area.set_spacing(8)
        area.append(Gtk.Label(label="Nombre de la skin", xalign=0, css_classes=["form-label"]))
        entry = Gtk.Entry(placeholder_text="Por ejemplo: Caballero azul", activates_default=True)
        if self.current:
            entry.set_text(self.current.stem + (" copia" if as_new else ""))
        area.append(entry)
        error = Gtk.Label(xalign=0, wrap=True, css_classes=["form-error"])
        area.append(error)
        dialog.set_default_response(Gtk.ResponseType.OK)

        def respond(_, response):
            if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return
            name = entry.get_text().strip()
            if not re.fullmatch(r"[\w][\w -]{0,47}", name):
                error.set_text("Usá hasta 48 letras, números, espacios o guiones, empezando por una letra o número.")
                return
            path = self.library / self.profile / f"{name}.png"
            if path.exists() and path != self.current:
                error.set_text("Ya hay una skin con ese nombre. Elegí otro.")
                return
            dialog.destroy()
            self.write(path, then)

        dialog.connect("response", respond)
        dialog.present()

    def delete_current(self):
        path = self.current
        if not path:
            return
        alert = Gtk.AlertDialog(message=f"¿Eliminar «{path.stem}»?", detail="Se borra de tu biblioteca y no se puede deshacer.")
        alert.set_buttons(["Cancelar", "Eliminar"])
        alert.set_cancel_button(0)

        def answered(dialog, result):
            try:
                choice = dialog.choose_finish(result)
            except GLib.Error:
                return
            if choice != 1:
                return
            try:
                path.unlink()
            except OSError as error:
                self.say(f"No se pudo eliminar: {error}")
                return
            self.current = None
            self.dirty = True
            self.persist_selection()
            self.refresh_library()
            self.sync_controls()
            self.say(f"Eliminada · {path.stem}. La skin sigue abierta: guardala de nuevo si la querés.")

        alert.choose(self.window, None, answered)

    def choose(self, export):
        action = Gtk.FileChooserAction.SAVE if export else Gtk.FileChooserAction.OPEN
        chooser = Gtk.FileChooserNative(title="Exportar skin" if export else "Importar skin", transient_for=self.window, action=action)
        filters = Gtk.FileFilter(name="Imagen PNG")
        filters.add_mime_type("image/png")
        filters.add_pattern("*.[pP][nN][gG]")
        chooser.add_filter(filters)
        if export:
            chooser.set_current_name(f"{self.current.stem if self.current else 'skin'}.png")

        def selected(dialog, response):
            if response == Gtk.ResponseType.ACCEPT and dialog.get_file() and dialog.get_file().get_path():
                path = Path(dialog.get_file().get_path())
                if export:
                    try:
                        pixbuf_from_pixels(self.pixels).savev(str(path), "png", [], [])
                        self.say(f"Exportada · {path.name}")
                    except (GLib.Error, OSError) as error:
                        self.say(f"No se pudo exportar: {error}")
                else:
                    self.confirm_discard(lambda: self.open_file(path))
            self.chooser = None

        self.chooser = chooser  # keep it alive until it answers
        chooser.connect("response", selected)
        chooser.show()

    # ------------------------------------------------------------ a player's skin
    def player_dialog(self):
        dialog = Gtk.Dialog(title="Skin de un jugador", transient_for=self.window, modal=True)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        go = dialog.add_button("Traer skin", Gtk.ResponseType.OK)
        go.add_css_class("primary")
        area = dialog.get_content_area()
        area.add_css_class("menu")
        area.set_spacing(8)
        area.append(Gtk.Label(label="Nombre del jugador de Minecraft", xalign=0, css_classes=["form-label"]))
        entry = Gtk.Entry(placeholder_text="Por ejemplo: jeb_", activates_default=True)
        area.append(entry)
        note = Gtk.Label(label="Nova baja la skin actual de ese jugador desde Mojang. La podés editar y guardar como tuya.",
                         xalign=0, wrap=True, css_classes=["muted"])
        area.append(note)
        dialog.set_default_response(Gtk.ResponseType.OK)

        def finished(data, slim, error):
            go.set_sensitive(True)
            if error:
                note.set_text(error)
                return False
            try:
                pixels, _ = decode_skin(data)
            except ValueError as problem:
                note.set_text(str(problem))
                return False
            dialog.destroy()
            self.confirm_discard(lambda: (self.adopt(pixels, slim=slim, current=None, note="Skin traída de Mojang. Guardala para conservarla."),
                                          setattr(self, "dirty", True), self.select_current_row()))
            return False

        def respond(_, response):
            if response != Gtk.ResponseType.OK:
                dialog.destroy()
                return
            name = entry.get_text().strip()
            if not skinlib.USERNAME.fullmatch(name):
                note.set_text("Escribí un nombre de jugador de Minecraft (3 a 16 letras, números o guion bajo).")
                return
            go.set_sensitive(False)
            note.set_text("Buscando…")

            def work():
                try:
                    data, slim = skinlib.fetch_player_skin(name)
                except ValueError as problem:
                    GLib.idle_add(finished, None, False, str(problem))
                except Exception:
                    GLib.idle_add(finished, None, False, "No pude conectar con Mojang. Revisá tu internet y probá de nuevo.")
                else:
                    GLib.idle_add(finished, data, slim, None)

            threading.Thread(target=work, daemon=True).start()

        dialog.connect("response", respond)
        dialog.present()

    # ------------------------------------------------------------ community and equipping
    def open_community(self):
        try:
            gi.require_version("WebKit", "6.0")
            from gi.repository import WebKit
        except (ImportError, ValueError):
            Gtk.show_uri(self.window, COMMUNITY_URL, Gdk.CURRENT_TIME)
            return
        window = Gtk.Window(title="Skins de la comunidad", transient_for=self.window, default_width=1000, default_height=680)
        network = WebKit.NetworkSession.new_ephemeral()
        web = WebKit.WebView(network_session=network)

        def download_started(_, download):
            temporary = TemporaryDirectory()
            path = Path(temporary.name) / "skin.png"

            def destination(item, _):
                item.set_destination(path.as_uri())
                return True

            def check_size(item, _):
                if item.get_received_data_length() > skinlib.MAX_SKIN_BYTES * 2:
                    item.cancel()

            def finished(_):
                if path.is_file():
                    window.close()
                    self.confirm_discard(lambda: self.open_file(path))
                temporary.cleanup()

            def failed(_, error):
                self.say(f"No se pudo descargar la skin: {error.message}")
                temporary.cleanup()

            download.connect("decide-destination", destination)
            download.connect("received-data", check_size)
            download.connect("finished", finished)
            download.connect("failed", failed)

        network.connect("download-started", download_started)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["menu"])
        layout.append(Gtk.LinkButton(uri=COMMUNITY_URL, label="Abrir en el navegador para publicar o iniciar sesión"))
        web.set_vexpand(True)
        layout.append(web)
        window.set_child(layout)
        web.load_uri(COMMUNITY_URL)
        window.present()

    def equip(self):
        app = self.app
        folder = app.selected
        if not app.profile or app.microsoft_active:
            self.say(self.equip_text())
            return
        if not folder or folder not in app.instances:
            self.say("Elegí una instancia en la biblioteca para equipar la skin.")
            return
        if app.busy:
            self.say("Nova está ocupada con otra operación. Esperá a que termine y probá de nuevo.")
            return
        instance = dict(app.instances[folder])
        if instance["loader"] == "vanilla":
            self.say(self.equip_text())
            return
        if not skinlib.count_painted(self.pixels):
            self.say("Pintá o importá una skin antes de equiparla.")
            return
        data = pixbuf_from_pixels(self.pixels).save_to_bufferv("png", [], [])[1]
        player = app.profile
        extra = " Aviso: hay partes vacías en la capa base y se verán negras." if skinlib.base_has_holes(self.pixels, self.slim) else ""
        integraciones.run(app, self.window, "Equipar skin offline",
                          lambda: integraciones.equip(folder, instance, player, data),
                          f"Skin equipada para {player} en {instance['name']}.{extra}")

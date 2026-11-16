"""Nova window: the start screen shown while Minecraft opens (animated logo, steps and the real progress message)."""
import math

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import lanzamiento
import motor
from widgets import button, instance_art, label


def star_path(cr, cx, cy, radius):
    """The four-point star of Nova's logo: curved sides pulled toward the centre."""
    tips = ((0, -1), (1, 0), (0, 1), (-1, 0))
    controls = ((0.18, -0.18), (0.18, 0.18), (-0.18, 0.18), (-0.18, -0.18))
    cr.move_to(cx + tips[0][0] * radius, cy + tips[0][1] * radius)
    for i in range(4):
        p0, p1, c = tips[i], tips[(i + 1) % 4], controls[i]
        # a quadratic curve as a cubic one
        c1 = (p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1]))
        c2 = (p1[0] + 2 / 3 * (c[0] - p1[0]), p1[1] + 2 / 3 * (c[1] - p1[1]))
        cr.curve_to(cx + c1[0] * radius, cy + c1[1] * radius, cx + c2[0] * radius, cy + c2[1] * radius,
                    cx + p1[0] * radius, cy + p1[1] * radius)
    cr.close_path()


class LanzamientoMixin:
    def setup_launch_screen(self, frame):
        """Add the (hidden) start screen over the main window."""
        self.launch_step = 0
        self.launch_failed = False
        self.launch_started_at = 0.0
        self.launch_hide_id = 0
        self.launch_view = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.FILL, valign=Gtk.Align.FILL,
                                   css_classes=["launch-screen"], visible=False)
        self.launch_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER,
                                   valign=Gtk.Align.CENTER, vexpand=True, css_classes=["launch-card"])
        self.launch_art = Gtk.Box(halign=Gtk.Align.CENTER)
        self.launch_card.append(self.launch_art)
        self.launch_orbit = Gtk.DrawingArea(content_width=124, content_height=124, halign=Gtk.Align.CENTER)
        self.launch_orbit.set_draw_func(self.draw_orbit)
        self.launch_card.append(self.launch_orbit)
        self.launch_title = label("", "heading")
        self.launch_title.set_xalign(0.5)
        self.launch_card.append(self.launch_title)
        self.launch_sub = label("", "muted")
        self.launch_sub.set_xalign(0.5)
        self.launch_card.append(self.launch_sub)
        self.launch_steps = Gtk.DrawingArea(content_width=300, content_height=4 * 34, halign=Gtk.Align.CENTER,
                                            margin_top=8)
        self.launch_steps.set_draw_func(self.draw_steps)
        self.launch_card.append(self.launch_steps)
        self.launch_message = label("", "muted")
        self.launch_message.set_xalign(0.5)
        self.launch_message.set_wrap(True)
        self.launch_message.set_max_width_chars(46)
        self.launch_card.append(self.launch_message)
        actions = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=6)
        self.launch_hide = button("Ocultar", self.launch_screen_hide, "quiet-button")
        self.launch_log = button("Ver registro", self.launch_open_log, "quiet-button")
        self.launch_log.set_visible(False)
        actions.append(self.launch_log)
        actions.append(self.launch_hide)
        self.launch_card.append(actions)
        self.launch_view.append(self.launch_card)
        self.launch_view.update_property([Gtk.AccessibleProperty.LABEL], ["Iniciando Minecraft"])
        frame.add_overlay(self.launch_view)
        self.launch_orbit.add_tick_callback(self.launch_tick)

    # ---- drawing
    def launch_tick(self, widget, clock):
        if self.launch_view.get_visible():
            fade = min(1.0, (clock.get_frame_time() / 1e6 - self.launch_started_at) / 0.3)
            self.launch_view.set_opacity(fade if self.launch_hide_id == 0 else self.launch_view.get_opacity())
            if self.animations_on():
                widget.queue_draw()
                self.launch_steps.queue_draw()
        return GLib.SOURCE_CONTINUE

    @staticmethod
    def animations_on():
        from gi.repository import Gtk as _Gtk
        return bool(_Gtk.Settings.get_default().get_property("gtk-enable-animations"))

    def draw_orbit(self, area, cr, width, height):
        t = GLib.get_monotonic_time() / 1e6 if self.animations_on() else 0.0
        cr.scale(width / 150, height / 150)   # drawn on a 150 x 150 board, shown smaller
        cx, cy = 75, 75
        accent = (0.56, 0.84, 0.91)
        for radius, alpha in ((66, 0.20), (52, 0.32), (38, 0.5)):
            cr.set_source_rgba(*accent, alpha)
            cr.set_line_width(1.5)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()
        glow = 0.5 + 0.5 * math.sin(t * 2.4)
        cr.set_source_rgba(*accent, 0.10 + 0.10 * glow)
        cr.arc(cx, cy, 46, 0, 2 * math.pi)
        cr.fill()
        for index, (radius, speed, size) in enumerate(((66, 0.9, 4.5), (52, -1.4, 3.2))):
            angle = t * speed + index * 2.1
            cr.set_source_rgba(0.93, 0.94, 0.96, 0.95)
            cr.arc(cx + radius * math.cos(angle), cy + radius * math.sin(angle), size, 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgb(*accent)
        star_path(cr, cx, cy, 30 + 2 * glow)
        cr.fill()

    def draw_steps(self, area, cr, width, height):
        t = GLib.get_monotonic_time() / 1e6 if self.animations_on() else 0.0
        accent, dim = (0.56, 0.84, 0.91), (0.45, 0.49, 0.58)
        for index, name in enumerate(lanzamiento.STEPS):
            state = lanzamiento.state_of(index, self.launch_step, self.launch_failed)
            cy = index * 34 + 17
            cx = 18
            cr.new_path()
            if state == "done":
                cr.set_source_rgb(*accent)
                cr.arc(cx, cy, 11, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgb(0.03, 0.09, 0.11)
                cr.set_line_width(2.4)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.move_to(cx - 5, cy + 0.5)
                cr.line_to(cx - 1.5, cy + 4)
                cr.line_to(cx + 5.5, cy - 4)
                cr.stroke()
            elif state == "active":
                cr.set_source_rgba(*accent, 0.25)
                cr.set_line_width(2.4)
                cr.arc(cx, cy, 10, 0, 2 * math.pi)
                cr.stroke()
                cr.set_source_rgb(*accent)
                cr.arc(cx, cy, 10, t * 4, t * 4 + 1.6)
                cr.stroke()
            elif state == "failed":
                cr.set_source_rgb(1.0, 0.66, 0.6)
                cr.set_line_width(2.4)
                cr.arc(cx, cy, 10, 0, 2 * math.pi)
                cr.stroke()
                cr.move_to(cx - 4, cy - 4)
                cr.line_to(cx + 4, cy + 4)
                cr.move_to(cx + 4, cy - 4)
                cr.line_to(cx - 4, cy + 4)
                cr.stroke()
            else:
                cr.set_source_rgba(*dim, 0.7)
                cr.set_line_width(1.6)
                cr.arc(cx, cy, 9, 0, 2 * math.pi)
                cr.stroke()
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD if state == "active" else cairo.FONT_WEIGHT_NORMAL)
            cr.new_path()
            cr.set_font_size(15)
            cr.set_source_rgba(*(0.93, 0.94, 0.96) if state in ("active", "done") else dim, 1.0 if state != "pending" else 0.85)
            cr.move_to(cx + 24, cy + 5)
            cr.show_text(name)

    # ---- life cycle
    def launch_screen_enabled(self):
        return self.preferences.get("launch_screen", True)

    def launch_screen_show(self, folder, instance, profile):
        if not self.launch_screen_enabled():
            return
        if self.launch_hide_id:
            GLib.source_remove(self.launch_hide_id)
            self.launch_hide_id = 0
        while child := self.launch_art.get_first_child():
            self.launch_art.remove(child)
        art = instance_art(instance, 280, 96)
        art.set_halign(Gtk.Align.CENTER)
        self.launch_art.append(art)
        loader = motor.LOADERS.get(instance.get("loader"), instance.get("loader", ""))
        self.launch_title.set_text(instance["name"])
        self.launch_sub.set_text(f"Minecraft {instance['version']} · {loader} · {profile}")
        self.launch_step, self.launch_failed = 0, False
        self.launch_log.set_visible(False)
        self.launch_hide.set_label("Ocultar")
        self.launch_message.set_text("Preparando Minecraft…")
        self.launch_started_at = GLib.get_monotonic_time() / 1e6
        self.launch_view.set_opacity(0.0)
        self.launch_view.set_visible(True)
        self.launch_orbit.queue_draw()

    def launch_screen_update(self, message):
        if not self.launch_view.get_visible() or self.launch_failed:
            return
        step, text = lanzamiento.stage(message)
        self.launch_step = max(self.launch_step, step)
        self.launch_message.set_text(text)
        self.launch_steps.queue_draw()

    def launch_screen_started(self, minimized):
        """Minecraft's window is open: show the last step, then get out of the way."""
        if not self.launch_view.get_visible():
            return
        self.launch_step = len(lanzamiento.STEPS) - 1
        self.launch_message.set_text("Minecraft se abrió. ¡A jugar!")
        self.launch_steps.queue_draw()
        self.launch_hide_id = GLib.timeout_add(150 if minimized else 1400, self._launch_fade)

    def _launch_fade(self):
        self.launch_hide_id = 0
        self.launch_screen_hide()
        return False

    def launch_screen_failed(self, message):
        if not self.launch_view.get_visible():
            return
        self.launch_failed = True
        self.launch_message.set_text(message)
        self.launch_log.set_visible(True)
        self.launch_hide.set_label("Cerrar")
        self.launch_view.set_opacity(1.0)
        self.launch_steps.queue_draw()

    def launch_screen_hide(self):
        if self.launch_hide_id:
            GLib.source_remove(self.launch_hide_id)
            self.launch_hide_id = 0
        self.launch_view.set_visible(False)

    def launch_screen_finished(self, failed, message):
        """The game process ended: a failed start stays on screen with the reason, a normal end just hides it."""
        if failed and self.launch_view.get_visible() and self.launch_step < len(lanzamiento.STEPS) - 1:
            self.launch_screen_failed(message)
        else:
            self.launch_screen_hide()

    def launch_open_log(self):
        folder = getattr(self, "failed_log", None)
        if folder:
            import consola
            consola.open_console(self.window, folder)

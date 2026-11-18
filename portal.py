"""The game portal: choosing Minecraft or Roblox floods the window with that game's colour from the clicked point,
a glyph of the game blooms at the peak, the content changes underneath, and the colour drains out from the same point."""
import math
import random

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from widgets import motion_enabled, ms, tween

# (dark, light) colours of the flood and the glyph
LOOKS = {"minecraft": ((0.13, 0.36, 0.18), (0.42, 0.74, 0.30)), "roblox": ((0.55, 0.08, 0.11), (0.93, 0.27, 0.27))}
BUSY = []
GRASS = ((0.42, 0.76, 0.27), (0.36, 0.68, 0.22), (0.48, 0.82, 0.31))
DIRT = ((0.55, 0.38, 0.25), (0.48, 0.32, 0.2), (0.6, 0.43, 0.29), (0.42, 0.28, 0.18))


def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _glyph(cr, game, size, alpha):
    cr.set_source_rgba(1, 1, 1, alpha)
    if game == "minecraft":  # a pixel grass block: green top, dirt sides with a grass fringe
        k = size * 0.87
        top, ur, bottom, ll, ul, mid = (0, -size), (k, -size / 2), (0, size), (-k, size / 2), (-k, -size / 2), (0, 0)
        grid = 8
        rng = random.Random(7)  # the same pixels every time

        def face(origin, u_end, v_end, shade, palette, fringe):
            cr.save()
            cr.transform(cairo.Matrix(u_end[0] - origin[0], u_end[1] - origin[1], v_end[0] - origin[0],
                                      v_end[1] - origin[1], origin[0], origin[1]))
            for row in range(grid):
                for col in range(grid):
                    colour = palette[rng.randrange(len(palette))] if row >= fringe + (col * 5 % 3 == 0) else GRASS[rng.randrange(3)]
                    cr.set_source_rgba(colour[0] * shade, colour[1] * shade, colour[2] * shade, alpha)
                    cr.rectangle(col / grid, row / grid, 1 / grid + 0.012, 1 / grid + 0.012)
                    cr.fill()
            cr.restore()

        face(ul, top, mid, 1.0, GRASS, grid)
        face(ul, mid, ll, 0.8, DIRT, 2)
        face(mid, ur, bottom, 0.62, DIRT, 2)
    else:  # a tilted tile with a square cut out of it
        cr.rotate(math.radians(15))
        cr.rectangle(-size * 0.82, -size * 0.82, size * 1.64, size * 1.64)
        cr.rectangle(-size * 0.3, -size * 0.3, size * 0.6, size * 0.6)
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.fill()


def play(frame, origin, game, swap, duration=860):
    """Flood from `origin` (x, y in the frame), call swap() once at the peak, then drain. Without animations: just swap."""
    if not motion_enabled() or BUSY or game not in LOOKS:
        swap()
        return
    BUSY.append(1)
    deep, light = LOOKS[game]
    state = {"t": 0.0, "swapped": False}

    def draw(_area, cr, width, height, *_):
        t, (ox, oy) = state["t"], origin
        far = math.hypot(max(ox, width - ox), max(oy, height - oy)) * 1.02
        flood = _smooth(min(t / 0.5, 1.0)) if t < 0.5 else 1.0
        drain = _smooth((t - 0.52) / 0.48)
        paint = cairo.RadialGradient(ox, oy, 0, ox, oy, max(far * flood, 1))
        paint.add_color_stop_rgb(0, *light)
        paint.add_color_stop_rgb(0.55, *deep)
        paint.add_color_stop_rgb(1, *deep)
        cr.set_source(paint)
        if drain <= 0:
            cr.arc(ox, oy, far * flood, 0, 2 * math.pi)
            cr.fill()
            if flood < 1:  # a bright rim on the leading edge
                cr.set_source_rgba(*light, 0.7 * (1 - flood))
                cr.set_line_width(4)
                cr.arc(ox, oy, far * flood, 0, 2 * math.pi)
                cr.stroke()
        else:  # the whole window minus a hole that grows from the same point
            cr.rectangle(0, 0, width, height)
            cr.arc(ox, oy, far * drain, 0, 2 * math.pi)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            cr.set_source_rgba(*light, 0.6 * (1 - drain))
            cr.set_line_width(3)
            cr.arc(ox, oy, far * drain, 0, 2 * math.pi)
            cr.stroke()
        # the glyph blooms in the middle of the window while it is covered
        peak = math.sin(math.pi * min(max((t - 0.18) / 0.6, 0.0), 1.0))
        if peak > 0:
            cr.save()
            cr.translate(width / 2, height / 2)
            scale = 0.7 + 0.4 * _smooth((t - 0.18) / 0.6)
            cr.scale(scale, scale)
            _glyph(cr, game, 46, min(peak * 1.4, 1.0))
            cr.restore()

    area = Gtk.DrawingArea(hexpand=True, vexpand=True)  # it takes the clicks: no double triggers mid-portal
    area.set_draw_func(draw)
    frame.add_overlay(area)

    def step(t):
        state["t"] = t
        if t >= 0.5 and not state["swapped"]:
            state["swapped"] = True
            swap()
        area.queue_draw()

    def done():
        frame.remove_overlay(area)
        BUSY.clear()

    tween(area, ms(duration), step, done=done, curve=None)

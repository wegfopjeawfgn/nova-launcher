"""Shared GTK helpers for Nova."""
from functools import lru_cache
from pathlib import Path
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gtk

import motor
from progreso import size_text  # noqa: F401  (re-exported for the views)


HERE = Path(__file__).resolve().parent
RESOLUTIONS = ("854x480", "1280x720", "1600x900", "1920x1080", "2560x1440")


def resolution_field(value, automatic):
    combo = Gtk.ComboBoxText()
    combo.append("default", automatic)
    for size in RESOLUTIONS:
        combo.append(size, size.replace("x", " × "))
    combo.set_active_id(value if value in RESOLUTIONS else "default")
    return combo


@lru_cache(maxsize=24)
def cover_texture(path, width, height):
    pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), width, height, True)
    return Gdk.Texture.new_for_pixbuf(pixels)


# Boxes of the three bundled covers inside referencia.png (x, y, width, height).
DEFAULT_COVERS = ((303, 311, 376, 216), (713, 311, 370, 216), (1116, 311, 377, 216))  # inset: skip the sheet's frame


@lru_cache(maxsize=8)
def default_cover(index):
    x, y, width, height = DEFAULT_COVERS[index % len(DEFAULT_COVERS)]
    sheet = GdkPixbuf.Pixbuf.new_from_file(str(HERE / "referencia.png"))
    return Gdk.Texture.new_for_pixbuf(sheet.new_subpixbuf(x, y, width, height))


def hero_art(instance, height=260):
    """Wide banner: the custom cover when there is one, else a bundled cover. The scrolled window
    only caps the height; a Picture would otherwise grow to its own aspect ratio."""
    picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER)
    cover = instance.get("cover", "")
    path = motor.ROOT / "covers" / cover if re.fullmatch(r"[a-f0-9]{64}\.png", cover) else None
    picture.set_paintable(default_cover(instance["artwork"]))
    try:
        if path and path.is_file():
            picture.set_paintable(cover_texture(path, 1600, height * 2))
    except GLib.Error:
        pass
    frame = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.NEVER,
                               min_content_height=height, max_content_height=height, can_target=False)
    frame.set_child(picture)
    return frame


def motion_enabled():
    return Gtk.Settings.get_default().get_property("gtk-enable-animations")


def enter(widget, delay=0):
    """Fade and rise into place. The `entering` class holds the start state; removing it lets the
    CSS transition run, so an interrupted entrance retargets instead of restarting."""
    if not motion_enabled():
        return
    widget.add_css_class("entering")

    def settle():
        widget.remove_css_class("entering")
        return False

    GLib.timeout_add(48 + delay, settle)


def instance_art(instance, width=-1, height=145):
    picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER, width_request=width,
                          height_request=height, css_classes=["instance-cover"])
    picture.set_overflow(Gtk.Overflow.HIDDEN)
    picture.set_paintable(default_cover(instance["artwork"]))
    cover = instance.get("cover", "")
    if re.fullmatch(r"[a-f0-9]{64}\.png", cover):
        path = motor.ROOT / "covers" / cover
        if path.is_file():
            try:
                picture.set_paintable(cover_texture(path, width * 2 if width > 0 else 768, height * 2))
            except GLib.Error:
                pass
    return picture


def label(value, style=None):
    widget = Gtk.Label(label=value, xalign=0)
    if style:
        widget.add_css_class(style)
    return widget


def button(value, action, style=None):
    widget = Gtk.Button(label=value)
    widget.connect("clicked", lambda _: action())
    if style:
        widget.add_css_class(style)
    return widget


def feature_button(title, detail, action):
    tile = button("", action, "feature")
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    content.append(label(title, "feature-title"))
    description = label(detail, "muted")
    description.set_wrap(True)
    content.append(description)
    tile.set_child(content)
    tile.update_property([Gtk.AccessibleProperty.LABEL], [title])
    return tile

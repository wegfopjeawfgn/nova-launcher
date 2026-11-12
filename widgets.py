"""Shared GTK helpers for Nova."""
from functools import lru_cache
from pathlib import Path
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gtk

import motor


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


def instance_art(instance, width=-1, height=145):
    frame = Gtk.Overlay(width_request=width, height_request=height)
    background = Gtk.Box(css_classes=[f"art{instance['artwork']}"])
    frame.set_child(background)
    picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER,
                          css_classes=["instance-cover"])
    frame.add_overlay(picture)
    cover = instance.get("cover", "")
    if re.fullmatch(r"[a-f0-9]{64}\.png", cover):
        path = motor.ROOT / "covers" / cover
        if path.is_file():
            try:
                picture.set_paintable(cover_texture(path, width * 2 if width > 0 else 768, height * 2))
            except GLib.Error:
                pass
    return frame


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

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


# Boxes of the three bundled covers inside referencia.png (x, y, width, height).
DEFAULT_COVERS = ((303, 311, 376, 216), (713, 311, 370, 216), (1116, 311, 377, 216))  # inset: skip the sheet's frame


@lru_cache(maxsize=1)
def _default_covers():
    """Decode the sheet once and cut all the covers from it, instead of decoding it again for each cover."""
    sheet = GdkPixbuf.Pixbuf.new_from_file(str(HERE / "referencia.png"))
    return tuple(Gdk.Texture.new_for_pixbuf(sheet.new_subpixbuf(*box)) for box in DEFAULT_COVERS)


def default_cover(index):
    return _default_covers()[index % len(DEFAULT_COVERS)]


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


def content_tile(title, count, manage, explore, import_files):
    """A shelf for one kind of content: the count opens the installed list; two actions add more."""
    tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["shelf-tile"])
    main = button("", manage, "shelf-main")
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, halign=Gtk.Align.START)
    inner.append(label(title, "shelf-title"))
    figures = Gtk.Box(spacing=6)
    figures.append(label(str(count), "shelf-count"))
    unit = label("instalado" if count == 1 else "instalados", "shelf-unit")
    unit.set_valign(Gtk.Align.END)
    figures.append(unit)
    inner.append(figures)
    main.set_child(inner)
    main.update_property([Gtk.AccessibleProperty.LABEL], [f"Gestionar {title}: {count} instalados"])
    tile.append(main)
    actions = Gtk.Box(spacing=6, css_classes=["shelf-actions"], homogeneous=True)
    explore_button = button("Explorar", explore, "shelf-action")
    explore_button.set_tooltip_text(f"Buscar {title.lower()} en Modrinth")
    explore_button.update_property([Gtk.AccessibleProperty.LABEL], [f"Explorar {title.lower()} en Modrinth"])
    import_button = button("Importar", import_files, "shelf-action")
    import_button.set_tooltip_text(f"Añadir {title.lower()} desde archivos de este equipo")
    import_button.update_property([Gtk.AccessibleProperty.LABEL], [f"Importar {title.lower()} desde el equipo"])
    actions.append(explore_button)
    actions.append(import_button)
    tile.append(actions)
    return tile


def stat_tile(title, value):
    tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["shelf-tile", "shelf-stat"])
    tile.append(label(title, "shelf-title"))
    tile.append(label(value, "shelf-count"))
    return tile


def feature_button(title, detail, action):
    tile = button("", action, "feature")
    content = Gtk.Box(spacing=12)
    texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
    texts.append(label(title, "feature-title"))
    description = label(detail, "muted")
    description.set_wrap(True)
    texts.append(description)
    content.append(texts)
    chevron = Gtk.Image.new_from_icon_name("go-next-symbolic")
    chevron.add_css_class("feature-chevron")
    chevron.set_valign(Gtk.Align.CENTER)
    content.append(chevron)
    tile.set_child(content)
    tile.update_property([Gtk.AccessibleProperty.LABEL], [title])
    return tile

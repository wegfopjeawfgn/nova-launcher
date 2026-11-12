"""Nova window: pick a detected Java installation for an entry field."""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import java_detect
import motor
from widgets import label, button


def required_java(version):
    """Java major version a Minecraft version asks for, when its metadata is already downloaded."""
    shared = motor.ROOT / "minecraft" / "versions" / str(version) / f"{version}.json"
    value = motor.read(shared, {}).get("javaVersion", {}).get("majorVersion")
    return value if isinstance(value, int) else None


def java_picker(entry, get_version):
    """A menu button that lists the Java installations found on this computer and fills `entry`."""
    picker = Gtk.MenuButton(label="Elegir un Java instalado", halign=Gtk.Align.START)
    popover = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["action-menu"])
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                  max_content_height=320, min_content_width=360)
    scroller.set_child(box)
    popover.set_child(scroller)
    picker.set_popover(popover)
    token = [0]

    def choose(path):
        entry.set_text(path)
        popover.popdown()

    def render(mine, found, required):
        if mine != token[0]:
            return
        while (child := box.get_first_child()):
            box.remove(child)
        box.append(button("Dejar vacío (Java administrado por Nova)", lambda: choose("")))
        if not found:
            box.append(label("No se encontró ningún Java instalado.", "muted"))
        for info in found:
            control = button(java_detect.label(info, required), lambda path=info["path"]: choose(path))
            child = control.get_child()
            if isinstance(child, Gtk.Label):
                child.set_xalign(0)
                child.set_wrap(True)
                child.set_max_width_chars(48)
            box.append(control)

    def show(*_):
        token[0] += 1
        mine = token[0]
        while (child := box.get_first_child()):
            box.remove(child)
        box.append(label("Buscando…", "muted"))
        required = required_java(get_version())

        def worker():
            found = java_detect.find_java()
            GLib.idle_add(render, mine, found, required)

        threading.Thread(target=worker, daemon=True).start()

    popover.connect("show", show)
    return picker

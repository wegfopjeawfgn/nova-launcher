"""Nova window: screens shown inside the main window instead of as separate windows."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

import i18n
from widgets import button, label

NAV_ALIASES = {"Sesiones de juego": "Sesiones", "Editor de skins": "Skins", "Explorar Modrinth": "Explorar",
               "Modpacks en Modrinth": "Modpacks"}


class PaginasMixin:
    def setup_pages(self, library):
        self.page_stack = Gtk.Stack(hexpand=True, vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE,
                                    transition_duration=200)
        self.page_stack.add_named(library, "library")
        self.current_page = None
        self.page_serial = 0
        return self.page_stack

    def show_page(self, win):
        """Take over a window that would have been presented and show its content here.
        Its close/destroy calls keep working, so the code that built it needs no changes."""
        if self.current_page and self.current_page[0] is win:
            return
        if self.current_page and self.current_page[0].get_title() == win.get_title():
            return  # a double click or a repeated request: keep the page already open
        if self.current_page and not self.leave_page(switch=False):
            return  # the page on screen refused to close (it is busy)
        child = win.get_child()
        win.set_child(None)
        title = win.get_title() or ""
        header = Gtk.Box(spacing=12, css_classes=["page-header"])
        back = button("", lambda: self.leave_page(win), "quiet-button")
        content = Gtk.Box(spacing=6)
        content.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
        content.append(label("Volver"))
        back.set_child(content)
        back.update_property([Gtk.AccessibleProperty.LABEL], ["Volver a la biblioteca"])
        header.append(back)
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["page"])
        page.append(header)
        child.set_vexpand(True)
        child.set_hexpand(True)
        page.append(child)
        self.page_serial += 1
        name = f"page{self.page_serial}"  # unique: a page that is still fading out must not shadow the new one
        self.page_stack.add_named(page, name)
        self.page_stack.set_visible_child_name(name)
        self.current_page = (win, page)
        win.present = lambda: None
        win.close = lambda: self.leave_page(win)
        win.destroy = lambda: self.leave_page(win, force=True)
        self.mark_nav(NAV_ALIASES.get(title, title))

    def leave_page(self, win=None, force=False, switch=True):
        if not self.current_page or (win is not None and self.current_page[0] is not win):
            return True
        current, page = self.current_page
        if not force and current.emit("close-request"):
            return False
        self.current_page = None
        if switch:
            self.page_stack.set_visible_child_name("library")
            self.mark_nav("Instancias")
        GLib.timeout_add(300, lambda: (page.get_parent() is self.page_stack and self.page_stack.remove(page), False)[1])
        return True

    def mark_nav(self, title):
        title = i18n.tr(title)
        button_ = self.nav_box.get_first_child()
        while button_:
            if isinstance(button_, Gtk.Button):
                texts = [w.get_label() for w in _labels(button_)]
                if title in texts:
                    button_.add_css_class("nav-active")
                else:
                    button_.remove_css_class("nav-active")
            button_ = button_.get_next_sibling()


def _labels(widget):
    child = widget.get_first_child()
    while child:
        if isinstance(child, Gtk.Label):
            yield child
        yield from _labels(child)
        child = child.get_next_sibling()

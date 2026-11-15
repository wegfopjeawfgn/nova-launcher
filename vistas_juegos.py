"""Nova window: choose a game (Minecraft or Roblox) and the Roblox screen."""
import threading

from pathlib import Path

import gi
import requests

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gtk

import motor
import roblox
from widgets import button, default_cover, label

HERE = Path(__file__).resolve().parent
MY_TABS = (("favs", "Favoritos"), ("recent", "Recientes"))


def _texture(url):
    loader = GdkPixbuf.PixbufLoader()
    loader.write(requests.get(url, timeout=15).content)
    loader.close()
    return Gdk.Texture.new_for_pixbuf(loader.get_pixbuf())


class JuegosMixin:
    def setup_games(self):
        """Build the chooser and the Roblox screen once; open the remembered game or ask."""
        self.roblox_loaded = False
        self.roblox_data = {}
        self.roblox_tab = "top-trending"
        self.roblox_serial = 0
        self.page_stack.add_named(self._chooser(), "games")
        self.page_stack.add_named(self._roblox_page(), "roblox")
        game = self.preferences.get("game")
        if self.preferences.get("remember_game") and game in ("minecraft", "roblox"):
            self.choose_game(game, save=False)
        else:
            self.show_games()
        self._load_roblox_cover()

    def show_games(self):
        self.sidebar.set_visible(False)
        self.page_stack.set_visible_child_name("games")

    def choose_game(self, game, save=True):
        if save:
            self.preferences = {**self.preferences, "game": game, "remember_game": self.remember_check.get_active()}
            motor.save(motor.ROOT / "settings.json", self.preferences)
        if game == "roblox":
            self.sidebar.set_visible(False)
            self.page_stack.set_visible_child_name("roblox")
            if not self.roblox_loaded:
                self.roblox_loaded = True
                self.roblox_open_tab("top-trending")
        else:
            self.sidebar.set_visible(True)
            self.page_stack.set_visible_child_name("library")

    # ---- chooser

    def _cover(self):
        picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER)
        # the frame fixes the size: a Picture alone grows to its image's own aspect ratio
        frame = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                   width_request=320, height_request=170, child=picture, css_classes=["instance-cover"])
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.picture = picture
        return frame

    def _chooser(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, halign=Gtk.Align.CENTER,
                      valign=Gtk.Align.CENTER, css_classes=["page"])
        title = label("¿A qué querés jugar?", "heading")
        title.set_xalign(0.5)
        box.append(title)
        row = Gtk.Box(spacing=20, halign=Gtk.Align.CENTER)
        minecraft_cover = self._cover()
        minecraft_cover.picture.set_paintable(default_cover(0))
        self.roblox_cover = self._cover()
        for key, name, note, cover in (("minecraft", "Minecraft", "Instancias, mods y Mi servidor", minecraft_cover),
                                       ("roblox", "Roblox", "Explorá y entrá directo a un juego", self.roblox_cover)):
            tile = button("", lambda k=key: self.choose_game(k), "card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            inner.append(cover)
            inner.append(label(name, "card-label"))
            meta = label(note, "card-meta")
            meta.set_margin_bottom(12)
            meta.set_margin_start(0)
            inner.append(meta)
            tile.set_child(inner)
            row.append(tile)
        box.append(row)
        self.remember_check = Gtk.CheckButton(label="Recordar mi elección", halign=Gtk.Align.CENTER,
                                              active=bool(self.preferences.get("remember_game")))
        box.append(self.remember_check)
        return box

    def _load_roblox_cover(self):
        def work():
            try:
                self.roblox_data = roblox.categories()
                texture = _texture(roblox.wide_cover(self.roblox_data["top-trending"][0]["universe"]))
            except Exception:  # no network: the tile just stays plain
                return
            GLib.idle_add(self.roblox_cover.picture.set_paintable, texture)

        threading.Thread(target=work, daemon=True).start()

    # ---- Roblox screen

    def _roblox_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["page"])
        header = Gtk.Box(spacing=10)
        header.append(button("Cambiar de juego", self.show_games, "quiet-button"))
        title = label("Roblox", "heading")
        title.set_hexpand(True)
        header.append(title)
        page.append(header)
        state, note = roblox.launcher_state()
        page.append(label(note, "muted" if state == "ready" else "status-error"))
        self.roblox_entry = Gtk.SearchEntry(placeholder_text="Buscar un juego, o pegá su enlace de roblox.com")
        self.roblox_entry.connect("activate", lambda e: self.roblox_submit(e.get_text()))
        page.append(self.roblox_entry)
        tabs = Gtk.Box(spacing=6)
        self.roblox_tabs = {}
        for key, name in roblox.CATEGORIES + MY_TABS:
            tab = button(name, lambda k=key: self.roblox_open_tab(k), "game-tab")
            self.roblox_tabs[key] = tab
            tabs.append(tab)
        page.append(tabs)
        self.roblox_status = label("", "muted")
        page.append(self.roblox_status)
        self.roblox_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                       min_children_per_line=2, max_children_per_line=6, row_spacing=12,
                                       column_spacing=12, valign=Gtk.Align.START)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.roblox_grid)
        page.append(scroll)
        return page

    def roblox_open_tab(self, key):
        self.roblox_tab = key
        self.roblox_entry.set_text("")
        for name, tab in self.roblox_tabs.items():
            tab.set_css_classes(["game-tab", "active"] if name == key else ["game-tab"])
        self.roblox_serial += 1
        if key in ("favs", "recent"):
            games = self.preferences.get("roblox_favs" if key == "favs" else "roblox_recent", [])
            empty = ("Todavía no marcaste favoritos: tocá la estrella de un juego." if key == "favs"
                     else "Acá van los juegos que abrís desde Nova.")
            self.roblox_show(self.roblox_serial, games, {}, empty)
            self.roblox_fetch_icons(self.roblox_serial, games, empty)
        elif key in self.roblox_data:
            games = self.roblox_data[key]
            self.roblox_show(self.roblox_serial, games, {}, "")
            self.roblox_fetch_icons(self.roblox_serial, games, "")
        else:
            self.roblox_load("", key)

    def roblox_submit(self, text):
        place = roblox.parse_place(text)
        if place:
            self.roblox_play({"place": place, "name": f"Juego {place}", "universe": None, "players": 0})
        elif text.strip():
            self.roblox_load(text.strip(), None)

    def roblox_play(self, game):
        try:
            roblox.play(game["place"])
        except (RuntimeError, OSError, ValueError) as error:
            self.roblox_status.set_text(f"No pude abrir Roblox: {error}")
            return
        self.roblox_status.set_text("Abriendo el juego… si es la primera vez, iniciá sesión en la ventana de Roblox.")
        recent = [g for g in self.preferences.get("roblox_recent", []) if g.get("place") != game["place"]]
        self._save_roblox({"roblox_recent": [game] + recent[:19]})

    def roblox_toggle_fav(self, game):
        favs = self.preferences.get("roblox_favs", [])
        if any(g.get("place") == game["place"] for g in favs):
            favs = [g for g in favs if g.get("place") != game["place"]]
        else:
            favs = [game] + favs
        self._save_roblox({"roblox_favs": favs})
        self.roblox_open_tab(self.roblox_tab) if self.roblox_tab in self.roblox_tabs else None

    def _save_roblox(self, changes):
        self.preferences = {**self.preferences, **changes}
        motor.save(motor.ROOT / "settings.json", self.preferences)

    def roblox_load(self, query, key):
        self.roblox_status.set_text("Buscando…" if query else "Cargando…")
        self.roblox_serial += 1
        serial = self.roblox_serial
        if query:
            for tab in self.roblox_tabs.values():
                tab.set_css_classes(["game-tab"])

        def work():
            try:
                if query:
                    games = roblox.search(query)
                else:
                    self.roblox_data = roblox.categories()
                    games = self.roblox_data.get(key, [])
                icons = roblox.icons([g["universe"] for g in games])
            except Exception as error:  # network or API change: say so, never crash the window
                GLib.idle_add(self.roblox_failed, serial, str(error))
                return
            GLib.idle_add(self.roblox_show, serial, games, icons, "No encontré juegos con eso.")

        threading.Thread(target=work, daemon=True).start()

    def roblox_fetch_icons(self, serial, games, empty):
        """Cached lists show at once; their icons arrive in the background."""
        def work():
            try:
                icons = roblox.icons([g.get("universe") for g in games])
            except Exception:
                return
            GLib.idle_add(self.roblox_show, serial, games, icons, empty)

        threading.Thread(target=work, daemon=True).start()

    def roblox_failed(self, serial, error):
        if serial == self.roblox_serial:
            self.roblox_status.set_text(f"No pude cargar los juegos ({error}). Igual podés pegar un enlace.")
        return False

    def roblox_show(self, serial, games, icons, empty):
        if serial != self.roblox_serial:
            return False
        child = self.roblox_grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.roblox_grid.remove(child)
            child = nxt
        self.roblox_status.set_text("" if games else empty)
        favs = {g.get("place") for g in self.preferences.get("roblox_favs", [])}
        for game in games:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["game-card"], width_request=170)
            picture = Gtk.Picture(width_request=150, height_request=150, halign=Gtk.Align.CENTER, can_shrink=False)
            overlay = Gtk.Overlay(child=picture)
            fav = game["place"] in favs
            star = Gtk.Button(css_classes=["game-star"], halign=Gtk.Align.END, valign=Gtk.Align.START,
                              tooltip_text="Quitar de favoritos" if fav else "Marcar como favorito",
                              child=Gtk.Image.new_from_file(str(HERE / "icons" / ("estrella-llena.svg" if fav else "estrella.svg"))))
            star.update_property([Gtk.AccessibleProperty.LABEL], [f"Favorito: {game['name']}"])
            star.connect("clicked", lambda _, g=game: self.roblox_toggle_fav(g))
            overlay.add_overlay(star)
            card.append(overlay)
            name = label(game["name"], "card-label")
            name.set_wrap(True)
            name.set_lines(2)
            name.set_max_width_chars(16)
            name.set_ellipsize(3)
            name.set_valign(Gtk.Align.START)
            name.set_size_request(-1, 44)  # two lines for every card, so the Jugar buttons line up
            card.append(name)
            if game.get("players"):
                card.append(label(f"{game['players']:,} jugando".replace(",", "."), "card-meta"))
            card.append(button("Jugar", lambda g=game: self.roblox_play(g), "game-play"))
            self.roblox_grid.append(card)
            url = icons.get(game.get("universe"))
            if url:
                threading.Thread(target=self._roblox_icon, args=(url, picture), daemon=True).start()
        return False

    def _roblox_icon(self, url, picture):
        try:
            texture = _texture(url)
        except Exception:
            return
        GLib.idle_add(picture.set_paintable, texture)

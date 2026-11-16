"""Nova window: choose a game (Minecraft or Roblox) and the Roblox screen."""
import threading

from pathlib import Path

import gi
import requests

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gio, Gtk

import motor
import roblox
import roblox_cuenta
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
        self.roblox_prices = {}
        self.current_game = "minecraft"
        self.library_query.connect("activate", self._search_activate)
        self.page_stack.add_named(self._chooser(), "games")
        self.page_stack.add_named(self._roblox_page(), "roblox")
        game = self.preferences.get("game")
        if self.preferences.get("remember_game") and game in ("minecraft", "roblox"):
            self.choose_game(game, save=False)
        else:
            self.show_games()
        self._load_roblox_cover()

    def _chrome(self, game):
        """The sidebar and Minecraft account belong to Minecraft; the top search follows the game on screen
        (game is "minecraft", "roblox" or None for the chooser)."""
        self.sidebar.set_visible(game == "minecraft")
        self.accounts.set_visible(game == "minecraft")
        self.library_query.set_visible(game is not None)
        if game != getattr(self, "current_game", None):
            self.current_game = game
            self.library_query.set_text("")
            if game:
                self.library_query.set_placeholder_text("Buscar un juego o pegar un enlace de Roblox" if game == "roblox"
                                                        else "Buscar instancias")

    def _search_activate(self, entry):
        if getattr(self, "current_game", None) == "roblox":
            self.roblox_submit(entry.get_text())

    def show_games(self):
        self._chrome(None)
        self.page_stack.set_visible_child_name("games")

    def choose_game(self, game, save=True):
        if save:
            self.preferences = {**self.preferences, "game": game, "remember_game": self.remember_check.get_active()}
            motor.save(motor.ROOT / "settings.json", self.preferences)
        if game == "roblox":
            self._chrome("roblox")
            self.page_stack.set_visible_child_name("roblox")
            self.roblox_render_account()
            self._roblox_load_first()
        else:
            self._chrome("minecraft")
            self.page_stack.set_visible_child_name("library")

    def _roblox_load_first(self):
        """Nothing of Roblox (catalog, friends) is fetched or shown until the person has signed in."""
        if self.roblox_person and not self.roblox_loaded:
            self.roblox_loaded = True
            last = self.preferences.get("roblox_tab")
            self.roblox_open_tab(last if last in self.roblox_tabs else "top-trending")

    # ---- chooser

    def _cover(self, width=320, height=170):
        picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.COVER)
        # the frame fixes the size: a Picture alone grows to its image's own aspect ratio
        frame = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.NEVER,
                                   width_request=width, height_request=height, child=picture, css_classes=["instance-cover"])
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
            GLib.idle_add(self.gate_cover.picture.set_paintable, texture)

        threading.Thread(target=work, daemon=True).start()

    # ---- Roblox screen

    def _roblox_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["page"])
        header = Gtk.Box(spacing=10)
        back = button("", self.show_games, "roblox-back")
        back_row = Gtk.Box(spacing=6)
        back_row.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
        back_row.append(label("Cambiar de juego"))
        back.set_child(back_row)
        back.update_property([Gtk.AccessibleProperty.LABEL], ["Cambiar de juego"])
        header.append(back)
        title = label("Roblox", "heading")
        title.set_hexpand(True)
        header.append(title)
        page.append(header)
        self.roblox_stack = Gtk.Stack(vexpand=True)
        self.roblox_stack.add_named(self._gate(), "gate")
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.roblox_stack.add_named(content, "content")
        page.append(self.roblox_stack)
        state, note = roblox.launcher_state()
        content.append(label(note, "muted" if state == "ready" else "status-error"))
        content.append(self._account_bar())
        content.append(self._friends_strip())
        tabs = Gtk.Box(spacing=6)
        self.roblox_tabs = {}
        for key, name in roblox.CATEGORIES + MY_TABS:
            tab = button(name, lambda k=key: self.roblox_open_tab(k), "game-tab")
            self.roblox_tabs[key] = tab
            tabs.append(tab)
        content.append(tabs)
        self.roblox_status = label("", "muted")
        content.append(self.roblox_status)
        self.roblox_render_friends()
        self.roblox_render_account()
        self.roblox_grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                       min_children_per_line=2, max_children_per_line=6, row_spacing=12,
                                       column_spacing=12, valign=Gtk.Align.START)
        self.roblox_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.roblox_scroll.set_child(self.roblox_grid)
        self.roblox_shown = ()
        content.append(self.roblox_scroll)
        return page

    def roblox_open_tab(self, key):
        self.roblox_tab = key
        if self.preferences.get("roblox_tab") != key:
            self._save_roblox({"roblox_tab": key})
        self.library_query.set_text("")
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
                self.roblox_prices.update(roblox.prices([g["universe"] for g in games]))
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
                self.roblox_prices.update(roblox.prices([g.get("universe") for g in games]))
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
        shown = tuple(g["place"] for g in games)
        if shown != self.roblox_shown:  # a new list starts at the top; the same list gaining icons keeps its scroll
            self.roblox_shown = shown
            for delay in (0, 300):  # the cards are measured a moment after they are added
                GLib.timeout_add(delay, lambda: self.roblox_scroll.get_vadjustment().set_value(0) or False)
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
                meta = f"{game['players']:,} jugando".replace(",", ".")
                if game.get("rating"):
                    meta += f" · {game['rating']} % positivo"
                card.append(label(meta, "card-meta"))
            price = self.roblox_prices.get(game.get("universe"))
            play = button(f"De pago · R$ {price:,}".replace(",", ".") if price else "Jugar",
                          lambda g=game: self.roblox_play(g), "game-play")
            if price:
                play.set_tooltip_text("Juego de pago. Nova no sabe si ya lo tenés: Roblox te pide comprarlo si hace falta.")
                play.add_css_class("paid")
            card.append(play)
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

    # ---- friends: a row on top, like Roblox's home. The list is yours: Roblox decides if you may join.

    def roblox_friends(self):
        return self.preferences.get("roblox_friend_list", [])

    def _friends_strip(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        head = Gtk.Box(spacing=10)
        title = label("Amigos", "card-label")
        title.set_hexpand(True)
        head.append(title)
        self.friend_hint = label("", "card-meta")
        self.friend_hint.set_valign(Gtk.Align.END)
        head.append(self.friend_hint)
        box.append(head)
        self.friend_row = Gtk.Box(spacing=14)
        scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER, height_request=104, child=self.friend_row)
        box.append(scroll)
        self.friend_entry = Gtk.Entry(placeholder_text="Nombre de usuario de Roblox de tu amigo", visible=False)
        self.friend_entry.connect("activate", lambda e: self.roblox_add_friend(e.get_text()))
        box.append(self.friend_entry)
        self.friend_status = label("", "muted")
        self.friend_status.set_visible(False)
        box.append(self.friend_status)
        return box

    def roblox_render_friends(self):
        while child := self.friend_row.get_first_child():
            self.friend_row.remove(child)
        friends = self.roblox_friends()
        self.friend_hint.set_text("Tocá uno para unirte a su partida. Roblox decide si podés." if friends
                                  else "Agregá a tus amigos por su nombre de usuario para unirte a sus partidas.")
        pictures = []
        for friend in friends:
            tile = Gtk.Overlay()
            chip = Gtk.Button(css_classes=["friend-chip"], tooltip_text=f"Unirme a {friend['display']}")
            chip.update_property([Gtk.AccessibleProperty.LABEL], [f"Unirme a {friend['display']}"])
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
            picture = Gtk.Picture(width_request=60, height_request=60, can_shrink=True, content_fit=Gtk.ContentFit.COVER,
                                  halign=Gtk.Align.CENTER, css_classes=["friend-avatar"])
            picture.set_overflow(Gtk.Overflow.HIDDEN)
            pictures.append(picture)
            inner.append(picture)
            name = label(friend["display"], "card-meta")
            name.set_ellipsize(3)
            name.set_max_width_chars(9)
            name.set_xalign(0.5)
            inner.append(name)
            chip.set_child(inner)
            chip.connect("clicked", lambda _, f=friend: self.roblox_join(f))
            tile.set_child(chip)
            gone = Gtk.Button(css_classes=["game-star"], halign=Gtk.Align.END, valign=Gtk.Align.START, tooltip_text="Quitar de la lista",
                              child=Gtk.Image.new_from_file(str(HERE / "icons" / "quitar.svg")))
            gone.update_property([Gtk.AccessibleProperty.LABEL], [f"Quitar a {friend['display']}"])
            gone.connect("clicked", lambda _, i=friend["id"]: self.roblox_remove_friend(i))
            tile.add_overlay(gone)
            self.friend_row.append(tile)
        add = Gtk.Button(css_classes=["friend-chip"], tooltip_text="Agregar un amigo")
        add.update_property([Gtk.AccessibleProperty.LABEL], ["Agregar un amigo"])
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
        plus = Gtk.Image.new_from_file(str(HERE / "icons" / "mas.svg"))
        plus.set_pixel_size(28)
        plus.set_size_request(60, 60)
        plus.add_css_class("friend-avatar")
        inner.append(plus)
        inner.append(label("Agregar", "card-meta"))
        add.set_child(inner)
        add.connect("clicked", lambda _: self._toggle_friend_entry())
        self.friend_row.append(add)
        if friends:
            self._friend_headshots(friends, pictures)

    def _toggle_friend_entry(self):
        show = not self.friend_entry.get_visible()
        self.friend_entry.set_visible(show)
        self.friend_status.set_visible(show)
        if show:
            self.friend_entry.grab_focus()

    def _friend_headshots(self, friends, pictures):
        def work():
            try:
                urls = roblox.headshots([f["id"] for f in friends])
                for friend, picture in zip(friends, pictures):
                    if friend["id"] in urls:
                        GLib.idle_add(picture.set_paintable, _texture(urls[friend["id"]]))
            except Exception:  # no avatars is fine: the names still work
                return

        threading.Thread(target=work, daemon=True).start()

    def roblox_add_friend(self, text):
        name = text.strip().lstrip("@")
        if not name:
            return
        self.friend_status.set_text(f"Buscando a {name}…")

        def work():
            try:
                user = roblox.find_user(name)
            except Exception as error:
                GLib.idle_add(self.friend_status.set_text, f"No pude buscar ahora ({error}).")
                return
            GLib.idle_add(self._friend_found, name, user)

        threading.Thread(target=work, daemon=True).start()

    def _friend_found(self, name, user):
        if not user:
            self.friend_status.set_text(f"No encontré a «{name}» en Roblox. Revisá que el nombre de usuario esté bien escrito.")
            return False
        friends = [f for f in self.roblox_friends() if f["id"] != user["id"]]
        self._save_roblox({"roblox_friend_list": friends + [user]})
        self.friend_entry.set_text("")
        self.friend_status.set_text(f"Agregaste a {user['display']}.")
        self.roblox_render_friends()
        return False

    def roblox_remove_friend(self, user_id):
        self._save_roblox({"roblox_friend_list": [f for f in self.roblox_friends() if f["id"] != user_id]})
        self.roblox_render_friends()

    def roblox_join(self, friend):
        try:
            roblox.join_friend(friend["id"])
        except (RuntimeError, OSError, ValueError) as error:
            self.roblox_status.set_text(f"No pude abrir Roblox: {error}")
            return
        self.roblox_status.set_text(f"Abriendo Roblox para unirte a {friend['display']}… Si no está jugando o no te deja unirte, Roblox te avisa.")

    # ---- Roblox account: the official sign-in (name and avatar only)

    def _gate(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                      css_classes=["game-card", "gate"], width_request=420)
        self.gate_cover = self._cover(396, 190)
        box.append(self.gate_cover)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=16, margin_start=6, margin_end=6, margin_bottom=6)
        title = label("Entrá a Roblox", "heading")
        body.append(title)
        self.account_note = label("Iniciá sesión o registrate en la página oficial de Roblox, autorizá y volvé a Nova.", "muted")
        self.account_note.set_wrap(True)
        self.account_note.set_max_width_chars(44)
        body.append(self.account_note)
        for line in ("Nova no ve tu contraseña.", "Solo recibe tu nombre y tu avatar."):
            body.append(label(line, "card-meta"))
        self.login_button = button("Iniciar sesión con Roblox", self.roblox_sign_in, "primary")
        self.login_button.set_margin_top(8)
        body.append(self.login_button)
        signup = button("Registrarme", lambda: Gio.AppInfo.launch_default_for_uri(roblox_cuenta.SIGN_UP, None), "quiet-button")
        body.append(signup)
        box.append(body)
        return box

    def _account_bar(self):
        self.account_bar = Gtk.Box(spacing=12, css_classes=["game-card"])
        self.roblox_person = roblox_cuenta.load()
        return self.account_bar

    def roblox_client_id(self):
        return self.preferences.get("roblox_client_id") or roblox_cuenta.DEFAULT_CLIENT_ID

    def roblox_render_account(self):
        """Signed in: the catalog, friends and the greeting. Signed out: only the sign-in card."""
        person = self.roblox_person
        self.roblox_stack.set_visible_child_name("content" if person else "gate")
        if getattr(self, "current_game", None) == "roblox":
            self.library_query.set_visible(bool(person))
        bar = self.account_bar
        while child := bar.get_first_child():
            bar.remove(child)
        if not person:
            return
        picture = Gtk.Picture(width_request=44, height_request=44, can_shrink=True, content_fit=Gtk.ContentFit.COVER,
                              css_classes=["friend-avatar"])
        picture.set_overflow(Gtk.Overflow.HIDDEN)
        bar.append(picture)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        texts.append(label(f"Hola, {person['display']}", "card-label"))
        texts.append(label(f"@{person['name']} · Nova solo ve tu nombre y tu avatar", "card-meta"))
        bar.append(texts)
        bar.append(button("Cerrar sesión", self.roblox_sign_out, "roblox-back"))
        if person.get("picture"):
            threading.Thread(target=self._account_picture, args=(person["picture"], picture), daemon=True).start()

    def _account_picture(self, url, picture):
        try:
            GLib.idle_add(picture.set_paintable, _texture(url))
        except Exception:
            pass

    def roblox_sign_in(self):
        if not self.roblox_client_id():
            self.roblox_client_guide(self.roblox_sign_in)
            return
        self.login_button.set_sensitive(False)
        self.account_note.set_text("Esperando tu autorización en la página de Roblox… (hasta 3 minutos)")

        def work():
            try:
                person = roblox_cuenta.login(self.roblox_client_id(), lambda url: GLib.idle_add(
                    Gio.AppInfo.launch_default_for_uri, url, None))
            except Exception as error:  # cancelled, timed out or refused: say so and let them retry
                GLib.idle_add(self._sign_in_failed, str(error) or error.__class__.__name__)
                return
            GLib.idle_add(self._signed_in, person)

        threading.Thread(target=work, daemon=True).start()

    def _sign_in_failed(self, message):
        self.login_button.set_sensitive(True)
        self.account_note.set_text(message)
        return False

    def _signed_in(self, person):
        roblox_cuenta.save(person)
        self.roblox_person = person
        self.roblox_render_account()
        self._roblox_load_first()
        return False

    def roblox_sign_out(self):
        roblox_cuenta.sign_out()
        self.roblox_person = None
        self.roblox_loaded = False
        self.login_button.set_sensitive(True)
        self.roblox_render_account()

    def roblox_client_guide(self, then):
        """Roblox needs an app registered by its owner: explain the steps and ask for the client ID."""
        dialog = Gtk.Dialog(title="Iniciar sesión con Roblox", transient_for=self.window, modal=True, default_width=540)
        dialog.add_button("Cancelar", Gtk.ResponseType.CANCEL)
        dialog.add_button("Guardar y seguir", Gtk.ResponseType.OK).add_css_class("primary")
        box = dialog.get_content_area()
        box.add_css_class("menu")
        box.set_spacing(8)
        box.append(label("Hace falta registrar una aplicación de Roblox (gratis)", "subheading"))
        for step in ("1. Entrá al Creator Hub con tu cuenta de Roblox → «Credenciales» → OAuth 2.0 → crear una aplicación. Roblox te pide antes verificar tu identidad (edad) en la configuración de tu cuenta.",
                     "2. Tipo de cliente: público (sin secreto).",
                     f"3. URL de redirección, exacta: {roblox_cuenta.redirect_uri()}",
                     "4. Permisos: solo «openid» y «profile».",
                     "5. Copiá el ID de cliente y pegalo acá."):
            line = label(step, "muted")
            line.set_wrap(True)
            line.set_selectable(True)
            box.append(line)
        link = Gtk.LinkButton.new_with_label(roblox_cuenta.CREATOR_HUB, "Abrir el Creator Hub de Roblox")
        link.set_halign(Gtk.Align.START)
        box.append(link)
        entry = Gtk.Entry(placeholder_text="ID de cliente")
        box.append(entry)

        def respond(_, response):
            value = entry.get_text().strip()
            dialog.destroy()
            if response == Gtk.ResponseType.OK and value:
                self._save_roblox({"roblox_client_id": value})
                then()

        dialog.connect("response", respond)
        dialog.present()

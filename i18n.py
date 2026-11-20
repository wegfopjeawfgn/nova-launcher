"""Translation base. The source language is the Spanish text already in the code, so a string without a
translation is simply shown in Spanish. To add a language, copy locales/en.json to locales/<code>.json."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
LOCALES = HERE / "locales"
_catalog = {}
_templates = []   # (regex, plantilla traducida): textos con valores intercalados, p. ej. "Descargando {} MiB"
_cache = {}
_language = "es"
_installed = False


def available():
    """Language codes with a catalog, plus Spanish."""
    return ["es"] + sorted(p.stem for p in LOCALES.glob("*.json") if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", p.stem))


def set_language(code):
    """Load a catalog. Unknown codes and damaged files fall back to Spanish; this never raises."""
    global _catalog, _templates, _language
    _catalog, _templates, _language = {}, [], "es"
    _cache.clear()
    if code == "es" or code not in available():
        return _language
    try:
        data = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _language
    if isinstance(data, dict):
        _catalog = {key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str) and value}
        _language = code
        for key, value in _catalog.items():
            if "{}" in key and value.count("{}") == key.count("{}"):
                pattern = "(.*?)".join(re.escape(part) for part in key.split("{}"))
                _templates.append((re.compile(pattern, re.S), value))
    return _language


def tr(text):
    """Translation of `text`, or `text` itself. Texts with interleaved values are matched against the templates."""
    if not _catalog or not isinstance(text, str):
        return text
    found = _catalog.get(text)
    if found is not None:
        return found
    if text in _cache:
        return _cache[text]
    result = text
    for pattern, template in _templates:
        match = pattern.fullmatch(text)
        if match:
            values = iter(match.groups())
            result = re.sub(r"\{\}", lambda _: next(values), template)
            break
    if len(_cache) < 4000:
        _cache[text] = result
    return result


def install_gtk():
    """Translate what Gtk shows (labels, buttons, tooltips, titles, placeholders) without touching every call site.
    Does nothing for Spanish. Call once, after set_language and before building the interface."""
    global _installed
    if not _catalog or _installed:
        return
    _installed = True
    from gi.repository import Gtk

    def init_keys(cls, *keys):
        original = cls.__init__

        def init(self, *args, **kwargs):
            for key in keys:
                if isinstance(kwargs.get(key), str):
                    kwargs[key] = tr(kwargs[key])
            original(self, *args, **kwargs)
        cls.__init__ = init

    def setter(cls, name, position=0):
        original = getattr(cls, name)

        def wrapped(self, *args):
            args = list(args)
            if len(args) > position and isinstance(args[position], str):
                args[position] = tr(args[position])
            return original(self, *args)
        setattr(cls, name, wrapped)

    for cls in (Gtk.Label, Gtk.Button, Gtk.CheckButton, Gtk.ToggleButton, Gtk.MenuButton, Gtk.Expander):
        init_keys(cls, "label", "tooltip_text")
    for cls in (Gtk.Label, Gtk.Button, Gtk.CheckButton, Gtk.ToggleButton, Gtk.MenuButton, Gtk.Expander):
        setter(cls, "set_label")
    setter(Gtk.Label, "set_text")
    init_keys(Gtk.Entry, "placeholder_text")
    setter(Gtk.Entry, "set_placeholder_text")
    init_keys(Gtk.SearchEntry, "placeholder_text")
    init_keys(Gtk.Window, "title")
    setter(Gtk.Window, "set_title")
    setter(Gtk.Widget, "set_tooltip_text")
    setter(Gtk.Dialog, "add_button")
    setter(Gtk.ComboBoxText, "append", 1)

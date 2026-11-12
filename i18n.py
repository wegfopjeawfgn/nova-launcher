"""Translation base. The source language is the Spanish text already in the code, so a string without a
translation is simply shown in Spanish. To add a language, copy locales/en.json to locales/<code>.json."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
LOCALES = HERE / "locales"
_catalog = {}
_language = "es"


def available():
    """Language codes with a catalog, plus Spanish."""
    return ["es"] + sorted(p.stem for p in LOCALES.glob("*.json") if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", p.stem))


def set_language(code):
    """Load a catalog. Unknown codes and damaged files fall back to Spanish; this never raises."""
    global _catalog, _language
    _catalog, _language = {}, "es"
    if code == "es" or code not in available():
        return _language
    try:
        data = json.loads((LOCALES / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _language
    if isinstance(data, dict):
        _catalog = {key: value for key, value in data.items() if isinstance(key, str) and isinstance(value, str) and value}
        _language = code
    return _language


def tr(text):
    return _catalog.get(text, text)

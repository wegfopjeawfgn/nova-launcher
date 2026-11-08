#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "4.0"); import cairo; gi.require_foreign("cairo"); from gi.repository import Gtk'; then
    echo "Instalá las dependencias con: sudo dnf install python3-gobject python3-cairo gtk4 python3-pip xdg-utils" >&2
    exit 1
fi
runtime="${XDG_CACHE_HOME:-$HOME/.cache}/nova-launcher/venv-8"
/usr/bin/python3 -m venv --system-site-packages "$runtime" 2>/dev/null || {
    echo "Instalá python3-pip y volvé a intentar." >&2
    exit 1
}
if ! "$runtime/bin/python" -c 'from importlib.metadata import version; assert version("minecraft-launcher-lib") == "8.0"' 2>/dev/null; then
    "$runtime/bin/python" -m pip install -r requirements.txt
fi
exec "$runtime/bin/python" -B nova.py "$@"

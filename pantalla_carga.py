"""Nova's loading screen inside Minecraft (Fabric/Quilt with the Dark Loading Screen mod): colours and the logo agent.
No GTK here, so it can run from the launcher worker and be tested."""
from pathlib import Path

import motor

VERSION = 2   # 1 was the old lavender palette; 2 follows the launcher's cyan
COLORS = {"background": "0b0d12", "bar": "8fd6e8", "barBackground": "151a23", "border": "2c3341", "logo": "eef0f5"}
MARKER = "nova-loading.json"


def config_path(folder):
    return Path(folder) / "game" / "config" / "dark-loading-screen.json"


def logo_supported(instance):
    """The logo texture is swapped only where the agent knows Minecraft's classes."""
    return instance.get("version") == "1.21.11" and instance.get("loader") == "fabric"


def status(folder):
    """'off', or 'on' when Nova's loading screen is applied to this instance."""
    return "on" if motor.read(Path(folder) / MARKER, {}).get("palette") else "off"


def apply(folder, instance):
    """Write the colours (remembering what was there) and turn the logo agent on where it is supported."""
    path = config_path(folder)
    with motor.instance_lock(folder):
        current = motor.read(path, {})
        marker = motor.read(Path(folder) / MARKER, {})
        previous = marker.get("previous") if marker.get("palette") else {key: current.get(key) for key in COLORS}
        motor.save(path, {**current, **COLORS})
        motor.save(Path(folder) / MARKER, {"logo": logo_supported(instance), "palette": VERSION, "previous": previous})


def upgrade(folder):
    """Instances that got the screen with an older palette move to the current one the next time they start."""
    marker = motor.read(Path(folder) / MARKER, {})
    if marker.get("palette") and marker["palette"] < VERSION and config_path(folder).is_file():
        path = config_path(folder)
        motor.save(path, {**motor.read(path, {}), **COLORS})
        motor.save(Path(folder) / MARKER, {**marker, "palette": VERSION})


def remove(folder):
    """Give back the colours the instance had before and stop the logo agent."""
    marker = motor.read(Path(folder) / MARKER, {})
    path = config_path(folder)
    with motor.instance_lock(folder):
        if path.is_file():
            data = motor.read(path, {})
            for key, value in (marker.get("previous") or {}).items():
                if key in COLORS:
                    if value is None:
                        data.pop(key, None)
                    else:
                        data[key] = value
            motor.save(path, data)
        try:
            (Path(folder) / MARKER).unlink()
        except FileNotFoundError:
            pass

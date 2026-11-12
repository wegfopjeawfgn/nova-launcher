"""Find Java installations on this computer so the user can pick one.

Only well-known places are searched, and each candidate is asked for its version with a short timeout.
Nothing is downloaded and nothing is run from anywhere the user did not already have a Java."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import motor

VERSION_RE = re.compile(r'version\s+"(?:1\.)?(\d+)')
VENDORS = ("Temurin", "Zulu", "Corretto", "GraalVM", "Microsoft", "Semeru", "Liberica", "Oracle", "OpenJDK")


def candidate_paths(home=None, environ=None, system_roots=None):
    """Executables worth asking, in a stable order and without duplicates."""
    environ = os.environ if environ is None else environ
    home = Path(home) if home else Path.home()
    exe = "java.exe" if os.name == "nt" else "java"
    found = []
    if environ.get("JAVA_HOME"):
        found.append(Path(environ["JAVA_HOME"]) / "bin" / exe)
    on_path = shutil.which("java")
    if on_path:
        found.append(Path(on_path))
    system = [Path("/usr/lib/jvm"), Path("/usr/java")] if system_roots is None else list(system_roots)
    roots = system + [home / ".jdks", home / ".sdkman/candidates/java", motor.ROOT / "minecraft" / "runtime"]
    if os.name == "nt":
        for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = environ.get(key)
            if base:
                roots += [Path(base) / "Java", Path(base) / "Eclipse Adoptium", Path(base) / "Microsoft",
                          Path(base) / "Programs" / "Eclipse Adoptium"]
    for root in roots:
        try:
            for child in sorted(root.glob("*")) + sorted(root.glob("*/*")) + sorted(root.glob("*/*/*")):
                for sub in ("bin", "jre/bin"):
                    candidate = child / sub / exe
                    if candidate.is_file():
                        found.append(candidate)
        except OSError:
            continue
    unique, seen = [], set()
    for path in found:
        try:
            key = path.resolve()
        except OSError:
            continue
        if key not in seen and os.access(path, os.X_OK):
            seen.add(key)
            unique.append(path)
    return unique


def inspect(path, timeout=5):
    """{"path", "major", "vendor"} for a working Java, else None."""
    try:
        result = subprocess.run([str(path), "-version"], capture_output=True, text=True, errors="replace",
                                timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    text = result.stderr + result.stdout
    match = VERSION_RE.search(text)
    if not match:
        return None
    vendor = next((name for name in VENDORS if name.lower() in text.lower()), "")
    return {"path": str(path), "major": int(match.group(1)), "vendor": vendor}


def find_java(*, paths=None, timeout=5):
    """Working Java installations, newest first."""
    found = []
    for path in paths if paths is not None else candidate_paths():
        info = inspect(path, timeout)
        if info:
            found.append(info)
    return sorted(found, key=lambda item: (-item["major"], item["path"]))


def label(info, required=None):
    """Text for a list: 'Java 21 · Temurin · /usr/lib/jvm/...'; marks versions that are too old."""
    text = f"Java {info['major']}" + (f" · {info['vendor']}" if info["vendor"] else "") + f" · {info['path']}"
    if required and info["major"] < required:
        text += f" · demasiado antiguo (Minecraft necesita {required})"
    return text

"""Create complete local instance copies and recover them as new instances."""
from datetime import datetime
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import uuid
import zipfile

import motor


def copy_instance(source, mode):
    destination = motor.ROOT / ("backups" if mode == "backup" else "instances")
    destination.mkdir(parents=True, exist_ok=True)
    with motor.instance_lock(source), TemporaryDirectory(dir=destination) as temporary:
        staged = Path(temporary) / "instance"

        def skip(path, names):
            omitted = {".nova.lock", "session.lock"} & set(names)
            if Path(path) == source:
                omitted |= {"minecraft.log"} & set(names)
            for name in set(names) - omitted:
                if (Path(path) / name).is_symlink():
                    raise ValueError(f"Quitá el enlace simbólico {name} antes de copiar la instancia.")
            return omitted

        shutil.copytree(source, staged, ignore=skip)
        settings = motor.read(staged / "instance.json", {})
        if not settings.get("name"):
            raise ValueError("La copia no contiene una instancia de Nova válida.")
        if mode == "backup":
            motor.save(staged / "backup.json", {"created": datetime.now().astimezone().isoformat(timespec="minutes")})
        else:
            (staged / "backup.json").unlink(missing_ok=True)
            suffix = " (restaurada)" if mode == "restore" else " (copia)"
            settings["name"] = settings["name"][:40-len(suffix)] + suffix
            motor.save(staged / "instance.json", settings)
        return staged.rename(destination / uuid.uuid4().hex)


def export_instance(source, destination, include_worlds):
    """Share portable settings and optional worlds as a Nova ZIP."""
    if destination.suffix.lower() != ".zip":
        raise ValueError("Guardá la instancia con extensión .zip.")

    with motor.instance_lock(source), TemporaryDirectory(dir=destination.parent) as temporary:
        settings = motor.read(source / "instance.json", {})
        dependencies = {"minecraft": settings["version"]}
        loader = settings["loader"]
        if loader != "vanilla":
            dependencies[{"fabric": "fabric-loader", "quilt": "quilt-loader"}.get(loader, loader)] = (
                settings["loader_version"] or "auto")
        manifest = {"formatVersion": 1, "name": settings["name"], "dependencies": dependencies}
        staged = Path(temporary) / "instance.zip"
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("nova-pack.json", json.dumps(manifest))
            game = source / "game"
            saves = game / "saves"
            total = 0
            if include_worlds:
                if game.is_symlink() or saves.is_symlink():
                    raise ValueError("La carpeta de mundos no puede ser un enlace simbólico.")
                for path in saves.rglob("*"):
                    if path.is_symlink():
                        raise ValueError("Quitá los enlaces simbólicos de los mundos antes de exportar.")
                    if path.is_file() and path.name != "session.lock":
                        total += path.stat().st_size
                        if total > 4 * 1024**3:
                            raise ValueError("Los mundos superan el límite de 4 GiB.")
                        archive.write(path, f"overrides/{path.relative_to(game).as_posix()}")
        staged.replace(destination)

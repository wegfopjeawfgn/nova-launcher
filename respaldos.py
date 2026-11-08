"""Create complete local instance copies and recover them as new instances."""
from datetime import datetime
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import uuid

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

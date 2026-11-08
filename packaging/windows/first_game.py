"""Check the installed Nova and Minecraft client on a Windows validation runner."""
import importlib
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

install_root = Path(sys.argv[1])
sys.path.insert(0, str(install_root / "app"))
motor = importlib.import_module("motor")

folder = motor.create("Validación de Windows", 2, 0, version="1.21.1")
game = folder / "game"
game.mkdir()
instance = motor.read(folder / "instance.json", {})
shared, launch_id = motor.prepare(instance, print)

from minecraft_launcher_lib import command

args = command.get_minecraft_command(launch_id, str(shared), {
    "username": "NovaTest", "uuid": "1e9172d560fc4c22a25bf07f8f63b88b",
    "token": "0", "gameDirectory": str(game), "jvmArguments": ["-Xmx2G"],
})
mesa = os.environ.get("NOVA_TEST_MESA")
if mesa:
    mesa = Path(mesa)
    java_bin = Path(args[0]).parent
    for name in ("opengl32.dll", "libgallium_wgl.dll", "libglapi.dll"):
        driver = mesa / name
        if driver.is_file():
            shutil.copy2(driver, java_bin / name)
    (java_bin / f"{Path(args[0]).name}.local").touch()
    os.environ["PATH"] = f"{mesa}{os.pathsep}{os.environ['PATH']}"
    os.environ["GALLIUM_DRIVER"] = "llvmpipe"
    os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
    args.insert(1, f"-Dorg.lwjgl.opengl.libname={java_bin / 'opengl32.dll'}")
log = Path(sys.argv[2])
with log.open("wb") as output:
    process = subprocess.Popen(args, cwd=game, stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline and process.poll() is None:
            text = log.read_text(encoding="utf-8", errors="replace")
            if "Created:" in text and "textures/atlas/" in text:
                print("Minecraft inicializó los recursos gráficos.")
                break
            time.sleep(2)
        else:
            raise RuntimeError(f"Minecraft no completó el arranque (código {process.poll()}).")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)

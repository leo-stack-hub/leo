"""One-time setup for Leo (macOS, Linux, Windows):  python3 setup.py   (Windows: py setup.py)

Creates ~/.leo/venv and installs PySide6 + Pillow into it. PySide6 is ~100 MB, so the
download takes a minute or two; progress is shown.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("Leo needs Python 3.10 or newer.")

home = Path(os.environ.get("LEO_HOME") or Path.home() / ".leo")
env = home / "venv"
py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

print(f"[1/3] Creating a private Python environment in {env}")
venv.EnvBuilder(with_pip=True).create(env)

# opencv <5: version 5 no longer ships the face-detector file the toon avatar uses
pkgs = ["PySide6-Essentials", "Pillow", "opencv-python-headless>=4.8,<5"]
if sys.platform == "darwin":
    pkgs += ["pyobjc-framework-Cocoa",  # hides the Dock icon
             "pyobjc-framework-ApplicationServices"]  # follows chats in the Claude desktop app

print("[2/3] Installing", ", ".join(pkgs), "(PySide6 and OpenCV are ~150 MB: this takes a few minutes)")
subprocess.check_call([str(py), "-m", "pip", "install", "--upgrade", "pip"])
subprocess.check_call([str(py), "-m", "pip", "install", *pkgs])

root = Path(__file__).resolve().parent
print("[3/3] Done. Leo is ready.\n")
print("Try it now:")
print(f'    "{py}" "{root / "run_leo.py"}" run --stay')
print("Then install the plugin in Claude Code:")
print(f"    /plugin marketplace add {root}")
print("    /plugin install leo@leo")
print("Optional: open Leo automatically at login (and add him to your apps):")
print(f'    "{py}" "{root / "run_leo.py"}" autostart on')

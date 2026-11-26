"""Leo as an app: a launcher in Applications / the Start menu, and "start at login".

    macOS    ~/Applications/Leo.app  +  ~/Library/LaunchAgents/<LABEL>.plist
    Windows  Start menu\\Programs\\Leo.lnk  +  Start menu\\Programs\\Startup\\Leo.lnk
    Linux    ~/.local/share/applications/leo.desktop  +  ~/.config/autostart/leo.desktop

Everything starts ~/.leo/launch.py, which finds the plugin wherever Claude Code installed
it (the install folder has the version in its name, so it moves on every update) and runs
the pet with --stay. Stdlib only, except the optional icon (Qt + Pillow from ~/.leo/venv).
"""

from __future__ import annotations

import os
import platform as platform_mod
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from .common import home, venv_python

LABEL = "io.github.leo-stack-hub.leo"
ROOT = Path(__file__).resolve().parent.parent  # this copy of the plugin (fallback)

LAUNCH_PY = '''"""Starts Leo (written by `run_leo.py autostart`). Finds the current plugin install."""
import json, sys
from pathlib import Path

FALLBACK = Path({fallback!r})


def plugin_root():
    f = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        for entry in json.loads(f.read_text())["plugins"].get("leo@leo", []):
            p = Path(entry["installPath"])
            if (p / "run_leo.py").exists():
                return p
    except Exception:
        pass
    return FALLBACK if (FALLBACK / "run_leo.py").exists() else None


root = plugin_root()
if root is None:
    sys.exit("Leo: plugin not found. Reinstall it in Claude Code (/plugin install leo@leo).")
sys.path.insert(0, str(root))
from leo.__main__ import main  # noqa: E402

sys.exit(main(["run", "--stay"]))
'''


def _platform(platform: str | None) -> str:
    """'mac' | 'win' | 'linux', from sys.platform style names or already-short ones."""
    p = platform or sys.platform
    if p in ("mac", "win", "linux"):
        return p
    return "mac" if p == "darwin" else "win" if p == "win32" else "linux"


def launch_py() -> Path:
    return home() / "launch.py"


def write_launcher() -> Path:
    home().mkdir(parents=True, exist_ok=True)
    launch_py().write_text(LAUNCH_PY.format(fallback=str(ROOT)))
    return launch_py()


# --- where things go -------------------------------------------------------------------------


def _win_programs() -> Path:
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def app_path(platform: str | None = None) -> Path:
    """The launcher people click: Leo.app, a Start menu shortcut, or a .desktop entry."""
    p = _platform(platform)
    if p == "mac":
        return Path.home() / "Applications" / "Leo.app"
    if p == "win":
        return _win_programs() / "Leo.lnk"
    return Path.home() / ".local" / "share" / "applications" / "leo.desktop"


def login_path(platform: str | None = None) -> Path:
    """What makes Leo start at login."""
    p = _platform(platform)
    if p == "mac":
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if p == "win":
        return _win_programs() / "Startup" / "Leo.lnk"
    return Path.home() / ".config" / "autostart" / "leo.desktop"


def enabled(platform: str | None = None) -> bool:
    return login_path(platform).exists()


# --- icon ------------------------------------------------------------------------------------


def _icon_png(size: int) -> bytes | None:
    """Leo's face at size x size (PNG bytes), drawn by his own code. None without Qt."""
    try:
        if not _has_gui_app():  # called from the command line: draw without a screen
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QBuffer, QIODevice, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter

        if QGuiApplication.instance() is None:
            _icon_png.app = QGuiApplication([])  # keep a reference
        from . import lion

        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        k = size / 140  # the mane reaches ~64 units from the head centre (0, -114)
        p.scale(k, k)
        p.translate(70, 70 + 114 - 2)
        lion.draw_head(p, lion.LPose(), 0.0)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        return bytes(buf.data())
    except Exception:
        return None


def _has_gui_app() -> bool:
    mod = sys.modules.get("PySide6.QtGui")
    return bool(mod and mod.QGuiApplication.instance())


def _write_icons(platform: str) -> Path | None:
    """leo.png / leo.ico / leo.icns in ~/.leo, as the platform needs. None if Qt is missing."""
    png = _icon_png(512)
    if png is None:
        return None
    (home() / "leo.png").write_bytes(png)
    if platform == "win":
        try:
            from PIL import Image

            Image.open(home() / "leo.png").save(home() / "leo.ico",
                                                sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
            return home() / "leo.ico"
        except Exception:
            return None
    if platform == "mac" and shutil.which("iconutil"):
        iconset = home() / "leo.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                data = _icon_png(s * scale)
                if data:
                    (iconset / f"icon_{s}x{s}{suffix}.png").write_bytes(data)
        out = home() / "leo.icns"
        ok = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
                            capture_output=True).returncode == 0
        shutil.rmtree(iconset, ignore_errors=True)
        return out if ok else None
    return home() / "leo.png"


# --- per platform ----------------------------------------------------------------------------


def _mac_app(app: Path, icon: Path | None) -> None:
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True, exist_ok=True)
    (contents / "Resources").mkdir(exist_ok=True)
    info = {
        "CFBundleName": "Leo", "CFBundleDisplayName": "Leo", "CFBundleIdentifier": LABEL,
        "CFBundleExecutable": "Leo", "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": _version(), "LSUIElement": True,  # no Dock icon
        "LSArchitecturePriority": ["arm64", "x86_64"],
    }
    if icon and icon.suffix == ".icns":
        shutil.copy(icon, contents / "Resources" / "Leo.icns")
        info["CFBundleIconFile"] = "Leo"
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    exe = contents / "MacOS" / "Leo"
    exe.write_text(mac_exe_script())
    exe.chmod(0o755)


def mac_exe_script(machine: str | None = None) -> str:
    """The app's executable. Pins Python to the CPU it was installed for: Finder starts a
    script-only app under Rosetta, and the venv's arm64 libraries then refuse to load."""
    machine = machine or platform_mod.machine()
    arch = f'/usr/bin/arch -{machine} ' if machine in ("arm64", "x86_64") else ""
    return f'#!/bin/sh\nexec {arch}"{venv_python()}" "{launch_py()}"\n'


def _mac_login(plist: Path, app: Path) -> None:
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(app / "Contents" / "MacOS" / "Leo")],
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",  # only in a logged-in desktop session
        "ProcessType": "Interactive",
    }))


def _desktop_entry(icon: Path | None) -> str:
    return ("[Desktop Entry]\nType=Application\nName=Leo\n"
            "Comment=A desktop pet that shows what Claude Code is doing\n"
            f'Exec="{venv_python()}" "{launch_py()}"\n'
            + (f"Icon={icon}\n" if icon else "") + "Terminal=false\nCategories=Utility;\n"
            "X-GNOME-Autostart-enabled=true\n")


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def win_shortcut_script(lnk: Path, icon: Path | None) -> str:
    """PowerShell that creates a .lnk running pythonw (no console window) on launch.py."""
    lines = [
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk)})",
        f"$s.TargetPath = {_ps_quote(venv_python(windowed=True, platform='win32'))}",
        f"$s.Arguments = {_ps_quote(chr(34) + str(launch_py()) + chr(34))}",
        f"$s.WorkingDirectory = {_ps_quote(home())}",
        "$s.Description = 'Leo: a desktop pet for Claude Code'",
    ]
    if icon:
        lines.append(f"$s.IconLocation = {_ps_quote(icon)}")
    lines.append("$s.Save()")
    return "; ".join(lines)


def _win_shortcut(lnk: Path, icon: Path | None) -> None:
    lnk.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    win_shortcut_script(lnk, icon)], check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _version() -> str:
    from . import __version__

    return str(__version__)


# --- public ----------------------------------------------------------------------------------


def install_app(platform: str | None = None, icons: bool = True) -> Path:
    """Put Leo in Applications / the Start menu / the app launcher. Returns its path."""
    p = _platform(platform)
    write_launcher()
    icon = _write_icons(p) if icons else None
    app = app_path(p)
    if p == "mac":
        _mac_app(app, icon)
    elif p == "win":
        _win_shortcut(app, icon)
    else:
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text(_desktop_entry(icon))
    return app


def set_login(on: bool, platform: str | None = None, icons: bool = True) -> Path:
    """Start Leo at login (installs the app too), or stop doing so."""
    p = _platform(platform)
    target = login_path(p)
    if not on:
        if p == "mac" and target.exists() and platform is None:
            subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"],
                           capture_output=True)
        target.unlink(missing_ok=True)
        return target
    app = install_app(p, icons)
    if p == "mac":
        _mac_login(target, app)
    elif p == "win":
        icon = home() / "leo.ico"
        _win_shortcut(target, icon if icon.exists() else None)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_desktop_entry(home() / "leo.png" if (home() / "leo.png").exists() else None))
    return target


def remove_all(platform: str | None = None) -> None:
    """Undo everything: login item, app launcher, launch.py and icons."""
    p = _platform(platform)
    set_login(False, platform)
    app = app_path(p)
    if app.is_dir():
        shutil.rmtree(app, ignore_errors=True)
    else:
        app.unlink(missing_ok=True)
    for name in ("launch.py", "leo.png", "leo.ico", "leo.icns"):
        (home() / name).unlink(missing_ok=True)

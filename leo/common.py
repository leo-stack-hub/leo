"""Paths and the tiny wire protocol. Stdlib only (the hook imports this).

The companion listens on 127.0.0.1 (random port) and writes the port plus a secret token to
~/.leo/leo.port. TCP works the same on macOS, Linux and Windows; the token keeps other
local programs from talking to the companion.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


def home() -> Path:
    """All Leo state lives here. Override with LEO_HOME (used by tests)."""
    return Path(os.environ.get("LEO_HOME") or Path.home() / ".leo")


def port_file() -> Path:
    return home() / "leo.port"


def venv_python(windowed: bool = False, platform: str | None = None) -> Path:
    """Python inside ~/.leo/venv. windowed=True gives pythonw.exe on Windows (no console)."""
    if (platform or sys.platform) == "win32":
        return home() / "venv" / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return home() / "venv" / "bin" / "python"


def launcher() -> Path:
    """run_leo.py at the plugin root: run the CLI without installing the package."""
    return Path(__file__).resolve().parent.parent / "run_leo.py"


def send(msg: dict, timeout: float = 0.2) -> None:
    """Send one JSON line to the running companion. Raises OSError if it isn't running."""
    try:
        info = json.loads(port_file().read_text())
        port, token = int(info["port"]), str(info["token"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OSError("leo is not running") from exc
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(json.dumps({"token": token, **msg}).encode() + b"\n")

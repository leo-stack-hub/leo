"""Claude Code hook: forward the event on stdin to the Leo companion.

Golden rule: stdlib only, print nothing, always exit 0, be fast.
Starts the companion on SessionStart if it isn't running (needs ~/.leo/venv from setup.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from leo.common import IS_WINDOWS, launcher, send, venv_python  # noqa: E402


def build_message(payload: dict) -> dict:
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return {
        "event": payload.get("hook_event_name", ""),
        "session": str(payload.get("session_id") or "default"),
        "cwd": payload.get("cwd") or os.getcwd(),
        "tool": payload.get("tool_name"),
        "command": command[:300] if isinstance(command, str) else None,  # read-only shell? Leo reads
        "ntype": payload.get("notification_type"),
        "message": payload.get("message"),
        "ts": time.time(),
    }


def launch_companion(first_event: dict) -> None:
    py = venv_python(windowed=True)
    if not py.exists() or os.environ.get("LEO_NO_LAUNCH"):  # setup.py not run: stay silent
        return
    kwargs: dict = {}
    if IS_WINDOWS:  # no console window, and not killed when Claude Code's console closes
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x8)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [str(py), str(launcher()), "run", "--first", json.dumps(first_event)],
        cwd=str(Path.home()), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, **kwargs,
    )


def main() -> None:
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        msg = build_message(payload if isinstance(payload, dict) else {})
        if not msg["event"]:
            return
        try:
            send(msg)
        except OSError:
            if msg["event"] == "SessionStart":
                launch_companion(msg)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)

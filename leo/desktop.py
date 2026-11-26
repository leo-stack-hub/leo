"""Watch the Claude desktop app (chat) so Leo reacts there too. macOS only.

Chat in the desktop app runs on Claude's servers, so no Claude Code hook fires. Instead this
reads the app's window through macOS Accessibility: while Claude is replying the window shows a
"Stop" button. Button appears -> UserPromptSubmit, button gone -> Stop, for a session called
"claude-desktop". Needs Accessibility permission for the app that launched Leo
(System Settings -> Privacy & Security -> Accessibility). Without it, it stays silent.
"""

from __future__ import annotations

import re
import sys
import threading
import time

BUNDLE = "com.anthropic.claudefordesktop"
SESSION = "claude-desktop"
STOP = re.compile(r"\bstop\b", re.I)
MAX_NODES = 6000  # keep one scan cheap even on long chats
POLL = 1.0

try:  # pyobjc-framework-ApplicationServices (setup.py installs it on macOS)
    import ApplicationServices as AS
    import AppKit
except ImportError:
    AS = AppKit = None


def available() -> bool:
    return sys.platform == "darwin" and AS is not None


def trusted(prompt: bool = False) -> bool:
    """True once this app may use Accessibility. prompt=True shows the macOS dialog."""
    if not available():
        return False
    if prompt:
        return bool(AS.AXIsProcessTrustedWithOptions({AS.kAXTrustedCheckOptionPrompt: True}))
    return bool(AS.AXIsProcessTrusted())


def claude_pid() -> int | None:
    for a in AppKit.NSWorkspace.sharedWorkspace().runningApplicationsWithBundleIdentifier_(BUNDLE):
        return int(a.processIdentifier())
    return None


def _attr(el, name):
    err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def _label(el) -> str:
    return " ".join(str(v) for n in ("AXTitle", "AXDescription", "AXHelp")
                    if (v := _attr(el, n)))


def _app(pid: int):
    app = AS.AXUIElementCreateApplication(pid)
    # Electron only builds its accessibility tree when asked to
    AS.AXUIElementSetAttributeValue(app, "AXManualAccessibility", True)
    return app


def find_stop_button(pid: int) -> str | None:
    """Label of a visible Stop button in the Claude app's windows, or None."""
    seen = 0
    stack = list(_attr(_app(pid), "AXWindows") or [])
    while stack and seen < MAX_NODES:
        el = stack.pop()
        seen += 1
        if _attr(el, "AXRole") == "AXButton":
            label = _label(el)
            if STOP.search(label) and "dictation" not in label.lower():
                return label
        stack.extend(_attr(el, "AXChildren") or [])
    return None


class Watcher:
    """Background thread; the app calls poll() from its timer to get hook-like events."""

    def __init__(self) -> None:
        self.replying = False
        self.events: list[dict] = []
        self.lock = threading.Lock()
        self.alive = True
        threading.Thread(target=self._run, daemon=True).start()

    def _emit(self, event: str) -> None:
        with self.lock:
            self.events.append({"event": event, "session": SESSION, "ts": time.time(),
                                "cwd": "Claude app"})

    def _run(self) -> None:
        started = False
        while self.alive:
            try:
                pid = claude_pid() if trusted() else None
                if pid is None:
                    if started:
                        self._emit("SessionEnd")
                        started, self.replying = False, False
                else:
                    if not started:
                        self._emit("SessionStart")
                        started = True
                    now = find_stop_button(pid) is not None
                    if now != self.replying:
                        self.replying = now
                        self._emit("UserPromptSubmit" if now else "Stop")
            except Exception as exc:  # never let the watcher break the companion
                print(f"leo: desktop watcher: {exc}", file=sys.stderr)
            time.sleep(POLL)

    def poll(self) -> list[dict]:
        with self.lock:
            out, self.events = self.events, []
        return out

    def stop(self) -> None:
        self.alive = False


def probe() -> int:
    """`run_leo.py desktop`: ask for permission and report what Leo can see."""
    if not available():
        print("desktop watching needs macOS and pyobjc-framework-ApplicationServices")
        return 1
    if not trusted(prompt=True):
        print("Accessibility permission is missing. macOS should have opened a dialog.\n"
              "Allow it in System Settings -> Privacy & Security -> Accessibility for the app\n"
              "that runs Leo (your terminal or VS Code), then run this again.")
        return 1
    pid = claude_pid()
    if pid is None:
        print("permission OK, but the Claude app is not running")
        return 1
    t = time.time()
    label = find_stop_button(pid)
    print(f"permission OK, Claude app pid {pid}, scan took {1000 * (time.time() - t):.0f} ms")
    print(f"Claude is replying (button: {label!r})" if label else "Claude is idle (no Stop button)")
    return 0

"""Hook events -> what the pet shows. Pure Python (no Qt), so it is easy to test."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Lowest -> highest priority. With several sessions, the highest one is displayed.
STATES = ["sleeping", "idle", "greeting", "thinking", "working", "done", "waiting", "permission"]
PRIORITY = {s: i for i, s in enumerate(STATES)}

TOOL_TEXT = {
    **dict.fromkeys(["Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch"], "reading"),
    **dict.fromkeys(["Edit", "Write", "MultiEdit", "NotebookEdit"], "typing"),
    **dict.fromkeys(["Bash", "BashOutput"], "running a command"),
}

TEXT = {
    "sleeping": "Leo is sleeping",
    "idle": "Leo is ready",
    "greeting": "Leo says hi!",
    "thinking": "Leo is thinking…",
    "working": "Leo is working…",
    "done": "Leo is done!",
    "waiting": "Leo is waiting for you",
    "permission": "Leo needs permission!",
    "hydrate": "Time to drink some water!",
}

GREETING_SECS = 3
DONE_SECS = 3
SLEEP_AFTER = 300
STALE_BUSY_AFTER = 900  # thinking/working with no events: probably interrupted
FORGET_AFTER = 6 * 3600  # SessionEnd never arrived


def fmt_duration(seconds: float) -> str:
    s = max(0, round(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


@dataclass
class Session:
    state: str = "idle"
    detail: str | None = None
    since: float = field(default_factory=time.time)
    last_event: float = field(default_factory=time.time)
    turn_start: float | None = None
    last_turn: float | None = None


@dataclass
class Display:
    state: str
    text: str
    sessions: int
    detail: str | None = None  # what 'working' means: reading / typing / running a command


class Tracker:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def apply(self, msg: dict) -> str | None:
        """Update from one hook message. Returns a sound cue name, or None."""
        ev, sid = msg.get("event"), msg.get("session", "default")
        now = msg["ts"] if msg.get("ts") is not None else time.time()
        if ev == "SessionEnd":
            self.sessions.pop(sid, None)
            return None
        s = self.sessions.setdefault(sid, Session(since=now))
        s.last_event = now

        def go(state: str, detail: str | None = None) -> None:
            if s.state != state:
                s.since = now
            s.state, s.detail = state, detail

        if ev == "SessionStart":
            go("greeting")
            return "hello"
        if ev == "UserPromptSubmit":
            s.turn_start = now
            go("thinking")
        elif ev == "PreToolUse":
            go("working", TOOL_TEXT.get(msg.get("tool") or "", "working"))
        elif ev == "PostToolUse":
            go("thinking")
        elif ev == "PreCompact":
            go("working", "tidying up")
        elif ev == "Notification":
            if msg.get("ntype") == "auth_success":
                return None
            perm = msg.get("ntype") == "permission_prompt" or "permission" in (
                msg.get("message") or ""
            ).lower()
            go("permission" if perm else "waiting")
            return "alert" if perm else "waiting"
        elif ev == "Stop":
            if s.turn_start:
                s.last_turn = now - s.turn_start
                s.turn_start = None
            go("done")
            return "done"
        return None

    def tick(self, now: float | None = None) -> None:
        """Time-based transitions: greeting/done fade, sleep, stale busy, forget."""
        now = time.time() if now is None else now
        for sid, s in list(self.sessions.items()):
            age = now - s.since
            if now - s.last_event > FORGET_AFTER:
                del self.sessions[sid]
            elif s.state == "greeting" and age > GREETING_SECS:
                s.state, s.since = "idle", now
            elif s.state == "done" and age > DONE_SECS:
                s.state, s.since = "waiting", now
            elif s.state in ("idle", "waiting") and age > SLEEP_AFTER:
                s.state, s.since = "sleeping", now
            elif s.state in ("thinking", "working") and age > STALE_BUSY_AFTER:
                s.state, s.since = "idle", now

    def display(self) -> Display:
        if not self.sessions:
            return Display("sleeping", TEXT["sleeping"], 0)
        s = max(self.sessions.values(), key=lambda x: (PRIORITY[x.state], x.since))
        text = TEXT[s.state]
        if s.state == "working" and s.detail:
            text = f"Leo is {s.detail}…"
        if s.state == "done" and s.last_turn is not None:
            text = f"Leo finished in {fmt_duration(s.last_turn)}!"
        if s.state == "waiting" and s.last_turn is not None:
            text = f"took {fmt_duration(s.last_turn)}, your turn"
        n = len(self.sessions)
        if n > 1:
            text += f" ({n} sessions)"
        return Display(s.state, text, n, s.detail if s.state == "working" else None)

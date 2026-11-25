"""Hydration reminder schedule. Pure Python (no Qt) so it is easy to test."""

from __future__ import annotations

MIN_MINUTES, MAX_MINUTES = 1, 480
CHOICES = (15, 20, 30, 45, 60, 90, 120)  # shown in the menu; any value works from the CLI
SHOW_SECS = 25  # how long Leo keeps drinking before the reminder fades by itself
SNOOZE_MINUTES = 10  # the reminder's "In 10 min" button


def clamp(minutes) -> int:
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        m = 45
    return max(MIN_MINUTES, min(MAX_MINUTES, m))


class Reminder:
    def __init__(self, enabled: bool, minutes: int, now: float) -> None:
        self.enabled = bool(enabled)
        self.minutes = clamp(minutes)
        self.next = now + self.minutes * 60
        self.since: float | None = None  # when the current reminder started

    def configure(self, enabled: bool, minutes: int, now: float) -> None:
        """Apply new settings; restarts the countdown only if they changed."""
        minutes = clamp(minutes)
        if bool(enabled) != self.enabled or minutes != self.minutes:
            self.enabled, self.minutes = bool(enabled), minutes
            self.next = now + minutes * 60
            if not self.enabled:
                self.since = None

    @property
    def active(self) -> bool:
        return self.since is not None

    def start(self, now: float) -> None:
        self.since = now

    def dismiss(self, now: float) -> None:
        """Drank it (or it timed out): count down to the next one."""
        self.since = None
        self.next = now + self.minutes * 60

    def snooze(self, now: float, minutes: int = SNOOZE_MINUTES) -> None:
        """Not now: remind again in a few minutes."""
        self.since = None
        self.next = now + minutes * 60

    def tick(self, now: float, can_show: bool = True) -> bool:
        """Advance the clock. Returns True the moment a reminder should start."""
        if self.active:
            if now - self.since >= SHOW_SECS:
                self.dismiss(now)
            return False
        if self.enabled and now >= self.next:
            if can_show:
                self.start(now)
                return True
            self.next = now + 60  # busy (e.g. a permission prompt): try again in a minute
        return False

    def minutes_left(self, now: float) -> int:
        return max(0, int((self.next - now) / 60 + 0.99))

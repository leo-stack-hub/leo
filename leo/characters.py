"""Built-in drawn characters (no image files): Leo the lion cub (default), a boy and a girl."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import lion, people


@dataclass(frozen=True)
class Character:
    key: str
    label: str
    w: int  # design size (units the draw function uses)
    h: int
    scale: float  # on-screen height = size * scale
    draw: Callable  # draw(painter, state, detail, t), origin at the feet
    badge: tuple[float, float]  # badge anchor as fractions of (width, height) from the top-left


CHARACTERS = {
    "leo": Character("leo", "Leo (lion cub)", lion.W, lion.H, 1.25, lion.draw_lion, (0.80, 0.08)),
    "boy": Character("boy", "Boy", people.W, people.H, 1.4,
                     lambda p, s, d, t: people.draw_person(p, "boy", s, d, t), (0.80, 0.06)),
    "girl": Character("girl", "Girl", people.W, people.H, 1.4,
                      lambda p, s, d, t: people.draw_person(p, "girl", s, d, t), (0.80, 0.06)),
}


def get(key: str) -> Character:
    return CHARACTERS.get(key, CHARACTERS["leo"])


def screen_size(ch: Character, size: int) -> tuple[float, float]:
    """On-screen (width, height) in px for the avatar size setting."""
    h = size * ch.scale
    return h * ch.w / ch.h, h

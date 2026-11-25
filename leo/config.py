"""~/.leo/config.json: a tiny JSON settings file. Stdlib only."""

from __future__ import annotations

import json

from .common import home

DEFAULTS = {
    "style": "sticker",  # sticker | cartoon | pixel | original | toon
    "custom": False,  # True once a picture was uploaded; False = a built-in character
    "character": "leo",  # drawn: leo (lion cub) | boy | girl, or the name of an image pack
    "body": "boy",  # boy | girl (toon style only)
    "remove_bg": False,
    "size": 128,  # avatar size on screen, px
    "muted": False,
    "hydrate": False,  # drink-water reminder on/off
    "hydrate_minutes": 45,  # how often
    "x": None,
    "y": None,
}


def load() -> dict:
    try:
        data = json.loads((home() / "config.json").read_text())
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


def save(cfg: dict) -> None:
    home().mkdir(parents=True, exist_ok=True)
    (home() / "config.json").write_text(json.dumps(cfg, indent=2))

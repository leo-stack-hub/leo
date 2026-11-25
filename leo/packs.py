"""Image character packs: a folder of transparent PNGs, one per state. Stdlib only.

    ~/.leo/characters/<name>/idle.png          (required; used for any missing state)
                              greeting.png thinking.png working.png reading.png typing.png
                              done.png waiting.png permission.png sleeping.png

Packs shipped with the plugin live in <plugin>/assets/characters/. A pack of yours with the same
name wins. The app animates the pictures (bobbing, tilt, squash), so one PNG is enough to start.
"""

from __future__ import annotations

from pathlib import Path

from .common import home

BUILTIN = Path(__file__).resolve().parent.parent / "assets" / "characters"
EXTS = (".png", ".webp")


def roots() -> list[Path]:
    return [home() / "characters", BUILTIN]  # the user's folder first


def find() -> dict[str, Path]:
    """name -> folder, for every pack that has at least an idle picture."""
    out: dict[str, Path] = {}
    for root in reversed(roots()):  # later roots are overridden by earlier ones
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and _pic(d, "idle"):
                    out[d.name] = d
    return out


def _pic(folder: Path, name: str) -> Path | None:
    for ext in EXTS:
        f = folder / f"{name}{ext}"
        if f.is_file():
            return f
    return None


def picture(folder: Path, state: str, detail: str | None = None) -> Path | None:
    """The picture for a state, falling back to working/idle."""
    names = []
    if state == "working":
        d = (detail or "").lower()
        names += ["reading"] if "read" in d else ["typing"] if "typ" in d else []
    names += [state]
    if state in ("permission", "waiting", "thinking"):
        names += ["idle"]
    names += ["idle"]
    for n in names:
        f = _pic(folder, n)
        if f:
            return f
    return None

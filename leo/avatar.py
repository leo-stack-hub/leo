"""Turn any picture into Leo's avatar. Needs only Pillow (no Qt, no AI model).

The app animates this single 256x256 RGBA image (bounce, tilt, shake...) and draws state
badges on top, so one PNG is all a character needs.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from . import config
from .common import home

SIZE = 256
PAD = 24
STYLES = ("sticker", "cartoon", "pixel", "original", "toon")
BODIES = ("boy", "girl")


def avatar_path() -> Path:
    return home() / "avatar.png"


def source_path() -> Path:
    return home() / "source.png"


def load_square(path: str | Path) -> Image.Image:
    """Open an image, fix its rotation and center-crop it to SIZE x SIZE."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    return ImageOps.fit(img, (SIZE, SIZE), Image.LANCZOS)


def has_transparency(img: Image.Image) -> bool:
    return img.getchannel("A").getextrema()[0] < 250


def remove_background(img: Image.Image, tolerance: int = 40) -> Image.Image:
    """Make a plain background transparent by flood-filling in from the four corners."""
    if has_transparency(img):
        return img
    rgb = img.convert("RGB")
    work = rgb.copy()
    w, h = img.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(work, corner, (255, 0, 255), thresh=tolerance)
    bg = ImageChops.difference(work, rgb).convert("L").point(lambda p: 255 if p else 0)
    out = img.copy()
    out.putalpha(ImageChops.invert(bg).filter(ImageFilter.GaussianBlur(1)))
    return out


def shape_mask(kind: str) -> Image.Image:
    m = Image.new("L", (SIZE * 4, SIZE * 4), 0)  # drawn 4x then shrunk: smooth edges
    d = ImageDraw.Draw(m)
    box = [0, 0, SIZE * 4 - 1, SIZE * 4 - 1]
    if kind == "circle":
        d.ellipse(box, fill=255)
    else:
        d.rounded_rectangle(box, radius=SIZE, fill=255)
    return m.resize((SIZE, SIZE), Image.LANCZOS)


def cartoonize(img: Image.Image) -> Image.Image:
    """Flat colours + ink outlines."""
    alpha = img.getchannel("A")
    rgb = img.convert("RGB").filter(ImageFilter.MedianFilter(5))
    rgb = ImageEnhance.Color(rgb).enhance(1.5)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.15)
    rgb = ImageOps.posterize(rgb, 3)
    edges = ImageOps.autocontrast(rgb.convert("L").filter(ImageFilter.FIND_EDGES))
    ink = edges.point(lambda p: 255 if p > 60 else 0).filter(ImageFilter.MaxFilter(3))
    rgb = ImageChops.multiply(rgb, ImageOps.invert(ink).convert("RGB"))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def pixelate(img: Image.Image, blocks: int = 40, colors: int = 16) -> Image.Image:
    """Chunky pixel art with a small palette."""
    alpha = img.getchannel("A").resize((blocks, blocks), Image.BOX).point(
        lambda p: 255 if p > 127 else 0
    )
    small = img.convert("RGB").resize((blocks, blocks), Image.BOX)
    small = small.quantize(colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    out = small.convert("RGBA")
    out.putalpha(alpha)
    return out.resize((SIZE, SIZE), Image.NEAREST)


def finish(img: Image.Image, outline: tuple[int, int, int]) -> Image.Image:
    """Fit into the canvas, add a sticker outline and a soft shadow."""
    inner = SIZE - 2 * PAD
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(img.resize((inner, inner), Image.LANCZOS), (PAD, PAD))
    ring = canvas.getchannel("A").filter(ImageFilter.MaxFilter(9))  # ~4px dilation
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow.putalpha(ring.filter(ImageFilter.GaussianBlur(4)).point(lambda p: p * 90 // 255))
    shadow = ImageChops.offset(shadow, 0, 4)
    outlined = Image.new("RGBA", (SIZE, SIZE), outline + (0,))
    outlined.putalpha(ring)
    return Image.alpha_composite(Image.alpha_composite(shadow, outlined), canvas)


def make_avatar(src: str | Path, style: str = "sticker", remove_bg: bool = False,
                body: str = "boy") -> Image.Image:
    if style not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}")
    if style == "toon":  # head from the photo on a drawn full body (256 x 384)
        from . import toon

        return toon.make_toon(src, body, remove_background if remove_bg else None)
    img = load_square(src)
    if remove_bg:
        img = remove_background(img)
    if style == "cartoon":
        img = cartoonize(img)
    elif style == "pixel":
        img = pixelate(img)
    if not has_transparency(img):  # a photo with a background: crop it to a shape
        img.putalpha(shape_mask("rounded" if style == "original" else "circle"))
    ink = (30, 30, 40) if style in ("cartoon", "pixel") else (255, 255, 255)
    return finish(img, ink)


def save_avatar(src: str | Path | None, style: str = "sticker", remove_bg: bool = False,
                body: str = "boy") -> Path:
    """Create ~/.leo/avatar.png from a picture. src=None goes back to the built-in character."""
    home().mkdir(parents=True, exist_ok=True)
    if src is None:
        avatar_path().unlink(missing_ok=True)
        source_path().unlink(missing_ok=True)
    else:
        img = make_avatar(src, style, remove_bg, body)  # raises on a bad image, before we save
        load_square(src).save(source_path())  # keep the original for re-styling
        img.save(avatar_path())
    cfg = config.load()
    cfg.update(style=style, remove_bg=remove_bg, body=body, custom=src is not None)
    config.save(cfg)
    return avatar_path()


def restyle(style: str, remove_bg: bool, body: str = "boy") -> Path:
    """Re-render the saved source picture in another style."""
    if not source_path().exists():
        raise ValueError("upload a picture first: leo avatar PHOTO")
    return save_avatar(source_path(), style, remove_bg, body)


def use_character(name: str) -> None:
    """Switch to a built-in character (drops any uploaded avatar)."""
    from . import packs
    from .characters import CHARACTERS

    options = [*packs.find(), *CHARACTERS]
    if name not in options:
        raise ValueError(f"unknown character: {name} (choose {', '.join(options)})")
    avatar_path().unlink(missing_ok=True)
    source_path().unlink(missing_ok=True)
    cfg = config.load()
    cfg.update(character=name, custom=False)
    config.save(cfg)


def custom_avatar() -> Path | None:
    """The uploaded avatar, or None when a built-in character is in use."""
    return avatar_path() if config.load()["custom"] and avatar_path().exists() else None

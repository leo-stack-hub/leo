"""Toon avatar: the head from a photo, cartoonized, on a drawn full body (boy or girl).

Pillow does the drawing. OpenCV (optional, ``opencv-python-headless``) finds the face and
gives the nicer painted look; without it Leo guesses a centred head and uses a simple filter.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

W, H = 256, 384  # final avatar
FACE_PX = 100  # width of the face on the avatar (hair and ears add to it)
FACE_CX, FACE_CY = 128, 102  # where the face centre lands
BODIES = ("boy", "girl")
S = 4  # body is drawn at 4x then shrunk, for smooth edges


# --- finding and cutting out the head -----------------------------------------------------


def _cv2():
    try:
        import cv2

        return cv2
    except ImportError:
        return None


def find_face(img: Image.Image) -> tuple[tuple[int, int, int, int], bool]:
    """((x, y, w, h), found): the largest face, or a centred guess when none is found."""
    iw, ih = img.size
    cv2 = _cv2()
    if cv2 is not None:
        import numpy as np

        gray = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        scale = min(1.0, 800 / max(iw, ih))
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(gray)
        data = getattr(getattr(cv2, "data", None), "haarcascades", "")
        cascade = cv2.CascadeClassifier(str(Path(data) / "haarcascade_frontalface_default.xml"))
        if not cascade.empty():  # OpenCV 5 ships no cascades: fall back to a centred guess
            mn = max(24, int(min(gray.shape) * 0.08))
            for neighbours in (5, 3):
                faces = cascade.detectMultiScale(gray, 1.1, neighbours, minSize=(mn, mn))
                if len(faces):
                    x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
                    return tuple(int(v / scale) for v in (x, y, w, h)), True
    side = int(min(iw, ih) * 0.5)
    return (iw // 2 - side // 2, int(ih * 0.45) - side // 2, side, side), False


def stylize(img: Image.Image) -> Image.Image:
    """Smooth, cartoon-like look with light ink lines. RGB in, RGB out."""
    cv2 = _cv2()
    if cv2 is not None:
        import numpy as np

        bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        smooth = bgr
        for _ in range(4):  # flatten skin and fabric, keep edges
            smooth = cv2.bilateralFilter(smooth, 9, 40, 9)
        gray = cv2.medianBlur(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 5)
        lines = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 8)
        ink = (lines.astype(np.float32) / 255 * 0.4 + 0.6)[..., None]
        out = Image.fromarray(cv2.cvtColor((smooth * ink).astype(np.uint8), cv2.COLOR_BGR2RGB))
    else:
        out = ImageOps.posterize(img.convert("RGB").filter(ImageFilter.MedianFilter(5)), 5)
    return ImageEnhance.Contrast(ImageEnhance.Color(out).enhance(1.25)).enhance(1.05)


def segment_head(img: Image.Image, face: tuple[int, int, int, int]) -> Image.Image | None:
    """Foreground (person) mask around the face via GrabCut, or None without OpenCV."""
    cv2 = _cv2()
    if cv2 is None:
        return None
    import numpy as np

    iw, ih = img.size
    x, y, w, h = face
    rx0, ry0 = max(0, int(x - 0.9 * w)), max(0, int(y - 0.9 * h))
    rx1, ry1 = min(iw, int(x + 1.9 * w)), min(ih, int(y + 1.9 * h))
    roi = img.convert("RGB").crop((rx0, ry0, rx1, ry1))
    k = min(1.0, 320 / max(roi.size))
    small = roi.resize((max(1, int(roi.width * k)), max(1, int(roi.height * k))), Image.LANCZOS)
    bgr = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2BGR)
    sh, sw = bgr.shape[:2]
    r = (max(1, int((x - 0.35 * w - rx0) * k)), max(1, int((y - 0.55 * h - ry0) * k)),
         min(sw - 2, int(1.7 * w * k)), min(sh - 2, int(1.7 * h * k)))
    mask = np.zeros((sh, sw), np.uint8)
    try:
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, r, bgd, fgd, 4, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    fg = cv2.GaussianBlur(fg, (5, 5), 0)
    m = Image.fromarray(fg).resize(roi.size, Image.LANCZOS)
    full = Image.new("L", img.size, 0)
    full.paste(m, (rx0, ry0))
    return full


def head_layer(img: Image.Image, face: tuple[int, int, int, int],
               fg: Image.Image | None) -> Image.Image:
    """A W x H transparent layer with the cartoon head placed where the body expects it."""
    x, y, w, h = face
    cx, cy = x + w / 2, y + h * 0.30  # an oval around face + hair + ears: head only
    rx, ry = w * 0.68, h * 0.76
    side = 2 * max(rx, ry) * 1.15
    T = 512
    box = (int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2))
    tile = img.convert("RGBA").crop(box).resize((T, T), Image.LANCZOS)
    k = T / (box[2] - box[0])
    rgb = stylize(tile.convert("RGB"))
    ox, oy = (cx - box[0]) * k, (cy - box[1]) * k
    mask = Image.new("L", (T * 2, T * 2), 0)  # drawn 2x, shrunk: smooth edge
    ImageDraw.Draw(mask).ellipse([(ox - rx * k) * 2, (oy - ry * k) * 2,
                                  (ox + rx * k) * 2, (oy + ry * k) * 2], fill=255)
    mask = mask.resize((T, T), Image.LANCZOS)
    if fg is not None:
        mask = ImageChops.multiply(mask, fg.crop(box).resize((T, T), Image.LANCZOS))
    alpha = ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(1.5)), tile.getchannel("A"))
    head = rgb.convert("RGBA")
    head.putalpha(alpha)
    scale = FACE_PX / (w * k)
    head = head.resize((round(T * scale), round(T * scale)), Image.LANCZOS)
    fx, fy = (x + w / 2 - box[0]) * k * scale, (y + h / 2 - box[1]) * k * scale
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(head, (round(FACE_CX - fx), round(FACE_CY - fy)), head)
    return layer


def _pixels(img: Image.Image) -> list:
    """All pixels as tuples (get_flattened_data on new Pillow, getdata on old)."""
    return list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())


def skin_tone(layer: Image.Image) -> tuple[int, int, int]:
    """Skin colour of the placed head (so neck and hands match), ignoring hair, beard, eyes."""
    px = [p[:3] for p in _pixels(layer.crop((FACE_CX - 36, FACE_CY - 24, FACE_CX + 36, FACE_CY + 34)))
          if p[3] > 200]
    if len(px) < 50:
        return (222, 178, 146)
    lum = sorted(sum(p) for p in px)
    cut = lum[len(lum) // 2] * 0.85  # keep pixels at least 85% as bright as the median
    keep = sorted((p for p in px if sum(p) >= cut), key=sum)
    return keep[len(keep) // 2]


# --- the bodies ------------------------------------------------------------------------------


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


class Pen:
    """Draws in avatar units (256x384) onto a 4x canvas."""

    def __init__(self) -> None:
        self.img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def rect(self, x0, y0, x1, y1, fill, r=0):
        self.d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=r * S, fill=fill)

    def oval(self, x0, y0, x1, y1, fill):
        self.d.ellipse([x0 * S, y0 * S, x1 * S, y1 * S], fill=fill)

    def poly(self, pts, fill):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def done(self) -> Image.Image:
        return self.img.resize((W, H), Image.LANCZOS)


def draw_body(body: str, skin: tuple[int, int, int]) -> Image.Image:
    p = Pen()
    skin_dk = shade(skin, 0.88)
    white, black = (246, 246, 250), (38, 38, 46)
    if body == "boy":
        top, sleeve, trim = (72, 84, 176), white, (150, 165, 235)
        shorts, cuff = (84, 126, 178), (112, 152, 200)
        # legs, socks, sneakers
        for lx in (98, 136):
            p.rect(lx, 296, lx + 22, 346, skin, 8)
            p.rect(lx, 334, lx + 22, 352, white, 4)
        p.rect(88, 350, 130, 376, white, 12)
        p.rect(88, 346, 128, 368, black, 11)
        p.rect(128, 350, 170, 376, white, 12)
        p.rect(130, 346, 170, 368, black, 11)
        # shorts with rolled cuffs
        p.rect(94, 256, 162, 284, shorts, 8)
        p.rect(90, 268, 130, 304, shorts, 8)
        p.rect(126, 268, 166, 304, shorts, 8)
        p.rect(90, 294, 130, 308, cuff, 5)
        p.rect(126, 294, 166, 308, cuff, 5)
        outfit_top = (top, sleeve, trim, white)
    else:
        top, sleeve, trim = (170, 140, 224), (214, 196, 244), (255, 214, 232)
        skirt, pleat = (244, 150, 176), (226, 124, 154)
        for lx in (102, 134):
            p.rect(lx, 300, lx + 20, 346, skin, 8)
            p.rect(lx, 334, lx + 20, 352, white, 4)
            p.rect(lx, 340, lx + 20, 344, (255, 170, 196), 1)
        p.rect(90, 350, 130, 376, white, 12)
        p.rect(90, 346, 128, 368, (255, 214, 226), 11)
        p.rect(128, 350, 168, 376, white, 12)
        p.rect(130, 346, 168, 368, (255, 214, 226), 11)
        # flared pleated skirt
        p.poly([(98, 258), (158, 258), (188, 318), (68, 318)], skirt)
        p.oval(68, 306, 188, 328, skirt)
        for fx in (84, 100, 116, 140, 156, 172):
            p.d.line([(128 * S + (fx - 128) * S * 0.42, 262 * S), (fx * S, 320 * S)],
                     fill=pleat, width=3 * S)
        outfit_top = (top, sleeve, trim, (255, 244, 232))
    top, sleeve, trim, tee = outfit_top
    # neck
    p.rect(114, 134, 142, 166, skin_dk, 8)
    # arms: sleeve, cuff band, hand
    for ax in (64, 170):
        p.rect(ax, 164, ax + 22, 254, sleeve, 11)
        p.rect(ax, 244, ax + 22, 256, trim if body == "boy" else top, 5)
        p.oval(ax + 1, 252, ax + 21, 274, skin)
    # torso: jacket, tee, collar, buttons
    p.rect(84, 152, 172, 270, top, 18)
    p.poly([(112, 154), (144, 154), (140, 270), (116, 270)], tee)
    p.rect(106, 148, 150, 164, trim, 7)
    p.poly([(112, 156), (144, 156), (128, 184)], skin_dk)
    for by in (196, 214, 232, 250):
        p.oval(106, by, 112, by + 6, trim)
        p.oval(144, by, 150, by + 6, trim)
    return light(p.done())


def light(body: Image.Image) -> Image.Image:
    """Soft left-to-right shading so the flat shapes feel rounder."""
    grad = Image.linear_gradient("L").rotate(-90).resize((W, H))  # 255 on the left .. 0 on the right
    shade_rgb = ImageChops.multiply(body.convert("RGB"),
                                    ImageOps.autocontrast(grad, cutoff=0).point(lambda v: 226 + v * 29 // 255).convert("RGB"))
    out = shade_rgb.convert("RGBA")
    out.putalpha(body.getchannel("A"))
    return out


def ground_shadow() -> Image.Image:
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([52, H - 18, W - 52, H - 4], fill=(0, 0, 0, 70))
    return sh.filter(ImageFilter.GaussianBlur(4))


def make_toon(photo: str | Path, body: str = "boy", remove_bg=None) -> Image.Image:
    if body not in BODIES:
        raise ValueError(f"body must be one of {', '.join(BODIES)}")
    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    img.thumbnail((1400, 1400), Image.LANCZOS)
    face, _found = find_face(img)
    rgba = img.convert("RGBA")
    if remove_bg is not None:
        rgba = remove_bg(rgba)
    head = head_layer(rgba, face, segment_head(img, face))
    fig = draw_body(body, skin_tone(head))
    fig.alpha_composite(head)
    ring = fig.getchannel("A").filter(ImageFilter.MaxFilter(7))  # ~3px white sticker outline
    outline = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    outline.putalpha(ring)
    out = Image.alpha_composite(ground_shadow(), outline)
    return Image.alpha_composite(out, fig)

"""Leo the lion cub, drawn live in a flat sticker style (no image files).

Front view, looking straight at you: big round head in a scalloped mane, glossy eyes, blush,
small sitting body. Flat colours with a dark outline. ``draw_lion`` expects the origin at the
feet (bottom centre); 1 unit = 1 px of a W x H box.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen

from .art import INK as OL
from .art import LW, blob, col, curve, dark, flat, rrect, soft, stroke, union
from .art import limb as _limb

W, H = 240, 210

FUR = (236, 168, 84)
BELLY = (252, 232, 192)
MANE = (196, 104, 46)
NOSE = (92, 50, 40)
PINK = (242, 150, 160)

NECK = (0.0, -80.0)  # head pivot
HEAD = (0.0, -114.0)  # head centre
SHOULDER = 27.0
REST = 30.0  # paw x when resting on the belly


@dataclass
class LPose:
    bob: float = 0.0  # whole body lift
    lean: float = 0.0  # whole body sway in degrees
    tilt: float = 0.0  # head roll in degrees
    head_dy: float = 0.0  # head drop (drinking, sleeping)
    eyes: str = "open"  # open | closed | happy | wide
    look: tuple = (0.0, 0.0)
    mouth: float = 0.1  # 0 smile .. 1 open
    tongue: bool = False
    ears: float = 0.0  # 1 = perked up
    tail: float = 0.0  # tail swing in degrees
    mane: float = 0.0  # mane ruffle
    arm_l: tuple | None = None  # paw position (viewer's left), None = resting
    arm_r: tuple | None = None
    front_l: bool = False  # draw that arm over the head
    front_r: bool = False
    feet: tuple = (0.0, 0.0)  # left / right foot lift
    prop: str | None = None  # book | laptop | bowl
    glow: bool = False  # screen light on the face


HYDRATE_LOOP = 9.0


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def pose_for(state: str, detail: str | None, t: float) -> LPose:
    s, c = math.sin, math.cos
    if state == "hydrate":  # lean down to the bowl, lap, lick lips
        T = t % HYDRATE_LOOP
        down = _ease(T / 1.2) * (1 - _ease((T - 7.0) / 1.0))
        lapping = 1.4 <= T <= 6.8
        return LPose(prop="bowl", head_dy=34 * down, look=(0, 2 * down),
                     eyes="closed" if lapping else "happy" if T > 7.2 else "open",
                     mouth=0.5 if lapping else 0.8 if T > 7.2 else 0.2,
                     tongue=lapping and s(T * 9) > 0 or T > 7.2, tail=10 * s(t * 2.4))
    if state == "greeting":  # wave a paw beside the mane
        return LPose(arm_r=(60 + 5 * s(t * 10), -116 + 5 * c(t * 10)), front_r=True,
                     eyes="happy", mouth=0.8, tilt=-6, ears=1, tail=26 * s(t * 7),
                     bob=1.2 * abs(s(t * 5)))
    if state == "thinking":  # head tilted, eyes up, paw on the chin
        return LPose(tilt=-10 + 3 * s(t * 1.6), look=(2, -3), mouth=0.0, ears=0.4,
                     arm_l=(-14, -80), front_l=True, tail=8 * s(t * 1.5))
    if state == "working":
        d = detail or ""
        if "reading" in d:
            return LPose(prop="book", arm_l=(-32, -60), arm_r=(32, -60), front_l=True,
                         front_r=True, head_dy=3, tilt=3 * s(t * 0.9), look=(0, 3), mouth=0.0,
                         tail=6 * s(t * 1.2), bob=0.5 * s(t * 2))
        if "typing" in d:
            return LPose(prop="laptop", arm_l=(-18, -42 - max(0, s(t * 13)) * 5),
                         arm_r=(18, -42 - max(0, c(t * 12)) * 5), head_dy=3, look=(0, 3),
                         mouth=0.0, glow=True, tail=8 * s(t * 2), tilt=2 * s(t * 3))
        fast = "running" in d  # marching on the spot
        ph = t * (11 if fast else 7)
        amp = 10 if fast else 6
        return LPose(feet=(max(0.0, s(ph)) * amp, max(0.0, -s(ph)) * amp), lean=3 * s(ph),
                     arm_l=(-32, -38 - 7 * s(ph)), arm_r=(32, -38 + 7 * s(ph)),
                     bob=abs(s(ph)) * amp * 0.3, mouth=0.45, ears=0.6, tail=14 * s(ph * 0.5),
                     mane=0.6)
    if state == "permission":  # alarmed: paw up high, eyes wide
        return LPose(arm_r=(52, -134 + 3 * s(t * 9)), front_r=True, eyes="wide", mouth=0.85,
                     ears=1, tilt=3 * s(t * 14), tail=18 * s(t * 9))
    if state == "waiting":  # sitting patiently, foot tapping
        return LPose(tilt=6 * s(t * 1.4), mouth=0.05, tail=12 * s(t * 2.2),
                     feet=(0.0, max(0.0, s(t * 6)) * 4))
    if state == "done":  # happy hop, both paws up
        h = abs(s(t * 6)) * 14
        return LPose(bob=h, arm_l=(-54, -122 + 4 * s(t * 12)), arm_r=(54, -122 - 4 * s(t * 12)),
                     front_l=True, front_r=True, eyes="happy", mouth=1, ears=1,
                     tail=30 * s(t * 8), mane=1)
    if state == "sleeping":  # head nodding, breathing
        return LPose(head_dy=8 + s(t * 1.1), tilt=12, eyes="closed", mouth=0.0,
                     tail=2 * s(t * 1.1), bob=0.8 * s(t * 1.1), ears=-0.5)
    return LPose(tail=10 * s(t * 1.8), tilt=3 * s(t * 1.1), bob=0.8 * (1 + s(t * 2)) / 2,
                 eyes="closed" if (t % 4.2) < 0.15 else "open", mane=0.4)  # idle


# --- primitives ------------------------------------------------------------------------------


def limb(p, a, b, width, fill) -> None:
    """Outlined capsule from a to b, with a round paw at b."""
    _limb(p, a, b, width, fill, (fill, width * 0.62, width * 0.58))


# --- parts -----------------------------------------------------------------------------------


def draw_tail(p, swing: float) -> None:
    r = math.radians(swing)
    base = (28, -20)
    end = (68 + 10 * math.sin(r), -66 - 8 * math.cos(r) + 6 * math.sin(r))
    path = QPainterPath(QPointF(*base))
    path.cubicTo(QPointF(58, -14), QPointF(end[0] + 4, end[1] + 30), QPointF(*end))
    stroke(p, path, OL, 7 + 2 * LW)
    stroke(p, path, FUR, 7)
    blob(p, end[0], end[1] - 4, 8, 10, MANE)


def draw_body(p, feet) -> None:
    blob(p, 0, -46, 38, 38, FUR)
    flat(p, 0, -40, 23, 24, BELLY)
    for sx, lift in ((-1, feet[0]), (1, feet[1])):
        x, y = sx * 22, -9 - lift
        blob(p, x, y, 15, 9, FUR)
        for dx in (-3.5, 3.5):  # toes
            stroke(p, curve((x + dx, y + 1), (x + dx, y + 4), (x + dx, y + 7)), OL, 1.8)


def draw_arm(p, side: int, paw, front: bool = False) -> None:
    paw = paw or (side * REST, -36)
    start = (side * 38, -84) if front else (side * SHOULDER, -72)  # front arms come out of the mane
    limb(p, start, paw, 14, FUR)


def draw_eye(p, x, y, kind: str, look) -> None:
    if kind == "closed":  # sleepy downward arc
        stroke(p, curve((x - 6, y), (x - 3, y + 4), (x + 3, y + 4), (x + 6, y)), OL, 2.8)
        return
    if kind == "happy":  # ^ arc
        stroke(p, curve((x - 6, y + 2), (x - 3, y - 5), (x + 3, y - 5), (x + 6, y + 2)), OL, 2.8)
        return
    lx, ly = look
    if kind == "wide":
        blob(p, x, y, 8.5, 9.5, (255, 255, 255), 2)
        flat(p, x + lx * 0.6, y + ly * 0.6, 4.6, 5.2, (36, 26, 22))
        flat(p, x + lx * 0.6 - 1.5, y + ly * 0.6 - 2, 1.6, 1.6, (255, 255, 255))
        return
    ex, ey = x + lx * 0.5, y + ly * 0.5
    flat(p, ex, ey, 6.4, 7.8, (36, 26, 22))
    flat(p, ex - 2, ey - 3, 2.6, 2.6, (255, 255, 255))
    flat(p, ex + 2.2, ey + 2.6, 1.2, 1.2, (255, 255, 255))


def draw_mouth(p, P: LPose) -> None:
    x, y = 0, -100
    stroke(p, curve((x, y - 1), (x, y + 1), (x, y + 2)), NOSE, 2)
    if P.mouth < 0.3:  # little "w" smile
        stroke(p, curve((x, y + 2), (x - 2, y + 5), (x - 6, y + 4), (x - 7, y + 1)), NOSE, 2)
        stroke(p, curve((x, y + 2), (x + 2, y + 5), (x + 6, y + 4), (x + 7, y + 1)), NOSE, 2)
    else:
        m = QPainterPath()
        m.addEllipse(QRectF(x - 5.5, y + 1, 11, 4 + 8 * P.mouth))
        p.setPen(QPen(col(NOSE), 1.6))
        p.setBrush(col((110, 40, 44)))
        p.drawPath(m)
        flat(p, x, y + 3 + 7 * P.mouth, 3.6, 1.8 + 1.4 * P.mouth, PINK)
    if P.tongue:
        blob(p, x, y + 9 + 3 * P.mouth, 4, 5, PINK, 1.6)


def draw_head(p, P: LPose, t: float) -> None:
    hx, hy = HEAD
    tufts = []
    for i in range(16):  # scalloped mane
        a = i / 16 * 2 * math.pi + 0.08 * math.sin(t * 2 + i) * (0.4 + P.mane)
        tufts.append((hx + 46 * math.cos(a), hy + 2 + 44 * math.sin(a), 15))
    union(p, tufts + [(hx, hy + 2, 48)], MANE)
    for sx in (-1, 1):  # ears
        ey = hy - 36 - 3 * P.ears
        blob(p, hx + sx * 27, ey, 12, 11.5, FUR)
        flat(p, hx + sx * 27, ey + 1.5, 6.5, 6, PINK)
    blob(p, hx, hy + 2, 37, 34, FUR)  # face
    for sx in (-1, 1):  # little forehead fur marks
        stroke(p, curve((hx + sx * 4, hy - 30), (hx + sx * 5, hy - 26), (hx + sx * 4, hy - 23)),
               dark(FUR, 0.18), 2.2)
    for sx in (-1, 1):
        flat(p, hx + sx * 24, hy + 13, 7, 4, PINK, 170)  # blush
        draw_eye(p, hx + sx * 14, hy - 3, P.eyes, P.look)
    for sx in (-1, 1):  # muzzle
        flat(p, hx + sx * 6.5, hy + 16, 9, 7, BELLY)
        for dx, dy in ((5, -2), (9, 0), (6, 2)):  # whisker dots
            flat(p, hx + sx * dx, hy + 16 + dy, 0.9, 0.9, dark(FUR, 0.35))
    nose = QPainterPath()
    nose.moveTo(QPointF(hx - 5.5, hy + 8))
    nose.quadTo(QPointF(hx, hy + 6), QPointF(hx + 5.5, hy + 8))
    nose.quadTo(QPointF(hx + 1, hy + 14), QPointF(hx, hy + 14))
    nose.quadTo(QPointF(hx - 1, hy + 14), QPointF(hx - 5.5, hy + 8))
    p.setPen(Qt.NoPen)
    p.setBrush(col(NOSE))
    p.drawPath(nose)
    flat(p, hx - 1.6, hy + 8.6, 1.6, 1, (180, 130, 120))
    draw_mouth(p, P)
    if P.glow:
        soft(p, hx, hy + 20, 30, 12, (170, 225, 255), 40)


def draw_prop(p, P: LPose) -> None:
    if P.prop == "book":  # open book held up, cover towards us
        for sx, c in ((-1, (226, 84, 74)), (1, (64, 132, 204))):
            cover = QPainterPath()
            cover.moveTo(QPointF(0, -78))
            cover.lineTo(QPointF(sx * 32, -82))
            cover.lineTo(QPointF(sx * 32, -48))
            cover.lineTo(QPointF(0, -44))
            cover.closeSubpath()
            p.setPen(QPen(col(OL), LW))
            p.setBrush(col(c))
            p.drawPath(cover)
        stroke(p, curve((0, -78), (0, -61), (0, -44)), dark((226, 84, 74), 0.4), 2)
        flat(p, -16, -64, 6, 6, (250, 220, 120))  # a little star-ish sticker
    elif P.prop == "laptop":  # back of the lid towards us
        base = rrect(-44, -16, 88, 8, 3)
        p.setPen(QPen(col(OL), LW))
        p.setBrush(col((150, 158, 172)))
        p.drawPath(base)
        p.setBrush(col((188, 194, 206)))
        p.drawPath(rrect(-36, -62, 72, 48, 6))
        flat(p, 0, -38, 6, 6, (250, 252, 255))  # logo light
        flat(p, -2.2, -40, 1.6, 1.6, (188, 194, 206))
        flat(p, 2.2, -40, 1.6, 1.6, (188, 194, 206))
    elif P.prop == "bowl":
        p.setPen(QPen(col(OL), LW))
        p.setBrush(col((120, 196, 240)))
        p.drawEllipse(QPointF(0, -18), 30, 6)
        bowl = QPainterPath()
        bowl.moveTo(QPointF(-32, -18))
        bowl.quadTo(QPointF(-30, 0), QPointF(0, 0))
        bowl.quadTo(QPointF(30, 0), QPointF(32, -18))
        bowl.quadTo(QPointF(0, -10), QPointF(-32, -18))
        p.setBrush(col((90, 150, 220)))
        p.drawPath(bowl)
        flat(p, -14, -8, 6, 2, (160, 210, 250))


def draw_lion(p: QPainter, state: str, detail: str | None, t: float) -> None:
    P = pose_for(state, detail, t)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    k = max(0.6, 1 - P.bob / 40)
    soft(p, 0, -2, 64 * k, 9 * k, (0, 0, 0), 80)  # ground shadow
    p.translate(0, -P.bob)
    p.rotate(P.lean)
    draw_tail(p, P.tail)
    draw_body(p, P.feet)
    for side, paw, front in ((-1, P.arm_l, P.front_l), (1, P.arm_r, P.front_r)):
        if not front:
            draw_arm(p, side, paw)
    p.save()
    p.translate(0, P.head_dy)
    p.translate(*NECK)
    p.rotate(P.tilt)
    p.translate(-NECK[0], -NECK[1])
    draw_head(p, P, t)
    p.restore()
    if P.prop:
        draw_prop(p, P)
    for side, paw, front in ((-1, P.arm_l, P.front_l), (1, P.arm_r, P.front_r)):
        if front:
            draw_arm(p, side, paw, True)
    p.restore()

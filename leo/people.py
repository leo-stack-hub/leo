"""Leo's human friends: an original boy and girl, drawn live in a flat sticker style.

Chibi proportions (big head, small body), flat colours with a dark outline, front view.
``draw_person`` expects the origin at the feet (bottom centre); 1 unit = 1 px of a W x H box.
Poses are just "where are the hands and feet".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath

from .art import INK, blob, col, curve, dark, flat, ink, light, limb, rrect, soft, stroke, union

W, H = 200, 240
HEAD = (0.0, -130.0)  # head centre
NECK = (0.0, -86.0)  # head pivot
SH_X, SH_Y = 21, -80  # shoulders
HIP_X, HIP_Y = 11, -40
SIT_DROP = 20
REST = ((-30, -46), (30, -46))  # hands hanging by the sides

SKIN = {"boy": (246, 200, 164), "girl": (250, 208, 176)}
LOOK = {
    "boy": dict(top=(240, 176, 62), legs=(108, 132, 96), shoe=(250, 250, 252), sole=(62, 156, 166),
                hair=(52, 50, 84), accent=(62, 170, 178)),
    "girl": dict(top=(146, 216, 198), skirt=(66, 86, 142), shoe=(250, 204, 72),
                 sole=(255, 248, 236), hair=(132, 76, 50), accent=(250, 140, 66)),
}


@dataclass
class HPose:
    hand_l: tuple = REST[0]
    hand_r: tuple = REST[1]
    front: bool = False  # draw the arms over the head (hand on chin)
    foot_l: float = 0.0  # foot lift
    foot_r: float = 0.0
    bob: float = 0.0
    lean: float = 0.0
    tilt: float = 0.0
    head_dy: float = 0.0
    mouth: float = 0.15  # 0 smile .. 1 open
    eyes: str = "open"  # open | closed | happy | wide
    look: tuple = (0.0, 0.0)
    brow: float = 0.0
    sit: bool = False
    prop: str | None = None  # book | laptop | bottle
    ponytail: float = 1.0
    extra: dict = field(default_factory=dict)


HYDRATE_LOOP = 9.0
# (time, bottle hand, bottle angle, head tilt): notice -> show the bottle -> sip -> "ahh"
_DRINK = [(0.0, REST[1], 0, 0), (1.2, (50, -112), 0, 5), (2.2, (16, -100), -75, -7),
          (6.0, (16, -100), -75, -7), (7.0, (50, -110), 0, 6), (9.0, REST[1], 0, 0)]


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def hydrate_pose(t: float) -> HPose:
    T = t % HYDRATE_LOOP
    for (t0, h0, r0, k0), (t1, h1, r1, k1) in zip(_DRINK, _DRINK[1:]):
        if T <= t1:
            e = _ease((T - t0) / (t1 - t0))
            hand = (h0[0] + (h1[0] - h0[0]) * e, h0[1] + (h1[1] - h0[1]) * e)
            rot, tilt = r0 + (r1 - r0) * e, k0 + (k1 - k0) * e
            break
    sipping = 2.2 <= T <= 6.0
    level = 0.9 - 0.45 * max(0.0, min(1.0, (T - 2.2) / 3.8))
    if sipping:
        eyes, mouth, dy = "closed", 0.0, 1.2 * abs(math.sin(T * 5.5))  # gulps
    elif T > 6.4:
        eyes, mouth, dy = "happy", 1.0, 0.0  # "ahh!"
    else:
        eyes, mouth, dy = "open", 0.6, 0.0
    return HPose(hand_r=hand, tilt=tilt, eyes=eyes, mouth=mouth, head_dy=dy, prop="bottle",
                 bob=1.0 * abs(math.sin(T * 4)) if T < 1.2 or T > 7 else 0.3,
                 extra={"rot": rot, "level": level}, ponytail=1.5)


def pose_for(state: str, detail: str | None, t: float) -> HPose:
    s, c = math.sin, math.cos
    if state == "hydrate":
        return hydrate_pose(t)
    if state == "greeting":
        return HPose(hand_r=(58 + 5 * s(t * 10), -122 + 5 * c(t * 10)), tilt=7, mouth=0.7,
                     eyes="happy", bob=1.2 * abs(s(t * 5)), ponytail=2.5)
    if state == "thinking":
        a = t * 3.2
        return HPose(hand_r=(12, -88), front=True, tilt=-6 + 2 * s(t * 1.6), look=(3, -4),
                     brow=0.4, mouth=0.0, bob=1.0 * abs(s(a)),
                     foot_l=max(0, s(a)) * 5, foot_r=max(0, -s(a)) * 5)
    if state == "working":
        d = detail or ""
        if "reading" in d:
            return HPose(hand_l=(-26, -62), hand_r=(26, -62), front=True, prop="book",
                         head_dy=3, tilt=-3, look=(0, 4), mouth=0.0, bob=0.6 * s(t * 2))
        if "typing" in d:
            return HPose(hand_l=(-16 + 2 * s(t * 13), -58 - max(0, s(t * 15)) * 4),
                         hand_r=(16 + 2 * c(t * 12), -58 - max(0, c(t * 14)) * 4), prop="laptop",
                         head_dy=3, look=(0, 3), mouth=0.0, bob=0.5 * s(t * 3))
        run = "running" in d
        ph = t * (11 if run else 7)
        amp = 9 if run else 6
        return HPose(hand_l=(-30, -54 + amp * s(ph)), hand_r=(30, -54 - amp * s(ph)),
                     foot_l=max(0, s(ph)) * amp, foot_r=max(0, -s(ph)) * amp,
                     bob=abs(s(ph)) * (4 if run else 2.5), lean=6 if run else 3, mouth=0.45,
                     ponytail=3)
    if state == "permission":
        return HPose(hand_r=(56, -150), eyes="wide", mouth=0.85, brow=1, head_dy=-2,
                     ponytail=0.5)
    if state == "waiting":
        return HPose(sit=True, hand_l=(-30, -38), hand_r=(30, -38), tilt=5 * s(t * 1.4),
                     mouth=0.05, ponytail=0.6)
    if state == "done":
        h = abs(s(t * 6)) * 12
        return HPose(hand_l=(-58, -142 + 4 * s(t * 12)), hand_r=(58, -142 - 4 * s(t * 12)),
                     bob=h, eyes="happy", mouth=1, ponytail=3)
    if state == "sleeping":
        return HPose(sit=True, hand_l=(-22, -40), hand_r=(22, -40), tilt=14 + 2 * s(t * 1.1),
                     head_dy=6 + s(t * 1.1), eyes="closed", mouth=0.1, ponytail=0.2,
                     bob=0.8 * s(t * 1.1))
    return HPose(hand_l=(-30, -46 + 2 * s(t * 2)), hand_r=(30, -46 + 2 * c(t * 2)),
                 tilt=2 * s(t * 1.1), bob=0.8 * (1 + s(t * 2)) / 2, ponytail=1)  # idle


# --- body ------------------------------------------------------------------------------------


def draw_legs(p, who, P: HPose, drop: float) -> None:
    A, skin = LOOK[who], SKIN[who]
    for side, lift in ((-1, P.foot_l), (1, P.foot_r)):
        if P.sit:  # legs out in front, feet turned out
            hip, foot = (side * HIP_X, HIP_Y + drop), (side * 24, -8)
        else:
            hip, foot = (side * HIP_X, HIP_Y), (side * 13, -6 - lift)
        if who == "boy":
            limb(p, hip, foot, 15, A["legs"])
        else:
            limb(p, hip, foot, 11, skin)
            limb(p, (foot[0], foot[1] - 7), foot, 12, (252, 252, 255))  # socks
        fx, fy = foot[0] + side * 2, foot[1]
        blob(p, fx, fy, 12, 7, A["shoe"])
        stroke(p, curve((fx - 10, fy + 3), (fx, fy + 6), (fx + 10, fy + 3)), A["sole"], 2.4)


def torso_path(top: float, bot: float, wt: float, wb: float) -> QPainterPath:
    path = QPainterPath(QPointF(-wt + 8, top))
    path.quadTo(QPointF(-wt, top), QPointF(-wt - 1, top + 9))
    path.lineTo(QPointF(-wb, bot - 7))
    path.quadTo(QPointF(-wb, bot), QPointF(-wb + 8, bot))
    path.lineTo(QPointF(wb - 8, bot))
    path.quadTo(QPointF(wb, bot), QPointF(wb, bot - 7))
    path.lineTo(QPointF(wt + 1, top + 9))
    path.quadTo(QPointF(wt, top), QPointF(wt - 8, top))
    path.closeSubpath()
    return path


def draw_torso(p, who) -> None:
    A = LOOK[who]
    top = SH_Y - 6
    if who == "boy":  # hoodie
        blob(p, 0, -42, 21, 9, A["legs"])  # pelvis
        ink(p, torso_path(top, -36, 22, 25), A["top"])
        blob(p, 0, top + 2, 15, 5, dark(A["top"], 0.22), 2)  # hood at the neck
        ink(p, rrect(-12, -60, 24, 14, 5), dark(A["top"], 0.08), 2)  # pocket
        for sx in (-1, 1):  # drawstrings
            stroke(p, curve((sx * 5, top + 6), (sx * 6, top + 12), (sx * 5, top + 18)),
                   (255, 246, 226), 2)
    else:  # tee + pinafore skirt
        ink(p, torso_path(top, -46, 20, 22), A["top"])
        skirt = QPainterPath(QPointF(-21, -56))
        skirt.lineTo(QPointF(21, -56))
        skirt.cubicTo(QPointF(26, -46), QPointF(32, -36), QPointF(35, -26))
        skirt.quadTo(QPointF(0, -20), QPointF(-35, -26))
        skirt.cubicTo(QPointF(-32, -36), QPointF(-26, -46), QPointF(-21, -56))
        ink(p, skirt, A["skirt"])
        ink(p, rrect(-12, -74, 24, 20, 4), A["skirt"], 2)  # bib
        for sx in (-1, 1):
            stroke(p, curve((sx * 9, -73), (sx * 12, -78), (sx * 15, top + 1)), A["skirt"], 4)
            flat(p, sx * 7, -68, 2.2, 2.2, (250, 214, 90))  # buttons
        for fx in (-16, 0, 16):  # skirt folds
            stroke(p, curve((fx * 0.6, -52), (fx * 0.9, -40), (fx * 1.2, -28)),
                   dark(A["skirt"], 0.35), 1.4)


def draw_arm(p, who, side: int, hand) -> None:
    sleeve = LOOK[who]["top"]
    limb(p, (side * SH_X, SH_Y), hand, 12, sleeve, (SKIN[who], 7, 7))


# --- head ------------------------------------------------------------------------------------


def draw_eye(p, x, y, kind: str, look, lashes: bool) -> None:
    if kind == "closed":
        stroke(p, curve((x - 6, y), (x - 3, y + 4), (x + 3, y + 4), (x + 6, y)), INK, 2.6)
        return
    if kind == "happy":
        stroke(p, curve((x - 6, y + 2), (x - 3, y - 5), (x + 3, y - 5), (x + 6, y + 2)), INK, 2.6)
        return
    lx, ly = look[0] * 0.5, look[1] * 0.5
    if kind == "wide":
        blob(p, x, y, 8.5, 9.5, (255, 255, 255), 2)
        flat(p, x + lx, y + ly, 4.6, 5.2, (36, 26, 22))
        flat(p, x + lx - 1.5, y + ly - 2, 1.6, 1.6, (255, 255, 255))
    else:
        flat(p, x + lx, y + ly, 6.2, 7.6, (36, 26, 22))
        flat(p, x + lx - 2, y + ly - 3, 2.5, 2.5, (255, 255, 255))
        flat(p, x + lx + 2.2, y + ly + 2.6, 1.1, 1.1, (255, 255, 255))
    if lashes:
        sx = 1 if x > 0 else -1
        stroke(p, curve((x + sx * 5, y - 6), (x + sx * 8, y - 8), (x + sx * 9, y - 10)), INK, 1.8)


def draw_head(p, who, P: HPose, t: float) -> None:
    A, skin = LOOK[who], SKIN[who]
    hair = A["hair"]
    hx, hy = HEAD
    boy = who == "boy"
    # hair behind the head
    if boy:
        union(p, [(hx, hy - 6, 50, 48)], hair)
        tuft = QPainterPath(QPointF(hx - 6, hy - 50))  # cowlick
        tuft.quadTo(QPointF(hx - 2, hy - 68), QPointF(hx + 16, hy - 70))
        tuft.quadTo(QPointF(hx + 6, hy - 62), QPointF(hx + 8, hy - 50))
        tuft.closeSubpath()
        ink(p, tuft, hair)
    else:
        p.save()  # ponytail, swinging from the top right
        p.translate(hx + 34, hy - 38)
        p.rotate(-50 + 10 * math.sin(t * 3) * P.ponytail)
        union(p, [(0, 24, 10, 24), (1, 44, 7, 9)], hair)
        p.restore()
        union(p, [(hx, hy - 4, 53, 49), (hx - 40, hy + 24, 10, 26), (hx + 40, hy + 24, 10, 26)],
              hair)
    for sx in (-1, 1):  # ears
        blob(p, hx + sx * 45, hy + 4, 7.5, 9.5, skin)
        flat(p, hx + sx * 45, hy + 5, 3.5, 5, dark(skin, 0.15))
    blob(p, hx, hy + 2, 45, 42, skin)  # face
    # front hair: a cap with a fringe edge cut out of it
    cap = QPainterPath()
    cap.addEllipse(QPointF(hx, hy - 6), 50, 48)
    face = QPainterPath(QPointF(hx - 60, hy + 60))
    if boy:  # spiky fringe
        pts = [(-60, -2), (-46, -2), (-38, -24), (-30, -12), (-20, -30), (-10, -14), (2, -32),
               (12, -16), (24, -30), (32, -12), (42, -22), (47, -2), (60, -2)]
    else:  # soft rounded bangs
        pts = [(-60, 6), (-47, 6)]
    for x, y in pts:
        face.lineTo(QPointF(hx + x, hy + y))
    if not boy:
        face.quadTo(QPointF(hx - 44, hy - 26), QPointF(hx - 24, hy - 22))
        face.quadTo(QPointF(hx - 14, hy - 32), QPointF(hx - 2, hy - 22))
        face.quadTo(QPointF(hx + 12, hy - 34), QPointF(hx + 26, hy - 22))
        face.quadTo(QPointF(hx + 44, hy - 26), QPointF(hx + 47, hy + 6))
        face.lineTo(QPointF(hx + 60, hy + 6))
    face.lineTo(QPointF(hx + 60, hy + 60))
    face.closeSubpath()
    ink(p, cap.subtracted(face), hair)
    stroke(p, curve((hx - 30, hy - 40), (hx - 10, hy - 52), (hx + 14, hy - 48)), light(hair, 0.4),
           3, 160)  # shine
    if not boy:
        blob(p, hx + 30, hy - 44, 10, 6.5, A["accent"])  # scrunchie
    # face
    eyes = "closed" if (t % 4.0) < 0.12 and P.eyes == "open" else P.eyes
    for sx in (-1, 1):
        flat(p, hx + sx * 27, hy + 16, 7.5, 4.5, (246, 140, 150), 160)  # blush
        draw_eye(p, hx + sx * 16, hy + 2, eyes, P.look, not boy)
        by = hy - 12 - 4 * P.brow
        stroke(p, curve((hx + sx * 10, by + 1 - 2 * P.brow), (hx + sx * 16, by - 2),
                        (hx + sx * 22, by + 1)), dark(hair, 0.15), 2.6 if boy else 2)
    flat(p, hx, hy + 14, 2.2, 1.6, dark(skin, 0.25))  # nose
    m, my = P.mouth, hy + 22
    if m < 0.25:
        stroke(p, curve((hx - 6, my), (hx, my + 5 * (1 - m * 3)), (hx + 6, my)), (130, 56, 56), 2.2)
    else:
        mouth = QPainterPath()
        mouth.addEllipse(QRectF(hx - 4 - 3 * m, my - 2, 8 + 6 * m, 4 + 7 * m))
        ink(p, mouth, (120, 40, 48), 1.6)
        flat(p, hx, my + 1 + 5 * m, 2.6 + 2 * m, 1.4 + 1.2 * m, (240, 130, 140))


# --- props -----------------------------------------------------------------------------------


def draw_prop(p, who, P: HPose) -> None:
    A = LOOK[who]
    if P.prop == "laptop":  # back of the lid towards us
        ink(p, rrect(-42, -32, 84, 7, 3), (150, 158, 172))
        ink(p, rrect(-34, -74, 68, 44, 6), (188, 194, 206))
        flat(p, 0, -52, 6, 6, (250, 252, 255))
    elif P.prop == "book":  # open book held up, cover towards us
        for sx, c in ((-1, A["accent"]), (1, (64, 132, 204))):
            cover = QPainterPath(QPointF(0, -78))
            cover.lineTo(QPointF(sx * 28, -82))
            cover.lineTo(QPointF(sx * 28, -50))
            cover.lineTo(QPointF(0, -46))
            cover.closeSubpath()
            ink(p, cover, c)
        flat(p, -14, -64, 5, 5, (250, 230, 140))


def draw_bottle(p, hand, P: HPose, who) -> None:
    """A water bottle in the right hand, tipping towards the mouth while sipping."""
    p.save()
    p.translate(*hand)
    p.rotate(P.extra.get("rot", 0))
    body = rrect(-7, -30, 14, 34, 5)
    ink(p, body, (214, 236, 250))
    p.save()  # the water, clipped to the bottle
    p.setClipPath(body)
    top = 4 - 34 * P.extra.get("level", 0.8)
    p.fillRect(QRectF(-8, top, 16, 40 - top), col((96, 176, 240)))
    p.restore()
    stroke(p, body, INK, 2.2)
    ink(p, rrect(-5, -36, 10, 7, 2), LOOK[who]["accent"], 2)  # cap
    blob(p, 0, 0, 7, 7, SKIN[who])  # fingers around the bottle
    p.restore()


def draw_person(p: QPainter, who: str, state: str, detail: str | None, t: float) -> None:
    P = pose_for(state, detail, t)
    drop = SIT_DROP if P.sit else 0
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    k = max(0.6, 1 - P.bob / 40)
    soft(p, 0, -2, (66 if P.sit else 52) * k, 8 * k, (0, 0, 0), 80)  # ground shadow
    p.translate(0, -P.bob)
    draw_legs(p, who, P, drop)
    p.save()  # the upper body sits down and leans around the hips
    p.translate(0, HIP_Y + drop)
    p.rotate(P.lean)
    p.translate(0, -HIP_Y)
    draw_torso(p, who)
    arms = ((-1, P.hand_l), (1, P.hand_r))
    if P.front:  # both arms over the head (hand on chin, holding a book)
        behind, front = (), arms
    elif P.prop == "bottle":  # the bottle hand comes up in front of the face
        behind, front = arms[:1], arms[1:]
    else:
        behind, front = arms, ()
    for side, hand in behind:
        draw_arm(p, who, side, hand)
    p.save()
    p.translate(NECK[0], NECK[1] + P.head_dy)
    p.rotate(P.tilt)
    p.translate(-NECK[0], -NECK[1])
    draw_head(p, who, P, t)
    p.restore()
    if P.prop in ("book", "laptop"):
        draw_prop(p, who, P)
    for side, hand in front:
        draw_arm(p, who, side, hand)
    if P.prop == "bottle":
        draw_bottle(p, P.hand_r, P, who)
    p.restore()
    p.restore()

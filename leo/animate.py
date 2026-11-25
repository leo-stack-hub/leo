"""Bring a single picture to life: mesh-style warps of one image (needs numpy + OpenCV).

Legs swing and lift, the head nods and tilts, the mane sways, the tail wags and the body
breathes. Each state is a short seamless loop of pre-rendered frames. The regions below are
tuned for a four-legged character standing in 3/4 view facing right;
other pictures just get gentler, still-plausible motion.
"""

from __future__ import annotations

import math

import numpy as np

try:
    import cv2
except ImportError:  # no OpenCV: the app falls back to a still picture
    cv2 = None

N = 24  # frames per loop

# amplitude presets, as fractions of the picture height (angles in degrees)
#   walk: leg swing   lift: foot lift   bob: body bob   breathe: chest rise
#   nod: head nod     tilt: head tilt (held)   sway: mane sway   tail: tail swing   shake: head shake
REST = dict(walk=0, lift=0, bob=0, breathe=0.004, nod=1.5, tilt=0, sway=0.004, tail=7, shake=0)
PRESETS = {
    "idle": REST,
    "greeting": dict(REST, nod=7, bob=0.01, sway=0.008, tail=24, tilt=-4),
    "thinking": dict(REST, tilt=9, nod=2, tail=5, breathe=0.003),
    "working": dict(REST, walk=0.05, lift=0.035, bob=0.012, nod=3, sway=0.009, tail=14, breathe=0.005),
    "reading": dict(REST, tilt=12, nod=2, tail=4),
    "typing": dict(REST, nod=4, bob=0.006, tail=10, sway=0.006),
    "done": dict(REST, nod=8, bob=0.015, tail=30, sway=0.01, tilt=-5),
    "waiting": dict(REST, tilt=-8, nod=1.5, tail=8),
    "permission": dict(REST, shake=6, tail=3, nod=0),
    "sleeping": dict(REST, tilt=16, nod=0.5, breathe=0.01, tail=2, sway=0.002),
}
CYCLES = {"working": 1.5, "greeting": 1.6, "done": 1.8, "permission": 2.2}  # loops per second
DEFAULT_CYCLES = 0.5


def _smooth(a, b, x):
    k = np.clip((x - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


class Animator:
    def __init__(self, rgba: np.ndarray) -> None:
        """rgba: uint8 H x W x 4 (straight alpha)."""
        h, w = rgba.shape[:2]
        self.h, self.w = h, w
        a = rgba[..., 3:4].astype(np.float32) / 255
        pre = np.concatenate([rgba[..., :3].astype(np.float32) * a, rgba[..., 3:4].astype(np.float32)], axis=2)
        self.src = pre
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        self.X, self.Y = xs, ys
        U, V = xs / w, ys / h
        self.U, self.V = U, V

        def g(cx, cy, rx, ry):
            return np.exp(-(((U - cx) / rx) ** 2) - (((V - cy) / ry) ** 2)).astype(np.float32)

        self.m_head = np.minimum(1, 1.7 * g(0.72, 0.22, 0.24, 0.2))
        self.m_mane = g(0.70, 0.50, 0.22, 0.26) * _smooth(0.12, 0.35, V)
        self.m_tail = np.minimum(1, 2.2 * g(0.10, 0.55, 0.12, 0.12))
        self.m_body = _smooth(0.80, 0.30, V) * _smooth(0.05, 0.2, U)
        self.legs = [(0.20, 0), (0.49, math.pi), (0.65, 0), (0.85, math.pi)]  # x centre, trot phase
        self.m_legs = [np.exp(-(((U - cx) / 0.07) ** 2)).astype(np.float32) for cx, _ in self.legs]
        self.m_foot = _smooth(0.62, 0.95, V)
        self.m_toe = _smooth(0.86, 0.97, V)
        self.cache: dict[tuple, list[np.ndarray]] = {}

    def _rot(self, pivot, ang_deg, mask):
        """Displacement of content rotated about pivot (pixels) weighted by mask."""
        a = math.radians(ang_deg)
        px, py = pivot[0] * self.w, pivot[1] * self.h
        rx, ry = self.X - px, self.Y - py
        dx = (math.cos(a) - 1) * rx - math.sin(a) * ry
        dy = math.sin(a) * rx + (math.cos(a) - 1) * ry
        return dx * mask, dy * mask

    def render(self, state: str, detail: str | None, k: int) -> np.ndarray:
        p = PRESETS.get(self._key(state, detail), REST)
        ph = 2 * math.pi * k / N
        s, c = math.sin, math.cos
        h = self.h
        dx = np.zeros_like(self.X)
        dy = np.zeros_like(self.Y)

        # body bob and breathing (the upper body rises slightly)
        dy += -(p["bob"] * abs(s(ph)) + p["breathe"] * s(ph)) * h * self.m_body
        # head: tilt held, plus nod (and a quick shake for "permission")
        ang = p["tilt"] + p["nod"] * s(ph + 0.6) + p["shake"] * s(ph * 3)
        hx, hy = self._rot((0.66, 0.36), ang, self.m_head)
        dx += hx
        dy += hy
        # mane sways with a delay, longer strands further down
        dx += p["sway"] * self.w * np.sin(ph - 1.0 + self.V * 3) * self.m_mane
        # tail wag
        tx, ty = self._rot((0.27, 0.60), p["tail"] * s(ph * (2 if state in ("greeting", "done") else 1) + 1.2),
                           self.m_tail)
        dx += tx
        dy += ty
        # legs: pendulum swing, lifting the foot while it swings forward
        if p["walk"]:
            for (cx, lp), m in zip(self.legs, self.m_legs):
                dx += p["walk"] * h * s(ph + lp) * m * self.m_foot
                dy += -p["lift"] * h * max(0.0, c(ph + lp)) * m * self.m_toe
        out = cv2.remap(self.src, self.X - dx, self.Y - dy, cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        return np.clip(out, 0, 255).astype(np.uint8)

    @staticmethod
    def _key(state: str, detail: str | None) -> str:
        d = (detail or "").lower()
        if state == "working":
            return "reading" if "read" in d else "typing" if "typ" in d else "working"
        return state

    def frames(self, state: str, detail: str | None) -> list[np.ndarray]:
        key = self._key(state, detail)
        if key not in self.cache:
            self.cache[key] = [self.render(state, detail, k) for k in range(N)]
        return self.cache[key]

    def frame(self, state: str, detail: str | None, t: float) -> np.ndarray:
        fr = self.frames(state, detail)
        cps = CYCLES.get(self._key(state, detail), DEFAULT_CYCLES)
        if self._key(state, detail) == "sleeping":
            cps = 0.25
        return fr[int(t * cps * N) % N]

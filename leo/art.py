"""Shading toolkit for the built-in characters: gradients, soft shadows, glossy eyes.

Everything draws with QPainter, so characters stay sharp at any size and can animate.
Colours are (r, g, b) tuples.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)


def col(c, a=255) -> QColor:
    return QColor(int(c[0]), int(c[1]), int(c[2]), int(a))


def light(c, k):
    return tuple(int(v + (255 - v) * k) for v in c)


def dark(c, k):
    return tuple(int(v * (1 - k)) for v in c)


def radial(r, base, hi=0.30, lo=0.30, a=255) -> QBrush:
    """Round, softly lit look: light spot upper-left, darker rim."""
    g = QRadialGradient(QPointF(0, 0), r, QPointF(-0.35 * r, -0.42 * r))
    g.setColorAt(0.0, col(light(base, hi), a))
    g.setColorAt(0.55, col(base, a))
    g.setColorAt(1.0, col(dark(base, lo), a))
    return QBrush(g)


def flat(p: QPainter, x, y, rx, ry, rgb, a=255) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(col(rgb, a))
    p.drawEllipse(QPointF(x, y), rx, ry)


def gblob(p: QPainter, x, y, rx, ry, base, a=255, hi=0.30, lo=0.30, rot=0.0) -> None:
    """Ellipse with a radial gradient."""
    p.save()
    p.translate(x, y)
    p.rotate(rot)
    p.scale(1, ry / rx)
    p.setPen(Qt.NoPen)
    p.setBrush(radial(rx, base, hi, lo, a))
    p.drawEllipse(QPointF(0, 0), rx, rx)
    p.restore()


def soft(p: QPainter, x, y, rx, ry, rgb=(0, 0, 0), a=70) -> None:
    """Soft-edged blob: shadows, blush, glows."""
    p.save()
    p.translate(x, y)
    p.scale(1, ry / rx)
    g = QRadialGradient(QPointF(0, 0), rx)
    g.setColorAt(0, col(rgb, a))
    g.setColorAt(1, col(rgb, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), rx, rx)
    p.restore()


def shape(p: QPainter, path: QPainterPath, base, hi=0.22, lo=0.28, vertical=False) -> None:
    """Fill a path with a light-to-dark linear gradient (left to right, or top to bottom)."""
    r = path.boundingRect()
    g = (QLinearGradient(r.center().x(), r.top(), r.center().x(), r.bottom()) if vertical
         else QLinearGradient(r.left(), r.top() + r.height() * 0.2, r.right(), r.bottom()))
    g.setColorAt(0, col(light(base, hi)))
    g.setColorAt(0.5, col(base))
    g.setColorAt(1, col(dark(base, lo)))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawPath(path)


def rrect(x, y, w, h, r) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(x, y, w, h, r, r)
    return path


def tube(p: QPainter, pts, width, base) -> None:
    """A rounded limb through the points, shaded so it looks round."""
    path = QPainterPath(QPointF(*pts[0]))
    for q in pts[1:]:
        path.lineTo(QPointF(*q))
    p.setBrush(Qt.NoBrush)
    for off, w, c in ((0.0, width, dark(base, 0.26)), (-0.07, width * 0.80, base),
                      (-0.2, width * 0.22, light(base, 0.30))):
        p.save()
        p.translate(off * width, off * width * 0.7)
        p.setPen(QPen(col(c), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.restore()


def stroke(p: QPainter, path: QPainterPath, rgb, w, a=255) -> None:
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(col(rgb, a), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)


def curve(p0, p1, p2, p3=None) -> QPainterPath:
    path = QPainterPath(QPointF(*p0))
    if p3 is None:
        path.quadTo(QPointF(*p1), QPointF(*p2))
    else:
        path.cubicTo(QPointF(*p1), QPointF(*p2), QPointF(*p3))
    return path


def eye(p: QPainter, x, y, rx, ry, iris, look=(0.0, 0.0), kind="open", lashes=False) -> None:
    """Big glossy cartoon eye (kind: open | wide | closed | happy)."""
    if kind in ("open", "wide"):
        k = 1.14 if kind == "wide" else 1.0
        gblob(p, x, y, rx * k, ry * k, (252, 252, 255), hi=0.0, lo=0.10)
        ix, iy = x + look[0], y + look[1]
        gblob(p, ix, iy, rx * 0.72 * k, ry * 0.76 * k, iris, hi=0.55, lo=0.45)
        flat(p, ix, iy + 0.5, rx * 0.36 * k, ry * 0.38 * k, (24, 18, 20))
        flat(p, ix - rx * 0.26, iy - ry * 0.30, rx * 0.2 * k, rx * 0.2 * k, (255, 255, 255))
        flat(p, ix + rx * 0.26, iy + ry * 0.26, rx * 0.1 * k, rx * 0.1 * k, (255, 255, 255), 190)
        lid = curve((x - rx * k, y + 1), (x, y - ry * 1.35 * k), (x + rx * k, y + 1))
        stroke(p, lid, (40, 28, 26), 2.6)
        if lashes:
            lash = curve((x + rx * 0.95 * k, y - 2), (x + rx * 1.2 * k, y - 3),
                         (x + rx * 1.32 * k, y - 6))
            stroke(p, lash, (40, 28, 26), 1.8)
            stroke(p, curve((x - rx * 0.95 * k, y - 2), (x - rx * 1.2 * k, y - 3),
                            (x - rx * 1.32 * k, y - 6)), (40, 28, 26), 1.8)
    elif kind == "happy":
        stroke(p, curve((x - rx, y + 3), (x, y - ry * 1.5), (x + rx, y + 3)), (40, 28, 26), 3)
    else:  # closed
        stroke(p, curve((x - rx, y - 1), (x, y + ry * 0.9), (x + rx, y - 1)), (40, 28, 26), 2.8)
        if lashes:
            stroke(p, curve((x + rx, y - 1), (x + rx * 1.3, y), (x + rx * 1.45, y - 3)),
                   (40, 28, 26), 2)


# --- flat sticker style: flat fills with one dark outline ------------------------------------

INK = (92, 52, 30)  # outline colour shared by the sticker-style characters
LW = 2.6  # outline width


def blob(p: QPainter, x, y, rx, ry, fill, w=LW) -> None:
    """Outlined ellipse (w=0 for no outline)."""
    p.setPen(QPen(col(INK), w) if w else Qt.NoPen)
    p.setBrush(col(fill))
    p.drawEllipse(QPointF(x, y), rx, ry)


def ink(p: QPainter, path: QPainterPath, fill, w=LW) -> None:
    """Outlined path."""
    p.setPen(QPen(col(INK), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(col(fill))
    p.drawPath(path)


def limb(p: QPainter, a, b, width, fill, end=None) -> None:
    """Outlined capsule from a to b; ``end`` = (fill, rx, ry) adds a round hand/paw at b."""
    path = curve(a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b)
    stroke(p, path, INK, width + 2 * LW)
    stroke(p, path, fill, width)
    if end:
        blob(p, b[0], b[1], end[1], end[2], end[0])


def union(p: QPainter, circles, fill) -> None:
    """Several ellipses (x, y, rx[, ry]) filled as one shape with a single outline around them."""
    for pen, brush in ((QPen(col(INK), 2 * LW), col(INK)), (Qt.NoPen, col(fill))):
        p.setPen(pen)
        p.setBrush(brush)
        for c in circles:
            p.drawEllipse(QPointF(c[0], c[1]), c[2], c[3] if len(c) > 3 else c[2])

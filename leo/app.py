"""The Leo desktop companion: a small always-on-top window that animates the avatar."""

from __future__ import annotations

import json
import math
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QImage, QPainter,
                           QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QWidget

from . import animate, autostart, avatar, characters, config, desktop, hydrate, packs
from .common import home, port_file, send
from .states import TEXT, Tracker

W, BUBBLE_H, QUIT_AFTER = 300, 40, 15 * 60

SOUNDS_MAC = {"hello": "Pop", "waiting": "Tink", "alert": "Sosumi", "done": "Hero"}
SOUNDS_LINUX = {"hello": "bell", "waiting": "message", "alert": "dialog-warning", "done": "complete"}


SOUNDS_WIN = {"hello": "chimes.wav", "waiting": "notify.wav", "alert": "Windows Exclamation.wav",
              "done": "tada.wav"}


def play(cue: str) -> None:
    """Fire-and-forget system sound (macOS, Linux, Windows)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["afplay", f"/System/Library/Sounds/{SOUNDS_MAC[cue]}.aiff"])
        elif sys.platform == "win32":
            import winsound

            media = Path(os.environ.get("WINDIR") or r"C:\Windows") / "Media" / SOUNDS_WIN[cue]
            if media.is_file():
                winsound.PlaySound(str(media), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.MessageBeep()
        elif shutil.which("canberra-gtk-play"):
            subprocess.Popen(["canberra-gtk-play", "-i", SOUNDS_LINUX[cue]])
    except (OSError, KeyError, ImportError, RuntimeError):
        pass


def pose(state: str, t: float) -> tuple[float, float, float, float]:
    """(dx, dy, rotation degrees, vertical scale) of the avatar at time t."""
    s = math.sin
    if state == "thinking":
        return 0, -2 * s(t * 4), 6 * s(t * 2.2), 1
    if state == "working":
        return 0, -5 * abs(s(t * 7)), 0, 1 - 0.04 * abs(s(t * 7))
    if state == "done":
        return 0, -22 * abs(s(t * 5)), 0, 1
    if state == "waiting":
        return 0, -3 * abs(s(t * 3)), 4 * s(t * 3), 1
    if state == "permission":
        return 6 * s(t * 30), 0, 0, 1
    if state == "greeting":
        return 0, 0, 14 * s(t * 8), 1
    if state == "sleeping":
        return 0, 2 * s(t), 0, 1 + 0.03 * s(t * 1.2)
    return 0, -2 * s(t * 2), 0, 1 + 0.02 * s(t * 2)  # idle: breathing


def soft_shadow(p: QPainter, fw: float) -> None:
    """A soft ground shadow under the feet (origin is at the feet)."""
    g = QRadialGradient(QPointF(0, 0), fw * 0.5)
    g.setColorAt(0, QColor(0, 0, 0, 80))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.save()
    p.scale(1, 0.12)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(0, 0), fw * 0.5, fw * 0.5)
    p.restore()


def star(cx: float, cy: float, r: float) -> QPolygonF:
    pts = []
    for i in range(8):
        a = i * math.pi / 4 - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.4
        pts.append(QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return QPolygonF(pts)


class Companion(QWidget):
    def __init__(self, stay: bool = False) -> None:
        super().__init__()
        self.cfg = config.load()
        self.tracker = Tracker()
        self.stay = stay
        self.override: tuple[str, float] | None = None  # (state, until) for `leo send`
        self.pix = QPixmap()
        self.builtin = True  # no uploaded avatar: use a built-in character or an image pack
        self.pack: Path | None = None  # folder of the active image pack, if any
        self.pixcache: dict[str, QPixmap] = {}
        self.animator: animate.Animator | None = None  # warps the pack's idle picture
        self.framecache: dict[tuple, QPixmap] = {}
        self.empty_since = time.time()
        self.water = hydrate.Reminder(self.cfg["hydrate"], self.cfg["hydrate_minutes"], time.time())
        self.toast: tuple[str, str, float] | None = None  # (state, text, until): a short reply
        # the desktop app's chat fires no hooks: watch its window instead (macOS)
        self.desktop = desktop.Watcher() if desktop.available() else None
        self.moved = False
        self.drag_from: QPointF | None = None
        self.t0 = time.time()
        self.setMouseTracking(True)  # pointing-hand cursor over the reminder's buttons

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # macOS hides Qt "tool" windows whenever the app isn't frontmost: keep Leo visible
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.reload_avatar()

        self.token = secrets.token_hex(8)
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self.on_connection)
        if self.server.listen(QHostAddress.LocalHost, 0):
            home().mkdir(parents=True, exist_ok=True)
            port_file().write_text(
                json.dumps({"port": self.server.serverPort(), "token": self.token})
            )
            try:
                os.chmod(port_file(), 0o600)
            except OSError:
                pass
            QApplication.instance().aboutToQuit.connect(lambda: port_file().unlink(missing_ok=True))
        else:
            print("leo: cannot open a local port", file=sys.stderr)

        for fn, ms in ((self.update, 40), (self.on_tick, 500)):
            tm = QTimer(self)
            tm.timeout.connect(fn)
            tm.start(ms)

    # --- avatar & layout ---------------------------------------------------------------
    def figure_size(self) -> tuple[float, float]:
        """On-screen (width, height) of the avatar: full-body characters are bigger."""
        size = int(self.cfg["size"])
        if self.pack:
            pm = self.pack_pixmap("idle", None)
            ar = pm.width() / max(1, pm.height())
            return size * 1.75 * ar, size * 1.75
        if self.builtin:
            return characters.screen_size(characters.get(self.cfg["character"]), size)
        ar = self.pix.width() / max(1, self.pix.height())
        h = size * 1.75 if ar < 0.9 else size
        return h * ar, h

    def make_animator(self) -> None:
        """Animated warps are used for states that have no picture of their own."""
        self.animator = None
        self.framecache.clear()
        idle = packs.picture(self.pack, "idle") if self.pack else None
        if idle is None or animate.cv2 is None:
            return
        try:
            import numpy as np

            img = QImage(str(idle)).convertToFormat(QImage.Format_RGBA8888)
            if img.height() > 480:
                img = img.scaledToHeight(480, Qt.SmoothTransformation)
            buf = img.constBits()
            arr = np.frombuffer(buf, np.uint8, img.height() * img.bytesPerLine())
            arr = arr.reshape(img.height(), img.bytesPerLine())[:, : img.width() * 4]
            self.animator = animate.Animator(arr.reshape(img.height(), img.width(), 4).copy())
        except Exception as exc:  # never let animation break the companion
            print(f"leo: animation off ({exc})", file=sys.stderr)

    def animated_pixmap(self, state: str, detail: str | None, t: float) -> QPixmap | None:
        """The warped frame for this moment, or None when the pack has its own picture."""
        if self.animator is None or self.pack is None:
            return None
        if packs.picture(self.pack, state, detail) != packs.picture(self.pack, "idle"):
            return None  # a dedicated picture exists for this state
        key = self.animator._key(state, detail)
        cps = 0.25 if key == "sleeping" else animate.CYCLES.get(key, animate.DEFAULT_CYCLES)
        k = int(t * cps * animate.N) % animate.N
        if (key, k) not in self.framecache:
            fr = self.animator.frames(state, detail)[k]
            img = QImage(fr.data, fr.shape[1], fr.shape[0], fr.shape[1] * 4,
                         QImage.Format_RGBA8888_Premultiplied).copy()
            self.framecache[(key, k)] = QPixmap.fromImage(img)
        return self.framecache[(key, k)]

    def pack_pixmap(self, state: str, detail: str | None) -> QPixmap:
        f = packs.picture(self.pack, state, detail) if self.pack else None
        if f is None:
            return QPixmap()
        key = str(f)
        if key not in self.pixcache:
            self.pixcache[key] = QPixmap(key)
        return self.pixcache[key]

    def reload_avatar(self) -> None:
        old_bottom = self.y() + self.height() if self.isVisible() else None
        self.cfg = config.load()
        custom = avatar.custom_avatar()
        self.builtin = custom is None
        found = packs.find()
        key = self.cfg["character"]
        self.pack = found.get(key) if self.builtin else None
        if self.builtin and self.pack is None and key not in characters.CHARACTERS:
            self.cfg["character"] = "leo"  # unknown or removed pack (or an old setting)
        self.pixcache.clear()
        self.make_animator()
        self.water.configure(self.cfg["hydrate"], self.cfg["hydrate_minutes"], time.time())
        self.pix = QPixmap(str(custom)) if custom else QPixmap()
        self.setFixedSize(W, BUBBLE_H + 14 + int(self.figure_size()[1]) + 16)
        if self.cfg["x"] is None:
            geo = QApplication.primaryScreen().availableGeometry()
            self.move(geo.right() - W - 30, geo.bottom() - self.height() - 30)
        elif old_bottom is not None:  # keep the feet where they were when the size changes
            self.move(self.x(), old_bottom - self.height())
        else:
            self.move(int(self.cfg["x"]), int(self.cfg["y"]))
        self.update()

    # --- events from the hook / CLI -----------------------------------------------------
    def on_connection(self) -> None:
        while (sock := self.server.nextPendingConnection()) is not None:
            sock.readyRead.connect(lambda s=sock: self.on_data(s))
            sock.disconnected.connect(sock.deleteLater)

    def on_data(self, sock: QTcpSocket) -> None:
        for line in bytes(sock.readAll()).splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and secrets.compare_digest(
                str(msg.pop("token", "")), self.token
            ):
                self.handle(msg)

    def handle(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "reload":
            self.reload_avatar()
        elif cmd == "quit":
            QApplication.quit()
        elif cmd == "stay":  # opened as an app while Claude Code's hook had started it
            self.stay = True
        elif cmd == "show" and msg.get("state") == "hydrate":
            self.start_water()
        elif cmd == "show":  # demo a state for 5 seconds
            self.override = (msg.get("state", "idle"), time.time() + 5)
        elif msg.get("event"):
            cue = self.tracker.apply(msg)
            if cue and not self.cfg["muted"]:
                play(cue)
        self.update()

    def start_water(self) -> None:
        self.water.start(time.time())
        if not self.cfg["muted"]:
            play("hello")

    def on_tick(self) -> None:
        for msg in self.desktop.poll() if self.desktop else []:
            cue = self.tracker.apply(msg)
            if cue and cue != "hello" and not self.cfg["muted"]:
                play(cue)
            self.update()
        self.tracker.tick()
        busy = self.tracker.display().state == "permission"
        if self.water.tick(time.time(), can_show=not busy) and not self.cfg["muted"]:
            play("hello")
        if self.tracker.sessions:
            self.empty_since = time.time()
        elif not self.stay and time.time() - self.empty_since > QUIT_AFTER:
            QApplication.quit()

    # --- painting ----------------------------------------------------------------------
    def current(self) -> tuple[str, str, str | None]:
        if self.water.active:
            return "hydrate", TEXT["hydrate"], None
        if self.toast and time.time() < self.toast[2]:
            return self.toast[0], self.toast[1], None
        if self.override and time.time() < self.override[1]:
            return self.override[0], TEXT.get(self.override[0], ""), None
        d = self.tracker.display()
        return d.state, d.text, d.detail

    def paintEvent(self, _) -> None:
        state, text, detail = self.current()
        t = time.time() - self.t0
        if state == "hydrate":  # the drinking routine starts from its first frame
            t = time.time() - self.water.since
        size = int(self.cfg["size"])
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                         | QPainter.TextAntialiasing)

        font = QFont()
        font.setPointSize(12)
        p.setFont(font)
        text = p.fontMetrics().elidedText(text, Qt.ElideRight, W - 40)
        bw = p.fontMetrics().horizontalAdvance(text) + 28
        bubble = QRectF((W - bw) / 2, 4, bw, BUBBLE_H - 12)
        p.setPen(QColor(0, 0, 0, 40))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(bubble, 12, 12)
        p.setPen(QColor(40, 40, 50))
        p.drawText(bubble, Qt.AlignCenter, text)

        fw, fh = self.figure_size()
        dx, dy, rot, sy = pose(state, t)
        cx, top = W / 2, BUBBLE_H + 14
        p.save()
        p.translate(cx + dx, top + fh + dy)  # animate around the feet
        if self.pack:  # picture pack: animate the image around the feet
            warped = self.animated_pixmap(state, detail, t)
            pm = warped or self.pack_pixmap(state, detail)
            soft_shadow(p, fw)
            if warped:  # the picture itself moves; only keep the happy hop
                if state == "done":
                    p.translate(0, dy)
            else:  # own picture for this state: animate it as a whole
                p.translate(dx, 0)
                p.rotate(rot)
                p.scale(1.0 + (1 - sy) * 0.6, sy)
            p.setOpacity(0.75 if state == "sleeping" else 1.0)
            p.drawPixmap(QRectF(-fw / 2, -fh, fw, fh), pm, QRectF(pm.rect()))
            bx, by = cx + fw * 0.52, top + fh * 0.02
        elif self.builtin:  # built-in characters animate their own limbs, head and tail
            ch = characters.get(self.cfg["character"])
            k = fw / ch.w
            p.scale(k, k)
            ch.draw(p, state, detail, t)
            bx, by = cx - fw / 2 + fw * ch.badge[0], top + fh * ch.badge[1]
        else:
            p.rotate(rot)
            p.scale(1, sy)
            p.setOpacity(0.65 if state == "sleeping" else 1.0)
            p.drawPixmap(QRectF(-fw / 2, -fh, fw, fh), self.pix, QRectF(self.pix.rect()))
            tall = fh > fw * 1.1
            bx = cx + (fw * 0.36 if tall else fw / 2 - 6)  # next to the head
            by = top + (fh * 0.10 if tall else 6)
        p.restore()
        self.draw_badge(p, state, t, cx, top, fw, bx, by)
        if state == "hydrate":  # buttons last, so the water drops never cover them
            self.draw_water_buttons(p)

    def water_buttons(self) -> dict[str, QRectF]:
        """The reminder's two buttons, just under the bubble."""
        y, h = BUBBLE_H - 4, 24
        return {"drank": QRectF(W / 2 - 106, y, 112, h), "later": QRectF(W / 2 + 12, y, 94, h)}

    def draw_water_buttons(self, p: QPainter) -> None:
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        looks = {"drank": ("\u2713 I drank", QColor(56, 150, 230), QColor("white")),
                 "later": (f"In {hydrate.SNOOZE_MINUTES} min", QColor(255, 255, 255, 240),
                           QColor(60, 70, 90))}
        for key, r in self.water_buttons().items():
            label, bg, fg = looks[key]
            p.setPen(QColor(0, 0, 0, 50))
            p.setBrush(bg)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            p.setPen(fg)
            p.drawText(r, Qt.AlignCenter, label)

    def drank_water(self) -> None:
        now = time.time()
        self.water.dismiss(now)
        self.toast = ("done", f"Nice! Next reminder in {self.water.minutes} min", now + 3)
        self.update()

    def snooze_water(self) -> None:
        now = time.time()
        self.water.snooze(now)
        self.toast = ("idle", f"OK, I'll remind you in {hydrate.SNOOZE_MINUTES} min", now + 2.5)
        self.update()

    def draw_badge(self, p: QPainter, state: str, t: float, cx: float, top: float,
                   fw: float, bx: float, by: float) -> None:
        p.setPen(Qt.NoPen)
        if state == "thinking":
            for i in range(3):
                p.setBrush(QColor(90, 90, 110, 255 if int(t * 3) % 3 >= i else 90))
                p.drawEllipse(QPointF(bx - 20 + i * 14, by - 4), 5, 5)
        elif state == "working":
            p.setPen(QColor(70, 130, 230))
            p.drawArc(QRectF(bx - 8, by - 8, 20, 20), int(-t * 360 * 16 * 1.5), 270 * 16)
        elif state == "permission":
            r = 15 + 2 * math.sin(t * 10)
            p.setBrush(QColor(230, 60, 60))
            p.drawEllipse(QPointF(bx, by), r, r)
            p.setPen(QColor("white"))
            p.setFont(QFont("Helvetica", 18, QFont.Bold))
            p.drawText(QRectF(bx - r, by - r, 2 * r, 2 * r), Qt.AlignCenter, "!")
        elif state == "hydrate":
            for i in range(4):  # water drops float up past the head
                ph = (t * 0.7 + i / 4) % 1
                x, y, r = bx - 10 + (i % 2) * 16 + 4 * math.sin(t * 3 + i), by + 22 - ph * 52, 5 + (i % 3)
                p.setOpacity(min(1, 2 * (1 - ph)))
                p.setBrush(QColor(80, 165, 240))
                p.drawEllipse(QPointF(x, y), r, r)
                p.drawPolygon(QPolygonF([QPointF(x - r * 0.85, y - r * 0.5), QPointF(x, y - r * 2.2),
                                         QPointF(x + r * 0.85, y - r * 0.5)]))
            p.setOpacity(1)
        elif state == "waiting":
            p.setBrush(QColor(60, 190, 120, int(130 + 100 * math.sin(t * 4))))
            p.drawEllipse(QPointF(bx, by), 9, 9)
        elif state == "done":
            p.setBrush(QColor(255, 200, 40))
            for i in range(3):
                ph = (t * 1.5 + i / 3) % 1
                p.setOpacity(1 - ph)
                p.drawPolygon(star(cx - fw / 2 + i * fw / 2.2 + 10, top + 8 - ph * 24, 9))
            p.setOpacity(1)
        elif state == "sleeping":
            p.setPen(QColor(90, 90, 120))
            for i in range(3):
                ph = (t * 0.5 + i / 3) % 1
                p.setOpacity(1 - ph)
                p.setFont(QFont("Helvetica", 12 + i * 3, QFont.Bold))
                p.drawText(QPointF(bx - 4 + ph * 12, by + 6 - ph * 30), "z")
            p.setOpacity(1)

    # --- mouse & menu -------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.drag_from = e.globalPosition() - QPointF(self.pos())
            self.moved = False

    def mouseMoveEvent(self, e) -> None:
        if self.drag_from is not None:
            self.moved = True
            self.move((e.globalPosition() - self.drag_from).toPoint())
        else:
            over = self.water.active and any(r.contains(e.position())
                                             for r in self.water_buttons().values())
            self.setCursor(Qt.PointingHandCursor if over else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e) -> None:
        if self.drag_from is not None:
            self.drag_from = None
            if not self.moved and self.water.active:  # "In 10 min", else a click means "I drank it"
                later = self.water_buttons()["later"].contains(e.position())
                self.snooze_water() if later else self.drank_water()
                return
            self.cfg.update(x=self.x(), y=self.y())
            config.save(self.cfg)

    def contextMenuEvent(self, e) -> None:
        m = QMenu(self)
        char_menu = m.addMenu("Character")
        cgroup = QActionGroup(char_menu)
        options = {n: n.replace("_", " ").title() for n in packs.find()}
        options.update({k: c.label for k, c in characters.CHARACTERS.items()})
        for key, label in options.items():
            a = QAction(label, char_menu, checkable=True)
            a.setChecked(self.builtin and self.cfg["character"] == key)
            a.triggered.connect(lambda _=False, key=key: self.pick_character(key))
            cgroup.addAction(a)
            char_menu.addAction(a)
        m.addAction("Upload avatar…", self.pick_image)
        have_src = avatar.source_path().exists()
        style_menu = m.addMenu("Avatar style")
        group = QActionGroup(style_menu)
        for st in avatar.STYLES:
            a = QAction(st.capitalize(), style_menu, checkable=True)
            a.setChecked(self.cfg["style"] == st)
            a.setEnabled(have_src)
            a.triggered.connect(lambda _=False, st=st: self.restyle(style=st))
            group.addAction(a)
            style_menu.addAction(a)
        body_menu = m.addMenu("Body (Toon style)")
        bgroup = QActionGroup(body_menu)
        for bd in avatar.BODIES:
            a = QAction(bd.capitalize(), body_menu, checkable=True)
            a.setChecked(self.cfg["body"] == bd)
            a.setEnabled(have_src)
            a.triggered.connect(lambda _=False, bd=bd: self.restyle(style="toon", body=bd))
            bgroup.addAction(a)
            body_menu.addAction(a)
        bg = QAction("Remove plain background", m, checkable=True)
        bg.setChecked(self.cfg["remove_bg"])
        bg.setEnabled(have_src)
        bg.triggered.connect(lambda on: self.restyle(remove_bg=on))
        m.addAction(bg)
        m.addAction("Remove uploaded avatar", self.reset_avatar).setEnabled(not self.builtin)
        m.addSeparator()

        water_menu = m.addMenu("Hydration reminder")
        on = QAction("Remind me to drink water", water_menu, checkable=True)
        on.setChecked(self.cfg["hydrate"])
        on.triggered.connect(lambda v: self.set_water(enabled=v))
        water_menu.addAction(on)
        water_menu.addSeparator()
        every = QActionGroup(water_menu)
        mins = int(self.cfg["hydrate_minutes"])
        for n in hydrate.CHOICES:
            a = QAction(f"Every {n} minutes" if n < 60 or n % 60 else f"Every {n // 60} hour" + ("s" if n > 60 else ""),
                        water_menu, checkable=True)
            a.setChecked(mins == n)
            a.triggered.connect(lambda _=False, n=n: self.set_water(enabled=True, minutes=n))
            every.addAction(a)
            water_menu.addAction(a)
        water_menu.addAction("Custom interval…", self.ask_water_interval)
        water_menu.addSeparator()
        if self.cfg["hydrate"]:
            water_menu.addAction(f"Next reminder in {self.water.minutes_left(time.time())} min").setEnabled(False)
        water_menu.addAction("Remind me now (preview)", self.start_water)
        water_menu.addAction("I just drank, restart timer", self.drank_water)
        if self.water.active:
            water_menu.addAction(f"Remind me in {hydrate.SNOOZE_MINUTES} min", self.snooze_water)

        size_menu = m.addMenu("Size")
        for name, px in (("Small", 96), ("Medium", 128), ("Large", 180)):
            size_menu.addAction(name, lambda px=px: self.set_cfg(size=px))
        login = QAction("Start at login", m, checkable=True)
        login.setChecked(autostart.enabled())
        login.triggered.connect(self.set_login)
        m.addAction(login)
        mute = QAction("Mute sounds", m, checkable=True)
        mute.setChecked(self.cfg["muted"])
        mute.triggered.connect(lambda on: self.set_cfg(muted=on))
        m.addAction(mute)
        m.addSeparator()
        m.addAction("Quit Leo", QApplication.quit)
        m.exec(e.globalPos())

    def set_login(self, on: bool) -> None:
        try:
            autostart.set_login(on)
            self.stay = self.stay or on  # started at login: don't wander off when idle
        except Exception as exc:  # never let a menu click crash the companion
            print(f"leo: could not change start at login: {exc}", file=sys.stderr)

    def set_water(self, enabled: bool | None = None, minutes: int | None = None) -> None:
        cfg = config.load()
        if enabled is not None:
            cfg["hydrate"] = bool(enabled)
        if minutes is not None:
            cfg["hydrate_minutes"] = hydrate.clamp(minutes)
        config.save(cfg)
        self.reload_avatar()

    def ask_water_interval(self) -> None:
        n, ok = QInputDialog.getInt(self, "Hydration reminder", "Remind me every (minutes):",
                                    int(self.cfg["hydrate_minutes"]), hydrate.MIN_MINUTES, hydrate.MAX_MINUTES)
        if ok:
            self.set_water(enabled=True, minutes=n)

    def set_cfg(self, **kw) -> None:
        cfg = config.load()
        cfg.update(kw)
        config.save(cfg)
        self.reload_avatar()

    def pick_character(self, key: str) -> None:
        avatar.use_character(key)
        self.reload_avatar()

    def reset_avatar(self) -> None:
        avatar.save_avatar(None)
        self.reload_avatar()

    def pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a picture for Leo", "", "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
        )
        if path:
            try:
                avatar.save_avatar(path, self.cfg["style"], self.cfg["remove_bg"], self.cfg["body"])
            except Exception as exc:  # unreadable image
                print(f"leo: {exc}", file=sys.stderr)
            self.reload_avatar()

    def restyle(self, **kw) -> None:
        cfg = {**config.load(), **kw}
        try:
            avatar.restyle(cfg["style"], cfg["remove_bg"], cfg["body"])
        except ValueError as exc:
            print(f"leo: {exc}", file=sys.stderr)
        self.reload_avatar()


def run(first_event: dict | None = None, stay: bool = False) -> int:
    try:  # already running? hand over the event and leave
        send({"cmd": "ping"}, timeout=0.3)
        if first_event:
            send(first_event)
        if stay:
            send({"cmd": "stay"})
        return 0
    except OSError:
        pass
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "darwin":
        try:  # no Dock icon (optional dependency)
            import AppKit

            AppKit.NSApplication.sharedApplication().setActivationPolicy_(1)
        except Exception:
            pass
    companion = Companion(stay=stay)
    if first_event:
        companion.handle(first_event)
    companion.show()
    companion.raise_()
    return app.exec()

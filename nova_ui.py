"""
nova_ui.py – Nova AI Assistant Visual HUD
==========================================
Reference-matched redesign.

Window layout (top → bottom):
  ┌─────────────────────────────────────────────────────┐
  │  [TOP BAR] Logo | Waveform+State | Clock+Controls   │  ~90px
  ├─────────────────────────────────────────────────────┤
  │  [CONTENT FRAME]  dark glass, blue border           │
  │    ┌ [CHAT PANEL]  compact, top of content ┐        │  ~72px
  │    └──────────────────────────────────────┘        │
  │                                                     │
  │         ★  LARGE ORANGE/GOLD HOLOGRAM  ★           │
  │              (fills remaining height)               │
  │                                                     │
  ├─────────────────────────────────────────────────────┤
  │  [BOTTOM HUD]  6 stat cards + center Nova logo      │  ~105px
  └─────────────────────────────────────────────────────┘

Only nova_ui.py is modified. No backend changes.
"""

import sys
import math
import random
import time
from datetime import datetime
import numpy as np

try:
    from PyQt6.QtCore import (
        Qt, QTimer, QPoint, QPointF, QRectF, QSize,
        pyqtSignal, QObject
    )
    from PyQt6.QtGui import (
        QBrush, QColor, QFont, QFontMetrics,
        QLinearGradient, QRadialGradient, QConicalGradient,
        QPainter, QPen, QPainterPath,
        QMouseEvent, QPolygonF, QPixmap, QCursor
    )
    from PyQt6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel,
        QMainWindow, QSizePolicy, QVBoxLayout,
        QWidget, QPushButton, QSlider, QScrollArea
    )
    _PYQT6 = True
except ImportError as _e:
    print(f"[ERROR] PyQt6 not found: {_e}")
    _PYQT6 = False

import os
from pathlib import Path
_NOVA_DIR = Path(__file__).resolve().parent
EXTRACTED_CORE_PATH = str(_NOVA_DIR / "resources" / "extracted_core.png")
BG_PATH = str(_NOVA_DIR / "resources" / "sci_fi_background.jpg")


# ═══════════════════════════════════════════════════════════════════════════
# State colour / speed tables
# ═══════════════════════════════════════════════════════════════════════════
_STATE_COLOR = {
    "READY":           "#00FF88",
    "LISTENING...":    "#00FFFF",
    "WAKE DETECTED":   "#00FFFF",
    "THINKING...":     "#FFAA00",
    "EXECUTING...":    "#FFD700",
    "SPEAKING...":     "#3399FF",
    "ERROR":           "#FF3333",
    "OFFLINE":         "#FF3333",
    "INITIALIZING...": "#666688",
}
_STATE_SPEED = {
    "READY":           0.8,
    "LISTENING...":    2.0,
    "WAKE DETECTED":   2.5,
    "THINKING...":     3.8,
    "EXECUTING...":    4.5,
    "SPEAKING...":     2.2,
    "ERROR":           0.6,
    "OFFLINE":         0.3,
    "INITIALIZING...": 0.5,
}

# ═══════════════════════════════════════════════════════════════════════════
# Thread-safe Qt signals
# ═══════════════════════════════════════════════════════════════════════════
class _Signaler(QObject):
    state = pyqtSignal(str, object, object)   # status, user_text, nova_text
    mic   = pyqtSignal(float, object)         # rms, indata


# ═══════════════════════════════════════════════════════════════════════════
# Circular Nova Reactor Logo  (painter-based, reusable)
# ═══════════════════════════════════════════════════════════════════════════
def draw_nova_reactor(painter: QPainter, cx: float, cy: float,
                      R: float, color: QColor = None, glow: bool = True):
    """
    Draw a glowing circular Nova reactor emblem centred at (cx,cy) with radius R.
    Blue concentric rings + radial spokes + inner white core.
    """
    if color is None:
        color = QColor(0, 200, 255)

    if glow:
        g = QRadialGradient(cx, cy, R * 1.6)
        g.setColorAt(0.0, QColor(0, 200, 255, 55))
        g.setColorAt(0.6, QColor(0, 150, 255, 20))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(g))
        painter.drawEllipse(QRectF(cx - R*1.6, cy - R*1.6, R*3.2, R*3.2))

    # Outer ring
    pen = QPen(QColor(0, 200, 255, 180), R * 0.07)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(cx - R, cy - R, R*2, R*2))

    # Middle ring
    pen2 = QPen(QColor(0, 160, 255, 130), R * 0.04)
    painter.setPen(pen2)
    painter.drawEllipse(QRectF(cx - R*0.68, cy - R*0.68, R*1.36, R*1.36))

    # Radial spokes (6)
    spoke_pen = QPen(QColor(0, 220, 255, 100), R * 0.03)
    painter.setPen(spoke_pen)
    for k in range(6):
        ang = k * math.pi / 3
        x1 = cx + math.cos(ang) * R * 0.28
        y1 = cy + math.sin(ang) * R * 0.28
        x2 = cx + math.cos(ang) * R * 0.92
        y2 = cy + math.sin(ang) * R * 0.92
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # Inner glow core
    ig = QRadialGradient(cx, cy, R * 0.30)
    ig.setColorAt(0.0, QColor(255, 255, 255, 240))
    ig.setColorAt(0.4, QColor(80, 200, 255, 200))
    ig.setColorAt(1.0, QColor(0, 100, 200, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(ig))
    painter.drawEllipse(QRectF(cx - R*0.30, cy - R*0.30, R*0.60, R*0.60))


# ═══════════════════════════════════════════════════════════════════════════
# Live Waveform Widget
# ═══════════════════════════════════════════════════════════════════════════
class WaveformWidget(QWidget):
    def __init__(self, status_fn, parent=None):
        super().__init__(parent)
        self._status = status_fn
        self._buf    = [0.0] * 120
        self._phase  = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30)

    def feed(self, indata):
        if indata is not None and len(indata) > 0:
            step = max(1, len(indata) // 120)
            s = [float(indata[i][0]) for i in range(0, len(indata), step)][:120]
            s += [0.0] * (120 - len(s))
            self._buf = s

    def _tick(self):
        st = self._status()
        if st not in ("LISTENING...", "WAKE DETECTED"):
            self._phase += 0.32
            for i in range(120):
                if st == "SPEAKING...":
                    e = 0.38 + 0.28 * math.sin(self._phase * 0.09)
                    self._buf[i] = 0.52 * math.sin(i * 0.23 + self._phase) * e
                elif st == "THINKING...":
                    self._buf[i] = 0.19 * math.cos(i * 0.41 + self._phase * 1.7)
                elif st == "EXECUTING...":
                    self._buf[i] = (0.28 * math.sin(i * 0.5 + self._phase * 2.2)
                                    if i % 5 == 0 else 0.0)
                else:
                    self._buf[i] = 0.06 * math.sin(i * 0.14 + self._phase * 0.4)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h * 0.5
        mid_x = w * 0.5
        st   = self._status()
        col  = QColor(_STATE_COLOR.get(st, "#00FFFF"))

        # Camera distance and Y-axis rotation tilt angle in radians
        d = 160.0
        tilt = 0.28
        
        # Render a 3D double helix perspective waveform
        strands = 2
        n = len(self._buf)
        
        for s in range(strands):
            path = QPainterPath()
            started = False
            strand_phase = s * math.pi
            
            for i, val in enumerate(self._buf):
                # 3D Coordinates: align along horizontal X axis
                # map i from 0..n to x in -w/2..w/2
                x3d = (i - n/2) * (w / max(1, n)) * 0.96
                
                # Dynamic radius of helix based on wave buffer value
                r = max(4.0, abs(val) * h * 0.52)
                
                # Calculate helical angle
                theta = i * 0.20 + self._phase * 1.6 + strand_phase
                
                # Helical cross section in Y and Z dimensions
                y3d = r * math.sin(theta)
                z3d = r * math.cos(theta)
                
                # Rotate coordinates around Y axis to give dynamic 3D perspective angle
                rot_x = x3d * math.cos(tilt) - z3d * math.sin(tilt)
                rot_z = x3d * math.sin(tilt) + z3d * math.cos(tilt)
                
                # Apply 3D perspective math (scale factor = d / (d + z))
                # offset Z so the helix stays centered and visible
                proj_scale = d / (d + rot_z + 60.0)
                px = mid_x + rot_x * proj_scale
                py = mid_y + y3d * proj_scale
                
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
                    
            # Draw gradient line
            g = QLinearGradient(0, 0, w, 0)
            g.setColorAt(0.00, QColor(col.red(), col.green(), col.blue(), 0))
            g.setColorAt(0.12, QColor(col.red(), col.green(), col.blue(), 180 if s == 0 else 100))
            g.setColorAt(0.88, QColor(col.red(), col.green(), col.blue(), 180 if s == 0 else 100))
            g.setColorAt(1.00, QColor(col.red(), col.green(), col.blue(), 0))
            
            p.setPen(QPen(QBrush(g), 1.8 if s == 0 else 1.0))
            p.drawPath(path)


# ═══════════════════════════════════════════════════════════════════════════
# Premium large cyan/blue holographic AI core  (NOVA branding, fully programmatic)
# ═══════════════════════════════════════════════════════════════════════════
class HoloCoreWidget(QWidget):
    """
    Large premium circular cyan holographic AI core.
    Programmatically renders all layers via QPainter - no images used.
    Fully voice-reactive.  ~60 FPS via a 16 ms QTimer.
    """

    # ring definition table:
    # (radius_frac, pen_width, base_alpha, rot_speed_multiplier, dash_pattern_or_None)
    _RING_DEFS = [
        (1.00, 2.5, 220, +6.0,  None),
        (1.00, 1.0, 100, +6.0,  None),
        (0.97, 4.5, 180, -4.0,  [18, 8, 4, 8]),
        (0.92, 1.2, 130, +9.0,  [6, 18]),
        (0.85, 3.0, 200, -5.0,  [28, 10, 6, 10]),
        (0.80, 0.8, 100, +12.0, None),
        (0.72, 2.0, 170, -7.0,  [12, 8]),
        (0.65, 1.0, 130, +15.0, [4, 12]),
        (0.58, 2.5, 190, -3.5,  [20, 12, 5, 12]),
        (0.50, 0.8, 110, +18.0, None),
        (0.42, 1.5, 150, -8.0,  [8, 6]),
    ]

    def __init__(self, status_fn, parent=None):
        super().__init__(parent)
        self._status   = status_fn
        self.mic_level = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._t0          = time.perf_counter()
        self._angle       = 0.0
        self._pulse_phase = 0.0
        self._scan_angle  = 0.0
        self._speech_amp  = 0.0

        # Pre-generate 24 orbiting tick-nodes
        rng = random.Random(42)
        self._nodes = []
        for i in range(24):
            self._nodes.append({
                'angle_off': rng.uniform(0, 360),
                'r_frac':    rng.uniform(0.94, 1.06),
                'size':      rng.uniform(2.5, 5.5),
                'speed':     rng.uniform(4.0, 14.0) * (1 if rng.random() > .5 else -1),
            })

        # Pre-generate 32 floating cyan data particles
        rng2 = random.Random(77)
        self._pts = []
        for i in range(32):
            self._pts.append({
                'angle':  rng2.uniform(0, 360),
                'r_frac': rng2.uniform(0.60, 1.12),
                'speed':  rng2.uniform(3.0, 10.0) * (1 if rng2.random() > .5 else -1),
                'size':   rng2.uniform(2.0, 4.0),
                'alpha':  rng2.randint(80, 200),
            })

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        now = time.perf_counter()
        dt  = min(now - self._t0, 0.05)
        self._t0 = now

        st    = self._status()
        speed = _STATE_SPEED.get(st, 1.0)

        self._angle       = (self._angle + 18.0 * speed * dt) % 360.0
        self._pulse_phase = (self._pulse_phase + 2.8 * speed * dt) % (2 * math.pi)
        self._scan_angle  = (self._scan_angle + 95.0 * speed * dt) % 360.0

        if st == "SPEAKING...":
            t   = time.perf_counter()
            raw = max(0.0, (0.55 * math.sin(t * 19.0) * math.cos(t * 7.3)
                          + 0.30 * math.sin(t * 34.0)
                          + 0.15 * math.cos(t * 9.7)))
            self._speech_amp = self._speech_amp * 0.68 + raw * 0.32
        else:
            self._speech_amp = max(0.0, self._speech_amp - 6.0 * dt)

        self.update()

    @staticmethod
    def _c(r, g, b, a=255):
        return QColor(max(0,min(255,int(r))), max(0,min(255,int(g))),
                      max(0,min(255,int(b))), max(0,min(255,int(a))))

    def _ring_pen(self, r, g, b, width, alpha, dash=None):
        pen = QPen(self._c(r, g, b, alpha), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if dash:
            pen.setDashPattern(dash)
        return pen

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H   = self.width(), self.height()
        cx, cy = W * 0.5, H * 0.5

        # Core radius = 30% of shortest dimension (diameter = 60%)
        R = min(W, H) * 0.30
        if R < 20:
            return

        st          = self._status()
        mic_v       = self.mic_level
        spk_v       = self._speech_amp
        is_speaking = (st == "SPEAKING...")
        is_listen   = (st in ("LISTENING...", "WAKE DETECTED"))
        is_think    = (st == "THINKING...")

        # Breathing scale
        breath = 1.0 + 0.018 * math.sin(self._pulse_phase)
        if is_speaking: breath += spk_v * 0.09
        if is_listen:   breath += mic_v * 0.05
        if is_think:    breath += 0.025 * math.sin(time.perf_counter() * 12.0)

        # Speaking vibration offsets (hologram only)
        rng = random.Random(int(time.perf_counter() * 120))
        vx = rng.uniform(-1, 1) * spk_v * 9.0 if is_speaking else \
             rng.uniform(-1, 1) * mic_v * 4.0 if is_listen else 0.0
        vy = rng.uniform(-1, 1) * spk_v * 9.0 if is_speaking else \
             rng.uniform(-1, 1) * mic_v * 4.0 if is_listen else 0.0
        hx, hy = cx + vx, cy + vy

        # No tilt – face-on circular hologram
        TILT = 1.0

        # ── 1. SOFT OUTER GLOW ────────────────────────────────────────────
        glow_r = R * 1.55 * breath
        glow_peak = 80 + int(spk_v * 60) if is_speaking else \
                    60 + int(mic_v * 40) if is_listen else 50
        g = QRadialGradient(hx, hy, glow_r)
        g.setColorAt(0.0,  self._c(0, 200, 255, min(255, glow_peak)))
        g.setColorAt(0.45, self._c(0, 100, 255, min(255, glow_peak // 2)))
        g.setColorAt(1.0,  self._c(0,  30, 100, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(hx - glow_r, hy - glow_r * TILT,
                             glow_r * 2,   glow_r * 2 * TILT))

        # ── 2. HUD RINGS ──────────────────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)

        for idx, (rfrac, pw, base_a, rot_spd, dash) in enumerate(self._RING_DEFS):
            ring_r = R * rfrac * breath
            a_boost = int(spk_v * 80) if is_speaking else \
                      int(mic_v * 50) if is_listen else \
                      30 if is_think else 0
            alpha = min(255, base_a + a_boost)

            ring_angle = self._angle * rot_spd / 18.0

            p.save()
            p.translate(hx, hy)
            p.rotate(ring_angle)
            p.scale(1.0, TILT)

            t_inner = idx / len(self._RING_DEFS)
            gc = int(200 - 80 * t_inner)
            bc = int(255 - 50 * t_inner)

            pen = self._ring_pen(0, gc, bc, pw, alpha, dash)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(-ring_r, -ring_r, ring_r * 2, ring_r * 2))
            p.restore()

        # ── 3. TICK MARKS ────────────────────────────────────────────────
        p.save()
        p.translate(hx, hy)
        p.scale(1.0, TILT)
        tick_r = R * 1.01 * breath
        for k in range(72):
            ang_rad = math.radians(k * 5.0 + self._angle * 0.25)
            major   = (k % 12 == 0)
            minor   = (k % 6  == 0)
            t_len   = 10 if major else (6 if minor else 3)
            t_alpha = 230 if major else (160 if minor else 100)
            t_width = 2.0 if major else (1.4 if minor else 0.8)
            x1 = math.cos(ang_rad) * tick_r
            y1 = math.sin(ang_rad) * tick_r
            x2 = math.cos(ang_rad) * (tick_r + t_len)
            y2 = math.sin(ang_rad) * (tick_r + t_len)
            p.setPen(QPen(self._c(0, 220, 255, t_alpha), t_width,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.restore()

        # ── 4. SEGMENTED ARC HIGHLIGHTS ──────────────────────────────────
        p.save()
        p.translate(hx, hy)
        p.scale(1.0, TILT)
        arc_r = R * 1.00 * breath
        p.setPen(QPen(self._c(0, 240, 255, 220), 4.5,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for seg in range(4):
            base_deg = seg * 90.0 + self._angle * -0.8
            p.drawArc(QRectF(-arc_r, -arc_r, arc_r*2, arc_r*2),
                      int(base_deg * 16), int(35 * 16))
        p.restore()

        # ── 5. RADAR SWEEP ───────────────────────────────────────────────
        p.save()
        p.translate(hx, hy)
        p.scale(1.0, TILT)
        sweep_r   = R * 0.92 * breath
        sweep_a   = self._scan_angle
        FAN_DEG   = 60
        steps     = 30
        sweep_path = QPainterPath()
        sweep_path.moveTo(0, 0)
        for si in range(steps + 1):
            frac   = si / steps
            a_rad  = math.radians(sweep_a - FAN_DEG * frac)
            sweep_path.lineTo(sweep_r * math.cos(a_rad),
                              sweep_r * math.sin(a_rad))
        sweep_path.closeSubpath()

        sweep_alpha = 55 if not is_think else 90
        sweep_grad  = QConicalGradient(0, 0, sweep_a)
        sweep_grad.setColorAt(0.0,  self._c(0, 220, 255, sweep_alpha))
        sweep_grad.setColorAt(0.16, self._c(0, 150, 255, sweep_alpha // 2))
        sweep_grad.setColorAt(1.0,  self._c(0, 100, 200, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(sweep_grad))
        p.drawPath(sweep_path)

        a_lead = math.radians(sweep_a)
        p.setPen(QPen(self._c(0, 255, 255, 200), 2.0,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(0, 0), QPointF(sweep_r * math.cos(a_lead),
                                          sweep_r * math.sin(a_lead)))
        p.restore()

        # ── 6. ORBITING NODE DOTS ────────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        for nd in self._nodes:
            nd_r   = R * nd['r_frac'] * breath
            nd_ang = math.radians(nd['angle_off'] + self._angle * nd['speed'] / 18.0)
            nd_x   = hx + nd_r * math.cos(nd_ang)
            nd_y   = hy + nd_r * math.sin(nd_ang) * TILT
            nd_sz  = nd['size'] * (1.0 + spk_v * 0.5)
            nd_a   = 200 + int(spk_v * 55) if is_speaking else 160
            gnd    = QRadialGradient(nd_x, nd_y, nd_sz * 3)
            gnd.setColorAt(0.0, self._c(0, 230, 255, nd_a))
            gnd.setColorAt(1.0, self._c(0, 100, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(gnd))
            p.drawEllipse(QRectF(nd_x - nd_sz*3, nd_y - nd_sz*3,
                                 nd_sz*6,         nd_sz*6))
            p.setBrush(self._c(200, 255, 255, 255))
            p.drawEllipse(QRectF(nd_x - nd_sz*0.6, nd_y - nd_sz*0.6,
                                 nd_sz*1.2,         nd_sz*1.2))

        # ── 7. FLOATING DATA PARTICLES ────────────────────────────────────
        for pt in self._pts:
            pt_r   = R * pt['r_frac'] * breath
            pt_ang = math.radians(pt['angle'] + self._angle * pt['speed'] / 18.0)
            pt_x   = hx + pt_r * math.cos(pt_ang)
            pt_y   = hy + pt_r * math.sin(pt_ang) * TILT
            pt_sz  = pt['size']
            pt_a   = min(255, pt['alpha'] + int(spk_v * 80))
            gpt    = QRadialGradient(pt_x, pt_y, pt_sz * 2.5)
            gpt.setColorAt(0.0, self._c(0, 200, 255, pt_a))
            gpt.setColorAt(1.0, self._c(0,  80, 200, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(gpt))
            p.drawEllipse(QRectF(pt_x - pt_sz*2.5, pt_y - pt_sz*2.5,
                                 pt_sz*5.0,         pt_sz*5.0))

        # ── 8. INNER DARK GLASS DISC ─────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        inner_r = R * 0.38 * breath
        glass_g = QRadialGradient(hx, hy, inner_r)
        glass_g.setColorAt(0.0, self._c(2,  8, 30, 230))
        glass_g.setColorAt(0.7, self._c(2,  8, 30, 200))
        glass_g.setColorAt(1.0, self._c(0, 20, 60, 140))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glass_g))
        p.drawEllipse(QRectF(hx - inner_r, hy - inner_r * TILT,
                             inner_r * 2,   inner_r * 2 * TILT))

        # ── 9. ENERGY CORE BLOOM ─────────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        base_bloom = R * 0.28 * breath
        if is_speaking:
            base_bloom *= (1.0 + 0.25 * spk_v
                          + 0.12 * math.sin(time.perf_counter() * 28.0))
        elif is_listen:
            base_bloom *= 1.0 + mic_v * 0.20
        elif is_think:
            base_bloom *= 1.0 + 0.10 * math.sin(time.perf_counter() * 15.0)

        eg1 = QRadialGradient(hx, hy, base_bloom * 2.6)
        eg1.setColorAt(0.0, self._c(0, 160, 255, 90))
        eg1.setColorAt(1.0, self._c(0,  40, 150, 0))
        p.setBrush(QBrush(eg1))
        p.drawEllipse(QRectF(hx - base_bloom*2.6, hy - base_bloom*2.6*TILT,
                             base_bloom*5.2,       base_bloom*5.2*TILT))

        eg2 = QRadialGradient(hx, hy, base_bloom * 1.6)
        eg2.setColorAt(0.0, self._c(0, 220, 255, 160))
        eg2.setColorAt(1.0, self._c(0,  80, 255, 0))
        p.setBrush(QBrush(eg2))
        p.drawEllipse(QRectF(hx - base_bloom*1.6, hy - base_bloom*1.6*TILT,
                             base_bloom*3.2,       base_bloom*3.2*TILT))

        eg3 = QRadialGradient(hx, hy, base_bloom * 0.9)
        eg3.setColorAt(0.0, self._c(240, 255, 255, 255))
        eg3.setColorAt(0.3, self._c( 80, 240, 255, 240))
        eg3.setColorAt(0.7, self._c(  0, 150, 255, 160))
        eg3.setColorAt(1.0, self._c(  0,  50, 200,   0))
        p.setBrush(QBrush(eg3))
        p.drawEllipse(QRectF(hx - base_bloom*0.9, hy - base_bloom*0.9*TILT,
                             base_bloom*1.8,       base_bloom*1.8*TILT))

        # ── 10. NOVA TEXT ─────────────────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        font_px = max(18, int(R * 0.38))
        font    = QFont("Consolas", font_px, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                              max(4.0, font_px * 0.55))
        p.setFont(font)

        fm   = QFontMetrics(font)
        text = "NOVA"
        tw   = fm.horizontalAdvance(text)
        th   = fm.ascent()
        tx   = hx - tw / 2
        ty   = hy + th / 3

        # Multi-pass glow text shadow
        for goff, ga, gcol in [
            (6, 50,  (0, 200, 255)),
            (4, 90,  (0, 220, 255)),
            (2, 140, (120, 240, 255)),
        ]:
            shadow_col = QColor(gcol[0], gcol[1], gcol[2], ga)
            for dx in range(-goff, goff+1, goff):
                for dy in range(-goff, goff+1, goff):
                    p.setPen(shadow_col)
                    p.drawText(QPointF(tx + dx, ty + dy), text)

        # Crisp NOVA text
        t_r, t_g, t_b = (200, 255, 255) if is_speaking else (230, 255, 255)
        p.setPen(self._c(t_r, t_g, t_b, 245))
        p.drawText(QPointF(tx, ty), text)

        # ── 11. THIN INNER BORDER RING ────────────────────────────────────
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.save()
        p.translate(hx, hy)
        p.scale(1.0, TILT)
        border_r = R * 0.405 * breath
        p.setPen(QPen(self._c(0, 200, 255, 160), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(-border_r, -border_r, border_r*2, border_r*2))
        p.restore()




# ═══════════════════════════════════════════════════════════════════════════
# Audio Level Bars (bottom HUD micro-widget)
# ═══════════════════════════════════════════════════════════════════════════
class AudioBars(QWidget):
    def __init__(self, status_fn, parent=None):
        super().__init__(parent)
        self._status = status_fn
        self._lvl = 0.0
        self._phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(44, 24)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(60)

    def set_level(self, v):
        self._lvl = min(1.0, v)

    def _tick(self):
        self._phase = (self._phase + 0.3) % (2*math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        st = self._status()
        w, h = self.width(), self.height()
        n = 7
        bw = (w - (n-1)*2) / n
        for i in range(n):
            # each bar pulses at a slightly different phase
            ph_off = i * 0.55
            if st in ("LISTENING...", "WAKE DETECTED"):
                height_f = 0.30 + 0.70 * abs(math.sin(self._phase + ph_off))
            elif st == "SPEAKING...":
                height_f = 0.20 + 0.60 * abs(math.sin(self._phase*1.5 + ph_off))
            else:
                height_f = 0.12 + 0.15 * abs(math.sin(self._phase*0.5 + ph_off))
            bh = max(3, int(height_f * h))
            x  = int(i * (bw + 2))
            y  = h - bh
            alpha = int(120 + 135 * height_f)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 200, 255, alpha))
            p.drawRoundedRect(int(x), y, max(2, int(bw)), bh, 1, 1)


# ═══════════════════════════════════════════════════════════════════════════
# Volume Bar (bottom HUD)
# ═══════════════════════════════════════════════════════════════════════════
class VolumeBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vol = 0.75
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(80, 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 80, 130, 100))
        p.drawRoundedRect(0, 0, w, h, h//2, h//2)
        # fill
        fw = int(w * self._vol)
        p.setBrush(QColor(0, 200, 255, 220))
        p.drawRoundedRect(0, 0, fw, h, h//2, h//2)


# ═══════════════════════════════════════════════════════════════════════════
# Inline Reactor Logo Widget (top-left)
# ═══════════════════════════════════════════════════════════════════════════
class ReactorLogoWidget(QWidget):
    def __init__(self, size=52, parent=None):
        super().__init__(parent)
        self._sz = size
        self._phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(size, size)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30)

    def _tick(self):
        self._phase = (self._phase + 0.05) % (2*math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        R  = self._sz * 0.47
        cx = self._sz * 0.5
        cy = self._sz * 0.5
        # rotating spoke offset gives spin illusion
        draw_nova_reactor(p, cx, cy, R)


# ═══════════════════════════════════════════════════════════════════════════
# Large Centre Reactor Logo (bottom-HUD centre card) – draws in paintEvent
# ═══════════════════════════════════════════════════════════════════════════
class CentreReactorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(68, 68)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(30)

    def _tick(self):
        self._phase = (self._phase + 0.04) % (2*math.pi)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        R  = 30.0
        cx, cy = 34.0, 34.0
        draw_nova_reactor(p, cx, cy, R)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════
_TOP_H    = 90
_BOTTOM_H = 108
_CHAT_H   = 70
_PAD      = 18

_DARK_BG     = "rgba(4, 6, 16, 250)"
_PANEL_BG    = "rgba(6, 10, 24, 210)"
_BORDER_BLUE = "rgba(0, 190, 255, 0.50)"
_TEXT_DIM    = "#2A4A6A"
_TEXT_CYAN   = "#00FFFF"
_TEXT_GREEN  = "#00FF88"
_TEXT_WHITE  = "#E8F0FF"


class RootWidget(QWidget):
    """
    Subclassed QWidget to cleanly paint a dark sci-fi spaceship control room
    background and overlay it with a dark transparent neon blue glass cover.
    Clips everything to the root's 20px rounded window corners.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg = QPixmap(BG_PATH)
        self._px = 0.0
        self._py = 0.0
        
    def set_parallax_offset(self, px, py):
        self._px = px
        self._py = py
        self.update()
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Clip painter to rounded window corners (20px border radius)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20.0, 20.0)
        p.setClipPath(path)
        
        rect = self.rect()
        # Fallback high-quality gradient
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(3, 5, 14))
        g.setColorAt(1.0, QColor(5, 9, 22))
        p.setBrush(QBrush(g))
        p.drawRect(rect)
            
        # Draw a vertical gradient overlay (leaving center clear for the reactor)
        h = self.height()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(4, 6, 16, 190))
        grad.setColorAt(0.18, QColor(4, 6, 16, 160))
        grad.setColorAt(0.28, QColor(4, 6, 16, 0))    # Transparent in the center
        grad.setColorAt(0.72, QColor(4, 6, 16, 0))    # Transparent in the center
        grad.setColorAt(0.82, QColor(4, 6, 16, 160))
        grad.setColorAt(1.0, QColor(4, 6, 16, 210))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(rect)


class NovaUI(QMainWindow):
    """
    Main HUD window.  Architectural choices:
    - root_widget  → dark glass base (painted in paintEvent).
    - core_widget  → positioned absolutely INSIDE root, raised above background.
    - HUD bars     → also children of root, raised; occupy top/bottom strips.
    - chat_panel   → absolutely positioned above core's top edge.
    """

    def __init__(self, on_close_callback=None, on_stop_callback=None):
        if not _PYQT6:
            raise RuntimeError("PyQt6 required.")
        self.app = QApplication.instance() or QApplication(sys.argv)
        super().__init__()

        self.on_close_callback = on_close_callback
        self.on_stop_callback  = on_stop_callback
        self.current_status    = "INITIALIZING..."

        self._sig = _Signaler()
        self._sig.state.connect(self._on_state)
        self._sig.mic.connect(self._on_mic)
        self._drag = QPoint()

        # ── window chrome ─────────────────────────────────────────────────
        self.setWindowTitle("NOVA AI")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1280, 900)
        sc = self.app.primaryScreen().geometry()
        self.move((sc.width()-1280)//2, (sc.height()-900)//2)

        self._build()

        # clock
        ct = QTimer(self)
        ct.timeout.connect(self._clock_tick)
        ct.start(500)
        self._clock_tick()

        # 3D mouse parallax tracking timer
        self._parallax_timer = QTimer(self)
        self._parallax_timer.timeout.connect(self._update_parallax)
        self._parallax_timer.start(30)

    # ═══════════════════════════════════════════════════════════════════════
    # Build UI
    # ═══════════════════════════════════════════════════════════════════════
    def _build(self):
        W, H = self.width(), self.height()

        # ── Root (dark glass background) ──────────────────────────────────
        self._root = RootWidget(self)
        self._root.setObjectName("Root")
        self._root.setGeometry(0, 0, W, H)
        self._root.setStyleSheet(f"""
            QWidget#Root {{
                border: 2px solid rgba(0,190,255,0.55);
                border-radius: 20px;
            }}
        """)

        # ── TOP BAR ───────────────────────────────────────────────────────
        self._top = QWidget(self._root)
        self._top.setGeometry(0, 0, W, _TOP_H)
        self._top.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        tb = QHBoxLayout(self._top)
        tb.setContentsMargins(_PAD, 10, _PAD, 8)
        tb.setSpacing(0)

        # LEFT: reactor logo + Nova branding
        lft = QHBoxLayout()
        lft.setSpacing(12)
        self._reactor_logo = ReactorLogoWidget(52)
        lft.addWidget(self._reactor_logo)
        lft_v = QVBoxLayout()
        lft_v.setSpacing(1)
        l_nova = QLabel("NOVA")
        l_nova.setStyleSheet(
            "font: 900 28px 'Consolas', 'Segoe UI'; letter-spacing: 5px;"
            "color: #00E8FF; background: transparent;")
        l_ai = QLabel("AI ASSISTANT")
        l_ai.setStyleSheet(
            "font: 700 9px 'Segoe UI'; letter-spacing: 3px;"
            "color: #1A4060; background: transparent;")
        lft_v.addWidget(l_nova)
        lft_v.addWidget(l_ai)
        lft_v.addStretch()
        lft.addLayout(lft_v)
        tb.addLayout(lft, 2)

        # CENTER: waveform + status label
        ctr = QVBoxLayout()
        ctr.setSpacing(4)
        ctr.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_lbl = QLabel("READY")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            "font: 900 19px 'Consolas'; letter-spacing: 3px;"
            "color: #00FF88; background: transparent;")
        self._wave = WaveformWidget(lambda: self.current_status)
        self._wave.setFixedSize(460, 36)
        self._wave.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        ctr.addWidget(self._wave)
        ctr.addWidget(self._status_lbl)
        tb.addLayout(ctr, 3)

        # RIGHT: clock + controls
        rgt = QVBoxLayout()
        rgt.setSpacing(3)
        rgt.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        # window control buttons
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(5)
        ctrl_row.addStretch()
        for lbl, obj, slot, is_close in [
            ("—",  "WMin", self.showMinimized,    False),
            ("⬜", "WMax", self._toggle_max,       False),
            ("✕",  "WCls", self.close,             True ),
        ]:
            b = QPushButton(lbl)
            b.setObjectName(obj)
            b.setFixedSize(28, 20)
            if is_close:
                b.setStyleSheet(
                    "QPushButton#WCls{background:rgba(220,40,0,0.08);"
                    "border:1px solid rgba(220,40,0,0.35);border-radius:3px;"
                    "color:#FF4422;font:bold 11px;}"
                    "QPushButton#WCls:hover{background:rgba(220,40,0,0.28);}")
            else:
                b.setStyleSheet(
                    f"QPushButton#{obj}{{background:rgba(0,190,255,0.06);"
                    "border:1px solid rgba(0,190,255,0.30);border-radius:3px;"
                    f"color:#00CCFF;font:bold 11px;}}"
                    f"QPushButton#{obj}:hover{{background:rgba(0,190,255,0.22);}}")
            b.clicked.connect(slot)
            ctrl_row.addWidget(b)
            if obj == "WMax":
                self._max_btn = b
        rgt.addLayout(ctrl_row)

        self._time_lbl = QLabel("00:00:00")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._time_lbl.setStyleSheet(
            "font: 700 22px 'Consolas'; color: #00FFFF; background: transparent;")
        self._date_lbl = QLabel("")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._date_lbl.setStyleSheet(
            "font: 700 9px 'Segoe UI'; letter-spacing: 1px;"
            "color: #1A4060; background: transparent;")
        rgt.addWidget(self._time_lbl)
        rgt.addWidget(self._date_lbl)
        rgt.addStretch()
        tb.addLayout(rgt, 2)

        # Top separator line
        sep1 = QFrame(self._root)
        sep1.setGeometry(_PAD, _TOP_H-1, W-2*_PAD, 1)
        sep1.setStyleSheet("background: rgba(0,190,255,0.22); border: none;")
        sep1.raise_()

        # ── CONTENT FRAME (dark glass with blue border) ───────────────────
        FRAME_Y = _TOP_H
        FRAME_H = H - _TOP_H - _BOTTOM_H
        self._frame = QFrame(self._root)
        self._frame.setObjectName("CFrame")
        self._frame.setGeometry(_PAD, FRAME_Y, W - 2*_PAD, FRAME_H)
        self._frame.setStyleSheet("""
            QFrame#CFrame {
                background: transparent;
                border: 1px solid rgba(0,180,255,0.30);
                border-radius: 12px;
            }
        """)
        self._frame.raise_()

        # ── HOLOGRAPHIC CORE (fills content frame, minus chat strip at top) ─
        core_y_in_frame = _CHAT_H + 4    # below chat panel inside the frame
        core_h_in_frame = FRAME_H - core_y_in_frame
        self._core = HoloCoreWidget(lambda: self.current_status, self._frame)
        self._core.setGeometry(0, core_y_in_frame,
                               W - 2*_PAD, core_h_in_frame)
        self._core.raise_()

        # ── CHAT PANEL (top of content frame, compact) ────────────────────
        self._chat = QFrame(self._frame)
        self._chat.setObjectName("Chat")
        self._chat.setGeometry(6, 6, W - 2*_PAD - 12, _CHAT_H - 8)
        self._chat.setStyleSheet("""
            QFrame#Chat {
                background: rgba(5,9,22,200);
                border: 1px solid rgba(0,180,255,0.28);
                border-radius: 10px;
            }
        """)
        self._chat.raise_()

        ch_lay = QHBoxLayout(self._chat)
        ch_lay.setContentsMargins(16, 6, 12, 6)
        ch_lay.setSpacing(12)

        ch_v = QVBoxLayout()
        ch_v.setSpacing(5)
        self._user_lbl = QLabel("YOU: —")
        self._user_lbl.setStyleSheet(
            "font: 700 11px 'Segoe UI'; color: #6680CC; background: transparent;")
        self._nova_lbl = QLabel("NOVA: Systems online. Waiting for wake word…")
        self._nova_lbl.setStyleSheet(
            "font: 600 12px 'Segoe UI'; color: #00FFCC; background: transparent;")
        self._hint_lbl = QLabel(
            "● [WAKE]  Say 'Hey Nova' or press SPACEBAR to activate")
        self._hint_lbl.setStyleSheet(
            "font: italic 9px 'Segoe UI'; color: #1A3850; background: transparent;")
        ch_v.addWidget(self._user_lbl)
        ch_v.addWidget(self._nova_lbl)
        ch_v.addWidget(self._hint_lbl)
        ch_lay.addLayout(ch_v, 1)

        self._stop_btn = QPushButton("🛑  STOP")
        self._stop_btn.setFixedSize(90, 44)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(180,30,0,0.14);
                border: 1px solid rgba(255,70,0,0.50);
                border-radius: 8px;
                color: #FF4422;
                font: bold 12px 'Segoe UI';
            }
            QPushButton:hover {
                background: rgba(255,60,0,0.28);
                border-color: rgba(255,100,0,0.9);
                color: #FFAA88;
            }
            QPushButton:pressed { background: rgba(255,60,0,0.45); }
        """)
        self._stop_btn.clicked.connect(self._do_stop)
        ch_lay.addWidget(self._stop_btn)

        # ── BOTTOM HUD ────────────────────────────────────────────────────
        self._bot = QWidget(self._root)
        self._bot.setGeometry(0, H - _BOTTOM_H, W, _BOTTOM_H)
        self._bot.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._bot.raise_()

        sep2 = QFrame(self._root)
        sep2.setGeometry(_PAD, H - _BOTTOM_H, W - 2*_PAD, 1)
        sep2.setStyleSheet("background: rgba(0,190,255,0.22); border: none;")
        sep2.raise_()

        bb = QHBoxLayout(self._bot)
        bb.setContentsMargins(_PAD, 10, _PAD, 14)
        bb.setSpacing(0)

        # Card factory
        def _card(title_txt, icon_txt, value_txt, val_color="#00FF88",
                  extra_widget=None):
            """Build a stat card widget; returns (card_widget, value_label)."""
            card = QFrame()
            card.setObjectName("StatCard")
            card.setStyleSheet("""
                QFrame#StatCard {
                    background: rgba(5, 9, 22, 160);
                    border: 1px solid rgba(0, 180, 255, 0.25);
                    border-radius: 8px;
                }
            """)
            vl = QVBoxLayout(card)
            vl.setContentsMargins(10, 6, 10, 6)
            vl.setSpacing(3)
            # title row
            hr = QHBoxLayout()
            hr.setSpacing(4)
            icon_l = QLabel(icon_txt)
            icon_l.setStyleSheet(
                "font: 11px; color: #0088CC; background: transparent;")
            title_l = QLabel(title_txt)
            title_l.setStyleSheet(
                "font: 700 8px 'Segoe UI'; letter-spacing: 2px;"
                "color: #5588AA; background: transparent;")
            hr.addWidget(icon_l)
            hr.addWidget(title_l)
            hr.addStretch()
            vl.addLayout(hr)
            if extra_widget:
                vl.addWidget(extra_widget)
            val_l = QLabel(value_txt)
            val_l.setStyleSheet(
                f"font: 700 11px 'Consolas'; color: {val_color};"
                "background: transparent;")
            vl.addWidget(val_l)
            return card, val_l

        # Set spacing for layout without vertical line separators
        bb.setSpacing(12)

        # CARD 1: Voice Active
        self._audio_bars = AudioBars(lambda: self.current_status)
        c1, self._b_voice = _card("VOICE ACTIVE", "🎤", "WAITING",
                                   "#00FF88", self._audio_bars)
        bb.addWidget(c1, 2)

        # CARD 2: Wake Word
        c2, _ = _card("WAKE WORD", "◈", "HEY NOVA", "#00FFFF")
        bb.addWidget(c2, 2)

        # CARD 3: Centre Nova Reactor (large)
        c3 = QWidget()
        c3.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        c3v = QVBoxLayout(c3)
        c3v.setContentsMargins(0, 0, 0, 0)
        c3v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._centre_reactor = CentreReactorWidget()
        c3_lbl = QLabel("NOVA")
        c3_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c3_lbl.setStyleSheet(
            "font: 900 9px 'Consolas'; letter-spacing: 4px;"
            "color: #00CCFF; background: transparent;")
        c3v.addWidget(self._centre_reactor, 0, Qt.AlignmentFlag.AlignHCenter)
        c3v.addWidget(c3_lbl)
        bb.addWidget(c3, 2)

        # CARD 4: Status
        c4, self._b_status = _card("STATUS", "●", "READY", "#00FF88")
        self._b_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        c4.layout().setAlignment(Qt.AlignmentFlag.AlignRight)
        bb.addWidget(c4, 2)

        # CARD 5: Mode
        c5, _ = _card("MODE", "⬡", "VOICE ASSISTANT", "#00FFFF")
        c5.layout().setAlignment(Qt.AlignmentFlag.AlignRight)
        bb.addWidget(c5, 2)

        # CARD 6: Volume
        self._vol_bar = VolumeBar()
        c6, _ = _card("VOLUME", "🔊", "80%", "#00CCFF", self._vol_bar)
        c6.layout().setAlignment(Qt.AlignmentFlag.AlignRight)
        bb.addWidget(c6, 2)

        # raise important elements to top
        self._top.raise_()
        self._bot.raise_()

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════
    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
            self._max_btn.setText("⬜")
        else:
            self.showMaximized()
            self._max_btn.setText("🗗")

    def _do_stop(self):
        if self.on_stop_callback:
            self.on_stop_callback()

    def _clock_tick(self):
        now = datetime.now()
        self._time_lbl.setText(now.strftime("%H:%M:%S"))
        self._date_lbl.setText(now.strftime("%a, %d %b %Y"))

    # ── state update (from Qt signal – always on GUI thread) ─────────────
    def _on_state(self, status, user_text, nova_text):
        self.current_status = status
        col = _STATE_COLOR.get(status, "#00FFFF")

        self._status_lbl.setText(status.upper())
        self._status_lbl.setStyleSheet(
            f"font: 900 19px 'Consolas'; letter-spacing: 3px;"
            f"color: {col}; background: transparent;")
        self._b_status.setText(status.replace("...", "").upper())
        self._b_status.setStyleSheet(
            f"font: 700 11px 'Consolas'; color: {col}; background: transparent;")

        if user_text and user_text.strip():
            self._user_lbl.setText(
                "YOU: " + user_text[:96] + ("…" if len(user_text) > 96 else ""))
        if nova_text and nova_text.strip():
            self._nova_lbl.setText(
                "NOVA: " + nova_text[:104] + ("…" if len(nova_text) > 104 else ""))

        _voice_map = {
            "LISTENING...":  ("🎤  LISTENING",  "#00FFFF",
                              "● [REC]  Recording your command…"),
            "WAKE DETECTED": ("🎤  ACTIVE",     "#00FFFF",
                              "● [WAKE]  Wake word detected!"),
            "THINKING...":   ("🧠  THINKING",   "#FFAA00",
                              "● [ENGINE]  Processing your request…"),
            "EXECUTING...":  ("⚡  EXECUTING",  "#FFD700",
                              "● [ACTION]  Running command…"),
            "SPEAKING...":   ("🔊  SPEAKING",   "#3399FF",
                              "● [TTS]  Nova is responding…"),
        }
        if status in _voice_map:
            vtxt, vcol, hint = _voice_map[status]
            self._b_voice.setText(vtxt)
            self._b_voice.setStyleSheet(
                f"font: 700 11px 'Consolas'; color: {vcol}; background: transparent;")
            self._hint_lbl.setText(hint)
        else:
            self._b_voice.setText("🎤  WAITING")
            self._b_voice.setStyleSheet(
                "font: 700 11px 'Consolas'; color: #00FF88; background: transparent;")
            self._hint_lbl.setText(
                "● [WAKE]  Say 'Hey Nova' or press SPACEBAR to activate")

    def _on_mic(self, rms, indata):
        self._core.mic_level = min(rms * 3.0, 1.0)
        self._audio_bars.set_level(rms * 3.0)
        self._wave.feed(indata)

    # ── Public thread-safe API (called from background threads) ──────────
    def update_state(self, status, user_text=None, nova_text=None):
        self._sig.state.emit(status, user_text or "", nova_text or "")

    def update_mic_level(self, rms, indata):
        self._sig.mic.emit(rms, indata)

    # ── Resize: re-layout absolute children ──────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        W, H = self.width(), self.height()
        FRAME_Y = _TOP_H
        FRAME_H = H - _TOP_H - _BOTTOM_H

        self._root.setGeometry(0, 0, W, H)
        self._top.setGeometry(0, 0, W, _TOP_H)
        self._bot.setGeometry(0, H - _BOTTOM_H, W, _BOTTOM_H)
        self._frame.setGeometry(_PAD, FRAME_Y, W - 2*_PAD, FRAME_H)
        self._chat.setGeometry(6, 6, W - 2*_PAD - 12, _CHAT_H - 8)

        core_y = _CHAT_H + 4
        self._core.setGeometry(0, core_y, W - 2*_PAD, FRAME_H - core_y)

    # ── 3D Parallax Mouse Tracking ────────────────────────────────────────
    def _update_parallax(self):
        # Translate global cursor coordinates to relative window coordinates
        pos = self.mapFromGlobal(QCursor.pos())
        w, h = self.width(), self.height()
        
        # Calculate horizontal and vertical displacement from screen center (-1.0 to 1.0)
        cx, cy = w * 0.5, h * 0.5
        dx = (pos.x() - cx) / cx
        dy = (pos.y() - cy) / cy
        
        # Clamp bounds to avoid wild shifts when mouse leaves the UI window bounds
        dx = max(-1.4, min(dx, 1.4))
        dy = max(-1.4, min(dy, 1.4))
        
        # Target parallax shift in pixels
        target_px = dx * 16.0
        target_py = dy * 16.0
        
        # Smoothly interpolate offset with linear damping (lerp factor = 0.1) for a high-end dynamic feel
        current_px = self._root._px
        current_py = self._root._py
        new_px = current_px + (target_px - current_px) * 0.1
        new_py = current_py + (target_py - current_py) * 0.1
        
        self._root.set_parallax_offset(new_px, new_py)

    # ── Window drag ───────────────────────────────────────────────────────
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._do_stop()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.on_close_callback:
            self.on_close_callback()
        else:
            event.accept()

    def start(self):
        self.show()
        sys.exit(self.app.exec())

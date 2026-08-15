"""
interface/gui/gui_app.py
------------------------
Desktop GUI for Nova AI Assistant — PyQt6.
Holographic 3D-style orbital core with:
  - 4 independent rotating orbital rings (different speeds, tilts, directions)
  - 8 orbital particles
  - State-reactive colors and animation speeds
  - Pulsing/waveform effects per state
  - Compact (190x220) and expanded (500x340) modes
  - Frameless, translucent, draggable, bottom-right desktop presence
  - Safe Qt timer shutdown (no RuntimeError on close)
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    from PyQt6 import sip
    from PyQt6.QtCore import (
        QPoint, QRectF, Qt, QThread, QTimer, pyqtSignal, QObject,
    )
    from PyQt6.QtGui import (
        QBrush, QColor, QFont, QLinearGradient,
        QMouseEvent, QPainter, QPen, QRadialGradient,
        QTransform,
    )
    from PyQt6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout,
        QLabel, QMainWindow, QPushButton,
        QVBoxLayout, QWidget,
    )
    PYQT6_AVAILABLE = True
except ImportError as _pyqt_err:
    logger.warning("PyQt6 not available: %s", _pyqt_err)
    PYQT6_AVAILABLE = False


# ---------------------------------------------------------------------------
# State colour palette: (primary, secondary, glow)
# ---------------------------------------------------------------------------
_STATE_COLORS: dict[str, tuple[str, str, str]] = {
    "IDLE":          ("#8b5cf6", "#4c1d95", "#7c3aed"),
    "WAKING":        ("#8b5cf6", "#4c1d95", "#7c3aed"),
    "WAKE DETECTED": ("#06b6d4", "#164e63", "#0891b2"),
    "LISTENING":     ("#06b6d4", "#164e63", "#22d3ee"),
    "PROCESSING":    ("#d946ef", "#701a75", "#c026d3"),
    "THINKING":      ("#d946ef", "#701a75", "#e879f9"),
    "EXECUTING":     ("#10b981", "#064e3b", "#34d399"),
    "SPEAKING":      ("#f59e0b", "#78350f", "#fbbf24"),
    "ERROR":         ("#ef4444", "#7f1d1d", "#f87171"),
}

# Speed multipliers for each state
_STATE_SPEED: dict[str, float] = {
    "IDLE": 1.0, "WAKING": 1.0, "WAKE DETECTED": 1.5,
    "LISTENING": 1.8, "PROCESSING": 2.8, "THINKING": 2.5,
    "EXECUTING": 3.2, "SPEAKING": 2.0, "ERROR": 1.2,
}


def _hex_color(hex_str: str, alpha: int = 255) -> "QColor":
    c = QColor(hex_str)
    c.setAlpha(alpha)
    return c


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------
class NovaWorker(QThread):
    """Async worker to run engine commands off the GUI thread."""
    chunk_received = pyqtSignal(str)
    finished       = pyqtSignal(str)
    error          = pyqtSignal(str)

    def __init__(self, engine: Any, user_input: str) -> None:
        super().__init__()
        self.engine     = engine
        self.user_input = user_input

    def run(self) -> None:
        try:
            response_gen = self.engine.handle_input(self.user_input, stream=True)
            if hasattr(response_gen, "__next__") or hasattr(response_gen, "__iter__"):
                full = ""
                for chunk in response_gen:
                    self.chunk_received.emit(chunk)
                    full += chunk
                self.finished.emit(full)
            else:
                self.finished.emit(str(response_gen))
        except Exception as exc:
            logger.exception("GUI worker error: %s", exc)
            self.error.emit(str(exc))


class NovaHolographicCore(QWidget):
    """
    Volumetric 3D Spherical Neural Intelligence visual target.
    Renders 2000 particles distributed throughout a large 3D spherical volume
    satisfying x^2 + y^2 + z^2 <= R^2.
    Includes a small luminous organic core with revolving filament threads, a dense neural field,
    and 6 rotating translucent curved glass shell arcs on tilted planes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_gui = parent
        self._destroyed = False
        self.voice_activity_level = 0.0
        self._active_state = "IDLE"

        self._wphase = 0.0
        self._pulse = 0.5
        self._pdir = 1

        import time as _time
        self._last_time = _time.perf_counter()
        self._fps_timer = self._last_time
        self._frame_count = 0

        self.angle_x = 0.0
        self.angle_y = 0.0
        self.angle_z = 0.0
        self.core_angle = 0.0

        # Small HUD label font
        self.font_hud = QFont("Consolas", 7)
        
        # Cache dictionaries for graphics resources to optimize painting
        self.color_cache = {}
        self.pen_cache = {}
        self.brush_cache = {}

        import random as _rng
        _rng.seed(2026)  # deterministic seeding for stable visual structure

        self.particles = []
        self.connections = []
        self.core_filaments = []  # List of lists of 3D points
        self.shell_arcs = []  # List of dicts with 3D points and properties

        # Large sphere radius
        R_SPHERE = 168.0

        # Layer 1: Inner Core region (r = 0 to 25.0) - 15% (300 particles)
        for _ in range(300):
            r = 25.0 * (_rng.random() ** (1.0 / 3.0))
            theta = math.acos(2.0 * _rng.random() - 1.0)
            phi = _rng.uniform(0.0, 2.0 * math.pi)
            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)
            
            size = _rng.uniform(0.7, 1.4)
            col = _rng.choice(["#ffffff", "#e0ffff", "#00f3ff", "#00ffcc"])
            self.particles.append({
                "r0": r, "base_x": x, "base_y": y, "base_z": z,
                "size": size, "col": col, "layer": "core",
                "phase": _rng.uniform(0.0, 2.0 * math.pi),
                "is_accent": False
            })

        # Layer 2: Mid Neural Field (r = 25.0 to 115.0) - 50% (1000 particles)
        for _ in range(1000):
            v_min = 25.0 ** 3
            v_max = 115.0 ** 3
            r = (v_min + _rng.random() * (v_max - v_min)) ** (1.0 / 3.0)
            theta = math.acos(2.0 * _rng.random() - 1.0)
            phi = _rng.uniform(0.0, 2.0 * math.pi)
            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)

            # Colors proportions: cyan/teal/blue (86%), violet/purple (11%), magenta (2.0%), orange/amber (1.0%)
            rv = _rng.random()
            is_accent = False
            if rv < 0.010:
                col = "#ff9900"  # Orange/amber accent node
                size = _rng.uniform(4.0, 5.5)  # Larger accents
                is_accent = True
            elif rv < 0.030:
                col = "#ff00cc"  # Magenta accent node
                size = _rng.uniform(2.8, 3.8)
                is_accent = True
            elif rv < 0.140:
                col = _rng.choice(["#7a00ff", "#b800ff"])  # Violet/purple
                size = _rng.uniform(2.0, 3.2)  # Medium nodes (2-4px)
            elif rv < 0.450:
                col = _rng.choice(["#0066ff", "#0000ff"])  # Blue
                size = _rng.uniform(0.7, 1.8)
            else:
                col = _rng.choice(["#00f3ff", "#00d8ff", "#00ffcc"])  # Cyan/teal
                size = _rng.uniform(0.7, 1.8)

            self.particles.append({
                "r0": r, "base_x": x, "base_y": y, "base_z": z,
                "size": size, "col": col, "layer": "mid",
                "phase": _rng.uniform(0.0, 2.0 * math.pi),
                "is_accent": is_accent
            })

        # Layer 3: Outer Volume Field (r = 115.0 to 168.0) - 35% (700 particles)
        for _ in range(700):
            v_min = 115.0 ** 3
            v_max = 168.0 ** 3
            r = (v_min + _rng.random() * (v_max - v_min)) ** (1.0 / 3.0)
            theta = math.acos(2.0 * _rng.random() - 1.0)
            phi = _rng.uniform(0.0, 2.0 * math.pi)
            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)
            
            rv = _rng.random()
            is_accent = False
            if rv < 0.010:
                col = "#ff9900"
                size = _rng.uniform(4.0, 5.0)
                is_accent = True
            elif rv < 0.030:
                col = "#ff00cc"
                size = _rng.uniform(2.8, 3.6)
                is_accent = True
            else:
                col = _rng.choice(["#00d8ff", "#00f3ff", "#0066ff"])
                size = _rng.uniform(0.7, 1.8)

            self.particles.append({
                "r0": r, "base_x": x, "base_y": y, "base_z": z,
                "size": size, "col": col, "layer": "outer",
                "phase": _rng.uniform(0.0, 2.0 * math.pi),
                "is_accent": is_accent
            })

        # Precompute neural connections (spatially local)
        # Select particles in neural region (r > 20)
        c_candidates = []
        for idx, p in enumerate(self.particles):
            if 20.0 < p["r0"] < 165.0:
                c_candidates.append((idx, p["base_x"], p["base_y"], p["base_z"]))
        
        # Sort by X coordinate for fast O(N log N) spatial sweep connection finder
        c_candidates.sort(key=lambda q: q[1])
        _cd = 20.0  # Local connection distance threshold
        for ii in range(len(c_candidates)):
            if len(self.connections) >= 2500:
                break
            i_idx, xi, yi, zi = c_candidates[ii]
            # Look at subsequent particles in sorted list
            for jj in range(ii + 1, min(ii + 60, len(c_candidates))):
                j_idx, xj, yj, zj = c_candidates[jj]
                if xj - xi > _cd:
                    break
                dx = xi - xj; dy = yi - yj; dz = zi - zj
                d = math.sqrt(dx*dx + dy*dy + dz*dz)
                if 8.0 < d < _cd:
                    self.connections.append((i_idx, j_idx, d))
                    if len(self.connections) >= 2500:
                        break

        # Precompute 20 organic core filament noisy helical paths
        # Core diameter is approx 16% of total sphere diameter (336px) -> radius 25 to 30px
        _rng.seed(88)
        for i in range(20):
            pts = []
            num_steps = 15
            base_theta = _rng.uniform(0.15 * math.pi, 0.85 * math.pi)
            base_phi = _rng.uniform(0.0, 2.0 * math.pi)
            direction = _rng.choice([-1, 1])
            # A noisy helical winding around the central core (radius 20 to 30)
            for step in range(num_steps):
                t = step / (num_steps - 1)
                phi = base_phi + direction * t * _rng.uniform(1.2, 3.2)
                theta = base_theta + math.sin(t * math.pi) * 0.4
                r = 20.0 + 8.0 * math.sin(t * math.pi)
                x = r * math.sin(theta) * math.cos(phi)
                y = r * math.sin(theta) * math.sin(phi)
                z = r * math.cos(theta)
                pts.append({
                    "base_x": x, "base_y": y, "base_z": z,
                    "phase": _rng.uniform(0.0, 2.0 * math.pi)
                })
            self.core_filaments.append(pts)

        # Generate 6 broken 3D glass shell arcs at radius R = 172
        # Tilted planes with various angular spans and colors to outline the sphere volume
        _rng.seed(999)
        num_arcs = 6
        arc_configs = [
            {"tilt_x": 0.5, "tilt_y": 0.3, "span": 1.5, "col": "#00f3ff"},
            {"tilt_x": -0.6, "tilt_y": 0.8, "span": 1.2, "col": "#00f3ff"},
            {"tilt_x": 0.7, "tilt_y": -0.5, "span": 1.8, "col": "#0066ff"},
            {"tilt_x": -0.4, "tilt_y": -0.6, "span": 1.4, "col": "#0066ff"},
            {"tilt_x": 0.9, "tilt_y": 0.2, "span": 1.6, "col": "#ff9900"},  # orange highlight shell
            {"tilt_x": -0.2, "tilt_y": 0.9, "span": 1.5, "col": "#00f3ff"}
        ]
        for config in arc_configs:
            tilt_x = config["tilt_x"]
            tilt_y = config["tilt_y"]
            span = config["span"]
            col = config["col"]
            start_angle = _rng.uniform(0.0, 2.0 * math.pi)
            
            # Generate points
            arc_pts = []
            steps = 24
            for s in range(steps + 1):
                ang = start_angle + (s / steps) * span
                lx = 172.0 * math.cos(ang)
                ly = 172.0 * math.sin(ang)
                lz = 0.0
                
                # Apply local tilt rotation
                cos_tx = math.cos(tilt_x); sin_tx = math.sin(tilt_x)
                cos_ty = math.cos(tilt_y); sin_ty = math.sin(tilt_y)
                
                # Rotate X
                rx = lx
                ry = ly * cos_tx - lz * sin_tx
                rz = ly * sin_tx + lz * cos_tx
                
                # Rotate Y
                fx = rx * cos_ty + rz * sin_ty
                fy = ry
                fz = -rx * sin_ty + rz * cos_ty
                
                arc_pts.append((fx, fy, fz))
            self.shell_arcs.append({"pts": arc_pts, "col": col})

        _rng.seed()  # reset random seed

        self._render_cache = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS tick

    def get_color(self, hex_str, opacity):
        key = (hex_str, opacity)
        if key not in self.color_cache:
            c = QColor(hex_str)
            c.setAlpha(max(0, min(255, opacity)))
            self.color_cache[key] = c
        return self.color_cache[key]

    def get_pen(self, hex_str, opacity, width=1.0):
        key = (hex_str, opacity, width)
        if key not in self.pen_cache:
            p = QPen(self.get_color(hex_str, opacity))
            p.setWidthF(width)
            p.setStyle(Qt.PenStyle.SolidLine)
            self.pen_cache[key] = p
        return self.pen_cache[key]

    def get_brush(self, hex_str, opacity):
        key = (hex_str, opacity)
        if key not in self.brush_cache:
            self.brush_cache[key] = QBrush(self.get_color(hex_str, opacity))
        return self.brush_cache[key]

    def stop_timer(self):
        self._destroyed = True
        try:
            if self._timer.isActive():
                self._timer.stop()
        except RuntimeError:
            pass

    def set_voice_activity(self, level):
        self.voice_activity_level = max(0.0, min(1.0, level))

    def set_state(self, state):
        self._active_state = str(state).upper()

    def _get_state(self):
        if sip.isdeleted(self) or self._destroyed:
            return "IDLE"
        if hasattr(self, "_active_state") and self._active_state:
            return self._active_state
        try:
            return str(getattr(self.parent_gui, "voice_state", "IDLE")).upper()
        except Exception:
            return "IDLE"

    def _tick(self):
        if sip.isdeleted(self) or self._destroyed:
            return
        if self.parent_gui and (self.parent_gui.isMinimized() or not self.parent_gui.isVisible()):
            return
        try:
            self._do_tick()
            self.update()
        except BaseException as e:
            logger.debug("Core tick: %s", e)

    def _do_tick(self):
        import time as _time
        now = _time.perf_counter()
        delta = min(now - self._last_time, 0.05)
        self._last_time = now

        self._frame_count += 1
        if now - self._fps_timer >= 1.0:
            logger.debug("[NOVA-GUI] FPS: %d", int(self._frame_count / (now - self._fps_timer)))
            self._frame_count = 0
            self._fps_timer = now

        state = self._get_state()
        state_mult = _STATE_SPEED.get(state, 1.0)
        base = delta * state_mult

        # Smooth slow rotation speeds per state
        rot_map = {
            "IDLE": 0.08, "LISTENING": 0.16, "WAKE DETECTED": 0.16,
            "PROCESSING": 0.38, "THINKING": 0.34,
            "EXECUTING": 0.46, "SPEAKING": 0.12, "ERROR": 0.08
        }
        rot = rot_map.get(state, 0.12)

        # 3D rotation angles update
        self.angle_x = (self.angle_x + rot * 0.35 * base) % (2.0 * math.pi)
        self.angle_y = (self.angle_y + rot * 0.80 * base) % (2.0 * math.pi)
        self.angle_z = (self.angle_z + rot * 0.18 * base) % (2.0 * math.pi)
        # Central core rotates independently
        self.core_angle = (self.core_angle + rot * 1.50 * base) % (2.0 * math.pi)
        self._wphase = (self._wphase + 2.2 * base) % (2.0 * math.pi)

        # Central core breathing pulse speed
        pulse_speed = 1.4 * base
        self._pulse += self._pdir * pulse_speed
        if self._pulse >= 1.0:
            self._pulse = 1.0
            self._pdir = -1
        elif self._pulse <= 0.35:
            self._pulse = 0.35
            self._pdir = 1

        voice_level = 0.0
        if state == "SPEAKING":
            voice_level = self.voice_activity_level if self.voice_activity_level > 0.01                 else 0.35 + 0.25 * math.sin(self._wphase * 3.5)

        # Compute rotation matrix elements (main sphere rotation)
        cx_a = math.cos(self.angle_x); sx_a = math.sin(self.angle_x)
        cy_a = math.cos(self.angle_y); sy_a = math.sin(self.angle_y)
        cz_a = math.cos(self.angle_z); sz_a = math.sin(self.angle_z)
        r11 = cy_a*cz_a; r12 = sx_a*sy_a*cz_a - cx_a*sz_a; r13 = cx_a*sy_a*cz_a + sx_a*sz_a
        r21 = cy_a*sz_a; r22 = sx_a*sy_a*sz_a + cx_a*cz_a; r23 = cx_a*sy_a*sz_a - sx_a*cz_a
        r31 = -sy_a;     r32 = sx_a*cy_a;                    r33 = cx_a*cy_a

        # Core rotation matrix (independent spin)
        c_ca = math.cos(self.core_angle); s_ca = math.sin(self.core_angle)
        c_ct = math.cos(0.20); s_ct = math.sin(0.20)
        cr11 = c_ca; cr12 = 0.0;  cr13 = s_ca
        cr21 = s_ca*s_ct; cr22 = c_ct; cr23 = -c_ca*s_ct
        cr31 = -s_ca*c_ct; cr32 = s_ct; cr33 = c_ca*c_ct

        # Projection settings (mild perspective projection for realistic 3D volume)
        D = 1000.0
        w, h = self.width(), self.height()
        cx_w, cy_w = w // 2, h // 2

        # 1. Project core plasma filaments segment-by-segment
        proj_core_segments = []
        for filament in self.core_filaments:
            col = "#ffffff" if state == "ERROR" else "#00f3ff"
            proj_pts_f = []
            for pt in filament:
                # Rotate with core rotation
                mx = pt["base_x"]
                my = pt["base_y"]
                mz = pt["base_z"]
                rx = mx*cr11 + my*cr12 + mz*cr13
                ry = mx*cr21 + my*cr22 + mz*cr23
                rz = mx*cr31 + my*cr32 + mz*cr33
                
                # Apply main sphere rotation matrix for composite depth coordinate
                fx = rx*r11 + ry*r12 + rz*r13
                fy = rx*r21 + ry*r22 + rz*r23
                fz = rx*r31 + ry*r32 + rz*r33
                
                sc = D / max(1.0, D + fz)
                proj_pts_f.append({"px": cx_w + fx*sc, "py": cy_w + fy*sc, "z": fz})

            # Create line segment primitives
            for s in range(len(proj_pts_f) - 1):
                pt1 = proj_pts_f[s]
                pt2 = proj_pts_f[s + 1]
                avg_z = (pt1["z"] + pt2["z"]) * 0.5
                proj_core_segments.append({
                    "type": "core_seg",
                    "z": avg_z,
                    "px1": pt1["px"],
                    "py1": pt1["py"],
                    "px2": pt2["px"],
                    "py2": pt2["py"],
                    "col": col
                })

        # 2. Project particles with state-reactive wave scaling
        proj_pts = []
        wph = self._wphase
        for pt in self.particles:
            bx = pt["base_x"]
            by = pt["base_y"]
            bz = pt["base_z"]
            r0 = pt["r0"]

            # Radial animation offsets
            if state == "IDLE":
                s = 1.0 + 0.012 * math.sin(wph * 1.1 + pt["phase"])
            elif state in ("LISTENING", "WAKE DETECTED"):
                s = 1.0 + 0.032 * math.sin(wph * 2.2 - r0 * 0.04 + pt["phase"])
            elif state in ("PROCESSING", "THINKING"):
                s = 1.0 + 0.020 * math.sin(wph * 4.2 + pt["phase"] * 1.4)
            elif state == "SPEAKING":
                s = 1.0 + (0.015 + voice_level * 0.055) * math.sin(wph * 3.5 - r0 * 0.035 + pt["phase"])
            elif state == "EXECUTING":
                s = 1.0 + 0.025 * math.sin(wph * 4.8 + pt["phase"] * 1.1)
            else:
                s = 1.0

            # Restrict particle movements to keep spherical silhouette clean
            s = max(0.92, min(1.08, s))
            bx_s = bx * s; by_s = by * s; bz_s = bz * s

            # Rotate
            fx = bx_s*r11 + by_s*r12 + bz_s*r13
            fy = bx_s*r21 + by_s*r22 + bz_s*r23
            fz = bx_s*r31 + by_s*r32 + bz_s*r33
            
            sc = D / max(1.0, D + fz)
            proj_pts.append({
                "type": "particle",
                "z": fz,
                "px": cx_w + fx*sc,
                "py": cy_w + fy*sc,
                "sc": sc,
                "size": pt["size"],
                "col": pt["col"],
                "layer": pt["layer"],
                "r0": r0,
                "is_accent": pt["is_accent"]
            })

        # 3. Project 3D broken glass shell arcs and generate segment primitives
        proj_arc_segments = []
        for arc in self.shell_arcs:
            arc_color = arc["col"]
            # First, project all points in the arc
            arc_proj_pts = []
            for ax, ay, az in arc["pts"]:
                fx = ax*r11 + ay*r12 + az*r13
                fy = ax*r21 + ay*r22 + az*r23
                fz = ax*r31 + ay*r32 + az*r33
                
                sc = D / max(1.0, D + fz)
                arc_proj_pts.append({"px": cx_w + fx*sc, "py": cy_w + fy*sc, "z": fz})
            
            # Create segment primitives
            for s in range(len(arc_proj_pts) - 1):
                pt1 = arc_proj_pts[s]
                pt2 = arc_proj_pts[s + 1]
                avg_z = (pt1["z"] + pt2["z"]) * 0.5
                proj_arc_segments.append({
                    "type": "arc_seg",
                    "z": avg_z,
                    "px1": pt1["px"],
                    "py1": pt1["py"],
                    "px2": pt2["px"],
                    "py2": pt2["py"],
                    "col": arc_color
                })

        # 4. Combine all projected elements and sort them by depth (back-to-front)
        combined_primitives = proj_pts + proj_arc_segments + proj_core_segments
        combined_primitives_sorted = sorted(combined_primitives, key=lambda p: p["z"], reverse=True)

        self._render_cache = {
            "state": state,
            "pulse": self._pulse,
            "voice_level": voice_level,
            "combined_prims": combined_primitives_sorted,
            "proj_pts_raw": proj_pts,  # Mapping to original indexes for neural lines
        }

    def paintEvent(self, _event):
        if self._destroyed or sip.isdeleted(self):
            return
        try:
            self._do_paint()
        except BaseException as e:
            logger.debug("Core paint: %s", e)

    def draw_vector_char(self, painter, char, x, y, w, h, pen):
        # Draw blocky vector characters using QPainter lines (J.A.R.V.I.S styled)
        painter.setPen(pen)
        if char == 'N':
            painter.drawLine(int(x), int(y), int(x), int(y + h))
            painter.drawLine(int(x), int(y), int(x + w), int(y + h))
            painter.drawLine(int(x + w), int(y), int(x + w), int(y + h))
        elif char == 'O':
            painter.drawLine(int(x), int(y), int(x + w), int(y))
            painter.drawLine(int(x + w), int(y), int(x + w), int(y + h))
            painter.drawLine(int(x + w), int(y + h), int(x), int(y + h))
            painter.drawLine(int(x), int(y + h), int(x), int(y))
        elif char == 'V':
            painter.drawLine(int(x), int(y), int(x + w/2), int(y + h))
            painter.drawLine(int(x + w/2), int(y + h), int(x + w), int(y))
        elif char == 'A':
            painter.drawLine(int(x), int(y + h), int(x + w/2), int(y))
            painter.drawLine(int(x + w/2), int(y), int(x + w), int(y + h))
            painter.drawLine(int(x + w/4), int(y + h/2), int(x + 3*w/4), int(y + h/2))
        elif char == '.':
            # Solid small square dot
            painter.fillRect(QRectF(x + 2, y + h - 4, 4, 4), pen.brush())

    def _do_paint(self):
        cache = getattr(self, "_render_cache", None)
        if not cache:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        state = cache["state"]
        p = cache["pulse"]
        voice_level = cache["voice_level"]
        combined_prims = cache["combined_prims"]
        proj_pts_raw = cache["proj_pts_raw"]

        # 1. Deep space background glow (dark navy/black gradient)
        bg_r = 200
        bg = QRadialGradient(cx, cy, bg_r)
        bg.setColorAt(0.0, self.get_color("#010b1a", 200))
        bg.setColorAt(0.6, self.get_color("#00050d", 130))
        bg.setColorAt(1.0, self.get_color("#000000", 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawEllipse(QRectF(cx - bg_r, cy - bg_r, bg_r * 2, bg_r * 2))

        # 2. Soft transparent shadow overlay (representing the transparent glass globe interior)
        glass_bg = QRadialGradient(cx, cy, 168.0)
        glass_bg.setColorAt(0.0, self.get_color("#000612", 40))
        glass_bg.setColorAt(0.85, self.get_color("#000308", 25))
        glass_bg.setColorAt(1.0, self.get_color("#000000", 0))
        painter.setBrush(QBrush(glass_bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - 168.0, cy - 168.0, 168.0 * 2, 168.0 * 2))

        # 3. Static Outer HUD Framework Dials & Crescent pointer symbols overlaying the border
        hud_col = "#ff3333" if state == "ERROR" else "#00d8ff"
        
        # Top-center vertical indicator
        painter.setPen(self.get_pen(hud_col, 50, 0.8))
        painter.drawLine(cx, cy - 168, cx, cy - 195)
        painter.setBrush(self.get_brush(hud_col, 160))
        painter.drawEllipse(QRectF(cx - 3, cy - 198, 6, 6))
        painter.drawLine(cx - 7, cy - 202, cx + 7, cy - 202)
        
        # Upper-left pointer indicator with crescent target arc (using QRectF instead of QRect)
        painter.setPen(self.get_pen(hud_col, 50, 0.8))
        painter.drawLine(cx - 120, cy - 120, cx - 146, cy - 146)
        painter.drawEllipse(QRectF(cx - 148, cy - 148, 4, 4))
        # Draw a small 90-degree crescent target ring around it
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(cx - 160, cy - 160, 20, 20), 45 * 16, 120 * 16)
        
        # Left-middle dial pointer
        painter.drawLine(cx - 168, cy - 30, cx - 192, cy - 30)
        painter.drawEllipse(QRectF(cx - 194, cy - 32, 4, 4))
        
        # Right-middle pointer ticks & Side HUD Labels ("CUE", "VIBES", "SYS: TC")
        painter.drawLine(cx + 168, cy + 40, cx + 188, cy + 40)
        painter.drawLine(cx + 188, cy + 36, cx + 188, cy + 44)
        
        painter.setFont(self.font_hud)
        painter.setPen(self.get_color(hud_col, 95))
        painter.drawText(cx + 195, cy + 33, "SYS: TC")
        painter.drawText(cx + 195, cy + 43, "VIBES")
        painter.drawText(cx + 195, cy + 53, "CUE")

        # 4. Soft radial glow behind the central filament energy core
        core_scale = 1.0
        if state in ("LISTENING", "WAKE DETECTED"):
            core_scale = 1.25
        elif state == "SPEAKING":
            core_scale = 1.0 + voice_level * 0.35
        elif state in ("PROCESSING", "THINKING"):
            core_scale = 1.15

        # Small energy center gradient ball (Transition: WHITE -> CYAN -> TEAL -> TRANSPARENT)
        cr = int((24 + 4 * p) * core_scale)
        cg = QRadialGradient(cx, cy, cr)
        if state == "ERROR":
            cg.setColorAt(0.00, self.get_color("#ffffff", int(255 * p)))
            cg.setColorAt(0.25, self.get_color("#ffdddd", int(220 * p)))
            cg.setColorAt(0.60, self.get_color("#ff3333", int(150 * p)))
            cg.setColorAt(0.90, self.get_color("#aa0000", int(60 * p)))
            cg.setColorAt(1.00, self.get_color("#330000", 0))
        else:
            cg.setColorAt(0.00, self.get_color("#ffffff", int(230 * p)))
            cg.setColorAt(0.30, self.get_color("#d5ffff", int(190 * p)))
            cg.setColorAt(0.65, self.get_color("#00e5ff", int(110 * p)))
            cg.setColorAt(0.85, self.get_color("#0033bb", int(40 * p)))
            cg.setColorAt(1.00, self.get_color("#000b1a", 0))

        painter.setBrush(QBrush(cg))
        painter.drawEllipse(QRectF(cx - cr, cy - cr, cr * 2, cr * 2))

        # Faint blue/cyan halo around energy core
        glow_r = int((55 + 10 * p) * core_scale)
        soft_g = QRadialGradient(cx, cy, glow_r)
        soft_g.setColorAt(0.0, self.get_color("#00d8ff", int(25 * p)))
        soft_g.setColorAt(1.0, self.get_color("#002266", 0))
        painter.setBrush(QBrush(soft_g))
        painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

        # 5. Neural connections (depth-faded, thin local lines)
        n_pts = len(proj_pts_raw)
        conn_base_op = 90
        if state in ("PROCESSING", "THINKING", "EXECUTING"):
            conn_base_op = 125
        elif state == "SPEAKING":
            conn_base_op = int(90 * (1.0 + 0.35 * voice_level))

        for idx_i, idx_j, dist in self.connections:
            if idx_i >= n_pts or idx_j >= n_pts:
                continue
            pt_i = proj_pts_raw[idx_i]
            pt_j = proj_pts_raw[idx_j]
            
            # Depth sorting projection values for depth fade
            avg_z = (pt_i["z"] + pt_j["z"]) * 0.5
            z_n = max(0.0, min(1.0, (avg_z + 168.0) / 336.0))
            
            # Distance fade
            d_fade = max(0.0, 1.0 - dist / 20.0)
            
            # Opacity minimum is 35% of core connection base, scaling to 100% at front
            opacity = int(conn_base_op * (0.35 + 0.65 * z_n) * d_fade)
            if opacity < 8:
                continue
                
            color = "#ef4444" if state == "ERROR" else "#00d8ff"
            painter.setPen(self.get_pen(color, opacity, 0.45))
            painter.drawLine(int(pt_i["px"]), int(pt_i["py"]),
                             int(pt_j["px"]), int(pt_j["py"]))

        # 6. Combined rendering of depth-sorted particles, core segments, and shell segments back-to-front
        for prim in combined_prims:
            fz = prim["z"]
            z_n = max(0.0, min(1.0, (fz + 168.0) / 336.0))
            
            if prim["type"] == "particle":
                # Depth coefficients (maintain background visibility so the sphere is clear)
                depth_scale = 0.65 + 0.35 * z_n
                depth_opacity = 0.40 + 0.60 * z_n

                layer = prim["layer"]
                if layer == "core":
                    base_op = 240
                elif layer == "mid":
                    base_op = 190
                else:
                    base_op = 145

                opacity = int(base_op * depth_opacity)
                if state in ("SPEAKING", "EXECUTING", "PROCESSING"):
                    opacity = min(255, int(opacity * 1.25))

                col = "#ff3333" if state == "ERROR" else prim["col"]
                sz = prim["size"] * (0.85 + 0.15 * prim["sc"]) * depth_scale

                # Apply accent glowing node treatment
                if prim["is_accent"] and state != "ERROR":
                    glow_sz = sz * 2.5
                    half_glow = glow_sz * 0.5
                    glow_op = max(0, min(255, int(opacity * 0.32)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(self.get_brush(col, glow_op))
                    painter.drawEllipse(QRectF(prim["px"] - half_glow, prim["py"] - half_glow, glow_sz, glow_sz))

                    half = sz * 0.5
                    core_op = max(0, min(255, int(opacity * 0.95)))
                    painter.setBrush(self.get_brush(col, core_op))
                    painter.drawEllipse(QRectF(prim["px"] - half, prim["py"] - half, sz, sz))
                else:
                    # Standard particle
                    half = sz * 0.5
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(self.get_brush(col, max(0, min(255, opacity))))
                    painter.drawEllipse(QRectF(prim["px"] - half, prim["py"] - half, sz, sz))
                    
            elif prim["type"] == "core_seg":
                # Render central rotating 3D organic filament energy thread segment
                filament_color = "#ff3333" if state == "ERROR" else prim["col"]
                base_op = int(140 + 80 * p)
                if state == "SPEAKING":
                    base_op = int(base_op * (1.0 + 0.35 * voice_level))
                opacity = int(base_op * (0.35 + 0.65 * z_n))
                
                painter.setPen(self.get_pen(filament_color, opacity, 1.2))
                painter.drawLine(int(prim["px1"]), int(prim["py1"]),
                                 int(prim["px2"]), int(prim["py2"]))

            elif prim["type"] == "arc_seg":
                # Render 3D projected broken curved glass shell arc segment
                arc_color = "#ff3333" if state == "ERROR" else prim["col"]
                
                # Front-facing shell arcs stand out, back arcs fade
                opacity = int(70 * z_n)
                if opacity < 6:
                    continue
                
                # Double pass rendering for glowing outline sheen:
                painter.setPen(self.get_pen(arc_color, int(opacity * 0.35), 3.0))
                painter.drawLine(int(prim["px1"]), int(prim["py1"]),
                                 int(prim["px2"]), int(prim["py2"]))
                
                painter.setPen(self.get_pen(arc_color, opacity, 1.0))
                painter.drawLine(int(prim["px1"]), int(prim["py1"]),
                                 int(prim["px2"]), int(prim["py2"]))

        # 6. Error overlay
        if state == "ERROR":
            eg = QRadialGradient(cx, cy, 75)
            eg.setColorAt(0.0, self.get_color("#ff0000", int(90 * p)))
            eg.setColorAt(1.0, self.get_color("#ff0000", 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(eg))
            painter.drawEllipse(QRectF(cx - 75, cy - 75, 150, 150))

        # 7. Draw Custom Blocky Sci-Fi Neon Wordmark N.O.V.A. manually using lines
        char_w = 20
        char_h = 24
        gap = 10
        total_width = 8 * char_w + 7 * gap
        start_x = cx - total_width // 2
        start_y = h - 55

        glow_col = "#00f3ff" if state != "ERROR" else "#ff3333"
        core_col = "#ffffff" if state != "ERROR" else "#ffdddd"
        
        # Double-pass drawing:
        # Pass 1: Neon Cyan glow backdrop (with width offsets to simulate a blur bloom)
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2), (-1, 0), (1, 0), (0, -1), (0, 1)]:
            curr_x = start_x + dx
            curr_y = start_y + dy
            pen_glow = self.get_pen(glow_col, 45, 2.5)
            
            self.draw_vector_char(painter, 'N', curr_x, curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, '.', curr_x + char_w + gap, curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, 'O', curr_x + 2 * (char_w + gap), curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, '.', curr_x + 3 * (char_w + gap), curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, 'V', curr_x + 4 * (char_w + gap), curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, '.', curr_x + 5 * (char_w + gap), curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, 'A', curr_x + 6 * (char_w + gap), curr_y, char_w, char_h, pen_glow)
            self.draw_vector_char(painter, '.', curr_x + 7 * (char_w + gap), curr_y, char_w, char_h, pen_glow)

        # Pass 2: Crisp core white line
        pen_core = self.get_pen(core_col, 240, 1.8)
        self.draw_vector_char(painter, 'N', start_x, start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, '.', start_x + char_w + gap, start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, 'O', start_x + 2 * (char_w + gap), start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, '.', start_x + 3 * (char_w + gap), start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, 'V', start_x + 4 * (char_w + gap), start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, '.', start_x + 5 * (char_w + gap), start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, 'A', start_x + 6 * (char_w + gap), start_y, char_w, char_h, pen_core)
        self.draw_vector_char(painter, '.', start_x + 7 * (char_w + gap), start_y, char_w, char_h, pen_core)

        painter.end()

    def mouseDoubleClickEvent(self, event):
        if self.parent_gui and hasattr(self.parent_gui, "toggle_compact_mode"):
            self.parent_gui.toggle_compact_mode()
        event.accept()


# ---------------------------------------------------------------------------

class PermissionRequester(QObject):
    request_signal = pyqtSignal(str, dict, list)  # tool_name, args, result_container


class NovaGUIApp(QMainWindow):
    """Frameless translucent draggable desktop AI presence."""

    voice_command_received = pyqtSignal(str, str)
    telemetry_updated      = pyqtSignal(str)

    def __init__(self, engine: Any) -> None:
        super().__init__()
        if not PYQT6_AVAILABLE:
            raise RuntimeError("PyQt6 is required but not installed.")

        self.engine        = engine
        self.current_worker: Optional[NovaWorker] = None
        self.voice_state   = "IDLE"
        self.drag_position = QPoint()
        self.compact_mode  = False
        self._closed       = False
        self._voice_plugin_cache = None  # cached voice plugin reference for _poll_voice_state
        self._last_voice_state   = ""    # track last state to avoid redundant text calls
        self._state_timer: Optional[QTimer] = None  # initialized after init_ui()

        # Connect security permission callback safety gate
        self.permission_requester = PermissionRequester()
        self.permission_requester.request_signal.connect(
            self._handle_permission_request,
            Qt.ConnectionType.BlockingQueuedConnection
        )
        if hasattr(self.engine, "permission_gate") and self.engine.permission_gate:
            self.engine.permission_gate.set_callback(self.gui_permission_callback)

        self.init_ui()
        self._bind_voice_callback()
        self._position_bottom_right()

        # Start voice state polling timer (must be created after init_ui so Qt event loop is ready)
        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._poll_voice_state)
        self._state_timer.start(120)

    def gui_permission_callback(self, tool_name: str, args: dict[str, Any]) -> bool:
        # Check if the operation is a safe filesystem action that is already approved by the default callback
        if tool_name == "file_manager":
            action = args.get("action")
            if action in ("create_folder", "write", "list", "read"):
                return True

        result_container = [False]
        self.permission_requester.request_signal.emit(tool_name, args, result_container)
        return result_container[0]

    def _handle_permission_request(self, tool_name: str, args: dict, result_container: list) -> None:
        from PyQt6.QtWidgets import QMessageBox
        msg = f"Nova is requesting permission to run high-risk tool '{tool_name}' with arguments:\n{args}\n\nDo you want to allow this execution?"
        reply = QMessageBox.question(
            self,
            "Nova Security Permission",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        result_container[0] = (reply == QMessageBox.StandardButton.Yes)

    # Public aliases for backward compatibility with tests
    def init_ui(self) -> None:
        """Public alias for _init_ui (test compatibility)."""
        return self._init_ui()

    def dispatch_voice_command(self, text: str, response: str, telemetry: str = "") -> None:
        """Public alias for _dispatch_voice_command (test compatibility)."""
        if sip.isdeleted(self):
            return
        return self._dispatch_voice_command(text, response, telemetry)

    def set_voice_activity(self, level: float) -> None:
        """Sets the voice activity amplitude level (0.0 to 1.0) on the holographic core."""
        if hasattr(self, "_core") and self._core is not None:
            try:
                self._core.set_voice_activity(level)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        self.setWindowTitle("Nova AI Assistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(500, 560)

        root = QWidget()
        root.setObjectName("RootWidget")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 15, 0, 0)
        rl.setSpacing(4)
        self.setCentralWidget(root)

        self._core = NovaHolographicCore(self)
        self._core.setFixedSize(480, 420)
        rl.addWidget(self._core, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        self._panel = self._build_panel()
        rl.addWidget(self._panel, 1)

        self._apply_stylesheet()

    def _build_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("InfoPanel")
        lo = QHBoxLayout(panel)
        lo.setContentsMargins(16, 8, 16, 8)
        lo.setSpacing(12)

        # Left block: Title and Online Badge
        v_left = QVBoxLayout()
        v_left.setSpacing(2)
        h_title = QHBoxLayout()
        title = QLabel("NOVA AI")
        title.setObjectName("TitleLabel")
        self._status_badge = QLabel("● ONLINE")
        self._status_badge.setObjectName("StatusBadge")
        h_title.addWidget(title)
        h_title.addWidget(self._status_badge)
        h_title.addStretch()
        v_left.addLayout(h_title)

        self._state_label = QLabel("Waiting for wake word…")
        self._state_label.setObjectName("StateLabel")
        v_left.addWidget(self._state_label)
        lo.addLayout(v_left, 2)

        # Middle block: Last Command & Response
        v_mid = QVBoxLayout()
        v_mid.setSpacing(2)
        self._cmd_label = QLabel("Last Command: —")
        self._cmd_label.setObjectName("FieldValue")
        self._resp_label = QLabel("Response: All systems operational.")
        self._resp_label.setObjectName("FieldValue")
        v_mid.addWidget(self._cmd_label)
        v_mid.addWidget(self._resp_label)
        lo.addLayout(v_mid, 3)

        # Right block: Control buttons & Mic
        v_right = QVBoxLayout()
        v_right.setSpacing(4)
        self._mic_btn = QPushButton("🎤  Mic ON")
        self._mic_btn.setObjectName("MicBtn")
        self._mic_btn.clicked.connect(self._toggle_mic)

        h_ctrl = QHBoxLayout()
        min_btn = QPushButton("—")
        min_btn.setObjectName("ControlBtn")
        min_btn.setFixedSize(22, 22)
        min_btn.clicked.connect(self.showMinimized)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(22, 22)
        close_btn.clicked.connect(self.close)
        h_ctrl.addWidget(min_btn)
        h_ctrl.addWidget(close_btn)

        v_right.addWidget(self._mic_btn)
        v_right.addLayout(h_ctrl)
        lo.addLayout(v_right, 1)

        return panel

    @staticmethod
    def _header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FieldHeader")
        return lbl

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QWidget#RootWidget {
                background-color: rgba(4, 4, 12, 0.96);
                border: 1px solid rgba(6, 182, 212, 0.28);
                border-radius: 20px;
            }
            QFrame#InfoPanel {
                background-color: rgba(12, 12, 28, 0.7);
                border-top: 1px solid rgba(6, 182, 212, 0.2);
                border-radius: 0px;
                border-bottom-left-radius: 20px;
                border-bottom-right-radius: 20px;
            }
            QFrame#Separator {
                border: none;
                border-top: 1px solid rgba(255,255,255,0.06);
            }
            QLabel { color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QLabel#TitleLabel {
                font-size: 13px; font-weight: 800;
                color: #06b6d4; letter-spacing: 2px;
            }
            QLabel#StatusBadge {
                font-size: 9px; font-weight: bold; color: #34d399;
                padding: 1px 6px;
                background: rgba(16,185,129,0.12);
                border: 1px solid rgba(16,185,129,0.25);
                border-radius: 6px;
            }
            QLabel#StateLabel { font-size: 11px; color: #94a3b8; font-style: italic; }
            QLabel#FieldValue { font-size: 11px; color: #cbd5e1; }
            QPushButton#MicBtn {
                background: rgba(6,182,212,0.15);
                border: 1px solid rgba(6,182,212,0.30);
                border-radius: 6px; padding: 4px 10px;
                color: #22d3ee; font-size: 10px; font-weight: bold;
            }
            QPushButton#MicBtn:hover {
                background: rgba(6,182,212,0.28);
                border-color: rgba(6,182,212,0.55);
            }
            QPushButton#ControlBtn {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px; color: #94a3b8; font-size: 10px;
            }
            QPushButton#ControlBtn:hover { background: rgba(255,255,255,0.12); color: white; }
            QPushButton#CloseBtn {
                background: rgba(239,68,68,0.10);
                border: 1px solid rgba(239,68,68,0.20);
                border-radius: 4px; color: #f87171; font-size: 10px;
            }
            QPushButton#CloseBtn:hover {
                background: rgba(239,68,68,0.32);
                border-color: #ef4444; color: white;
            }
        """)

    # ------------------------------------------------------------------
    def _position_bottom_right(self) -> None:
        try:
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.width() - self.width() - 40,
                      screen.height() - self.height() - 80)
        except Exception:
            pass

    def toggle_compact_mode(self) -> None:
        self.compact_mode = not self.compact_mode
        if self.compact_mode:
            self._panel.hide()
            self._core.setFixedSize(480, 480)
            self.resize(500, 500)
        else:
            self._panel.show()
            self._core.setFixedSize(480, 420)
            self.resize(500, 560)
        self._position_bottom_right()

    # ------------------------------------------------------------------
    def _poll_voice_state(self) -> None:
        if sip.isdeleted(self) or self._closed:
            return
        try:
            # Use cached voice plugin reference to avoid searching plugin list every 120ms
            if self._voice_plugin_cache is None:
                plugins = []
                if hasattr(self.engine, "plugins"):
                    plugins = self.engine.plugins
                elif hasattr(self.engine, "engine") and hasattr(self.engine.engine, "plugins"):
                    plugins = self.engine.engine.plugins
                self._voice_plugin_cache = next(
                    (p for p in plugins if p.name == "voice"), None
                )

            voice_plugin = self._voice_plugin_cache
            if voice_plugin and voice_plugin.voice_manager:
                new_state = str(
                    getattr(voice_plugin.voice_manager, "state", "IDLE")
                ).upper()
            else:
                new_state = "IDLE"

            self.voice_state = new_state

            _msgs = {
                "IDLE":          "Waiting for wake word\u2026",
                "WAKING":        "Listening for 'Hey Nova'\u2026",
                "WAKE DETECTED": "Wake word detected \u2014 listening\u2026",
                "WAITING":       "Listening for your command\u2026",
                "LISTENING":     "Listening for your command\u2026",
                "PROCESSING":    "Processing command\u2026",
                "THINKING":      "Thinking\u2026",
                "EXECUTING":     "Executing command\u2026",
                "SPEAKING":      "Speaking response\u2026",
                "INITIALIZING":  "Initializing models\u2026 please wait.",
                "ERROR":         "An error occurred.",
            }

            # Only update label if state changed (avoid redundant Qt updates)
            if new_state != self._last_voice_state:
                self._last_voice_state = new_state
                if hasattr(self, "_state_label") and self._state_label is not None:
                    self._state_label.setText(_msgs.get(new_state, new_state))

                # Update holographic core state
                if hasattr(self, "_core") and self._core is not None:
                    try:
                        self._core.set_state(new_state)
                    except Exception:
                        pass

            from config import GEMINI_API_KEY
            api = "ONLINE" if GEMINI_API_KEY else "LOCAL"
            if hasattr(self, "_status_badge") and self._status_badge is not None:
                self._status_badge.setText(f"\u25cf {api}")

        except (RuntimeError, AttributeError):
            pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _bind_voice_callback(self) -> None:
        try:
            plugins = []
            if hasattr(self.engine, "plugins"):
                plugins = self.engine.plugins
            elif hasattr(self.engine, "engine") and hasattr(self.engine.engine, "plugins"):
                plugins = self.engine.engine.plugins

            voice_plugin = next(
                (p for p in plugins if p.name == "voice"), None
            )
            if voice_plugin and voice_plugin.voice_manager:
                # Use public method so tests patching dispatch_voice_command work correctly
                voice_plugin.voice_manager.on_command_callback = self.dispatch_voice_command
                self.voice_command_received.connect(self._handle_voice_command)
                self.telemetry_updated.connect(self._handle_telemetry)
        except Exception as exc:
            logger.warning("Could not bind voice callback: %s", exc)

    def _dispatch_voice_command(self, text: str, response: str, telemetry: str = "") -> None:
        if sip.isdeleted(self) or self._closed:
            return
        try:
            self.voice_command_received.emit(text, response)
            if telemetry:
                self.telemetry_updated.emit(telemetry)
        except RuntimeError:
            pass

    def _handle_voice_command(self, text: str, response: str) -> None:
        if sip.isdeleted(self) or self._closed:
            return
        try:
            if hasattr(self, "_cmd_label") and self._cmd_label is not None:
                self._cmd_label.setText(text[:120])
            if hasattr(self, "_resp_label") and self._resp_label is not None:
                display = response[:200] + ("\u2026" if len(response) > 200 else "")
                self._resp_label.setText(display)
        except (RuntimeError, AttributeError):
            pass

    def _handle_telemetry(self, telemetry: str) -> None:
        if sip.isdeleted(self) or self._closed:
            return
        try:
            if hasattr(self, "_telemetry_label") and self._telemetry_label is not None:
                self._telemetry_label.setText(telemetry)
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------
    def _toggle_mic(self) -> None:
        try:
            voice_plugin = next(
                (p for p in self.engine.plugins if p.name == "voice"), None
            )
            if not voice_plugin or not voice_plugin.voice_manager:
                return
            mgr = voice_plugin.voice_manager
            if mgr.is_active:
                mgr.stop()
                if hasattr(self, "_mic_btn"):
                    self._mic_btn.setText("\U0001f507  Mic OFF")
            else:
                mgr.voice_input_enabled = True
                mgr.start()
                if hasattr(self, "_mic_btn"):
                    self._mic_btn.setText("\U0001f3a4  Mic ON")
        except Exception as exc:
            logger.warning("Mic toggle error: %s", exc)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Gracefully and idempotently shut down all components, timers, and threads."""
        if self._closed:
            return
        self._closed = True
        logger.info("[Watchdog] Executing GUI App graceful shutdown...")

        # 1. Stop GUI QTimer
        try:
            if hasattr(self, "_state_timer") and self._state_timer.isActive():
                logger.info("[Watchdog] Stopping state timer...")
                self._state_timer.stop()
        except (RuntimeError, AttributeError) as e:
            logger.debug("Error stopping state timer: %s", e)

        # 2. Stop holographic visualizer core timer
        try:
            if hasattr(self, "_core") and self._core is not None:
                logger.info("[Watchdog] Stopping holographic core timer...")
                self._core.stop_timer()
        except (RuntimeError, AttributeError) as e:
            logger.debug("Error stopping core timer: %s", e)

        # 3. Stop current NovaWorker cleanly
        try:
            if getattr(self, "current_worker", None) is not None:
                worker = self.current_worker
                if worker.isRunning():
                    logger.info("[Watchdog] Stopping current NovaWorker...")
                    try:
                        worker.disconnect()
                    except Exception:
                        pass
                    worker.quit()
                    worker.wait(timeout=1000)
                    if worker.isRunning():
                        worker.terminate()
                        worker.wait()
                self.current_worker = None
        except Exception as e:
            logger.debug("Error cleaning up worker thread: %s", e)

        # 4. Stop AlwaysListeningEngine & VoiceManager cleanly
        try:
            plugins = []
            if hasattr(self.engine, "plugins"):
                plugins = self.engine.plugins
            elif hasattr(self.engine, "engine") and hasattr(self.engine.engine, "plugins"):
                plugins = self.engine.engine.plugins

            voice_plugin = next(
                (p for p in plugins if p.name == "voice"), None
            )
            if voice_plugin:
                logger.info("[Watchdog] Voice plugin found, shutting down...")
                if voice_plugin.voice_manager:
                    voice_plugin.voice_manager.on_command_callback = None
                    
                    if hasattr(voice_plugin.voice_manager, "always_listening") and voice_plugin.voice_manager.always_listening:
                        logger.info("[Watchdog] Stopping AlwaysListeningEngine...")
                        try:
                            voice_plugin.voice_manager.always_listening.stop()
                        except Exception as ale_err:
                            logger.error("Error stopping AlwaysListeningEngine: %s", ale_err)
                            
                    logger.info("[Watchdog] Stopping VoiceManager...")
                    try:
                        voice_plugin.voice_manager.stop()
                    except Exception as vm_err:
                        logger.error("Error stopping VoiceManager: %s", vm_err)
                
                try:
                    voice_plugin.shutdown()
                except Exception as vp_err:
                    logger.error("Error shutting down VoicePlugin: %s", vp_err)
        except Exception as e:
            logger.warning("Error stopping voice/listening components: %s", e)

        # 5. Quit QApplication
        try:
            app = QApplication.instance()
            if app:
                logger.info("[Watchdog] Quitting QApplication event loop...")
                app.quit()
        except Exception as e:
            logger.debug("Error quitting QApplication: %s", e)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle standard window close event by calling graceful shutdown."""
        self.shutdown()
        event.accept()

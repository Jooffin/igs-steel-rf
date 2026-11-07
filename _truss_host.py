# SPDX-License-Identifier: GPL-3.0-or-later
"""Truss axes in the host: the document block section, the viewport overlay,
the snap provider and pickables. Mirrors _grid_host but for truss segments.
Nothing here may raise into the host."""
from __future__ import annotations

import logging
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen, QVector3D

from ._grid_host import project
from ._i18n import tr
from ._truss import parse_trusses, new_truss_id

log = logging.getLogger("ingetrazo.plugins.igz_steel_rf")

COLOR = (0.20, 0.75, 0.70)              # teal: distinct from the orange grids
SEL_COLOR = (1.0, 0.85, 0.20)
DEFAULT_SNAP_PX = 12.0
PICK_PX = 6.0
_UNREAD = object()


def _qcolor(c=COLOR, alpha=1.0):
    return QColor.fromRgbF(c[0], c[1], c[2], alpha)


class TrussStore:
    def __init__(self, app):
        self.app = app
        self.trusses = []
        self.errors = []
        self.selected_id = None
        self._last_raw = _UNREAD
        self._overlay_failed = False
        self._snap_failed = False
        self._pick_failed = False
        self.reload()

    # -- data -----------------------------------------------------------------
    def reload(self):
        """Re-read the document trusses section. True when it changed."""
        try:
            raw = self.app.document_data({})
        except Exception:
            raw = {}
        if self._last_raw is not _UNREAD and raw == self._last_raw:
            return False
        items, errors = parse_trusses(raw.get("trusses") if isinstance(raw, dict) else None)
        self.trusses, self.errors = items, errors
        for e in self.errors:
            log.warning("igz_steel_rf trusses: %s", e)
        if self.selected_id and self.find(self.selected_id) is None:
            self.selected_id = None
        self._last_raw = raw
        try:
            vp = getattr(self.app, "viewport", None)
            if vp is not None:
                vp.update()
        except Exception:
            pass
        return True

    def save(self, trusses):
        """Write the trusses section (a merge - the grids and any other
        section of the plugin block survive). One host undo step."""
        cur = self.app.document_data({}) or {}
        if not isinstance(cur, dict):
            cur = {}
        cur = dict(cur)
        cur["trusses"] = trusses
        cur["trusses_version"] = 1
        self.app.set_document_data(cur)
        self.reload()

    def add(self, spec):
        spec = dict(spec)
        if not spec.get("id"):
            spec["id"] = new_truss_id(self.trusses)
        self.save(self.trusses + [spec])
        return spec

    def remove(self, tid):
        self.save([t for t in self.trusses if t.get("id") != tid])
        if self.selected_id == tid:
            self.selected_id = None

    def find(self, tid):
        for t in self.trusses:
            if t.get("id") == tid:
                return t
        return None

    # -- overlay --------------------------------------------------------------
    def paint(self, viewport, painter):
        if self._overlay_failed or not self.trusses:
            return
        try:
            self._paint(viewport, painter)
        except Exception:
            self._overlay_failed = True
            log.exception("igz_steel_rf trusses: overlay disabled after an error")

    def _paint(self, viewport, painter):
        clip = getattr(viewport, "_clip_pixel_line", None)
        for t in self.trusses:
            segs = _segments_cached(t)
            pts = [p for a, b, _k, _l in segs for p in (a, b)]
            px = project(self.app, viewport, pts)
            selected = t.get("id") == self.selected_id
            pen = QPen(_qcolor(SEL_COLOR if selected else COLOR, 0.95),
                       2.2 if selected else 1.4, Qt.SolidLine)
            painter.setPen(pen)
            for i, ((a, b, kind, _lbl)) in enumerate(segs):
                pa, pb = px[2 * i], px[2 * i + 1]
                if pa is None or pb is None:
                    continue
                if callable(clip):
                    c = clip(pa, pb, margin=0.0)
                    if c is None:
                        continue
                    pa, pb = c
                painter.drawLine(QPointF(pa[0], pa[1]), QPointF(pb[0], pb[1]))
            o = px[1] if len(px) > 1 else None    # left bottom chord endpoint
            if o is not None:
                painter.setPen(QPen(_qcolor(SEL_COLOR if selected else COLOR, 1.0)))
                painter.drawText(QPointF(o[0] - 6, o[1] - 10), str(t.get("name", "")))

    # -- snapping -------------------------------------------------------------
    def snap(self, viewport, snap, px, py):
        try:
            if not self.trusses:
                return None
            if px is None or py is None:
                point = getattr(snap, "point", None)
                if not isinstance(point, QVector3D):
                    return None
                here = project(self.app, viewport,
                               [(point.x(), point.y(), point.z())])[0]
                if here is None:
                    return None
                px, py = here
            threshold = float(getattr(viewport, "snap_threshold_px", DEFAULT_SNAP_PX)) * 1.5
            best = None                          # (d, world, label, node)
            for t in self.trusses:
                segs = _segments_cached(t)
                pts = [p for a, b, _k, _l in segs for p in (a, b)]
                pxy = project(self.app, viewport, pts)
                for i, ((a, b, _kind, lbl)) in enumerate(segs):
                    pa, pb = pxy[2 * i], pxy[2 * i + 1]
                    if pa is not None:
                        d = math.hypot(pa[0] - px, pa[1] - py)
                        if d <= threshold and (best is None or d < best[0] - 1e-6):
                            best = (d, a, f"{t.get('name', '')} \u00b7 {lbl}", True)
                    if pb is not None:
                        d = math.hypot(pb[0] - px, pb[1] - py)
                        if d <= threshold and (best is None or d < best[0] - 1e-6):
                            best = (d, b, f"{t.get('name', '')} \u00b7 {lbl}", True)
                    if pa is None or pb is None:
                        continue
                    vx, vy = pb[0] - pa[0], pb[1] - pa[1]
                    ln2 = vx * vx + vy * vy
                    if ln2 <= 1e-9:
                        continue
                    u = ((px - pa[0]) * vx + (py - pa[1]) * vy) / ln2
                    if not 0.05 <= u <= 0.95:
                        continue
                    d = math.hypot(pa[0] + u * vx - px, pa[1] + u * vy - py)
                    if d <= threshold and (best is None or d < best[0] - 1e-6):
                        w = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u,
                             a[2] + (b[2] - a[2]) * u)
                        best = (d, w, f"{t.get('name', '')} \u00b7 {lbl}", False)
            if best is None:
                return None
            from core.snap import SnapResult
            _d, w, label, _node = best
            return SnapResult(QVector3D(*w), "reference", COLOR, label=label)
        except Exception:
            if not self._snap_failed:
                self._snap_failed = True
                log.exception("igz_steel_rf trusses: snap provider error")
            return None

    # -- pickables ------------------------------------------------------------
    def pick(self, viewport, px, py):
        try:
            for t in self.trusses:
                segs = _segments_cached(t)
                pts = [p for a, b, _k, _l in segs for p in (a, b)]
                pxy = project(self.app, viewport, pts)
                for i, (_a, _b, _kind, _lbl) in enumerate(segs):
                    pa, pb = pxy[2 * i], pxy[2 * i + 1]
                    if pa is None or pb is None:
                        continue
                    if _dist_px(px, py, pa, pb) <= PICK_PX:
                        return t.get("id")
        except Exception:
            if not self._pick_failed:
                self._pick_failed = True
                log.exception("igz_steel_rf trusses: pick error")
        return None

    def on_select(self, item):
        self.selected_id = item
        t = self.find(item) if item else None
        flash = getattr(getattr(self.app, "viewport", None), "flash_status", None)
        if t is not None and callable(flash):
            try:
                flash(tr("Оси фермы «{name}»: {n} линий. Delete удаляет оси.").format(name=t.get("name", ""), n=len(_segments_cached(t))), 3000)
            except Exception:
                pass
        vp = getattr(self.app, "viewport", None)
        if vp is not None:
            try:
                vp.update()
            except Exception:
                pass

    def delete(self, item):
        if self.find(item) is not None:
            self.remove(item)

    def register(self):
        app = self.app
        for name, fn in (("add_overlay", self.paint), ("add_snap_provider", self.snap)):
            reg = getattr(app, name, None)
            if callable(reg):
                try:
                    reg(fn)
                except Exception:
                    log.exception("igz_steel_rf trusses: %s failed", name)
        reg = getattr(app, "add_pickable", None)
        if callable(reg):
            try:
                reg(pick=self.pick, on_select=self.on_select, delete=self.delete)
            except Exception:
                log.exception("igz_steel_rf trusses: add_pickable failed")


def _dist_px(px, py, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    ln2 = vx * vx + vy * vy
    if ln2 <= 1e-9:
        return math.hypot(px - a[0], py - a[1])
    u = max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / ln2))
    return math.hypot(a[0] + u * vx - px, a[1] + u * vy - py)


_SEG_CACHE = {}


def _segments_cached(spec):
    """Segments per truss spec, recomputed only when the spec dict changes."""
    key = spec.get("id")
    hit = _SEG_CACHE.get(key)
    if hit is not None and hit[0] == spec:
        return hit[1]
    from ._truss import segments as build
    try:
        segs = build(spec)
    except Exception:
        segs = []
    _SEG_CACHE[key] = (dict(spec), segs)
    return segs

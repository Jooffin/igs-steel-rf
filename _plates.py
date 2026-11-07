# SPDX-License-Identifier: GPL-3.0-or-later
"""End plates (косынки / торцевые пластины) for steel members.

The dialog picks the plate thickness and overall size (width x height) plus
small offsets; the tool asks for a click on the end of the member. The plate
is built as an exact box in the member's local frame — width along local y,
height along local z, thickness along the member axis — either just beyond
the clicked end (flush cap) or overlapping it inwards. The plate is a loose
group (IfcPlate) sharing the member's pose and layer; it is static geometry,
moved and deleted with the usual IngeTrazo tools.
"""
from __future__ import annotations

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QSpinBox, QVBoxLayout)

from tools.base import Tool

from . import KEY
from ._host import is_steel_group, member_endpoints, member_params
from ._tools import _dist2, _flash, _leave, xyz
from ._i18n import tr


def is_plate_group(group) -> bool:
    """A loose plate group placed by this extension."""
    block = (getattr(group, "ext", None) or {}).get(KEY)
    return isinstance(block, dict) and "plate" in block


class PlateDialog(QDialog):
    """Thickness / width / height / offsets for the plate to place."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Пластина на конце профиля"))
        form = QFormLayout()
        self.t = QSpinBox()
        self.t.setRange(1, 200)
        self.t.setValue(10)
        self.w = QSpinBox()
        self.w.setRange(10, 3000)
        self.w.setValue(200)
        self.h = QSpinBox()
        self.h.setRange(10, 3000)
        self.h.setValue(200)
        self.side = QComboBox()
        self.side.addItem(tr("за торцом (наружу)"))
        self.side.addItem(tr("по торцу (внутрь)"))
        self.off = QSpinBox()
        self.off.setRange(0, 1000)
        self.off.setValue(0)
        self.oy = QSpinBox()
        self.oy.setRange(-1500, 1500)
        self.oy.setValue(0)
        self.oz = QSpinBox()
        self.oz.setRange(-1500, 1500)
        self.oz.setValue(0)
        form.addRow(tr("Толщина пластины:"), self.t)
        form.addRow(tr("Ширина (по y):"), self.w)
        form.addRow(tr("Высота (по z):"), self.h)
        form.addRow(tr("Размещение:"), self.side)
        form.addRow(tr("Отступ от торца:"), self.off)
        form.addRow(tr("Смещение по ширине (y):"), self.oy)
        form.addRow(tr("Смещение по высоте (z):"), self.oz)
        hint = QLabel(tr("Кликните по концу стального профиля — пластина встанет\nперпендикулярно его оси: ширина — по y, высота — по z\n(локальные оси профиля), центр — на оси профиля + смещения."))
        hint.setStyleSheet("color: palette(mid)")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.on_apply = on_apply
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Установить"))
        cancel = buttons.button(QDialogButtonBox.Cancel)
        cancel.setText(tr("Закрыть") if on_apply is not None else tr("Отмена"))
        if on_apply is not None:
        	ok.clicked.connect(lambda: on_apply(self.spec()))
        else:
        	buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def spec(self) -> dict:
        return {"t": self.t.value() / 1000.0, "w": self.w.value() / 1000.0,
                "h": self.h.value() / 1000.0,
                "outward": self.side.currentIndex() == 0,
                "off": self.off.value() / 1000.0,
                "oy": self.oy.value() / 1000.0, "oz": self.oz.value() / 1000.0,
                "w_mm": self.w.value(), "h_mm": self.h.value(),
                "t_mm": self.t.value()}


def plate_frame(spec, end, length, cut=None):
    """(c, n, e1, e2): the plate centre point and its orthonormal frame in
    the member's local frame — n along the plate normal (thickness), e1 the
    width direction, e2 the height direction. With a mitre cut the frame is
    rotated by the cut and centred where the cut plane crosses the MEMBER
    AXIS (so the plate stays centred on the profile even when the cut is
    hinged on a face), offset along n by ``off`` and in-plane by oy/oz."""
    import math
    from ._cuts import IDENTITY, rotv, rotation
    R = rotation(cut) if cut else IDENTITY
    xp = float(length) if end == "finish" else 0.0
    if cut:
        ang = math.radians(float(cut.get("angle", 0.0)))
        if int(cut.get("dir", 1)) < 0:
            ang = -ang
        tan = math.tan(ang)                 # signed tilt, as in hole_positions
        hy = float(cut.get("hy", 0.0))
        hz = float(cut.get("hz", 0.0))
        if cut.get("axis", "z") == "z":
            anchor = (xp + hy * tan, 0.0, 0.0)
        else:
            anchor = (xp - hz * tan, 0.0, 0.0)
    else:
        anchor = (xp, 0.0, 0.0)
    n = rotv(R, (1.0, 0.0, 0.0))
    e1 = rotv(R, (0.0, 1.0, 0.0))           # width (w) direction
    e2 = rotv(R, (0.0, 0.0, 1.0))           # height (h) direction
    outward = 1.0 if end == "finish" else -1.0
    inward = 1.0 if spec.get("outward", True) else -1.0
    d = outward * inward * (spec.get("off", 0.0) + spec["t"] / 2.0)
    oy, oz = spec.get("oy", 0.0), spec.get("oz", 0.0)
    c = (anchor[0] + n[0] * d + e1[0] * oy + e2[0] * oz,
         anchor[1] + n[1] * d + e1[1] * oy + e2[1] * oz,
         anchor[2] + n[2] * d + e1[2] * oy + e2[2] * oz)
    return c, n, e1, e2


def plate_box_mesh(spec, c, n, e1, e2):
    """Exact watertight box for the plate at frame (c, n, e1, e2)."""
    from core.mesh import Mesh
    from core.orient import orient_outward
    t, w, h = spec["t"], spec["w"], spec["h"]
    hx, hy, hz = t / 2.0, w / 2.0, h / 2.0
    corners = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
               (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]
    pts = []
    for v in corners:
        pts.append(QVector3D(c[0] + v[0] * n[0] + v[1] * e1[0] + v[2] * e2[0],
                             c[1] + v[0] * n[1] + v[1] * e1[1] + v[2] * e2[1],
                             c[2] + v[0] * n[2] + v[1] * e1[2] + v[2] * e2[2]))
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6),
             (1, 2, 6, 5), (0, 4, 7, 3)]
    m = Mesh()
    for f in faces:
        m.add_face([pts[i] for i in f])
    orient_outward(m)
    return m


def plate_build(spec, end, length, cut=None):
    """Exact box mesh in the member's local frame: thickness t, width w,
    height h; with a mitre cut at that end the box lies on / parallel to
    the cut plane (see plate_frame)."""
    return plate_box_mesh(spec, *plate_frame(spec, end, length, cut))


# ------------------------------------------------------------ plate holes

class PlateHoleDialog(QDialog):
    """A centred row of holes drilled through the plate along its normal."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Отверстия в пластине"))
        form = QFormLayout()
        self.dia = QSpinBox()
        self.dia.setRange(4, 120)
        self.dia.setValue(18)
        self.dia.setSuffix(" мм")
        self.count = QSpinBox()
        self.count.setRange(1, 24)
        self.count.setValue(3)
        self.pitch = QSpinBox()
        self.pitch.setRange(10, 600)
        self.pitch.setValue(60)
        self.pitch.setSuffix(" мм")
        self.along = QComboBox()
        self.along.addItem(tr("по высоте пластины"))
        self.along.addItem(tr("по ширине пластины"))
        self.off = QSpinBox()
        self.off.setRange(-1500, 1500)
        self.off.setValue(0)
        self.off.setSuffix(" мм")
        self.edge = QSpinBox()
        self.edge.setRange(0, 500)
        self.edge.setValue(20)
        self.edge.setSuffix(" мм")
        form.addRow(tr("Диаметр отверстия:"), self.dia)
        form.addRow(tr("Количество:"), self.count)
        form.addRow(tr("Шаг:"), self.pitch)
        form.addRow(tr("Ряд идёт:"), self.along)
        form.addRow(tr("Смещение центра ряда:"), self.off)
        form.addRow(tr("Отступ от края пластины:"), self.edge)
        hint = QLabel(tr("Кликните по пластине — ряд отверстий просверлится насквозь\n(вдоль нормали пластины), ряд центрирован по пластине; при\nнаклонном резе конецa отверстия идут вместе с пластиной.\nОтступ проверяет, что ряд помещается с краями."))
        hint.setStyleSheet("color: palette(mid)")
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.on_apply = on_apply
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Применить"))
        cancel = buttons.button(QDialogButtonBox.Cancel)
        cancel.setText(tr("Закрыть") if on_apply is not None else tr("Отмена"))
        if on_apply is not None:
        	ok.clicked.connect(lambda: on_apply(self.spec()))
        else:
        	buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def spec(self) -> dict:
        return {"dia": self.dia.value() / 1000.0,
                "count": self.count.value(),
                "pitch": self.pitch.value() / 1000.0,
                "along": "h" if self.along.currentIndex() == 0 else "w",
                "off": self.off.value() / 1000.0,
                "edge": self.edge.value() / 1000.0,
                "segs": 24,
                "dia_mm": self.dia.value(), "pitch_mm": self.pitch.value(),
                "off_mm": self.off.value(), "edge_mm": self.edge.value()}


def plate_hole_positions(hs, w, h) -> list:
    """Hole centres in PLATE-PLANE coordinates (a along the width e1, b
    along the height e2), the row centred on the plate and stepped along
    the chosen direction; ``off`` shifts the row along the other axis."""
    n, pitch = int(hs["count"]), float(hs["pitch"])
    off = float(hs.get("off", 0.0))
    if hs.get("along", "h") == "w":
        return [((i - (n - 1) / 2.0) * pitch, off) for i in range(n)]
    return [(off, (i - (n - 1) / 2.0) * pitch) for i in range(n)]


def plate_hole_fit(hs, plate_spec) -> bool:
    """Every hole keeps at least ``edge`` clearance from the plate rim."""
    r = float(hs["dia"]) / 2.0
    edge = float(hs.get("edge", 0.0))
    w, h = float(plate_spec["w"]), float(plate_spec["h"])
    for (a, b) in plate_hole_positions(hs, w, h):
        if abs(a) + r > w / 2.0 - edge + 1e-9 or abs(b) + r > h / 2.0 - edge + 1e-9:
            return False
    return True


def plate_holed_mesh(plate_spec, hole_specs):
    """Plate box minus all hole cylinders (drilled along the stored plate
    normal) — ONE combined boolean, so stacked hole rows never degrade the
    rim welding. Returns a new core Mesh in the member's local frame."""
    import manifold3d as m3d
    from core.group import Group
    from core import solids
    from ._holes import _cyl_mesh
    fr = plate_spec.get("frame")
    if not fr:
        raise ValueError(tr("у пластины нет сохранённой рамки — установите пластину заново"))
    c, n, e1, e2 = fr["c"], fr["n"], fr["e1"], fr["e2"]
    base = plate_box_mesh(plate_spec, c, n, e1, e2)
    sources = solids._Sources()
    man = solids._to_manifold(Group(mesh=base), sources)
    span = 2.0 * max(float(plate_spec["w"]), float(plate_spec["h"]),
                     float(plate_spec["t"])) + 2.0
    w, h = float(plate_spec["w"]), float(plate_spec["h"])
    mans = []
    for hs in hole_specs:
        r = float(hs["dia"]) / 2.0
        segs = max(8, int(hs.get("segs", 24)))
        for (a, b) in plate_hole_positions(hs, w, h):
            ctr = (c[0] + e1[0] * a + e2[0] * b,
                   c[1] + e1[1] * a + e2[1] * b,
                   c[2] + e1[2] * a + e2[2] * b)
            cm = _cyl_mesh(ctr, n, r, span, segs)
            mans.append(solids._to_manifold(Group(mesh=cm), sources))
    if not mans:
        return base
    one = mans[0] if len(mans) == 1 else \
        m3d.Manifold.batch_boolean(mans, m3d.OpType.Add)
    res = man - one
    loops = solids._loops_from(res, sources)
    if not loops:
        raise ValueError(tr("вычитание не оставило материала"))
    return solids._group_from_loops(loops, sources, "", None).mesh


class PlateHoleTool(Tool):
    """One click on a plate drills the prepared row of holes through it."""

    name = tr("Вырезать отверстия в пластине")
    description = tr("Вырезать ряд отверстий в пластине расширения «Сталь РФ»: клик по пластине — отверстия насквозь вдоль её нормали.")
    uses_snap = False

    def __init__(self, spec, on_pick):
        self.spec = dict(spec)
        self.on_pick = on_pick

    def on_activate(self, viewport):
        d = self.spec
        _flash(viewport, tr("Отверстия Ø{dia} мм ×{count} в пластине: кликните по пластине  •  Esc — выход").format(dia=d["dia_mm"], count=d["count"]), 4000)

    def on_deactivate(self, viewport):
        pass

    def on_click(self, ctx):
        vp = ctx.viewport
        g = vp.pick_group(ctx.screen.x(), ctx.screen.y()) if hasattr(vp, "pick_group") else None
        if g is None or not is_plate_group(g):
            _flash(vp, tr("Кликните по пластине, установленной расширением «Сталь РФ»."), 2500)
            return
        if self.on_pick(g, self.spec):
            _leave(vp)

    def on_cancel(self, viewport):
        _leave(viewport)

    def status_clause(self):
        d = self.spec
        return tr("отверстия Ø{dia} мм ×{count} в пластине: клик  пластину  •  Esc  выход").format(dia=d["dia_mm"], count=d["count"])


# ------------------------------------------------------------ tool

class PlateTool(Tool):
    """One click on the end of a steel member places the plate there."""

    name = tr("Пластина на конце профиля")
    description = tr("Установить пластину (косынку) на конце стального профиля: клик по концу — пластина перпендикулярно оси профиля.")
    uses_snap = False

    def __init__(self, spec, on_pick):
        self.spec = dict(spec)
        self.on_pick = on_pick

    def on_activate(self, viewport):
        d = self.spec
        _flash(viewport, tr("Пластина {w}x{h}x{t} мм: кликните по концу стального профиля  •  Esc — выход").format(w=d["w_mm"], h=d["h_mm"], t=d["t_mm"]), 4000)

    def on_deactivate(self, viewport):
        pass

    def on_click(self, ctx):
        vp = ctx.viewport
        g = vp.pick_group(ctx.screen.x(), ctx.screen.y()) if hasattr(vp, "pick_group") else None
        if g is None or not is_steel_group(g):
            _flash(vp, tr("Кликните по стальному профилю, созданному расширением «Сталь РФ»."), 2500)
            return
        p0, p1 = member_endpoints(g)
        w = xyz(ctx.world)
        end = "start" if _dist2(w, p0) <= _dist2(w, p1) else "finish"
        if self.on_pick(g, end, self.spec):
            _leave(vp)

    def on_cancel(self, viewport):
        _leave(viewport)

    def status_clause(self):
        d = self.spec
        return tr("пластина {w}x{h}x{t} мм: клик  конец профиля  •  Esc  выход").format(w=d["w_mm"], h=d["h_mm"], t=d["t_mm"])

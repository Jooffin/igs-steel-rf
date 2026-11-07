# SPDX-License-Identifier: GPL-3.0-or-later
"""A row of bolt holes at the end of a member: dialog, CSG cut, click tool.

The cut is a solid subtraction in the member's LOCAL frame (manifold3d via
the host's own core.solids kernel), so the member group keeps its identity —
ext block, xform, layer, uid — and the extension's stretch/edit keep working:
the hole specs are stored in the ext block and re-applied on every rebuild.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout,
                               QWidget)

from tools.base import Tool

from ._host import is_steel_group, member_endpoints
from ._tools import _dist2, _flash, _leave, xyz
from ._i18n import tr

#: Cylinder axis in the member's local frame: u -> y, v -> z (see _geometry).
AXES = [("y", tr("через стенку (ось горизонтальна)")),
        ("z", tr("через полку (ось вертикальна)"))]

#: How the row of hole centres is laid out near the clicked end.
ROWS = [("along", tr("вдоль профиля (горизонтально)")),
        ("column", tr("столбцом у торца (вертикально)")),
        ("edge", tr("вдоль кромки реза (подрезка конца)"))]


# ------------------------------------------------------------ dialog

class HolesDialog(QDialog):
    """Diameter / pitch / count / edge distance for one row of holes.
    All in millimetres; the spec returned is in metres."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Отверстия на конце профиля"))
        form = QFormLayout()
        self.dia = self._spin(0.5, 500.0, 22.0)
        self.pitch = self._spin(1.0, 2000.0, 60.0)
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.count.setValue(3)
        self.edge = self._spin(0.0, 5000.0, 40.0)
        self.row = QComboBox()
        for _key, label in ROWS:
            self.row.addItem(label)
        self.axis = QComboBox()
        for _key, label in AXES:
            self.axis.addItem(label)
        self.off_u = self._spin(-2000.0, 2000.0, 0.0)
        self.off_v = self._spin(-2000.0, 2000.0, 0.0)
        self.segs = QSpinBox()
        self.segs.setRange(8, 128)
        self.segs.setValue(32)
        form.addRow(tr("Диаметр отверстия:"), self.dia)
        form.addRow(tr("Шаг ряда:"), self.pitch)
        form.addRow(tr("Количество:"), self.count)
        form.addRow(tr("Размещение ряда:"), self.row)
        form.addRow(tr("От конца до 1-го отверстия:"), self.edge)
        form.addRow(tr("Ось отверстий:"), self.axis)
        form.addRow(tr("Смещение u (по полке):"), self.off_u)
        form.addRow(tr("Смещение v (по высоте):"), self.off_v)
        form.addRow(tr("Сегментов окружности:"), self.segs)
        hint = QLabel(tr("После закрытия диалога кликните по нужному концу\nстального профиля — ряд отверстий вырежется от этого конца.\nСтолбец: отверстия складываются по высоте вокруг смещения v.\n«Вдоль кромки реза» — ряд идёт параллельно кромке угловой\nподрезки этого конца (сначала обрежьте конец под углом)."))
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

    @staticmethod
    def _spin(lo, hi, val):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(val)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        sp.setSuffix(" мм")
        return sp

    def spec(self) -> dict:
        return {"dia": self.dia.value() / 1000.0,
                "pitch": self.pitch.value() / 1000.0,
                "count": int(self.count.value()),
                "edge": self.edge.value() / 1000.0,
                "row": ROWS[self.row.currentIndex()][0],
                "axis": AXES[self.axis.currentIndex()][0],
                "off_u": self.off_u.value() / 1000.0,
                "off_v": self.off_v.value() / 1000.0,
                "segs": int(self.segs.value())}


def fit_ok(spec, length_m) -> bool:
    """Does the row still fit on the member (the far edge of the last hole)?"""
    n, pitch, edge = int(spec["count"]), float(spec["pitch"]), float(spec["edge"])
    row = spec.get("row", "along")
    if row == "column":
        span = edge
    else:  # along and edge: conservative upper bound along x
        span = edge + (n - 1) * pitch
    return spec["dia"] > 0.0 and span + spec["dia"] / 2.0 <= length_m + 1e-9


def row_in_section(spec, profile) -> bool:
    """Sanity: does the row footprint touch the profile bbox at all? A row
    entirely in the air (u/v offsets read against the WRONG side after a
    roll, or just mistyped) would cut nothing and then strand the bolt
    probe with a cryptic ray error - reject it at cut time instead."""
    u0, u1, v0, v1 = _bbox(profile)
    r = float(spec["dia"]) / 2.0
    ou, ov = float(spec.get("off_u", 0.0)), float(spec.get("off_v", 0.0))
    if spec.get("axis", "y") == "y":          # drill along y: footprint in v(z)
        if spec.get("row", "along") == "column":
            n, pitch = int(spec["count"]), float(spec["pitch"])
            lo, hi = ov - (n - 1) * pitch / 2.0 - r, ov + (n - 1) * pitch / 2.0 + r
        else:
            lo, hi = ov - r, ov + r
        return lo < v1 and hi > v0
    return ou - r < u1 and ou + r > u0        # drill along z: footprint in u(y)


# ------------------------------------------------------------ geometry

def hole_positions(spec, length_m, cut=None) -> list:
    """Local (x, y, z) hole centres. The row grows away from the chosen end;
    a column stands at one x near that end and stacks along v around off_v.

    A mitre cut at the end does NOT tilt the drill axis — the faces the
    holes pierce (web / flange) are untouched by the cut. Edge distance is
    measured from the point where the cut plane crosses the member axis, so
    a cut hinged on a face (top/bottom/left/right) shifts the whole row with
    the face. The third pattern, ``row == "edge"``, runs the row PARALLEL
    TO THE CUT EDGE: centres sit at edge distance from the cut edge line
    and step along it (the cut must exist at that end)."""
    n, pitch, edge = int(spec["count"]), float(spec["pitch"]), float(spec["edge"])
    ou, ov = float(spec.get("off_u", 0.0)), float(spec.get("off_v", 0.0))
    finish = spec.get("end", "start") == "finish"
    f = 1.0 if finish else -1.0
    xp = float(length_m) if finish else 0.0
    row = spec.get("row", "along")
    if cut:
        import math
        ang = math.radians(float(cut.get("angle", 0.0)))
        if int(cut.get("dir", 1)) < 0:
            ang = -ang
        tan, cos = math.tan(ang), math.cos(ang)   # tan carries the tilt sign
        hy, hz = float(cut.get("hy", 0.0)), float(cut.get("hz", 0.0))
        if cut.get("axis", "z") == "z":
            x_face = lambda y: xp - (y - hy) * tan
            xp0 = xp + hy * tan
        else:
            x_face = lambda z: xp + (z - hz) * tan
            xp0 = xp - hz * tan
        # a hinge/direction pair can leave the cut plane OUTSIDE the material
        # (the cut is then a no-op): the row must grow from the real end, not
        # from a phantom plane beyond it
        lim = (lambda x: min(x, xp)) if finish else (lambda x: max(x, 0.0))
        xp0 = lim(xp0)
        if row == "edge":
            if cut.get("axis", "z") == "z":
                x = lim(x_face(ou)) - f * edge * cos
                return [(x, ou, ov + i * pitch) for i in range(n)]
            pts = []
            for i in range(n):
                z = ov + i * pitch * cos
                pts.append((lim(x_face(z)) - f * edge * cos, ou, z))
            return pts
        if row == "column":
            return [(xp0 - f * edge, ou, ov + (i - (n - 1) / 2.0) * pitch)
                    for i in range(n)]
        return [(xp0 - f * (edge + i * pitch), ou, ov) for i in range(n)]
    if row == "column":
        x = length_m - edge if finish else edge
        return [(x, ou, ov + (i - (n - 1) / 2.0) * pitch) for i in range(n)]
    if finish:
        return [(length_m - edge - i * pitch, ou, ov) for i in range(n)]
    return [(edge + i * pitch, ou, ov) for i in range(n)]


def _cyl_mesh(center, axis, r, span, segs):
    """A watertight cylinder: segs side quads + two cap n-gons, along the
    unit axis (either the "y"/"z" key or an explicit (x, y, z) vector — a
    mitre-cut end rotates the drill axis with the hole row)."""
    from core.mesh import Mesh
    from core.orient import orient_outward
    if axis == "y":
        a = (0.0, 1.0, 0.0)
    elif axis == "z":
        a = (0.0, 0.0, 1.0)
    else:
        a = axis
    from ._cuts import frame
    e1, e2 = frame(a)
    cx, cy, cz = center
    half = span / 2.0
    top, bot = [], []
    for i in range(segs):
        th = 2.0 * math.pi * i / segs
        c, s = r * math.cos(th), r * math.sin(th)
        px = cx + c * e1[0] + s * e2[0]
        py = cy + c * e1[1] + s * e2[1]
        pz = cz + c * e1[2] + s * e2[2]
        top.append(QVector3D(px + a[0] * half, py + a[1] * half, pz + a[2] * half))
        bot.append(QVector3D(px - a[0] * half, py - a[1] * half, pz - a[2] * half))
    mesh = Mesh()
    mesh.add_face(top)
    mesh.add_face(list(reversed(bot)))
    for i in range(segs):
        j = (i + 1) % segs
        mesh.add_face([top[i], top[j], bot[j], bot[i]])
    orient_outward(mesh)
    return mesh


def _bbox(profile):
    us = [p[0] for reg in profile.regions for p in reg.outer.points]
    vs = [p[1] for reg in profile.regions for p in reg.outer.points]
    return min(us), max(us), min(vs), max(vs)


def _hole_cutters(specs, length_m, profile, cuts, include_cuts, sources):
    """All subtracted solids (hole cylinders + mitre half-spaces) for one
    combined boolean. Kept out of both entry points so the mesh and the
    manifold variants cannot drift apart."""
    from core.group import Group
    from core import solids
    u0, u1, v0, v1 = _bbox(profile)
    mans_c = []
    for spec in specs:
        r = float(spec["dia"]) / 2.0
        segs = max(8, int(spec.get("segs", 32)))
        cut = None
        for c in cuts or []:
            if c.get("end") == spec.get("end", "start"):
                cut = c
                break
        base_axis = spec.get("axis", "y")
        span = 2.0 * (float(length_m) + 2.0 * max(u1, -u0, v1, -v0) + 1.0)
        for (xc, cy, cz) in hole_positions(spec, float(length_m), cut):
            cm = _cyl_mesh((xc, cy, cz), base_axis, r, span, segs)
            mans_c.append(solids._to_manifold(Group(mesh=cm), sources))
    if include_cuts and cuts:
        from ._cuts import cutter_manifold, profile_reach
        reach = profile_reach(profile, float(length_m))
        for cut in cuts:
            mans_c.append(cutter_manifold(cut, float(length_m), reach))
    return mans_c


def cut_holes_manifold(mesh, specs, length_m, profile, cuts=None, include_cuts=False,
                       extra_mans=None):
    """Same boolean as ``cut_holes`` but returns the manifold3d result (or
    None when nothing would be subtracted). The bolt seating probe reads the
    member through this: a hole rim grazing a mitre face can make the core
    Mesh loop round-trip lossy, while the manifold stays exact."""
    import manifold3d as m3d
    from core.group import Group
    from core import solids
    man_m = solids._to_manifold(Group(mesh=mesh), solids._Sources())
    mans_c = _hole_cutters(specs, length_m, profile, cuts, include_cuts,
                           solids._Sources())
    if extra_mans:
        mans_c.extend(extra_mans)
    if not mans_c:
        return None
    man_c = mans_c[0] if len(mans_c) == 1 else \
        m3d.Manifold.batch_boolean(mans_c, m3d.OpType.Add)
    return man_m - man_c


def cut_holes(mesh, specs, length_m, profile, cuts=None, include_cuts=False,
             extra_mans=None):
    """member mesh (local frame) minus all hole cylinders of all specs (and,
    with ``include_cuts``, also the mitre half-spaces — one combined boolean,
    because chained sequential booleans corrupt the loop welding of rotated
    hole rims). ``cuts`` (the member's stored end cuts) rotate the pattern
    and drill axis of any spec whose end carries a mitre. Returns a new core
    Mesh; raises on failure."""
    import manifold3d as m3d
    from core.group import Group
    from core import solids
    sources = solids._Sources()
    member_g = Group(mesh=mesh)
    man_m = solids._to_manifold(member_g, sources)
    mans_c = _hole_cutters(specs, length_m, profile, cuts, include_cuts, sources)
    if extra_mans:
        mans_c.extend(extra_mans)
    if not mans_c:
        return mesh
    man_c = mans_c[0] if len(mans_c) == 1 else \
        m3d.Manifold.batch_boolean(mans_c, m3d.OpType.Add)
    res = man_m - man_c
    loops = solids._loops_from(res, sources)
    if not loops:
        raise ValueError(tr("вычитание не оставило материала"))
    return solids._group_from_loops(loops, sources, "", None).mesh


# ------------------------------------------------------------ tool

class CutHolesTool(Tool):
    """One click on the end of a steel member cuts the prepared row of holes."""

    name = tr("Вырезать отверстия в профиле")
    description = tr("Вырезать ряд отверстий на конце стального профиля: клик по концу — отверстия вырежутся от этого конца.")
    uses_snap = False

    def __init__(self, spec, on_pick):
        self.spec = dict(spec)
        self.on_pick = on_pick

    def on_activate(self, viewport):
        d = self.spec
        mode = tr("столбец") if d.get("row") == "column" else tr("ряд")
        _flash(viewport, tr("Ø{dia:g} мм, {mode} {count} шт, шаг {pitch:g} мм: кликните по концу стального профиля  •  Esc — выход").format(dia=d["dia"] * 1000, mode=mode, count=d["count"], pitch=d["pitch"] * 1000), 4000)

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
        spec = dict(self.spec)
        spec["end"] = "start" if _dist2(w, p0) <= _dist2(w, p1) else "finish"
        if self.on_pick(g, spec):
            _leave(vp)

    def on_cancel(self, viewport):
        _leave(viewport)

    def status_clause(self):
        d = self.spec
        mode = {"column": tr("столбец"), "edge": tr("вдоль реза")}.get(d.get("row"), tr("ряд"))
        return tr("Ø{dia:g} мм, {mode} {count} шт: клик  конец профиля  •  Esc  выход").format(dia=d["dia"] * 1000, mode=mode, count=d["count"])

# SPDX-License-Identifier: GPL-3.0-or-later
"""Mitre (angled) end cuts for steel members.

A cut is stored in the member's ext block (``cuts``: one entry per end) and
applied as a solid subtraction in the member's LOCAL frame — the same CSG
path the hole rows use — so stretch, edit and undo keep working and every
rebuild re-cuts the stored angles.

The cut plane passes through the point where the member axis meets that end;
it is turned by the chosen angle around the local z (tilt seen in plan) or
local y (tilt seen in elevation) axis, to either side. Everything placed at
a cut end — hole rows, plates — is rotated by the same rotation around the
same pivot, so rows run parallel to the cut edge and plates lie on the cut
face. Bolt seating faces are found by ray casting along the (unchanged)
drill axis, so bolts keep sitting flush on the real faces of the trimmed
member.
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QLabel, QVBoxLayout)

from tools.base import Tool

from ._host import is_steel_group, member_endpoints
from ._tools import _dist2, _flash, _leave, xyz
from ._i18n import tr

#: Axis the cut plane is rotated around (see the module docstring).
CUT_AXES = [("z", tr("вокруг z — наклон в плане (угол виден сверху)")),
            ("y", tr("вокруг y — наклон в фасад (угол виден сбоку)"))]

#: Hinge face the cut plane pivots on (instead of the section centre).
#: left/right tilt the plan cuts (around z), top/bottom the elevation ones
#: (around y); the resolved offset (hy, hz) is stored from the profile bbox.
HINGES = [("center", tr("центр сечения")),
          ("top", tr("верхняя грань (+z)")),
          ("bottom", tr("нижняя грань (−z)")),
          ("left", tr("левая сторона (−y)")),
          ("right", tr("правая сторона (+y)"))]

IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def end_cut(params, end):
    """The stored cut spec for the given end ("start"/"finish"), or None."""
    for c in (params or {}).get("cuts") or []:
        if c.get("end") == end:
            return c
    return None


def rotation(cut):
    """Row-major 3x3 rotation of the cut (identity when cut is None/0°)."""
    if not cut:
        return IDENTITY
    ang = math.radians(float(cut.get("angle", 0.0)))
    if int(cut.get("dir", 1)) < 0:
        ang = -ang
    c, s = math.cos(ang), math.sin(ang)
    if cut.get("axis", "z") == "z":
        return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rotv(R, v):
    return (R[0][0] * v[0] + R[0][1] * v[1] + R[0][2] * v[2],
            R[1][0] * v[0] + R[1][1] * v[1] + R[1][2] * v[2],
            R[2][0] * v[0] + R[2][1] * v[1] + R[2][2] * v[2])


def _norm(a):
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (a[0] / n, a[1] / n, a[2] / n) if n else a


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def frame(a):
    """Orthonormal (e1, e2) perpendicular to the unit axis a."""
    ref = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_cross(ref, a))
    return e1, _cross(a, e1)


def rot_from_z_to(a):
    """Row-major rotation taking +z onto the unit vector a."""
    if a[2] > 0.999999:
        return IDENTITY
    if a[2] < -0.999999:
        return ((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0))
    u = _norm((-a[1], a[0], 0.0))            # z x a
    c = max(-1.0, min(1.0, a[2]))
    th = math.acos(c)
    s, k = math.sin(th), 1.0 - c
    ux, uy, uz = u
    return ((k * ux * ux + c, k * ux * uy - s * uz, k * ux * uz + s * uy),
            (k * ux * uy + s * uz, k * uy * uy + c, k * uy * uz - s * ux),
            (k * ux * uz - s * uy, k * uy * uz + s * ux, k * uz * uz + c))


def pivot_of(end, length_m, hy=0.0, hz=0.0):
    """The cut plane's pivot: on the member axis at the clicked end, offset
    to the chosen hinge face (hy across y, hz across z — resolved once from
    the profile's bounding box when the cut is stored)."""
    xp = float(length_m) if end == "finish" else 0.0
    return (xp, float(hy), float(hz))


def cut_pivot(cut, length_m):
    return pivot_of(cut.get("end", "finish"), length_m,
                    float(cut.get("hy", 0.0)), float(cut.get("hz", 0.0)))


def rotate_about_pivot(R, pivot, p):
    q = rotv(R, (p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]))
    return (pivot[0] + q[0], pivot[1] + q[1], pivot[2] + q[2])


def profile_reach(profile, length_m):
    """A box edge long enough to cover the whole member from any cut pivot."""
    us = [p[0] for reg in profile.regions for p in reg.outer.points]
    vs = [p[1] for reg in profile.regions for p in reg.outer.points]
    return 2.0 * (float(length_m) + 2.0 * max(max(us), -min(us), max(vs), -min(vs), 1.0) + 1.0)


def cutter_manifold(cut, length_m, reach):
    """Half-space box beyond the cut plane (built at the origin, then posed):
    x in [0, reach] rotated around y/z and moved to the end's pivot, so its
    inner face IS the cut plane and it reaches over the whole member."""
    import manifold3d as m3d
    ang = math.radians(float(cut.get("angle", 0.0)))
    if int(cut.get("dir", 1)) < 0:
        ang = -ang
    deg = math.degrees(ang)
    end = cut.get("end", "finish")
    if end == "start":
        deg += 180.0          # the box must reach to the -x side
    h = reach / 2.0
    cs = m3d.CrossSection([[(0.0, -h), (reach, -h), (reach, h), (0.0, h)]])
    man = cs.extrude(reach).translate((0.0, 0.0, -h))
    axis = cut.get("axis", "z")
    euler = (0.0, 0.0, deg) if axis == "z" else (0.0, deg, 0.0)
    return man.rotate(euler).translate(cut_pivot(cut, length_m))


def cut_ends(mesh, cuts, length_m, profile):
    """member mesh (local frame) minus the half-space beyond every cut plane.
    Returns a new core Mesh; raises on boolean failure."""
    from core.group import Group
    from core import solids
    if not cuts:
        return mesh
    reach = profile_reach(profile, length_m)
    sources = solids._Sources()
    man_m = solids._to_manifold(Group(mesh=mesh), sources)
    mans = [cutter_manifold(cut, float(length_m), reach) for cut in cuts]
    man_c = mans[0] if len(mans) == 1 else m3d_union(mans)
    res = man_m - man_c
    loops = solids._loops_from(res, sources)
    if not loops:
        raise ValueError(tr("подрезка не оставила материала"))
    return solids._group_from_loops(loops, sources, "", None).mesh


def m3d_union(mans):
    import manifold3d as m3d
    return m3d.Manifold.batch_boolean(mans, m3d.OpType.Add)


# ------------------------------------------------------------ dialog

class CutDialog(QDialog):
    """Angle / rotation axis / tilt direction for one end cut."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Обрезать конец под углом"))
        form = QFormLayout()
        self.action = QComboBox()
        self.action.addItem(tr("Обрезать конец"))
        self.action.addItem(tr("Вернуть прямой торец"))
        self.angle = QDoubleSpinBox()
        self.angle.setRange(0.1, 85.0)
        self.angle.setValue(45.0)
        self.angle.setDecimals(1)
        self.angle.setSingleStep(5.0)
        self.angle.setSuffix(" °")
        self.axis = QComboBox()
        for _key, label in CUT_AXES:
            self.axis.addItem(label)
        self.dir = QComboBox()
        self.dir.addItem(tr("в сторону +y / +z"))
        self.dir.addItem(tr("в сторону −y / −z"))
        self.hinge = QComboBox()
        for _key, label in HINGES:
            self.hinge.addItem(label)
        form.addRow(tr("Действие:"), self.action)
        form.addRow(tr("Угол реза:"), self.angle)
        form.addRow(tr("Ось поворота реза:"), self.axis)
        form.addRow(tr("Направление наклона:"), self.dir)
        form.addRow(tr("Опора реза (ось поворота):"), self.hinge)
        hint = QLabel(tr("Кликните по концу стального профиля — его торец срежется\nплоскостью под заданным углом. Опора реза — грань, вокруг\nкоторой поворачивается плоскость: для наклона в фасад —\nверх/низ элемента, для наклона в план — левая/правая\nсторона («центр сечения» — как раньше, через ось).\nОтверстия, пластины и болты на этом конце размещаются\nпараллельно отрезу. «Вернуть прямой торец» снимает обрезку."))
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
        self.action.currentIndexChanged.connect(
            lambda _i: (self.angle.setEnabled(self.action.currentIndex() == 0),
                        self.axis.setEnabled(self.action.currentIndex() == 0),
                        self.dir.setEnabled(self.action.currentIndex() == 0),
                        self.hinge.setEnabled(self.action.currentIndex() == 0)))

    def spec(self) -> dict:
        return {"action": "cut" if self.action.currentIndex() == 0 else "restore",
                "angle": float(self.angle.value()),
                "axis": CUT_AXES[self.axis.currentIndex()][0],
                "dir": 1 if self.dir.currentIndex() == 0 else -1,
                "hinge": HINGES[self.hinge.currentIndex()][0]}


# ------------------------------------------------------------ tool

class CutEndTool(Tool):
    """One click on the end of a steel member cuts (or restores) that end."""

    name = tr("Обрезать конец профиля под углом")
    description = tr("Срезать торец стального профиля под углом: клик по концу — плоскость реза проходит через ось профиля на этом конце.")
    uses_snap = False

    def __init__(self, spec, on_pick):
        self.spec = dict(spec)
        self.on_pick = on_pick

    def on_activate(self, viewport):
        d = self.spec
        if d["action"] == "cut":
            axis_word = tr("вокруг z") if d["axis"] == "z" else tr("вокруг y")
            _flash(viewport, tr("Рез {angle:g}° ({axis}): кликните по концу стального профиля  •  Esc — выход").format(angle=d["angle"], axis=axis_word), 4000)
        else:
            _flash(viewport, tr("Кликните по концу профиля, чтобы вернуть ему прямой торец  •  Esc — выход"), 4000)

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
        if d["action"] == "restore":
            return tr("прямой торец: клик  конец профиля  •  Esc  выход")
        return tr("рез {angle:g}°: клик  конец профиля  •  Esc  выход").format(angle=d["angle"])

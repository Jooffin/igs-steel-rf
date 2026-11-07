# SPDX-License-Identifier: GPL-3.0-or-later
"""Bolts (DIN / GOST) into the hole rows cut at a member end.

The dialog picks the fastener family, size, length, and how many washers and
nuts; the tool then asks for a click on the end of the member. Every hole row
stored in the member's ext block at that end gets a bolt: the bolt axis is the
hole axis, the seating faces are found by a ray cast through the hole, and the
head / washer stack / nut stack sit outside the material. Threads and fillets
are not modelled (a deliberate simplification); the hex head, washer rings and
hex nuts are exact prisms per the standard dimensions.

Dimensions are catalogue values: DIN 931/933 (ISO 4014/4017) hex bolts,
DIN 934 / GOST 5915-70 hex nuts (ISO 4032 heights), DIN 125 / ISO 7089 flat
washers (GOST 11371 is the close GOST analogue). Two wrench series are
offered: the modern ISO/DIN one (16/18/36 for M10/M12/M24) and the old
DIN/GOST series (17/19 for M10/M12).
"""
from __future__ import annotations

import math

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QSpinBox, QVBoxLayout)

from tools.base import Tool

from ._holes import hole_positions
from ._host import is_steel_group, member_endpoints
from ._tools import _dist2, _flash, _leave, xyz
from ._i18n import tr

SIZES = ["M6", "M8", "M10", "M12", "M16", "M20", "M24", "M30"]
D_MM = {"M6": 6.0, "M8": 8.0, "M10": 10.0, "M12": 12.0,
        "M16": 16.0, "M20": 20.0, "M24": 24.0, "M30": 30.0}
K_MM = {"M6": 4.0, "M8": 5.3, "M10": 6.4, "M12": 7.5,
        "M16": 10.0, "M20": 12.5, "M24": 15.0, "M30": 18.7}     # head height
NUT_M = {"M6": 5.0, "M8": 6.5, "M10": 8.0, "M12": 10.0,
         "M16": 13.0, "M20": 16.0, "M24": 19.0, "M30": 24.0}    # DIN 934
WASH = {"M6": (6.6, 12.0, 1.6), "M8": (9.0, 16.0, 1.6), "M10": (10.5, 20.0, 2.0),
        "M12": (13.0, 24.0, 2.5), "M16": (17.0, 30.0, 3.0), "M20": (21.0, 37.0, 3.5),
        "M24": (24.0, 39.0, 4.0), "M30": (30.0, 56.0, 4.0)}     # d1, d2, h
SW_NEW = {"M6": 10.0, "M8": 13.0, "M10": 16.0, "M12": 18.0,
          "M16": 24.0, "M20": 30.0, "M24": 36.0, "M30": 46.0}
SW_OLD = {"M6": 10.0, "M8": 14.0, "M10": 17.0, "M12": 19.0,
          "M16": 24.0, "M20": 30.0, "M24": 36.0, "M30": 46.0}
L_MM = {
    "M6": [12, 16, 20, 25, 30, 35, 40, 45, 50, 60],
    "M8": [12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80],
    "M10": [16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100],
    "M12": [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120],
    "M16": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120,
            140, 150, 160, 180, 200],
    "M20": [30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 140,
            150, 160, 180, 200],
    "M24": [40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 120, 140, 150, 160, 180,
            200, 220, 240, 260, 280, 300],
    "M30": [45, 50, 55, 60, 70, 80, 90, 100, 110, 120, 140, 150, 160, 180,
            200, 220, 240, 260, 280, 300],
}
L_DEFAULT = {"M6": 30, "M8": 30, "M10": 40, "M12": 40,
             "M16": 60, "M20": 80, "M24": 100, "M30": 120}
FAMILIES = [("new", "DIN 931/933 · ISO (новый ряд ключей: 16/18/36)"),
            ("old", "DIN 934 old · ГОСТ 5915-70 (старый ряд: 14/17/19)")]


# ------------------------------------------------------------ dialog

class BoltDialog(QDialog):
    """Family / size / length / washer & nut counts for the bolts to insert."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Болты в отверстия на конце профиля"))
        form = QFormLayout()
        self.family = QComboBox()
        for _key, label in FAMILIES:
            self.family.addItem(tr(label))
        self.size = QComboBox()
        self.size.addItems(SIZES)
        self.length = QComboBox()
        self._fill_lengths()
        self.size.currentIndexChanged.connect(self._fill_lengths)
        self.wh = QSpinBox()
        self.wh.setRange(0, 2)
        self.wh.setValue(1)
        self.wn = QSpinBox()
        self.wn.setRange(0, 2)
        self.wn.setValue(1)
        self.nuts = QSpinBox()
        self.nuts.setRange(1, 3)
        self.nuts.setValue(1)
        self.head = QComboBox()
        self.head.addItem(tr("+y / +z (по умолчанию)"))
        self.head.addItem(tr("−y / −z (напротив)"))
        self.maxb = QSpinBox()
        self.maxb.setRange(0, 100)
        self.maxb.setValue(0)
        self.maxb.setSpecialValueText(tr("все отверстия"))
        self.segs = QComboBox()
        for n in (16, 24, 32, 48):
            self.segs.addItem(str(n))
        self.segs.setCurrentText("24")
        form.addRow(tr("Стандарт:"), self.family)
        form.addRow(tr("Резьба:"), self.size)
        form.addRow(tr("Длина болта:"), self.length)
        form.addRow(tr("Шайб под головку:"), self.wh)
        form.addRow(tr("Шайб под гайку:"), self.wn)
        form.addRow(tr("Гаек:"), self.nuts)
        form.addRow(tr("Сторона головки:"), self.head)
        form.addRow(tr("Максимум болтов:"), self.maxb)
        form.addRow(tr("Сегментов окружности:"), self.segs)
        hint = QLabel(tr("Кликните по концу профиля — болты встанут в вырезанные\nотверстия этого конца (сначала прорежьте отверстия).\nСторона головки — в локальных осях профиля (y — ширина,\nz — высота). Резьба и скругления не моделируются."))
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

    def _fill_lengths(self):
        size = self.size.currentText()
        cur = L_DEFAULT.get(size)
        self.length.clear()
        for mm in L_MM[size]:
            self.length.addItem(tr("{mm} мм").format(mm=mm), mm)
        idx = L_MM[size].index(cur) if cur in L_MM[size] else 0
        self.length.setCurrentIndex(idx)

    def spec(self) -> dict:
        return {"family": FAMILIES[self.family.currentIndex()][0],
                "size": self.size.currentText(),
                "L": self.length.currentData() / 1000.0,
                "wh": int(self.wh.value()), "wn": int(self.wn.value()),
                "nuts": int(self.nuts.value()),
                "head_side": 1 if self.head.currentIndex() == 0 else -1,
                "max": int(self.maxb.value()),
                "segs": int(self.segs.currentText())}


# ------------------------------------------------------------ geometry

def _neg(a):
    return (-a[0], -a[1], -a[2])


def _add(p, q, s=1.0):
    return (p[0] + s * q[0], p[1] + s * q[1], p[2] + s * q[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    return (a[0] / n, a[1] / n, a[2] / n) if n else a


def _frame(a):
    """Orthonormal (e1, e2) perpendicular to the unit axis a."""
    ref = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _norm(_cross(ref, a))
    return e1, _cross(a, e1)


def _circle_pts(r, segs):
    return [(r * math.cos(2 * math.pi * i / segs),
             r * math.sin(2 * math.pi * i / segs)) for i in range(segs)]


def _hex_pts(sw):
    rr = sw / math.sqrt(3.0)
    return [(rr * math.cos(math.pi / 6 + math.pi * i / 3),
             rr * math.sin(math.pi / 6 + math.pi * i / 3)) for i in range(6)]


_RHO = 7850.0


def fastener_parts(spec):
    """Per-part breakdown of one bolt assembly for the BOM:
    ``[(label, mass_kg, qty), …]`` — bolt / nut / washer counted and weighed
    separately. Masses are analytic from the SAME catalogue dimensions the
    model is built with (hex head across flats, cylindrical shank, hex nut
    with bore, annular washer); thread, chamfers and fillets are not
    modelled, so these are model-consistent approximations."""
    mm = str(spec["size"])
    sw_map = SW_NEW if spec.get("family", "new") == "new" else SW_OLD
    d = D_MM[mm] / 1000.0
    sw = sw_map[mm] / 1000.0
    k = K_MM[mm] / 1000.0
    m_n = NUT_M[mm] / 1000.0
    d1, d2, h_w = (v / 1000.0 for v in WASH[mm])
    L = float(spec["L"])
    wh, wn, nuts = int(spec["wh"]), int(spec["wn"]), int(spec["nuts"])
    hex_a = math.sqrt(3.0) / 2.0 * sw * sw          # hexagon area from AF
    m_bolt = (hex_a * k + math.pi * d * d / 4.0 * L) * _RHO
    m_nut = max(0.0, hex_a - math.pi * d * d / 4.0) * m_n * _RHO
    m_wash = math.pi * (d2 * d2 - d1 * d1) / 4.0 * h_w * _RHO
    out = [(f"Болт {mm}×{round(L * 1000):g}", m_bolt, 1)]
    if nuts > 0:
        out.append((f"Гайка {mm}", m_nut, nuts))
    if wh + wn > 0:
        out.append((f"Шайба {mm}", m_wash, wh + wn))
    return out


def _ray_tv(man):
    """Manifold triangles as an (n,3,3) float64 array — convert once, probe
    many times (the seating sweep below casts several rays per hole)."""
    import numpy as np
    mesh = man.to_mesh64()
    vp = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    return vp[np.asarray(mesh.tri_verts, dtype=np.int64)]


def _ray_hits_tv(tv, o, d):
    """All Moller-Trumbore hit distances along the unit ``direction`` d from
    ``o`` against precomputed triangles ``tv`` (version-proof for manifold3d:
    coordinates live in Mesh64.vert_properties, tri_verts are indices)."""
    import numpy as np
    if not len(tv):
        return np.array([])
    a0, b0, c0 = tv[:, 0], tv[:, 1], tv[:, 2]
    e1, e2 = b0 - a0, c0 - a0
    h = np.cross(np.broadcast_to(d, tv[:, 0].shape), e2)
    det = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(det) > 1e-12
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = o - a0
    u = np.einsum("ij,ij->i", s, h) * inv
    q = np.cross(s, e1)
    v = np.einsum("j,ij->i", d, q) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-4)
    return t[hit]


def _ray_hits(man, origin, direction):
    import numpy as np
    return _ray_hits_tv(_ray_tv(man), np.asarray(origin, dtype=np.float64),
                        np.asarray(direction, dtype=np.float64))


def _transform_mesh(mesh, R, t):
    """Rigid motion (det = +1, winding preserved) of a core Mesh."""
    from core.mesh import Mesh
    from PySide6.QtGui import QVector3D
    out = Mesh()
    for f in mesh.faces:
        def mv(q):
            q = q.position if hasattr(q, "position") else q
            x, y, z = q.x(), q.y(), q.z()
            return QVector3D(R[0][0] * x + R[0][1] * y + R[0][2] * z + t[0],
                             R[1][0] * x + R[1][1] * y + R[1][2] * z + t[1],
                             R[2][0] * x + R[2][1] * y + R[2][2] * z + t[2])
        outer = [mv(q) for q in f.loop]
        holes = [[mv(q) for q in h] for h in
                 (getattr(f, "hole_loops", None) or getattr(f, "holes", None) or [])]
        out.add_face(outer, holes)
    return out


def bolt_assembly_mesh(hole_center, axis, spec, man_member, hole_r):
    """Union of bolt + washer/nut stacks as one core Mesh in the member's
    local frame. ``axis`` is the drill axis — the "y"/"z" key or an explicit
    unit vector (a mitre-cut end turns the drill axis together with the hole
    row). ``man_member`` is the member manifold (local, identity pose).
    Seating faces: a probe ray offset just outside the hole edge; the OUTER
    face on each side is the LAST hit along the drill axis. Pieces are built
    in BOLT space (origin at the hole centre, +z toward the head) with
    manifold3d primitives, then the union lands in the member frame through
    one rigid motion — so any axis angle works and the union is manifold."""
    import manifold3d as m3d
    from core import solids
    from ._cuts import rot_from_z_to
    a = ((0.0, 1.0, 0.0) if axis == "y" else
         (0.0, 0.0, 1.0) if axis == "z" else tuple(float(v) for v in axis))
    c = tuple(hole_center)
    e1, e2 = _frame(a)
    side = int(spec.get("head_side", 1))
    ah = a if side > 0 else _neg(a)              # toward the head side
    # A single probe offset can point into thin air — a hole grazing a free
    # edge, a mitre shaving a flange, a rolled section seen across the row.
    # Sweep the offset around the drill axis and keep the first direction
    # whose rays find seating faces on BOTH sides of the hole.
    tv = _ray_tv(man_member)
    th = tn = None
    for i in range(8):
        ang = 2.0 * math.pi * i / 8.0
        ca, sa = math.cos(ang), math.sin(ang)
        e = (ca * e1[0] + sa * e2[0], ca * e1[1] + sa * e2[1], ca * e1[2] + sa * e2[2])
        probe = _add(c, e, hole_r + 0.002)
        t_head = _ray_hits_tv(tv, probe, ah)
        t_nut = _ray_hits_tv(tv, probe, _neg(ah))
        if len(t_head) and len(t_nut):
            th, tn = float(t_head.max()), float(t_nut.max())
            break
    if th is None:
        raise ValueError(tr("луч не нашёл посадочные грани отверстия"))
    mm = spec["size"]
    sw_map = SW_NEW if spec.get("family", "new") == "new" else SW_OLD
    d, sw_b, k = D_MM[mm] / 1000.0, sw_map[mm] / 1000.0, K_MM[mm] / 1000.0
    m_n = NUT_M[mm] / 1000.0
    d1, d2, h_w = (v / 1000.0 for v in WASH[mm])
    segs = int(spec.get("segs", 24))
    L = float(spec["L"])
    wh, wn, nuts = int(spec["wh"]), int(spec["wn"]), int(spec["nuts"])
    mans = []
    # head sits on its washer stack: the head underside is off the material
    seat = th + wh * h_w
    head = m3d.CrossSection([_hex_pts(sw_b)]).extrude(k)
    shank = m3d.Manifold.cylinder(L, d / 2.0, circular_segments=segs)
    mans.append(head.translate((0.0, 0.0, seat)))
    mans.append(shank.translate((0.0, 0.0, seat - L)))
    washer = m3d.CrossSection([_circle_pts(d2 / 2.0, segs),
                               _circle_pts(d1 / 2.0, segs)]).extrude(h_w)
    for j in range(wh):
        mans.append(washer.translate((0.0, 0.0, th + j * h_w)))
    for j in range(wn):
        mans.append(washer.translate((0.0, 0.0, -tn - (j + 1) * h_w)))
    # 0.5 mm radial clearance over the shank: no coincident faces in the union
    nut = m3d.CrossSection([_hex_pts(sw_b),
                            _circle_pts(d / 2.0 + 0.0005, segs)]).extrude(m_n)
    for j in range(nuts):
        mans.append(nut.translate((0.0, 0.0, -tn - wn * h_w - (j + 1) * m_n)))
    one = mans[0] if len(mans) == 1 else \
        m3d.Manifold.batch_boolean(mans, m3d.OpType.Add)
    sources = solids._Sources()
    loops = solids._loops_from(one, sources)
    if not loops:
        raise ValueError(tr("объединение крепежа не удалось"))
    bolt_mesh = solids._group_from_loops(loops, sources, "", None).mesh
    return _transform_mesh(bolt_mesh, rot_from_z_to(ah), c)


# ------------------------------------------------------------ tool

class BoltTool(Tool):
    """One click on the end of a steel member puts a bolt into every hole row
    stored at that end."""

    name = tr("Установить болты в отверстия")
    description = tr("Установить болты (DIN/ГОСТ) в отверстия на конце стального профиля: клик по концу — болт в каждое отверстие этого конца.")
    uses_snap = False

    def __init__(self, spec, on_pick):
        self.spec = dict(spec)
        self.on_pick = on_pick

    def on_activate(self, viewport):
        d = self.spec
        _flash(viewport, tr("Болты {size}x{L:g}: кликните по концу стального профиля или по пластине с высверленными отверстиями  •  Esc — выход").format(size=d["size"], L=d["L"] * 1000), 4000)

    def on_deactivate(self, viewport):
        pass

    def on_click(self, ctx):
        vp = ctx.viewport
        g = vp.pick_group(ctx.screen.x(), ctx.screen.y()) if hasattr(vp, "pick_group") else None
        if g is None:
            _flash(vp, tr("Кликните по стальному профилю или пластине расширения «Сталь РФ»."), 2500)
            return
        from ._plates import is_plate_group
        if is_plate_group(g):
            if self.on_pick(g, "plate", self.spec):
                _leave(vp)
            return
        if not is_steel_group(g):
            _flash(vp, tr("Кликните по стальному профилю или пластине расширения «Сталь РФ»."), 2500)
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
        return tr("болты {size}x{L:g}: клик  конец профиля  •  Esc  выход").format(size=d["size"], L=d["L"] * 1000)

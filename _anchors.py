# SPDX-License-Identifier: GPL-3.0-or-later
"""Anchor bolts (анкерные болты) per the GOST 24379 family.

An anchor is a standalone fastener group placed on a snapped point: the
mounting surface sits at the group origin and the bolt runs along the local
z (up by default). Three shapes are modelled:

* type 1 — straight rod with a bent (hook) end, the hook leg along local +x
  rotated by ``az`` about the vertical;
* type 2 — straight rod with an anchor plate at the embedded end;
* type 4 — stud threaded at both ends: nut and washer above AND below the
  mounting surface.

Thread, chamfers and the bend radius are not modelled — the union is built
from manifold3d primitives (rod cylinder, leg cylinder, plate cube, hex nut
with bore, annular washer) so the result is watertight and IFC-exportable.
Masses in the BOM are analytic from the same catalogue dimensions.
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout)

from tools.base import Tool

from ._i18n import tr
from ._tools import _flash, _leave

# ---------------------------------------------------------------- catalogue
# GOST 24379-2012 working subset: diameters, common lengths (mm) and
# fastener dimensions (DIN 934/125 style, extended to the big anchor sizes).
SIZES = ["M12", "M16", "M20", "M24", "M30", "M36", "M42", "M48"]
D_MM = {"M12": 12.0, "M16": 16.0, "M20": 20.0, "M24": 24.0,
        "M30": 30.0, "M36": 36.0, "M42": 42.0, "M48": 48.0}
SW_MM = {"M12": 19.0, "M16": 24.0, "M20": 30.0, "M24": 36.0,
         "M30": 46.0, "M36": 55.0, "M42": 65.0, "M48": 75.0}      # nut AF
NUT_M = {"M12": 10.0, "M16": 13.0, "M20": 16.0, "M24": 19.0,
         "M30": 24.0, "M36": 29.0, "M42": 34.0, "M48": 38.0}      # nut height
WASH = {                                                            # d1, d2, h
    "M12": (13.0, 24.0, 2.5), "M16": (17.0, 30.0, 3.0),
    "M20": (21.0, 37.0, 3.5), "M24": (25.0, 46.0, 4.0),
    "M30": (32.0, 56.0, 4.0), "M36": (39.0, 69.0, 5.0),
    "M42": (46.0, 80.0, 6.0), "M48": (52.0, 92.0, 6.0),
}
L_MM = {
    "M12": [400, 500, 630, 800],
    "M16": [400, 500, 630, 800, 950],
    "M20": [400, 500, 630, 800, 950, 1100],
    "M24": [500, 630, 800, 950, 1100, 1250],
    "M30": [560, 720, 800, 950, 1100, 1250],
    "M36": [720, 800, 950, 1100, 1250, 1420],
    "M42": [950, 1100, 1250, 1420, 1570],
    "M48": [1000, 1250, 1420, 1570, 1730],
}
L_DEFAULT = {"M12": 500, "M16": 630, "M20": 800, "M24": 800,
             "M30": 950, "M36": 1100, "M42": 1250, "M48": 1420}
TYPES = [("1", "1 — с загнутым концом (крюк)"),
         ("2", "2 — с анкерной плитой"),
         ("4", "4 — шпилька, резьба с двух сторон")]

_RHO = 7850.0


def e_default(size: str) -> int:
    """Sensible projection above the surface: thread beyond the nut plus a
    small allowance, rounded to 5 mm."""
    return int(round((2.0 * D_MM[size] + NUT_M[size]) / 5.0) * 5)


def anchor_label(spec) -> str:
    return (f"Анкер {spec['size']}×{round(float(spec['L']) * 1000):g}"
            f" тип {spec['type']}")


def anchor_parts(spec):
    """Per-part BOM breakdown: ``[(label, mass_kg, qty), …]`` — the rod
    (with the hook leg or the anchor plate), the nut(s) and the washer(s)."""
    mm = str(spec["size"])
    d = D_MM[mm] / 1000.0
    sw = SW_MM[mm] / 1000.0
    m_n = NUT_M[mm] / 1000.0
    d1, d2, h_w = (v / 1000.0 for v in WASH[mm])
    L = float(spec["L"])
    typ = str(spec.get("type", "1"))
    rod = math.pi * d * d / 4.0 * L
    if typ == "1":
        # rod below the surface up to the bend centre + the horizontal leg +
        # the ball corner's extra steel (sphere minus the two half-cylinders
        # it wraps: net about +1/2 * pi r^3)
        r = d / 2.0
        rod += math.pi * r * r * (hook_leg(spec) + 0.5 * r)
    elif typ == "2":
        side, t = plate_dims(spec)
        rod += side * side * t
    hex_a = math.sqrt(3.0) / 2.0 * sw * sw
    m_nut = max(0.0, hex_a - math.pi * d * d / 4.0) * m_n * _RHO
    m_wash = math.pi * (d2 * d2 - d1 * d1) / 4.0 * h_w * _RHO
    n = 2 if typ == "4" else 1
    return [(anchor_label(spec), rod * _RHO, 1),
            (f"Гайка {mm}", m_nut, n),
            (f"Шайба {mm}", m_wash, n)]


def hook_leg(spec) -> float:
    """Total horizontal leg length of the type-1 hook, measured from the
    rod axis (model approximation)."""
    d = D_MM[str(spec["size"])] / 1000.0
    return max(4.0 * d, 0.060)


def bend_radius(spec) -> float:
    """Effective centreline radius of the type-1 hook bend: the ball-elbow
    rounds the corner over one rod radius."""
    return D_MM[str(spec["size"])] / 2000.0


def plate_dims(spec):
    """Anchor plate side and thickness for type 2 (model approximation)."""
    d = D_MM[str(spec["size"])] / 1000.0
    return max(0.060, 3.5 * d), max(0.006, 0.25 * d)


# ------------------------------------------------------------- geometry

def _circle_pts(r, segs):
    return [(r * math.cos(2 * math.pi * i / segs),
             r * math.sin(2 * math.pi * i / segs)) for i in range(segs)]


def _hex_pts(sw):
    rr = sw / math.sqrt(3.0)
    return [(rr * math.cos(math.pi / 6 + math.pi * i / 3),
             rr * math.sin(math.pi / 6 + math.pi * i / 3)) for i in range(6)]


def _anchor_manifold(spec):
    """The anchor as one manifold3d solid in LOCAL bolt space (see
    anchor_mesh); split out so QA can probe the solid directly."""
    import manifold3d as m3d

    mm = str(spec["size"])
    if mm not in D_MM:
        raise ValueError(tr("неизвестный диаметр анкера {size}").format(size=mm))
    d = D_MM[mm] / 1000.0
    sw = SW_MM[mm] / 1000.0
    m_n = NUT_M[mm] / 1000.0
    d1, d2, h_w = (v / 1000.0 for v in WASH[mm])
    L = float(spec["L"])
    e = float(spec["e"])
    segs = int(spec.get("segs", 24))
    typ = str(spec.get("type", "1"))
    Le = L - e                                   # embedded rod length
    if Le <= 0.01:
        raise ValueError(tr("выступ не может превышать длину анкера"))

    mans = []
    rod = m3d.Manifold.cylinder(Le + e, d / 2.0,
                                circular_segments=segs).translate((0.0, 0.0, -Le))
    mans.append(rod)
    if typ == "1":
        # A proper bent end (ball-elbow capsule): the rod runs straight down
        # to the bend centre, a sphere of rod radius rounds the corner, and
        # the horizontal leg leaves that centre along +x (rotation vectors in
        # manifold3d are DEGREES, not radians). The end caps sit INSIDE the
        # sphere — capsule construction — so every union is clean: no
        # coincident caps, no sliver faces, watertight result. The leg bottom
        # is flush with the rod end (z = -Le).
        r = d / 2.0
        hb = hook_leg(spec)
        z_c = -Le + r                          # bend centre = leg axis
        mans.pop()                             # full-length rod replaced below
        mans.append(m3d.Manifold.cylinder(e - z_c, d / 2.0,
                                          circular_segments=segs)
                    .translate((0.0, 0.0, z_c)))
        mans.append(m3d.Manifold.sphere(r, segs).translate((0.0, 0.0, z_c)))
        mans.append(m3d.Manifold.cylinder(hb, d / 2.0,
                                          circular_segments=segs)
                    .rotate((0.0, 90.0, 0.0))   # +z -> +x
                    .translate((0.0, 0.0, z_c)))
    elif typ == "2":
        side, t = plate_dims(spec)
        # center=True: manifold3d cubes default to the first octant (a corner
        # at the origin) — without it the plate sits off-axis (issue found in
        # the live model).
        plate = m3d.Manifold.cube([side, side, t], True)
        mans.append(plate.translate((0.0, 0.0, -Le + t / 2.0)))
    elif typ == "4":
        washer = m3d.CrossSection([_circle_pts(d2 / 2.0, segs),
                                   _circle_pts(d1 / 2.0, segs)]).extrude(h_w)
        nut = m3d.CrossSection([_hex_pts(sw),
                                _circle_pts(d / 2.0 + 0.0005, segs)]).extrude(m_n)
        mans.append(washer.translate((0.0, 0.0, -Le - h_w)))
        mans.append(nut.translate((0.0, 0.0, -Le - h_w - m_n)))
    else:
        raise ValueError(tr("неизвестный тип анкера {type}").format(type=typ))

    # top stack: washer on the surface, nut above it (all types)
    washer = m3d.CrossSection([_circle_pts(d2 / 2.0, segs),
                               _circle_pts(d1 / 2.0, segs)]).extrude(h_w)
    nut = m3d.CrossSection([_hex_pts(sw),
                            _circle_pts(d / 2.0 + 0.0005, segs)]).extrude(m_n)
    mans.append(washer)
    mans.append(nut.translate((0.0, 0.0, h_w)))

    return mans[0] if len(mans) == 1 else \
        m3d.Manifold.batch_boolean(mans, m3d.OpType.Add)


def anchor_mesh(spec):
    """Watertight anchor in LOCAL bolt space: the mounting surface is z = 0,
    the rod runs up to ``z = +e`` (projection) and down to ``z = -(L - e)``
    (type 1 ends in a horizontal hook leg, flush at the bottom). Placement
    (translation, hook rotation, up/down flip) lives in the group's xform —
    the mesh itself is never re-baked."""
    from core import solids
    one = _anchor_manifold(spec)
    if one.volume() <= 1e-12:
        raise ValueError(tr("объединение анкера не удалось"))
    sources = solids._Sources()
    loops = solids._loops_from(one, sources)
    if not loops:
        raise ValueError(tr("объединение анкера не удалось"))
    return solids._group_from_loops(loops, sources, "", None).mesh


# ---------------------------------------------------------------- dialog

class AnchorDialog(QDialog):
    """Modeless dialog; «Установить» keeps it open and arms the tool."""

    def __init__(self, parent=None, on_apply=None):
        super().__init__(parent)
        self.on_apply = on_apply
        self.setWindowTitle(tr("Анкерные болты"))
        hint = QLabel(tr("Анкер ставится в точку клика (снап ловит узлы, "
                         "оси сеток и ферм): поверхность установки — основание "
                         "гайки и шайбы. Ещё клик — ещё анкер, Esc — выход."))
        hint.setWordWrap(True)

        form = QFormLayout()
        self.type = QComboBox()
        for key, label in TYPES:
            self.type.addItem(tr(label), key)
        form.addRow(tr("Тип анкера"), self.type)

        self.size = QComboBox()
        self.size.addItems(SIZES)
        form.addRow(tr("Диаметр"), self.size)

        self.length = QComboBox()
        form.addRow(tr("Длина L"), self.length)

        self.e = QDoubleSpinBox()
        self.e.setRange(10.0, 500.0)
        self.e.setSingleStep(5.0)
        self.e.setDecimals(0)
        self.e.setSuffix(" мм")
        form.addRow(tr("Выступ над поверхностью"), self.e)

        self.az = QDoubleSpinBox()
        self.az.setRange(0.0, 350.0)
        self.az.setSingleStep(10.0)
        self.az.setDecimals(0)
        self.az.setSuffix(" °")
        form.addRow(tr("Поворот крюка"), self.az)

        self.dir = QComboBox()
        self.dir.addItem(tr("Вертикально вверх"))
        self.dir.addItem(tr("Вертикально вниз"))
        form.addRow(tr("Направление"), self.dir)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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

        self.size.currentTextChanged.connect(self._refill)
        self._refill(self.size.currentText())

    def _refill(self, size):
        cur = L_DEFAULT.get(size)
        self.length.clear()
        for mm in L_MM[size]:
            self.length.addItem(tr("{mm} мм").format(mm=mm), mm)
        idx = L_MM[size].index(cur) if cur in L_MM[size] else 0
        self.length.setCurrentIndex(idx)
        self.e.setValue(e_default(size))

    def spec(self) -> dict:
        return {"size": self.size.currentText(),
                "type": self.type.currentData(),
                "L": self.length.currentData() / 1000.0,
                "e": self.e.value() / 1000.0,
                "az": float(self.az.value()),
                "down": self.dir.currentIndex() == 1,
                "segs": 24}


# ------------------------------------------------------------------ tool

class AnchorTool(Tool):
    """Every click (on a snapped point) drops one anchor; Esc exits."""

    name = tr("Поставить анкерный болт")
    description = tr("Поставить анкерный болт (ГОСТ 24379): клик по точке — анкер вертикально, ещё клик — ещё анкер.")
    uses_snap = True

    def __init__(self, spec, on_place):
        self.spec = dict(spec)
        self.on_place = on_place

    def on_activate(self, viewport):
        _flash(viewport, self._clause(), 4000)

    def on_deactivate(self, viewport):
        pass

    def on_click(self, ctx):
        p = ctx.world
        point = (float(p.x()), float(p.y()), float(p.z())) \
            if hasattr(p, "x") else (float(p[0]), float(p[1]), float(p[2]))
        self.on_place(point, self.spec)   # persistent: stay in the tool

    def on_cancel(self, viewport):
        _leave(viewport)

    def status_clause(self):
        return self._clause()

    def _clause(self):
        d = self.spec
        return tr("Анкер {size}×{L:g} тип {t}: кликните точку установки  •  ещё клик — ещё анкер  •  Esc — выход").format(
            size=d["size"], L=float(d["L"]) * 1000, t=d["type"])

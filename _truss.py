# SPDX-License-Identifier: GPL-3.0-or-later
"""Truss axis lines: parameters, validation and pure segment generation.

No Qt, no host. Metres inside; the dialog speaks millimetres. A truss
lives in a vertical plane: local s along the span, z upward; the plane
passes through ``place`` and turns about the world Z by ``az`` degrees.
Segments come out as world-space endpoint pairs tagged by kind, so the
host paints them, snaps to their nodes, and the user places profiles
along them.

``molodcheno`` (parallel chords of double angles / bent channels, web
members of angles) trims every web-member axis at the chord installation
faces and shifts web members sideways in plan - the real tolerances that
make profiles fit at the node without re-trimming on site.
"""
from __future__ import annotations

import math
import uuid

TRUSS_BLOCK_VERSION = 1
MAX_TRUSSES = 100
MAX_PANELS = 60

TYPES = [("parallel", "Балка (параллельные пояса)"),
         ("molodcheno", "Молодечно (пояса параллельны, с допусками)"),
         ("triangle", "Треугольная"),
         ("trapezoid", "Трапецеидальная")]
LATTICES = [("triangle", "треугольная решётка (раскосы в шахматном порядке)"),
            ("diagonal", "раскосная решётка (раскосы + стойки)"),
            ("vertical", "вертикальная решётка (только стойки)")]


class TrussError(ValueError):
    """A user-facing problem with a truss definition."""


def new_truss_id(existing) -> str:
    taken = {t.get("id") for t in existing}
    while True:
        gid = uuid.uuid4().hex[:12]
        if gid not in taken:
            return gid


def _f(v, what):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise TrussError(f"{what}: не число") from None


def validate(spec):
    """Normalise one truss spec (metres). Raises TrussError."""
    out = dict(spec)
    out["type"] = str(spec.get("type", "parallel"))
    if out["type"] not in dict(TYPES):
        raise TrussError("неизвестный тип фермы")
    out["lattice"] = str(spec.get("lattice", "triangle"))
    if out["lattice"] not in dict(LATTICES):
        raise TrussError("неизвестный тип решётки")
    L = _f(spec.get("L", 0.0), "span")
    H = _f(spec.get("H", 0.0), "height")
    if not 0.0 < L <= 200.0:
        raise TrussError("пролёт должен быть 0…200 м")
    if not 0.0 < H <= 20.0:
        raise TrussError("высота должна быть 0…20 м")
    try:
        n = int(spec.get("panels", 0))
    except (TypeError, ValueError):
        raise TrussError("панели: целое число") from None
    if not 2 <= n <= MAX_PANELS:
        raise TrussError(f"панелей: 2…{MAX_PANELS}")
    a = _f(spec.get("haunch", 0.0), "haunch")
    if out["type"] == "trapezoid" and not 0.0 < a < L / 2.0:
        raise TrussError("скос трапеции: 0…L/2")
    out["L"], out["H"], out["panels"], out["haunch"] = L, H, n, max(0.0, a)
    pl = spec.get("place") or {}
    out["place"] = {"x": _f(pl.get("x", 0.0), "X"), "y": _f(pl.get("y", 0.0), "Y"),
                    "z": _f(pl.get("z", 0.0), "Z"), "az": _f(pl.get("az", 0.0), "поворот")}
    tol = spec.get("tol") or {}
    out["tol"] = {"top": max(0.0, _f(tol.get("top", 0.0), "высота верхнего пояса")),
                  "bottom": max(0.0, _f(tol.get("bottom", 0.0), "высота нижнего пояса")),
                  "gap": max(0.0, _f(tol.get("gap", 0.0), "зазор")),
                  "shift": _f(tol.get("shift", 0.0), "сдвиг раскосов")}
    t = out["tol"]
    if out["type"] == "molodcheno" and (t["bottom"] / 2.0 + t["gap"] >= H
                                       or t["top"] / 2.0 + t["gap"] >= H):
        raise TrussError("допуски поясов больше высоты фермы")
    if not str(spec.get("name", "")).strip():
        raise TrussError("имя фермы пусто")
    return out


def top_z(spec, x):
    """Top-chord elevation at spanwise position x (metres)."""
    L, H, a = spec["L"], spec["H"], spec["haunch"]
    t = spec["type"]
    if t in ("parallel", "molodcheno"):
        return H
    if t == "triangle":
        m = L / 2.0
        return H * (x / m if x <= m else (L - x) / m)
    if x < a:
        return H * x / a
    if x > L - a:
        return H * (L - x) / a
    return H


def _chord_slope(spec, x):
    e = 1e-4 * max(spec["L"], 1.0)
    return (top_z(spec, x + e) - top_z(spec, x - e)) / (2.0 * e)


def segments(spec):
    """``[(a, b, kind, label)]`` world-space axis segments; a, b are
    (x, y, z) metres; kind: "top"/"bottom"/"diag"/"post"."""
    spec = validate(spec)
    L, H, n = spec["L"], spec["H"], spec["panels"]
    pl, tol = spec["place"], spec["tol"]
    az = math.radians(pl["az"])
    ux, uy = math.cos(az), math.sin(az)
    vx, vy = -math.sin(az), math.cos(az)      # sideways in the truss plane
    ox, oy, oz = pl["x"], pl["y"], pl["z"]

    def W(s, z, y=0.0):
        return (ox + ux * s + vx * y, oy + uy * s + vy * y, oz + z)

    xs = [L * i / n for i in range(n + 1)]
    segs = []
    if spec["type"] in ("parallel", "molodcheno"):
        segs.append((W(0.0, H), W(L, H), "top", "Пояс верхний"))
    elif spec["type"] == "triangle":
        m = L / 2.0
        segs.append((W(0.0, 0.0), W(m, H), "top", "Пояс верхний (левый)"))
        segs.append((W(m, H), W(L, 0.0), "top", "Пояс верхний (правый)"))
    else:
        a = spec["haunch"]
        segs.append((W(0.0, 0.0), W(a, H), "top", "Пояс верхний (левый скос)"))
        segs.append((W(a, H), W(L - a, H), "top", "Пояс верхний"))
        segs.append((W(L - a, H), W(L, 0.0), "top", "Пояс верхний (правый скос)"))
    segs.append((W(0.0, 0.0), W(L, 0.0), "bottom", "Пояс нижний"))

    # web members: ideal node-to-node axes, then the installation trim.
    # "molodcheno" always trims; other types trim when tolerances are set.
    tol_on = spec["type"] == "molodcheno" or any(
        tol[k] != 0.0 for k in ("top", "bottom", "gap", "shift"))
    zb = tol["bottom"] / 2.0 + tol["gap"] if tol_on else 0.0
    dtop = tol["top"] / 2.0 + tol["gap"] if tol_on else 0.0
    ysh = tol["shift"] if tol_on else 0.0

    def make_web(s1, z1, s2, z2, kind, idx):
        z2 = min(z2, top_z(spec, s2))
        dz, ds = z2 - z1, s2 - s1
        if dz <= 1e-9:
            return
        t0 = max(0.0, (zb - z1) / dz)
        kc = _chord_slope(spec, s2)
        denom = dz - kc * ds
        t1 = 1.0
        if dtop > 0.0 and denom > 1e-9:
            t1 = 1.0 - dtop / denom
        if t1 <= t0 + 1e-9:
            return                       # the member never clears the faces
        s1n, z1n = s1 + ds * t0, z1 + dz * t0
        s2n, z2n = s1 + ds * t1, z1 + dz * t1
        y = ysh
        lbl = "Раскос" if kind == "diag" else "Стойка"
        segs.append((W(s1n, z1n, y), W(s2n, z2n, y), kind, f"{lbl} {idx}"))

    di = po = 0
    if spec["lattice"] in ("triangle", "diagonal"):
        for i in range(n):
            x1, x2 = xs[i], xs[i + 1]
            if spec["lattice"] == "triangle" and i % 2 == 1:
                di += 1
                make_web(x2, 0.0, x1, top_z(spec, x1), "diag", di)
            else:
                di += 1
                make_web(x1, 0.0, x2, top_z(spec, x2), "diag", di)
    if spec["lattice"] in ("diagonal", "vertical"):
        for i in range(n + 1):
            zt = top_z(spec, xs[i])
            if zt > 1e-9:
                po += 1
                make_web(xs[i], 0.0, xs[i], zt, "post", po)
    return segs


def counts(spec):
    c = {"top": 0, "bottom": 0, "diag": 0, "post": 0}
    for _a, _b, kind, _l in segments(spec):
        c[kind] += 1
    return c


def parse_trusses(raw):
    """``(trusses, errors)`` from the document block list. Never raises."""
    items, errors = [], []
    if not isinstance(raw, list):
        return items, errors
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            errors.append(f"ферма {i + 1}: не объект")
            continue
        try:
            d = validate(d)
        except TrussError as exc:
            errors.append(f"ферма {i + 1}: {exc}")
            continue
        if not d.get("id"):
            d["id"] = new_truss_id(items)
        items.append(d)
    return items, errors

# SPDX-License-Identifier: GPL-3.0-or-later
"""Where tuples become IngeTrazo objects: Mesh, Group, xform, commands."""
from __future__ import annotations

import copy
import logging

from PySide6.QtGui import QMatrix4x4, QVector3D

from . import EXT_VERSION, KEY
from ._geometry import (MIN_LENGTH, apply_matrix, cross, direction_and_length, dot, extrude,
                        ifc_class_for, member_matrix, unit)
from ._profiles import build_profile

log = logging.getLogger("ingetrazo.plugins.igz_steel")

_PROFILE_CACHE = {}


# ------------------------------------------------------------ parameters

def is_steel_group(group) -> bool:
    ext = getattr(group, "ext", None)
    block = ext.get(KEY) if isinstance(ext, dict) else None
    return (isinstance(block, dict) and "label" in block
            and getattr(group, "xform", None) is not None)


def member_params(group):
    ext = getattr(group, "ext", None)
    block = ext.get(KEY) if isinstance(ext, dict) else None
    if not isinstance(block, dict) or "label" not in block:
        return None
    return copy.deepcopy(block)


def new_params(label, unit_system, insertion, roll, fillets, segments) -> dict:
    return {"version": EXT_VERSION, "label": str(label), "unit_system": str(unit_system),
            "insertion": str(insertion), "roll": float(roll), "fillets": bool(fillets),
            "segments": int(segments)}


# ------------------------------------------------------------ geometry

def profile_for(shape, params):
    key = (shape.label, bool(params.get("fillets", True)), int(params.get("segments", 24)))
    prof = _PROFILE_CACHE.get(key)
    if prof is None:
        prof = build_profile(shape.family, shape.dims_m(), fillets=key[1], segments=key[2])
        _PROFILE_CACHE[key] = prof
    return prof


def insertion_uv(profile, insertion_id):
    for p in profile.points:
        if p.id == insertion_id:
            return p.uv
    return (0.0, 0.0)


def _qv(p):
    return QVector3D(float(p[0]), float(p[1]), float(p[2]))


def build_mesh(member_mesh):
    from core.mesh import Mesh
    mesh = Mesh()
    for face in member_mesh.faces:
        if isinstance(face, tuple):
            outer, holes = face
            mesh.add_face([_qv(p) for p in outer], [[_qv(p) for p in h] for h in holes] or None)
        else:
            mesh.add_face([_qv(p) for p in face])
    try:
        from core.orient import orient_outward
        orient_outward(mesh)
    except Exception:
        log.exception("igz_steel: orient_outward failed")
    if member_mesh.soft_pairs:
        index = {id(f): i for i, f in enumerate(mesh.faces)}
        for edge in mesh.edges:
            if len(edge.faces) != 2:
                continue
            i, j = index.get(id(edge.faces[0])), index.get(id(edge.faces[1]))
            if (i, j) in member_mesh.soft_pairs or (j, i) in member_mesh.soft_pairs:
                edge.soft = True
    return mesh


def member_parts(shape, params, start, direction, length, scene=None, db=None) -> dict:
    length = float(length)
    direction = unit(direction) if length >= MIN_LENGTH else (1.0, 0.0, 0.0)
    if length < MIN_LENGTH:
        length = 0.0
    profile = profile_for(shape, params)
    uv = insertion_uv(profile, params.get("insertion", "centroid"))
    mm = extrude(profile, length, uv)
    rows = member_matrix(start, direction, float(params.get("roll", 0.0)))
    ext_block = dict(params)
    ext_block.update({"version": EXT_VERSION, "start": [float(c) for c in start],
                      "direction": [float(c) for c in direction], "length": length})
    name = shape.label if length > 0 else f"{shape.label} (profile)"
    ifc = {"class": ifc_class_for(direction) if length > 0 else "IfcMember", "name": shape.label}
    mesh = build_mesh(mm)
    holes = params.get("holes")
    cuts = params.get("cuts")
    extra = []
    if length >= MIN_LENGTH and ext_block.get("trims"):
        extra = trim_cutters(ext_block, QMatrix4x4(*rows), scene, db)
    if (holes or cuts or extra) and length >= MIN_LENGTH:
        # stored rows, mitres and profile trims re-applied on every rebuild —
        # one combined boolean keeps the loop welding of rotated rims clean
        from ._holes import cut_holes
        mesh = cut_holes(mesh, holes or [], length, profile, cuts,
                         include_cuts=bool(cuts), extra_mans=extra)
    return {"mesh": mesh, "xform": QMatrix4x4(*rows), "name": name,
            "ifc": ifc, "ext": {KEY: ext_block}, "length": length}


def member_manifold(shape, params, length, target=None, scene=None, db=None):
    """The member solid as a manifold3d object in the member's local frame,
    rebuilt from the parametric pipeline (base extrusion minus every stored
    hole row and mitre cutter in ONE boolean) instead of from the group's
    extracted mesh. A hole rim grazing a mitre face can make the Mesh loop
    round-trip lossy; the bolt seating probe needs the exact faces."""
    profile = profile_for(shape, params)
    uv = insertion_uv(profile, params.get("insertion", "centroid"))
    base = build_mesh(extrude(profile, float(length), uv))
    from ._holes import cut_holes_manifold
    extra = []
    if target is not None and params.get("trims") and scene is not None and db is not None:
        xt = getattr(target, "xform", None)
        if xt is not None:
            extra = trim_cutters(params, xt, scene, db)
    res = cut_holes_manifold(base, list(params.get("holes") or []), float(length),
                             profile, params.get("cuts"), include_cuts=True,
                             extra_mans=extra)
    if res is not None:
        return res
    from core.group import Group
    from core import solids
    return solids._to_manifold(Group(mesh=base), solids._Sources())


def _m3x4(m):
    """QMatrix4x4 -> nested 3x4 [R|t] for manifold3d Manifold.transform()."""
    o = m.map(QVector3D(0.0, 0.0, 0.0))
    cx = m.map(QVector3D(1.0, 0.0, 0.0)) - o
    cy = m.map(QVector3D(0.0, 1.0, 0.0)) - o
    cz = m.map(QVector3D(0.0, 0.0, 1.0)) - o
    return [[cx.x(), cy.x(), cz.x(), o.x()],
            [cx.y(), cy.y(), cz.y(), o.y()],
            [cx.z(), cy.z(), cz.z(), o.z()]]


def trim_cutters(params, xt, scene, db):
    """The cutter solids referenced by params["trims"] (uid links to other
    steel members) as manifolds in the target's LOCAL frame — the target is
    placed by the world xform ``xt``. Each cutter is rebuilt from its own
    parameters WITHOUT its own trims, so a pair of mutually trimmed members
    cuts each other with full solids, not with notched leftovers. A cutter
    missing from the document is skipped silently: the reference survives,
    so re-inserting it and rebuilding the target restores the cut."""
    out = []
    inv, ok = xt.inverted()
    if not ok:
        return out
    for tr in params.get("trims") or []:
        uid = tr.get("uid")
        cg = None
        for g in iter_groups(scene):
            if g is not None and is_steel_group(g) and getattr(g, "uid", id(g)) == uid:
                cg = g
                break
        if cg is None:
            continue
        cp = member_params(cg)
        cshape = db.find(cp.get("label", "")) if cp else None
        clen = float(cp.get("length", 0.0)) if cp else 0.0
        if cshape is None or clen < MIN_LENGTH:
            continue
        man = member_manifold(cshape, cp, clen)
        xc = cg.xform if getattr(cg, "xform", None) is not None else QMatrix4x4()
        out.append(man.transform(_m3x4(inv * xc)))
    return out


def make_group(parts, layer=None):
    from core.group import Group
    g = Group(mesh=parts["mesh"], name=parts["name"])
    g.xform = parts["xform"]
    g.component = False
    g.ifc = dict(parts["ifc"])
    g.ext = copy.deepcopy(parts["ext"])
    if layer:
        g.layer = layer
    return g


# ------------------------------------------------------------ commands

def _command_base():
    from core.history import Command
    return Command


class RebuildMemberCommand(_command_base()):
    """Swap a member's mesh, pose and parameters in place; undo puts them back."""

    def __init__(self, group, parts):
        self.group = group
        self.parts = parts
        self._before = None

    def _apply(self, scene, mesh, xform, name, ifc, ext):
        g = self.group
        g.mesh, g.xform, g.name = mesh, xform, name
        g.ifc = copy.deepcopy(ifc)
        g.ext = copy.deepcopy(ext)
        try:
            from core.history import _dirty_group_chunks
            _dirty_group_chunks(scene)
        except Exception:
            pass
        sel = getattr(scene, "selection", None)
        if sel is not None:
            sel.clear()
            sel.add(g)
        scene.version += 1

    def do(self, scene):
        g = self.group
        if self._before is None:
            self._before = (g.mesh, g.xform, g.name, copy.deepcopy(g.ifc), copy.deepcopy(g.ext))
        p = self.parts
        self._apply(scene, p["mesh"], p["xform"], p["name"], p["ifc"], p["ext"])

    def undo(self, scene):
        self._apply(scene, *self._before)


def insert_command(group, layer=None):
    from core.history import AssignLayerCommand, CompoundCommand, InsertGroupCommand
    cmds = [InsertGroupCommand(group)]
    if layer:
        cmds.append(AssignLayerCommand([group], layer))
    return CompoundCommand(cmds)


def rebuild_command(group, parts, layer=None):
    from core.history import AssignLayerCommand, CompoundCommand
    from core.layers import layer_of
    cmds = [RebuildMemberCommand(group, parts)]
    if layer and layer_of(group) != layer:
        cmds.append(AssignLayerCommand([group], layer))
    return CompoundCommand(cmds)


def run(viewport, command):
    """Execute through the history; return the error text or None."""
    history = viewport.history
    history.execute(command)
    err = getattr(history, "last_error", None)
    if err:
        return str(err)
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()
    return None


# ------------------------------------------------------------ queries

def member_endpoints(group):
    params = member_params(group) or {}
    length = float(params.get("length", 0.0))
    m = group.xform
    a = m.map(QVector3D(0.0, 0.0, 0.0))
    b = m.map(QVector3D(length, 0.0, 0.0))
    return ((a.x(), a.y(), a.z()), (b.x(), b.y(), b.z()))


def member_frame(group):
    """``(start, direction, length, roll_deg)`` measured from the LIVE ``xform``,
    so a member the host's Move or Rotate tools touched keeps its place and
    its roll when it is stretched or edited. A profile object (length 0)
    keeps its stored direction and roll."""
    import math
    params = member_params(group) or {}
    p0, p1 = member_endpoints(group)
    direction, length = direction_and_length(p0, p1)
    if direction is None or length < MIN_LENGTH:
        return (p0, tuple(float(c) for c in params.get("direction", (1.0, 0.0, 0.0))),
                0.0, float(params.get("roll", 0.0)))
    m = group.xform
    origin = m.map(QVector3D(0.0, 0.0, 0.0))
    zc = m.map(QVector3D(0.0, 0.0, 1.0)) - origin
    zc = unit((zc.x(), zc.y(), zc.z()))
    ref = member_matrix(p0, direction, 0.0)
    y0 = (ref[1], ref[5], ref[9])
    z0 = (ref[2], ref[6], ref[10])
    roll = math.degrees(math.atan2(-dot(zc, y0), dot(zc, z0)))
    return (p0, direction, length, roll)


def member_record(group, db):
    params = member_params(group)
    if params is None:
        return None
    shape = db.find(params.get("label", ""))
    from core.layers import layer_of
    return {"label": params.get("label", ""),
            "family": shape.family if shape else "",
            "length_m": float(params.get("length", 0.0)),
            "weight_per_m": shape.weight_per_m() if shape else 0.0,
            "layer": layer_of(group),
            "ifc_class": (group.ifc or {}).get("class", "") if isinstance(group.ifc, dict) else "",
            "uid": getattr(group, "uid", id(group))}


def iter_groups(scene):
    stack = list(reversed(list(getattr(scene, "groups", []) or [])))
    while stack:
        g = stack.pop()
        yield g
        kids = getattr(g, "children", None) or []
        stack.extend(reversed(list(kids)))


# ---------------------------------------------------------------- IFC export fix
def bake_mesh(mesh, m):
    """Copy of a core Mesh with every vertex mapped by the world matrix m."""
    from core.mesh import Mesh
    out = Mesh()
    for f in mesh.faces:
        outer = [m.map(q.position if hasattr(q, "position") else q)
                 for q in f.loop]
        holes = [[m.map(q.position if hasattr(q, "position") else q) for q in h]
                 for h in (getattr(f, "hole_loops", None)
                           or getattr(f, "holes", None) or [])]
        out.add_face(outer, holes)
    return out


def patch_ifc_export() -> bool:
    """Fix the core IFC4 exporter's placement bug (v0.5.9: formats/ifc.py
    line 161 falls back to the RAW group.mesh while collect_objects already
    measured the world-space copy) - every member we place through xform
    exports collapsed at the origin. Wrap the core save_ifc: bake the world
    xform into a copy of each such mesh and hide xform for the duration (so
    the quantity pass in core.bim agrees), then restore the originals.
    Returns False when the core module cannot be reached."""
    try:
        import formats.ifc as _ifc
    except Exception:
        return False
    if getattr(_ifc.save_ifc, "_igz_rf_bake", False):
        return True
    orig = _ifc.save_ifc

    def save_ifc_baked(scene, path, project_name="IngeTrazo project"):
        saved = []
        try:
            for g in list(getattr(scene, "groups", ())):
                xf = getattr(g, "xform", None)
                if xf is None or getattr(g, "mesh", None) is None:
                    continue
                saved.append((g, xf, g.mesh))
                g.mesh = bake_mesh(g.mesh, xf)
                g.xform = None
            return orig(scene, path, project_name)
        finally:
            for g, xf, m in reversed(saved):
                g.xform = xf
                g.mesh = m

    save_ifc_baked._igz_rf_bake = True
    _ifc.save_ifc = save_ifc_baked
    return True

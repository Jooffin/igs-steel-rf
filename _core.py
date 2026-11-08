# SPDX-License-Identifier: GPL-3.0-or-later
"""Extension wiring: toolbar, menus, context menu, Browser kind, and the
session object that owns the dialogs and turns tool callbacks into commands."""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPalette
from PySide6.QtWidgets import QMessageBox, QToolBar

from . import KEY
from ._bom import collect
from ._db import load as load_db
from ._geometry import MIN_LENGTH
from ._grid_host import GridStore
from ._truss_host import TrussStore
from ._i18n import tr
from ._holes import hole_positions
from ._host import (insert_command, is_steel_group, iter_groups, make_group, member_frame,
                    member_manifold, member_params, member_parts, member_record, new_params,
                    profile_for, rebuild_command, run)
from ._tools import PlaceMemberTool, StretchMemberTool
from ._units import fmt_len, fmt_weight

log = logging.getLogger("ingetrazo.plugins.igz_steel")
_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
_SESSIONS = {}
TOOLBAR_NAME = "igz_steel_rf_toolbar"   # distinct from upstream igz_steel so both can coexist


def _deferred(fn):
    """A slot that runs ``fn`` on the next event-loop turn and ignores the
    ``checked`` bool Qt may pass to a triggered handler."""
    return lambda _checked=False, f=fn: QTimer.singleShot(0, f)


def load_icon(name, window):
    """icons/<name>.svg (light strokes) for a dark palette, <name>_light.svg
    for a light one; either file serves as the fallback for the other."""
    dark = True
    try:
        bg = window.palette().color(QPalette.Window)
        dark = bg.lightness() < 128
    except Exception:
        pass
    order = [f"{name}.svg", f"{name}_light.svg"] if dark else [f"{name}_light.svg", f"{name}.svg"]
    for fn in order:
        path = os.path.join(_ICONS, fn)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


class SteelSession:
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.dialog = None
        self.bom_dialog = None
        self._dlgs = {}                   # persistent tool dialogs (settings kept)
        self._edit_target = None
        self.grid_dialog_ = None
        self._applying_grids = False      # our own Apply is writing the document
        self._dialog_block = None         # the grid block the dialog last loaded
        self.grids = GridStore(app)
        self.trusses = TrussStore(app)
        self.grids.confirm = self._confirm_grid_delete
        self.grids.on_edit_request = lambda gid: QTimer.singleShot(0, lambda: self.open_grids(gid))

    # -- helpers ------------------------------------------------------------
    def _kept_dialog(self, key, make):
        """Persistent modeless tool dialog: the same instance is reused for
        every opening, so the user's parameters (plate size, bolt size, hole
        pitch, cut angle…) survive between placements — press «Установить» /
        «Применить» again and place the next copy without re-entering
        anything; the dialog stays open while you click members."""
        d = self._dlgs.get(key)
        if d is None:
            d = self._dlgs[key] = make()
        d.show()
        d.raise_()
        d.activateWindow()
        return d

    @property
    def scene(self):
        return self.app.viewport.scene

    def layer_names(self):
        return [ly.name for ly in getattr(self.scene, "layers", []) or []]

    def _guard(self, message=None):
        if getattr(self.scene, "edit_group", None) is not None:
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    message or tr("Закройте редактируемую группу, прежде чем размещать или менять стальные профили."))
            return False
        return True

    def single_selected(self):
        found = []
        for item in getattr(self.scene, "selection", ()) or ():
            g = getattr(item, "owner", None) or item
            if is_steel_group(g) and g not in found:
                found.append(g)
        if len(found) != 1:
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Выберите ровно один стальной профиль, созданный этим расширением."))
            return None
        return found[0]

    # -- dialogs ------------------------------------------------------------
    def member_dialog(self):
        if self.dialog is None:
            from ._dialog import MemberDialog
            self.dialog = MemberDialog(self.db, self.app.window)
            self.dialog.place_requested.connect(self.on_place)
            self.dialog.update_requested.connect(self.on_update)
        self.dialog.set_layers(self.layer_names())
        return self.dialog

    def _show(self, dialog):
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_place(self):
        d = self.member_dialog()
        d.set_mode("place")
        self._show(d)

    def open_edit(self):
        g = self.single_selected()
        if g is None:
            return
        params = member_params(g)
        _start, _direction, length, roll = member_frame(g)
        params["roll"] = roll
        from core.layers import layer_of
        d = self.member_dialog()
        d.set_mode("edit")
        d.load(params, layer_of(g), length)
        self._edit_target = g
        self._show(d)

    def open_stretch(self):
        g = self.single_selected()
        if g is None:
            return
        params = member_params(g)
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            QMessageBox.warning(self.app.window, tr("Сталь РФ"),
                                tr("Неизвестный профиль {label!r} в этом элементе.").format(label=params.get('label')))
            return
        from core.layers import layer_of
        layer = layer_of(g)
        params["roll"] = member_frame(g)[3]

        def on_commit(fixed, direction, length):
            return self.rebuild(g, params, fixed, direction, length, layer)
        self.app.viewport.set_active_tool(StretchMemberTool(g, shape, params, on_commit))

    def open_bom(self):
        if self.bom_dialog is None:
            from ._dialog import BomDialog
            self.bom_dialog = BomDialog(self.app.window, self.collect_bom, self.select_uid,
                                        fmt_len, fmt_weight)
        self.bom_dialog.refresh()
        self._show(self.bom_dialog)

    # -- grids ----------------------------------------------------------------
    def _confirm_grid_delete(self, grid):
        return QMessageBox.question(
            self.app.window, "Оси сеток",
            tr("Удалить ось {name} с {n} ур.(-ями)?").format(name=grid.name, n=len(grid.levels))) == QMessageBox.Yes

    def grid_dialog(self):
        if self.grid_dialog_ is None:
            from ._grid_dialog import GridDialog
            d = GridDialog(self.app.window)
            self._dialog_block = self.grids.raw_block()
            d.load_block(self._dialog_block)
            d.applied.connect(self.on_grids_applied)
            d.pick_origin_requested.connect(self.pick_origin)
            d.pick_direction_requested.connect(self.pick_direction)
            self.grid_dialog_ = d
        return self.grid_dialog_

    # -- truss axes -----------------------------------------------------------
    def open_trusses(self):
        from ._truss_dialog import TrussesDialog

        def make():
            return TrussesDialog(self.app.window, self.trusses,
                                 on_change=self._trusses_changed)
        self._kept_dialog("trusses", make)

    def _trusses_changed(self):
        try:
            self.app.viewport.update()
        except Exception:
            pass

    def open_options(self):
        from ._options_dialog import OptionsDialog
        self._kept_dialog("options", lambda: OptionsDialog(self.app.window))

    def open_grids(self, grid_id=None):
        d = self.grid_dialog()
        if grid_id:
            d.select_grid(grid_id)
        self._show(d)
        return d

    def on_grids_applied(self, block):
        if not self._guard(tr("Закройте редактируемую группу, прежде чем менять оси сеток.")):
            return
        self._applying_grids = True       # the document-changed hook may run inside save_block
        try:
            self.grids.save_block(block)
        except Exception as exc:
            log.exception("igz_steel_rf: saving grids failed")
            QMessageBox.critical(self.app.window, "Оси сеток", tr("Не удалось сохранить оси сетки: {exc}").format(exc=exc))
            return
        finally:
            self._applying_grids = False
        if self.grid_dialog_ is not None:
            # our own write: show the saved block quietly, keeping the preview's view
            self._dialog_block = self.grids.raw_block()
            self.grid_dialog_.load_block(self._dialog_block, notice=None, fit=False)
        self.app.viewport.update()

    def delete_selected_grid(self):
        gid = self.grids.selected_id
        if gid:
            self.grids.delete(gid)
            self.app.viewport.update()

    def _previous_tool(self):
        """The tool a pick should hand back to. When a pick tool is already
        active (Pick origin, then Pick dir.), its own ``previous``, so the
        chain never ends on a pick tool."""
        from ._grid_dialog import PickDirectionTool, PickPointTool
        vp = self.app.viewport
        for attr in ("active_tool", "tool", "_tool"):
            t = getattr(vp, attr, None)
            if t is not None and not callable(t):
                if isinstance(t, (PickPointTool, PickDirectionTool)):
                    return t.previous
                return t
        return None

    def pick_origin(self):
        from ._grid_dialog import PickPointTool
        d = self.grid_dialog()

        def on_point(p):
            d.set_origin(p)
            self.app.viewport.update()
        self.app.viewport.set_active_tool(PickPointTool(on_point, previous=self._previous_tool()))

    def pick_direction(self):
        from ._grid_dialog import PickDirectionTool
        d = self.grid_dialog()

        def on_angle(deg):
            d.set_rotation(deg)
            self.app.viewport.update()
        self.app.viewport.set_active_tool(PickDirectionTool(on_angle, previous=self._previous_tool()))

    # -- actions ------------------------------------------------------------
    def on_place(self, p):
        shape = self.db.find(p.get("label", ""))
        if shape is None:
            return
        params = new_params(shape.label, p.get("unit_system", "metric"),
                            p.get("insertion", "centroid"), p.get("roll", 0.0),
                            p.get("fillets", True), p.get("segments", 24))
        layer = (p.get("layer") or "").strip() or None

        def on_member(start, direction, length):
            return self.insert(shape, params, start, direction, length, layer)

        def on_profile(start):
            return self.insert(shape, params, start, (1.0, 0.0, 0.0), 0.0, layer)
        self.app.viewport.set_active_tool(PlaceMemberTool(shape, params, on_member, on_profile))

    def on_update(self, p):
        g = self._edit_target
        if g is None or not is_steel_group(g) or g not in list(iter_groups(self.scene)):
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Профиля больше нет в документе. Выберите его заново."))
            return
        shape = self.db.find(p.get("label", ""))
        if shape is None:
            return
        old = member_params(g)
        params = new_params(shape.label, p.get("unit_system", "metric"),
                            p.get("insertion", "centroid"), p.get("roll", 0.0),
                            p.get("fillets", True), p.get("segments", 24))
        params["holes"] = list(old.get("holes") or [])      # keep cut hole rows
        params["cuts"] = list(old.get("cuts") or [])        # keep mitre cuts
        params["trims"] = list(old.get("trims") or [])      # keep profile trims
        length = float(p.get("length", old.get("length", 0.0)))
        if length < MIN_LENGTH:
            length = 0.0
        layer = (p.get("layer") or "").strip() or None
        start, direction, _length, _roll = member_frame(g)
        if self.rebuild(g, params, start, direction, length, layer) and self.dialog is not None:
            self.dialog.close()

    def insert(self, shape, params, start, direction, length, layer):
        if not self._guard():
            return False
        try:
            parts = member_parts(shape, params, start, direction, length,
                                 scene=self.scene, db=self.db)
            group = make_group(parts)
        except Exception as exc:
            log.exception("igz_steel_rf: building a member failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось построить профиль: {exc}").format(exc=exc))
            return False
        err = run(self.app.viewport, insert_command(group, layer))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        self._refresh_bom()
        return True

    def rebuild(self, group, params, start, direction, length, layer):
        if not self._guard():
            return False
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        try:
            parts = member_parts(shape, params, start, direction, length,
                                 scene=self.scene, db=self.db)
        except Exception as exc:
            log.exception("igz_steel_rf: rebuilding a member failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось перестроить профиль: {exc}").format(exc=exc))
            return False
        err = run(self.app.viewport, rebuild_command(group, parts, layer))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        self._refresh_bom()
        return True

    # -- end-of-member holes ---------------------------------------------------
    def open_holes(self):
        from ._holes import CutHolesTool, HolesDialog

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем вырезать отверстия.")):
                return
            self.app.viewport.set_active_tool(CutHolesTool(spec, self.apply_holes))
        self._kept_dialog("holes", lambda: HolesDialog(self.app.window, on_apply=apply))

    def apply_holes(self, group, spec):
        """Cut one prepared row of holes into the member, in place: the group
        keeps its identity and the spec lands in its ext block, so stretching
        or editing the member re-applies every stored row."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем вырезать отверстия.")):
            return False
        params = member_params(group)
        if params is None:
            return False
        length = float(params.get("length", 0.0))
        if length < MIN_LENGTH:
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Отверстия вырезаются у вытянутого элемента: сначала вытяните профиль (или задайте длину)."))
            return False
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        from ._holes import fit_ok
        if not fit_ok(spec, length):
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Ряд отверстий не помещается на длине профиля — уменьшите отступ, шаг или количество."))
            return False
        prof = profile_for(shape, params)
        from ._holes import row_in_section
        if not row_in_section(spec, prof):
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Ряд отверстий лежит вне материала сечения — проверьте смещения u/v (они задаются по не повернутому сечению, без учёта крена)."))
            return False
        specs = list(params.get("holes") or []) + [spec]
        p2 = dict(params)
        p2["holes"] = specs
        # Rebuild from the clean base profile with ONE combined boolean
        # (all hole cylinders + the mitre cutter boxes subtracted together).
        # Cutting into the already-cut mesh instead would stack booleans,
        # and each extra fuse pass degrades the hole-rim welding.
        try:
            parts = member_parts(shape, p2, tuple(params.get("start") or (0.0, 0.0, 0.0)),
                                 tuple(params.get("direction") or (1.0, 0.0, 0.0)), length,
                                 scene=self.scene, db=self.db)
        except Exception as exc:
            log.exception("igz_steel_rf: cutting holes failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось вырезать отверстия: {exc}").format(exc=exc))
            return False
        if getattr(group, "xform", None) is not None:
            parts["xform"] = group.xform
        if group.name:
            parts["name"] = group.name
        if isinstance(group.ifc, dict):
            parts["ifc"] = dict(group.ifc)
        err = run(self.app.viewport, rebuild_command(group, parts))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(f"{shape.label}: вырезано {int(spec['count'])} отв. "
                      f"Ø{spec['dia'] * 1000:g} мм", 3000)
            except Exception:
                pass
        self._refresh_bom()
        return True

    # -- bolts into the hole rows ----------------------------------------------
    def open_bolts(self):
        from ._bolts import BoltDialog, BoltTool

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить болты.")):
                return
            self.app.viewport.set_active_tool(BoltTool(spec, self.apply_bolts))
        self._kept_dialog("bolts", lambda: BoltDialog(self.app.window, on_apply=apply))

    def apply_bolts(self, group, end, spec):
        """Put one bolt (head + washers + nuts per spec) into every hole row
        stored at the clicked end. The bolts are loose groups that share the
        member's pose, layer and IFC-ready ext block."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить болты.")):
            return False
        from ._plates import is_plate_group
        if is_plate_group(group):
            return self.apply_plate_bolts(group, spec)
        params = member_params(group)
        if params is None:
            return False
        rows = [hs for hs in (params.get("holes") or []) if hs.get("end") == end]
        if not rows:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("На этом конце нет вырезанных отверстий — сначала прорежьте их («Отверстия на конце профиля…»)"), 3500)
                except Exception:
                    pass
            return False
        length = float(params.get("length", 0.0))
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        from ._bolts import bolt_assembly_mesh
        from ._cuts import end_cut
        from core.group import Group
        try:
            # The seating probe reads a manifold rebuilt from the parametric
            # pipeline, not from the group's extracted mesh: a hole rim that
            # grazes a mitre face can make that loop round-trip lossy, and
            # the ray needs the exact faces to seat the head and the nut.
            man = member_manifold(shape, params, length, target=group,
                                  scene=self.scene, db=self.db)
        except Exception as exc:
            log.exception("igz_steel_rf: member manifold failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Профиль не годится для болтов: {exc}").format(exc=exc))
            return False
        cut = end_cut(params, end)
        spots = []
        for hs in rows:
            for p in hole_positions(hs, length, cut):
                spots.append((p, hs))
        if spec.get("max"):
            spots = spots[:int(spec["max"])]
        from core.layers import layer_of
        from core.history import CompoundCommand
        layer = layer_of(group)
        cmds = []
        name = f"Болт {spec['size']}×{int(round(spec['L'] * 1000))}"
        for (p, hs) in spots:
            try:
                mesh = bolt_assembly_mesh(p, hs.get("axis", "y"), spec, man,
                                          float(hs.get("dia", 0.02)) / 2.0)
            except Exception as exc:
                log.exception("igz_steel_rf: bolt assembly failed")
                QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось собрать болт: {exc}").format(exc=exc))
                return False
            bg = Group(mesh=mesh, name=name)
            if getattr(group, "xform", None) is not None:
                from PySide6.QtGui import QMatrix4x4
                bg.xform = QMatrix4x4(group.xform)
            bg.component = False
            bg.ifc = {"class": "IfcMechanicalFastener", "name": name}
            bg.ext = {KEY: {"bolt": dict(spec)}}
            cmds.append(insert_command(bg, layer))
        err = run(self.app.viewport, CompoundCommand(cmds)) if cmds else None
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(tr("Установлено болтов: {n} — {name}").format(n=len(spots), name=name), 3000)
            except Exception:
                pass
        return True

    # -- anchor bolts -----------------------------------------------------------
    def open_anchors(self):
        from ._anchors import AnchorDialog, AnchorTool

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить анкеры.")):
                return
            self.app.viewport.set_active_tool(AnchorTool(spec, self.apply_anchor))
        self._kept_dialog("anchors", lambda: AnchorDialog(self.app.window, on_apply=apply))

    def apply_anchor(self, point, spec):
        """Drop one anchor group at a snapped world point. The mesh is built
        once in bolt space (surface at z=0, rod up); the point, the hook
        rotation and the up/down flip live in the group's xform."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить анкеры.")):
            return False
        from ._anchors import anchor_mesh, anchor_label
        from core.group import Group
        from PySide6.QtGui import QMatrix4x4
        from core.layers import layer_of
        name = anchor_label(spec)
        try:
            mesh = anchor_mesh(spec)
        except Exception as exc:
            log.exception("igz_steel_rf: anchor mesh failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось построить анкер: {exc}").format(exc=exc))
            return False
        ag = Group(mesh=mesh, name=name)
        m = QMatrix4x4()
        m.translate(float(point[0]), float(point[1]), float(point[2]))
        m.rotate(float(spec.get("az", 0.0)), 0.0, 0.0, 1.0)
        if spec.get("down"):
            m.rotate(180.0, 1.0, 0.0, 0.0)
        ag.xform = m
        ag.component = False
        ag.ifc = {"class": "IfcMechanicalFastener", "name": name}
        ag.ext = {KEY: {"anchor": dict(spec)}}
        layer = "Layer 0"
        try:
            layer = layer_of(self.single_selected()) if self.single_selected() else "Layer 0"
        except Exception:
            layer = "Layer 0"
        err = run(self.app.viewport, insert_command(ag, layer))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(tr("Установлен {name} — ещё клик ставит следующий, Esc — выход").format(name=name), 3000)
            except Exception:
                pass
        self._refresh_bom()
        return True

    # -- trim by another member --------------------------------------------------
    def open_trims(self):
        if not self._guard(tr("Закройте редактируемую группу, прежде чем обрезать профиль.")):
            return
        from ._trims import TrimByMemberTool
        self.app.viewport.set_active_tool(TrimByMemberTool(self.apply_trim))

    def apply_trim(self, target, cutter):
        """Record that ``target`` is cut by the solid of ``cutter`` (any other
        steel member — column vs beam, at any angle). The trim is a uid link,
        replayed as a solid subtraction on every rebuild of the target."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем обрезать профиль.")):
            return False
        if target is cutter:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("Профиль не может обрезать сам себя."), 2500)
                except Exception:
                    pass
            return False
        params = member_params(target)
        if params is None:
            return False
        cuid = getattr(cutter, "uid", id(cutter))
        trims = [t for t in (params.get("trims") or []) if t.get("uid") != cuid]
        trims.append({"uid": cuid})
        return self._retrim(target, params, trims)

    def remove_trims(self, target):
        """Drop every profile trim from the member and rebuild it whole."""
        params = member_params(target)
        if params is None or not params.get("trims"):
            return False
        return self._retrim(target, params, [])

    def _retrim(self, group, params, trims):
        params["trims"] = trims
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        start, direction, length, roll = member_frame(group)
        params["roll"] = roll
        if length < MIN_LENGTH:
            length = float(params.get("length", 0.0))
        try:
            parts = member_parts(shape, params, start, direction, length,
                                 scene=self.scene, db=self.db)
        except Exception as exc:
            log.exception("igz_steel_rf: trim rebuild failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось обрезать профиль: {exc}").format(exc=exc))
            return False
        if getattr(group, "xform", None) is not None:
            parts["xform"] = group.xform
        if group.name:
            parts["name"] = group.name
        if isinstance(group.ifc, dict):
            parts["ifc"] = dict(group.ifc)
        err = run(self.app.viewport, rebuild_command(group, parts))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(tr("Обрезка по профилю применена") if trims
                      else tr("Обрезки по профилю сняты"), 2500)
            except Exception:
                pass
        self._refresh_bom()
        return True

    # -- end plates ------------------------------------------------------------
    def open_plates(self):
        from ._plates import PlateDialog, PlateTool

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить пластины.")):
                return
            self.app.viewport.set_active_tool(PlateTool(spec, self.apply_plates))
        self._kept_dialog("plates", lambda: PlateDialog(self.app.window, on_apply=apply))

    def apply_plates(self, group, end, spec):
        """Place one plate (box) at the clicked end, in the member's local
        frame, as a loose IfcPlate group sharing pose and layer."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем ставить пластины.")):
            return False
        params = member_params(group)
        if params is None:
            return False
        length = float(params.get("length", 0.0))
        if length < MIN_LENGTH:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("Пластина ставится на вытянутый элемент — сначала вытяните его."), 3000)
                except Exception:
                    pass
            return False
        from ._cuts import end_cut
        from ._plates import plate_build, plate_frame
        from core.group import Group
        from core.layers import layer_of
        from PySide6.QtGui import QMatrix4x4
        try:
            cut = end_cut(params, end)
            mesh = plate_build(spec, end, length, cut)
            c, n, e1, e2 = plate_frame(spec, end, length, cut)
        except Exception as exc:
            log.exception("igz_steel_rf: plate mesh failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось построить пластину: {exc}").format(exc=exc))
            return False
        name = f"Пластина {spec['w_mm']}×{spec['h_mm']}×{spec['t_mm']}"
        pg = Group(mesh=mesh, name=name)
        if getattr(group, "xform", None) is not None:
            pg.xform = QMatrix4x4(group.xform)
        pg.component = False
        pg.ifc = {"class": "IfcPlate", "name": name}
        block = {k: v for k, v in spec.items() if not k.startswith("_")}
        # the plate frame (centre + normal + in-plane axes, member local
        # frame) is stored so holes can be drilled / re-drilled parametrically
        block["frame"] = {"c": list(c), "n": list(n), "e1": list(e1), "e2": list(e2)}
        pg.ext = {KEY: {"plate": block}}
        err = run(self.app.viewport, insert_command(pg, layer_of(group)))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(tr("Установлена пластина {name} мм").format(name=name), 3000)
            except Exception:
                pass
        return True

    # -- holes drilled through plates ------------------------------------------
    def open_plate_holes(self):
        from ._plates import PlateHoleDialog, PlateHoleTool

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем сверлить пластины.")):
                return
            self.app.viewport.set_active_tool(PlateHoleTool(spec, self.apply_plate_holes))
        self._kept_dialog("plate_holes",
                          lambda: PlateHoleDialog(self.app.window, on_apply=apply))

    def apply_plate_holes(self, group, spec):
        """Drill one prepared row through the clicked plate: the row spec is
        stored in the plate ext and the plate mesh is rebuilt (box minus all
        rows) with ONE combined boolean, so rows stack without degrading the
        hole rims. The plate keeps identity, pose and layer; Undo restores."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем сверлить пластины.")):
            return False
        from ._plates import is_plate_group, plate_holed_mesh, plate_hole_fit
        if not is_plate_group(group):
            return False
        block = dict((group.ext or {}).get(KEY) or {})
        plate_spec = dict(block.get("plate") or {})
        if "frame" not in plate_spec:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("Эта пластина поставлена старой версией — установите её заново."), 3500)
                except Exception:
                    pass
            return False
        if not plate_hole_fit(spec, plate_spec):
            QMessageBox.information(self.app.window, tr("Сталь РФ"),
                                    tr("Ряд отверстий не помещается на пластине — уменьшите шаг, количество или отступ от края."))
            return False
        rows = list(block.get("holes") or []) + [spec]
        try:
            mesh = plate_holed_mesh(plate_spec, rows)
        except Exception as exc:
            log.exception("igz_steel_rf: plate holes failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось просверлить пластину: {exc}").format(exc=exc))
            return False
        parts = {"mesh": mesh, "xform": group.xform, "name": group.name,
                 "ifc": dict(group.ifc) if isinstance(group.ifc, dict) else {},
                 "ext": {KEY: {"plate": plate_spec, "holes": rows}}}
        err = run(self.app.viewport, rebuild_command(group, parts))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(f"{group.name}: просверлено {int(spec['count'])} отв. "
                      f"Ø{spec['dia_mm']} мм", 3000)
            except Exception:
                pass
        self._refresh_bom()
        return True

    def apply_plate_bolts(self, group, spec):
        """One bolt into every hole row stored in the clicked plate; seating
        faces are found by ray-tracing the plate itself (head on one face,
        nuts on the other), so the bolt clamps the plate along its normal."""
        from ._bolts import bolt_assembly_mesh
        from ._plates import plate_hole_positions
        from core.group import Group
        from core import solids
        from core.layers import layer_of
        block = (group.ext or {}).get(KEY) or {}
        rows = block.get("holes") or []
        if not rows:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("В пластине нет отверстий — сначала вырежьте их («Отверстия в пластине…»)"), 3500)
                except Exception:
                    pass
            return False
        plate_spec = block.get("plate") or {}
        fr = plate_spec.get("frame") or {}
        c, nrm = fr.get("c"), fr.get("n")
        e1, e2 = fr.get("e1"), fr.get("e2")
        if not all((c, nrm, e1, e2)):
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("Эта пластина поставлена старой версией — установите её заново."), 3500)
                except Exception:
                    pass
            return False
        try:
            sources = solids._Sources()
            man = solids._to_manifold(Group(mesh=group.mesh), sources)
        except Exception as exc:
            log.exception("igz_steel_rf: plate manifold failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Пластина не годится для болтов: {exc}").format(exc=exc))
            return False
        spots = []
        for hs in rows:
            for (a, b) in plate_hole_positions(hs, float(plate_spec["w"]),
                                               float(plate_spec["h"])):
                ctr = (c[0] + e1[0] * a + e2[0] * b,
                       c[1] + e1[1] * a + e2[1] * b,
                       c[2] + e1[2] * a + e2[2] * b)
                spots.append((ctr, hs))
        if spec.get("max"):
            spots = spots[:int(spec["max"])]
        from core.history import CompoundCommand
        layer = layer_of(group)
        cmds = []
        name = f"Болт {spec['size']}×{int(round(spec['L'] * 1000))}"
        for (p, hs) in spots:
            try:
                mesh = bolt_assembly_mesh(p, nrm, spec, man,
                                          float(hs.get("dia", 0.02)) / 2.0)
            except Exception as exc:
                log.exception("igz_steel_rf: plate bolt assembly failed")
                QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось собрать болт: {exc}").format(exc=exc))
                return False
            bg = Group(mesh=mesh, name=name)
            if getattr(group, "xform", None) is not None:
                from PySide6.QtGui import QMatrix4x4
                bg.xform = QMatrix4x4(group.xform)
            bg.component = False
            bg.ifc = {"class": "IfcMechanicalFastener", "name": name}
            bg.ext = {KEY: {"bolt": dict(spec)}}
            cmds.append(insert_command(bg, layer))
        err = run(self.app.viewport, CompoundCommand(cmds)) if cmds else None
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                flash(tr("Установлено болтов: {n} — {name}").format(n=len(spots), name=name), 3000)
            except Exception:
                pass
        self._refresh_bom()
        return True

    # -- mitre end cuts --------------------------------------------------------
    def open_cuts(self):
        from ._cuts import CutDialog, CutEndTool

        def apply(spec):
            if not self._guard(tr("Закройте редактируемую группу, прежде чем резать концы.")):
                return
            self.app.viewport.set_active_tool(CutEndTool(spec, self.apply_cut))
        self._kept_dialog("cuts", lambda: CutDialog(self.app.window, on_apply=apply))

    def apply_cut(self, group, end, spec):
        """Store (or remove) the mitre for the clicked end and rebuild the
        member from its profile: stored hole rows and cuts are re-applied in
        order, so hole patterns rotate with the bevel and undo restores the
        member exactly. Identity, pose and layer are kept."""
        if not self._guard(tr("Закройте редактируемую группу, прежде чем резать концы.")):
            return False
        params = member_params(group)
        if params is None:
            return False
        length = float(params.get("length", 0.0))
        if length < MIN_LENGTH:
            flash = getattr(self.app.viewport, "flash_status", None)
            if callable(flash):
                try:
                    flash(tr("Торец режется у вытянутого элемента — сначала вытяните профиль."), 3000)
                except Exception:
                    pass
            return False
        shape = self.db.find(params.get("label", ""))
        if shape is None:
            return False
        cuts = [c for c in (params.get("cuts") or []) if c.get("end") != end]
        cut = None
        if spec.get("action") == "cut" and float(spec.get("angle", 0.0)) > 0.0:
            prof = profile_for(shape, params)
            us = [p[0] for reg in prof.regions for p in reg.outer.points]
            vs = [p[1] for reg in prof.regions for p in reg.outer.points]
            hinge = spec.get("hinge", "center")
            hy = {"left": min(us), "right": max(us)}.get(hinge, 0.0)
            hz = {"bottom": min(vs), "top": max(vs)}.get(hinge, 0.0)
            cut = {"end": end, "angle": float(spec["angle"]),
                   "axis": spec.get("axis", "z"), "dir": int(spec.get("dir", 1)),
                   "hinge": hinge, "hy": float(hy), "hz": float(hz)}
            cuts.append(cut)
        p2 = dict(params)
        p2["cuts"] = cuts
        try:
            parts = member_parts(shape, p2, tuple(params.get("start") or (0.0, 0.0, 0.0)),
                                 tuple(params.get("direction") or (1.0, 0.0, 0.0)), length,
                                 scene=self.scene, db=self.db)
        except Exception as exc:
            log.exception("igz_steel_rf: mitre rebuild failed")
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), tr("Не удалось обрезать конец: {exc}").format(exc=exc))
            return False
        if getattr(group, "xform", None) is not None:
            parts["xform"] = group.xform
        if group.name:
            parts["name"] = group.name
        if isinstance(group.ifc, dict):
            parts["ifc"] = dict(group.ifc)
        err = run(self.app.viewport, rebuild_command(group, parts))
        if err:
            QMessageBox.critical(self.app.window, tr("Сталь РФ"), err)
            return False
        flash = getattr(self.app.viewport, "flash_status", None)
        if callable(flash):
            try:
                if cut:
                    side = tr("вокруг z") if cut["axis"] == "z" else tr("вокруг y")
                    flash(tr("{label}: торец срезан под {angle:g}° ({side})").format(label=shape.label, angle=cut["angle"], side=side), 3000)
                else:
                    flash(tr("{label}: торец выправлен (обрезка снята)").format(label=shape.label), 3000)
            except Exception:
                pass
        self._refresh_bom()
        return True

    # -- queries ------------------------------------------------------------
    def collect_bom(self):
        """Rolled members (catalogue kg/m), plates and fasteners (weight from
        the modelled volume x 7850 kg/m3 — approximate for bolts, whose
        threads are not modelled)."""
        from core.bim import face_set_volume
        from core.layers import layer_of
        records = []
        for g in iter_groups(self.scene):
            if is_steel_group(g):
                r = member_record(g, self.db)
                if r is not None:
                    records.append(r)
                continue
            block = (getattr(g, "ext", None) or {}).get(KEY)
            if not isinstance(block, dict):
                continue
            if "plate" in block:
                p = block["plate"]
                try:
                    vol = face_set_volume(g.mesh.faces)
                except Exception:
                    vol = 0.0
                label = (f"Пластина {p.get('w_mm', 0):g}×{p.get('h_mm', 0):g}"
                         f"×{p.get('t_mm', 0):g}")
                records.append({"label": label, "kind": "Пластина",
                                "family": "Пластины", "length_m": 0.0,
                                "weight_kg": vol * 7850.0,
                                "layer": layer_of(g),
                                "ifc_class": (g.ifc or {}).get("class", "")
                                if isinstance(g.ifc, dict) else "",
                                "uid": getattr(g, "uid", id(g))})
            elif "bolt" in block:
                b = block["bolt"]
                layer = layer_of(g)
                ifc_cls = ((g.ifc or {}).get("class", "")
                           if isinstance(g.ifc, dict) else "")
                uid = getattr(g, "uid", id(g))
                from ._bolts import fastener_parts
                try:
                    parts = fastener_parts(b)
                except Exception:
                    parts = None
                if parts is not None:
                    # count bolt, nut and washer as separate BOM items
                    for label, mass, qty in parts:
                        for _q in range(qty):
                            records.append({"label": label, "kind": "Крепёж",
                                            "family": "Крепёж", "length_m": 0.0,
                                            "weight_kg": mass, "layer": layer,
                                            "ifc_class": ifc_cls, "uid": uid})
                else:
                    try:
                        vol = face_set_volume(g.mesh.faces)
                    except Exception:
                        vol = 0.0
                    label = f"Болт {b.get('size', '')}×{round(float(b.get('L', 0.0)) * 1000):g}"
                    records.append({"label": label, "kind": "Крепёж",
                                    "family": "Крепёж", "length_m": 0.0,
                                    "weight_kg": vol * 7850.0,
                                    "layer": layer, "ifc_class": ifc_cls,
                                    "uid": uid})
            elif "anchor" in block:
                a = block["anchor"]
                layer = layer_of(g)
                ifc_cls = ((g.ifc or {}).get("class", "")
                           if isinstance(g.ifc, dict) else "")
                uid = getattr(g, "uid", id(g))
                from ._anchors import anchor_parts
                try:
                    parts = anchor_parts(a)
                except Exception:
                    parts = None
                if parts is None:
                    try:
                        vol = face_set_volume(g.mesh.faces)
                    except Exception:
                        vol = 0.0
                    parts = [(f"Анкер {a.get('size', '')}", vol, 1)]
                    parts = [(lbl, vol * 7850.0, q) for (lbl, vol, q) in parts]
                for label, mass, qty in parts:
                    for _q in range(qty):
                        records.append({"label": label, "kind": "Крепёж",
                                        "family": "Анкеры", "length_m": 0.0,
                                        "weight_kg": mass, "layer": layer,
                                        "ifc_class": ifc_cls, "uid": uid})
        return collect(records)

    def select_uid(self, uid):
        for g in iter_groups(self.scene):
            if getattr(g, "uid", None) == uid:
                self.scene.selection.clear()
                self.scene.selection.add(g)
                self.app.viewport.update()
                return

    def _refresh_bom(self):
        d = self.bom_dialog
        if d is not None and d.isVisible():
            d.refresh()

    def on_document_changed(self):
        self._refresh_bom()
        if self.dialog is not None and self.dialog.isVisible():
            self.dialog.set_layers(self.layer_names())
        # the host calls this on every scene-version bump (edits, selection
        # clicks): reload the dialog only when the grid block itself changed,
        # and not for our own Apply (on_grids_applied refreshes it quietly).
        # ``stale`` covers a viewport Delete whose save already consumed the
        # change when the host runs this hook after set_document_data returns.
        self.trusses.reload()
        changed = self.grids.reload()
        if self.grid_dialog_ is not None and not self._applying_grids:
            block = self.grids.raw_block()
            stale = block != self._dialog_block
            if changed or stale:
                self._dialog_block = block
                self.grid_dialog_.load_block(block, notice=tr("Перезагружено из документа"))
        try:
            self.app.viewport.update()
        except Exception:
            pass

    # -- host hooks ---------------------------------------------------------
    def context_menu(self, menu, selection):
        menu.addSeparator()
        grids = menu.addAction(tr("Оси стальных сеток…"))
        grids.triggered.connect(_deferred(self.open_grids))
        trusses = menu.addAction(tr("Оси ферм…"))
        trusses.triggered.connect(_deferred(self.open_trusses))
        if self.trusses.selected_id:
            dtr = menu.addAction(tr("Удалить выбранные оси фермы"))
            dtr.triggered.connect(_deferred(lambda: self.trusses.remove(self.trusses.selected_id)))
        if self.grids.selected_id:
            edit = menu.addAction(tr("Изменить ось сетки…"))
            edit.triggered.connect(_deferred(lambda: self.open_grids(self.grids.selected_id)))
            delete = menu.addAction(tr("Удалить ось сетки"))
            delete.triggered.connect(_deferred(self.delete_selected_grid))
        steel = []
        for item in selection:
            g = getattr(item, "owner", None) or item
            if is_steel_group(g) and g not in steel:
                steel.append(g)
        from ._plates import is_plate_group
        plate = None
        for item in selection:
            g = getattr(item, "owner", None) or item
            if is_plate_group(g):
                plate = g
                break
        if plate is not None:
            ph = menu.addAction(tr("Отверстия в пластине…"))
            ph.triggered.connect(_deferred(self.open_plate_holes))
            pb = menu.addAction(tr("Болты в отверстия пластины…"))
            pb.triggered.connect(_deferred(self.open_bolts))
        if len(steel) != 1:
            return
        edit = menu.addAction(tr("Изменить стальной профиль…"))
        edit.triggered.connect(_deferred(self.open_edit))
        stretch = menu.addAction(tr("Вытянуть стальной профиль"))
        stretch.triggered.connect(_deferred(self.open_stretch))
        holes = menu.addAction(tr("Отверстия на конце профиля…"))
        holes.triggered.connect(_deferred(self.open_holes))
        cuts = menu.addAction(tr("Обрезать конец под углом…"))
        cuts.triggered.connect(_deferred(self.open_cuts))
        bolts = menu.addAction(tr("Болты в отверстия…"))
        bolts.triggered.connect(_deferred(self.open_bolts))
        plates = menu.addAction(tr("Пластина на конце профиля…"))
        plates.triggered.connect(_deferred(self.open_plates))
        p0 = member_params(steel[0]) or {}
        if p0.get("trims"):
            untrim = menu.addAction(tr("Снять обрезку по профилю"))
            untrim.triggered.connect(_deferred(lambda g=steel[0]: self.remove_trims(g)))

    def outliner_kind(self, group):
        block = (getattr(group, "ext", None) or {}).get(KEY)
        if isinstance(block, dict) and "anchor" in block:
            a = block["anchor"]
            from core.layers import layer_of
            from ._anchors import TYPES
            tlabel = dict(TYPES).get(str(a.get("type")), str(a.get("type")))
            return {"type": tr("Анкерный болт"),
                    "props": [(tr("Размер"), str(a.get("size", ""))),
                              (tr("Тип"), tr(tlabel)),
                              (tr("Длина"), fmt_len(float(a.get("L", 0.0)))),
                              (tr("Выступ"), fmt_len(float(a.get("e", 0.0)))),
                              (tr("Слой"), layer_of(group))]}
        if not is_steel_group(group):
            return None
        p = member_params(group) or {}
        shape = self.db.find(p.get("label", ""))
        length = float(p.get("length", 0.0))
        weight = length * (shape.weight_per_m() if shape else 0.0)
        from core.layers import layer_of
        props = [(tr("Профиль"), p.get("label", "")), (tr("Длина"), fmt_len(length)),
                 (tr("Масса"), fmt_weight(weight)), (tr("Слой"), layer_of(group))]
        if p.get("trims"):
            props.append((tr("Обрезки по профилю"), tr("{n} шт").format(n=len(p["trims"]))))
        return {"type": tr("Стальной профиль") if length < MIN_LENGTH else tr("Стальной элемент"),
                "props": props}


def _install_toolbar(app, session):
    win = app.window
    if win is None or not hasattr(win, "addToolBar"):
        return None
    if win.findChild(QToolBar, TOOLBAR_NAME) is not None:
        return None
    tb = None
    maker = getattr(win, "_new_toolbar", None)
    if callable(maker):
        try:
            tb = maker(tr("Сталь РФ"), TOOLBAR_NAME)
        except Exception:
            tb = None
    if tb is None:
        tb = QToolBar(tr("Сталь РФ"), win)
        tb.setObjectName(TOOLBAR_NAME)
        tb.setMovable(True)
        tb.setFloatable(True)
        px = 24
        try:
            from views.icons import toolbar_icon_px
            px = toolbar_icon_px()
        except Exception:
            pass
        tb.setIconSize(QSize(px, px))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        win.addToolBar(Qt.TopToolBarArea, tb)
    entries = [("tb_place", tr("Разместить стальной профиль…"), session.open_place),
               ("tb_stretch", tr("Вытянуть стальной профиль"), session.open_stretch),
               ("tb_edit", tr("Изменить стальной профиль…"), session.open_edit),
               ("tb_holes", tr("Отверстия на конце профиля…"), session.open_holes),
               ("tb_cuts", tr("Обрезать конец под углом…"), session.open_cuts),
               ("tb_trims", tr("Обрезать профиль по другому профилю…"), session.open_trims),
               ("tb_bolts", tr("Болты в отверстия на конце профиля…"), session.open_bolts),
               ("tb_anchor", tr("Анкерные болты…"), session.open_anchors),
               ("tb_plates", tr("Пластина на конце профиля…"), session.open_plates),
               ("tb_plate_holes", tr("Отверстия в пластине…"), session.open_plate_holes),
               ("tb_bom", tr("Ведомость стали…"), session.open_bom),
               ("tb_grid", tr("Оси стальных сеток…"), session.open_grids),
               ("tb_truss", tr("Оси ферм…"), session.open_trusses),
               ("tb_options", tr("Настройки…"), session.open_options)]
    refs = []
    for icon, text, fn in entries:
        act = QAction(load_icon(icon, win), text, win)
        act.setToolTip(text)
        act.setStatusTip(text)
        act.triggered.connect(_deferred(fn))
        tb.addAction(act)
        refs.append(act)
    tb._igz_steel_rf_refs = refs
    return tb


def setup(app):
    from ._host import patch_ifc_export
    patch_ifc_export()                     # core export ignores group.xform: bake it
    db = load_db()                         # a broken JSON surfaces as a load error
    session = SteelSession(app, db)
    _SESSIONS[id(app)] = session
    session.grids.register()
    session.trusses.register()
    try:
        toolbar = _install_toolbar(app, session)
    except Exception:
        log.exception("igz_steel: toolbar install failed")
        toolbar = None
    menu = app.add_menu(tr("Сталь РФ"))
    if menu is not None:
        for text, fn in ((tr("Разместить профиль…"), session.open_place),
                         (tr("Вытянуть профиль"), session.open_stretch),
                         (tr("Изменить профиль…"), session.open_edit),
                         (tr("Отверстия на конце профиля…"), session.open_holes),
                         (tr("Обрезать конец под углом…"), session.open_cuts),
                         (tr("Обрезать профиль по другому…"), session.open_trims),
                         (tr("Болты в отверстия…"), session.open_bolts),
                         (tr("Анкерные болты…"), session.open_anchors),
                         (tr("Пластина на конце профиля…"), session.open_plates),
                         (tr("Отверстия в пластине…"), session.open_plate_holes),
                         (tr("Ведомость стали…"), session.open_bom),
                         (tr("Оси стальных сеток…"), session.open_grids),
                         (tr("Оси ферм…"), session.open_trusses),
                         (tr("Настройки…"), session.open_options)):
            menu.addAction(text, _deferred(fn))
        if toolbar is not None:
            menu.addSeparator()
            toggle = toolbar.toggleViewAction()
            toggle.setText(tr("Показать панель «Сталь РФ»"))
            menu.addAction(toggle)
    app.add_context_menu(session.context_menu)
    outliner = getattr(app, "add_outliner_kind", None)
    if callable(outliner):
        outliner(session.outliner_kind)
    app.on_document_changed(session.on_document_changed)

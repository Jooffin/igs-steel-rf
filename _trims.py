# SPDX-License-Identifier: GPL-3.0-or-later
"""Trim one steel member by another member\'s solid.

Two clicks: first the member to trim (e.g. a column), then the cutting
member (e.g. a beam). The trim is stored on the target as a uid link and
replayed as a solid subtraction on every rebuild of the target — the cut
therefore follows the cutter (rebuild the target after moving the beam)
and works at any angle, including skew.
"""
from __future__ import annotations

from tools.base import Tool

from ._host import is_steel_group
from ._i18n import tr
from ._tools import _flash, _leave


class TrimByMemberTool(Tool):
    """Click the member to trim, then the member to cut it with."""

    name = tr("Обрезать профиль по другому профилю")
    description = tr("Обрезать стальной профиль телом другого профиля (например верх колонны — балкой), в том числе под углом.")
    uses_snap = False

    def __init__(self, on_pick):
        self.on_pick = on_pick
        self.target = None

    def on_activate(self, viewport):
        _flash(viewport, tr("Клик 1 — какой профиль обрезать (например колонну); клик 2 — каким профилем (например балкой)  •  Esc — выход"), 5000)

    def on_deactivate(self, viewport):
        self.target = None

    def on_click(self, ctx):
        vp = ctx.viewport
        g = vp.pick_group(ctx.screen.x(), ctx.screen.y()) if hasattr(vp, "pick_group") else None
        if g is None or not is_steel_group(g):
            _flash(vp, tr("Кликните по стальному профилю расширения «Сталь РФ»."), 2500)
            return
        if self.target is None:
            self.target = g
            _flash(vp, tr("Теперь кликните по профилю-обрезчику — он останется целым."), 3500)
            return
        if g is self.target:
            _flash(vp, tr("Обрезчик не может быть тем же профилем — кликните по другому."), 2500)
            return
        if self.on_pick(self.target, g):
            self.target = None
            _leave(vp)

    def on_cancel(self, viewport):
        self.target = None
        _leave(viewport)

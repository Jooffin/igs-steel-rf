# SPDX-License-Identifier: GPL-3.0-or-later
"""Bill of Materials arithmetic. Pure Python; formatting is injected.

Three kinds of rows live side by side: rolled stock ("Прокат" — weight from
the catalogue kg/m x length), end plates ("Пластина" — weight from the model
volume x steel density) and fasteners ("Крепёж" — same, approximate because
threads are not modelled).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from ._db import FAMILIES
from ._geometry import MIN_LENGTH
from ._i18n import tr

KINDS = ("Прокат", "Пластина", "Крепёж")
KIND_RANK = {k: i for i, k in enumerate(KINDS)}
STEEL_DENSITY = 7850.0    # kg/m3, plates and fasteners


@dataclass
class Row:
    mark: str
    label: str
    family: str
    kind: str
    length_m: float
    weight_kg: float
    layer: str
    ifc_class: str
    uid: object

    @property
    def is_profile(self):
        return self.kind == "Прокат" and self.length_m < MIN_LENGTH


@dataclass
class SummaryRow:
    label: str
    family: str
    kind: str
    count: int
    total_length_m: float
    total_weight_kg: float


@dataclass
class BOM:
    rows: list
    summary: list
    count: int
    total_length_m: float
    total_weight_kg: float
    #: kind -> (count, total_length_m, total_weight_kg)
    totals_by_kind: dict = field(default_factory=dict)


def collect(records) -> BOM:
    rows = []
    counters = {}
    totals = {}
    by_kind = {k: [0, 0.0, 0.0] for k in KINDS}
    for rec in records:
        kind = str(rec.get("kind") or "Прокат")
        if kind not in KINDS:
            kind = "Прокат"
        label = str(rec["label"])
        counters[label] = counters.get(label, 0) + 1
        length = float(rec.get("length_m") or 0.0)
        if kind == "Прокат":
            is_profile = length < MIN_LENGTH
            weight = 0.0 if is_profile else length * float(rec.get("weight_per_m") or 0.0)
        else:
            is_profile = False
            weight = float(rec.get("weight_kg") or 0.0)
        rows.append(Row(f"{label}-{counters[label]}", label, str(rec.get("family", "")),
                        kind, length, weight, str(rec.get("layer") or "Layer 0"),
                        str(rec.get("ifc_class") or ""), rec.get("uid")))
        if kind == "Прокат" and is_profile:
            continue        # a bare cross-section counts nowhere in the totals
        k = by_kind.setdefault(kind, [0, 0.0, 0.0])
        k[0] += 1
        k[1] += length
        k[2] += weight
        t = totals.setdefault((kind, label), [str(rec.get("family", "")), 0, 0.0, 0.0])
        t[1] += 1
        t[2] += length
        t[3] += weight
    order = {f: i for i, f in enumerate(FAMILIES)}
    summary = [SummaryRow(label, fam, kind, n, L, w)
               for (kind, label), (fam, n, L, w) in totals.items()]
    summary.sort(key=lambda s: (KIND_RANK.get(s.kind, 99), order.get(s.family, 99), s.label))
    return BOM(rows, summary, sum(s.count for s in summary),
               sum(s.total_length_m for s in summary),
               sum(s.total_weight_kg for s in summary),
               {k: tuple(v) for k, v in by_kind.items()})


def to_csv(bom: BOM, fmt_len, fmt_weight) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([tr("Метка"), tr("Профиль/изделие"), tr("Группа"), tr("Тип"), tr("Длина"), tr("Масса"),
                tr("Слой"), tr("IFC"), "length_m", "weight_kg"])
    for r in bom.rows:
        w.writerow([r.mark, r.label, r.family, r.kind, fmt_len(r.length_m),
                    fmt_weight(r.weight_kg), r.layer, r.ifc_class,
                    round(r.length_m, 4), round(r.weight_kg, 2)])
    w.writerow([])
    w.writerow([tr("Профиль/изделие"), tr("Группа"), tr("Тип"), tr("Кол-во"), tr("Длина всего"),
                tr("Масса всего"), "total_length_m", "total_weight_kg"])
    for s in bom.summary:
        w.writerow([s.label, s.family, s.kind, s.count, fmt_len(s.total_length_m),
                    fmt_weight(s.total_weight_kg), round(s.total_length_m, 4),
                    round(s.total_weight_kg, 2)])
    for kind in KINDS:
        c, L, W = bom.totals_by_kind.get(kind, (0, 0.0, 0.0))
        if c:
            w.writerow([tr("ИТОГО {kind}").format(kind=kind), "", kind, c, fmt_len(L), fmt_weight(W),
                        round(L, 4), round(W, 2)])
    w.writerow([tr("TOTAL"), "", "", bom.count, fmt_len(bom.total_length_m),
                fmt_weight(bom.total_weight_kg), round(bom.total_length_m, 4),
                round(bom.total_weight_kg, 2)])
    return out.getvalue()

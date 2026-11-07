# SPDX-License-Identifier: GPL-3.0-or-later
"""Truss axes dialog: dimensions, lattice, placement, installation
tolerances; the live segment counts; the list of the document's trusses."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from ._i18n import tr
from ._truss import (LATTICES, TYPES, TrussError, counts, validate)

MM = 1000.0


def _mm_spin(lo, hi, default, step=1.0):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(1)
    s.setSingleStep(step)
    s.setValue(default)
    s.setSuffix(" мм")
    return s


class TrussesDialog(QDialog):
    """Modeless and kept open: the values survive between additions, so a
    series of trusses (Ф-1, Ф-2, ...) is placed by editing only the name
    and the insertion point."""

    def __init__(self, parent, store, on_change=None):
        super().__init__(parent)
        self.store = store
        self.on_change = on_change
        self.setWindowTitle(tr("Оси ферм"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.name = QLineEdit("Ф-1")
        form.addRow(tr("Имя"), self.name)
        self.type = QComboBox()
        for key, label in TYPES:
            self.type.addItem(tr(label), key)
        form.addRow(tr("Тип фермы"), self.type)
        self.L = _mm_spin(100.0, 200000.0, 24000.0, 500.0)
        form.addRow(tr("Пролёт L"), self.L)
        self.H = _mm_spin(100.0, 20000.0, 2400.0, 100.0)
        form.addRow(tr("Высота H"), self.H)
        self.haunch = _mm_spin(0.0, 100000.0, 4000.0, 500.0)
        form.addRow(tr("Скос трапеции a"), self.haunch)
        self.panels = QSpinBox()
        self.panels.setRange(2, 60)
        self.panels.setValue(12)
        form.addRow(tr("Панелей"), self.panels)
        self.lattice = QComboBox()
        for key, label in LATTICES:
            self.lattice.addItem(tr(label), key)
        form.addRow(tr("Решётка"), self.lattice)
        root.addLayout(form)

        place = QGroupBox(tr("Размещение"))
        pf = QFormLayout(place)
        row = QHBoxLayout()
        self.px = _mm_spin(-100000.0, 100000.0, 0.0, 100.0)
        self.py = _mm_spin(-100000.0, 100000.0, 0.0, 100.0)
        self.pz = _mm_spin(-100000.0, 100000.0, 0.0, 100.0)
        for lab, w in (("X", self.px), ("Y", self.py), ("Z", self.pz)):
            row.addWidget(QLabel(lab))
            row.addWidget(w)
        pf.addRow(tr("Левая опора"), row)
        self.az = QDoubleSpinBox()
        self.az.setRange(-360.0, 360.0)
        self.az.setDecimals(1)
        self.az.setSuffix("\u00b0")
        pf.addRow(tr("Поворот вокруг Z"), self.az)
        root.addWidget(place)

        tol = QGroupBox(tr("Допуски на установку профилей (для «Молодечно» обязательны)"))
        tf = QFormLayout(tol)
        self.t_top = _mm_spin(0.0, 2000.0, 0.0)
        tf.addRow(tr("Высота верхнего пояса"), self.t_top)
        self.t_bot = _mm_spin(0.0, 2000.0, 0.0)
        tf.addRow(tr("Высота нижнего пояса"), self.t_bot)
        self.t_gap = _mm_spin(0.0, 500.0, 0.0)
        tf.addRow(tr("Зазор g"), self.t_gap)
        self.t_shift = _mm_spin(-500.0, 500.0, 0.0)
        tf.addRow(tr("Сдвиг раскосов в плане e"), self.t_shift)
        root.addWidget(tol)

        self.preview = QLabel("")
        root.addWidget(self.preview)

        row2 = QHBoxLayout()
        self.add_btn = QPushButton(tr("Добавить ферму"))
        row2.addWidget(self.add_btn)
        root.addLayout(row2)

        self.list = QListWidget()
        root.addWidget(self.list)
        row3 = QHBoxLayout()
        self.del_btn = QPushButton(tr("Удалить выбранные"))
        self.del_btn.setEnabled(False)
        row3.addWidget(self.del_btn)
        root.addLayout(row3)

        for w in (self.name, self.type, self.L, self.H, self.haunch, self.panels,
                  self.lattice, self.px, self.py, self.pz, self.az,
                  self.t_top, self.t_bot, self.t_gap, self.t_shift):
            w.textChanged.connect(self._refresh) if isinstance(w, QLineEdit) else None
        for w in (self.type, self.lattice):
            w.currentIndexChanged.connect(self._refresh)
        for w in (self.L, self.H, self.haunch, self.az,
                  self.px, self.py, self.pz, self.t_top, self.t_bot,
                  self.t_gap, self.t_shift):
            w.valueChanged.connect(self._refresh)
        self.panels.valueChanged.connect(self._refresh)
        self.type.currentIndexChanged.connect(self._sync_enabled)
        self.add_btn.clicked.connect(self._add)
        self.del_btn.clicked.connect(self._delete)
        self.list.itemSelectionChanged.connect(
            lambda: self.del_btn.setEnabled(bool(self.list.selectedItems())))

        self._sync_enabled()
        self._refresh()
        self._reload_list()

    # -- ui helpers -----------------------------------------------------------
    def _sync_enabled(self):
        t = self.type.currentData()
        self.haunch.setEnabled(t == "trapezoid")

    def _spec(self):
        return {
            "name": self.name.text().strip(),
            "type": self.type.currentData(),
            "lattice": self.lattice.currentData(),
            "L": self.L.value() / MM, "H": self.H.value() / MM,
            "haunch": self.haunch.value() / MM,
            "panels": self.panels.value(),
            "place": {"x": self.px.value() / MM, "y": self.py.value() / MM,
                      "z": self.pz.value() / MM, "az": self.az.value()},
            "tol": {"top": self.t_top.value() / MM, "bottom": self.t_bot.value() / MM,
                    "gap": self.t_gap.value() / MM, "shift": self.t_shift.value() / MM},
        }

    def _refresh(self, *_a):
        try:
            c = counts(self._spec())
            self.preview.setText(
                tr("Линий: {total}  (поясов {chords}, раскосов {diags}, стоек {posts})").format(
                    total=c["top"] + c["bottom"] + c["diag"] + c["post"],
                    chords=c["top"] + c["bottom"], diags=c["diag"], posts=c["post"]))
            self.preview.setStyleSheet("")
        except TrussError as exc:
            self.preview.setText(str(exc))
            self.preview.setStyleSheet("color: #c04040;")

    def _reload_list(self):
        self.list.clear()
        for t in self.store.trusses:
            it = self.list.addItem(f"{t.get('name', '')}  "
                                   f"[{tr(dict(TYPES).get(t.get('type'), t.get('type')))}]")
            it.setData(t.get("id"))

    # -- actions ---------------------------------------------------------------
    def _add(self):
        try:
            spec = validate(self._spec())
        except TrussError as exc:
            self.preview.setText(str(exc))
            self.preview.setStyleSheet("color: #c04040;")
            return
        spec["id"] = None
        self.store.add(spec)
        self._reload_list()
        self._bump_name()
        if callable(self.on_change):
            self.on_change()

    def _bump_name(self):
        """Ф-1 -> Ф-2 -> ... so a run of trusses needs no typing."""
        base = self.name.text().strip()
        i = 0
        while i < len(base) and base[i].isdigit():
            i += 1
        if i and base[i] == "-":
            try:
                n = int(base[i + 1:])
                self.name.setText(base[:i + 1] + str(n + 1))
            except ValueError:
                pass

    def _delete(self):
        for it in self.list.selectedItems():
            tid = it.data()
            if tid is not None:
                self.store.remove(tid)
        self._reload_list()
        if callable(self.on_change):
            self.on_change()

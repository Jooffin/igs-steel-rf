# SPDX-License-Identifier: GPL-3.0-or-later
"""Options dialog: the plugin language. Applies to newly opened dialogs at
once; menus, the toolbar and the outliner follow the language after an
IngeTrazo restart."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QVBoxLayout,
                               QLabel, QPushButton)

from ._i18n import LANGS, current_lang, save_lang, tr


class OptionsDialog(QDialog):
    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self.setWindowTitle(tr("Настройки"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.lang = QComboBox()
        for _code, label in LANGS:
            self.lang.addItem(label, _code)
        idx = self.lang.findData(current_lang())
        self.lang.setCurrentIndex(max(0, idx))
        form.addRow(tr("Язык интерфейса"), self.lang)
        root.addLayout(form)

        self.note = QLabel(tr("Новые диалоги сразу говорят на выбранном языке. "
                              "Меню, панель инструментов и панель сцены "
                              "переключатся после перезапуска IngeTrazo."))
        self.note.setWordWrap(True)
        root.addWidget(self.note)

        self.apply = QPushButton(tr("Применить язык"))
        root.addWidget(self.apply)

        self.apply.clicked.connect(self._apply)

    def _apply(self):
        code = self.lang.currentData()
        if code not in ("ru", "en"):
            return
        save_lang(code)
        self.setWindowTitle(tr("Настройки"))
        flash = None
        try:
            flash = self.parent().viewport.flash_status
        except Exception:
            flash = None
        if callable(flash):
            flash(tr("Язык применён. Перезапустите IngeTrazo для меню и панели инструментов."),
                  4000)
        if callable(self.on_change):
            self.on_change()

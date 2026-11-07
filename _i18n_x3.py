# SPDX-License-Identifier: GPL-3.0-or-later
"""Russian<->English translations for _holes.py and _cuts.py (i18n batch 3)."""
T_EXTRA = {
    # -- _holes.py: combo labels (display text of ROWS / AXES) --------------
    "через стенку (ось горизонтальна)":
        ("через стенку (ось горизонтальна)", "through the web (axis horizontal)"),
    "через полку (ось вертикальна)":
        ("через полку (ось вертикальна)", "through the flange (axis vertical)"),
    "вдоль профиля (горизонтально)":
        ("вдоль профиля (горизонтально)", "along the profile (horizontal)"),
    "столбцом у торца (вертикально)":
        ("столбцом у торца (вертикально)", "in a column at the end (vertical)"),
    "вдоль кромки реза (подрезка конца)":
        ("вдоль кромки реза (подрезка конца)", "along the cut edge (end trim)"),
    # -- _holes.py: dialog ---------------------------------------------------
    "Отверстия на конце профиля": ("Отверстия на конце профиля", "Holes at the profile end"),
    "Диаметр отверстия:": ("Диаметр отверстия:", "Hole diameter:"),
    "Шаг ряда:": ("Шаг ряда:", "Row pitch:"),
    "Количество:": ("Количество:", "Count:"),
    "Размещение ряда:": ("Размещение ряда:", "Row layout:"),
    "От конца до 1-го отверстия:": ("От конца до 1-го отверстия:", "End to first hole:"),
    "Ось отверстий:": ("Ось отверстий:", "Axis of holes:"),
    "Смещение u (по полке):": ("Смещение u (по полке):", "Offset u (along the flange):"),
    "Смещение v (по высоте):": ("Смещение v (по высоте):", "Offset v (along the depth):"),
    "Сегментов окружности:": ("Сегментов окружности:", "Circle segments:"),
    "После закрытия диалога кликните по нужному концу\nстального профиля — ряд отверстий вырежется от этого конца.\nСтолбец: отверстия складываются по высоте вокруг смещения v.\n«Вдоль кромки реза» — ряд идёт параллельно кромке угловой\nподрезки этого конца (сначала обрежьте конец под углом).":
        ("После закрытия диалога кликните по нужному концу\nстального профиля — ряд отверстий вырежется от этого конца.\nСтолбец: отверстия складываются по высоте вокруг смещения v.\n«Вдоль кромки реза» — ряд идёт параллельно кромке угловой\nподрезки этого конца (сначала обрежьте конец под углом).",
         "After closing the dialog, click the required end of the\nsteel profile — the row of holes is cut from that end.\nA column stacks the holes along the depth around offset v.\n“Along the cut edge” runs the row parallel to the edge of the\nangled end trim at this end (cut the end at an angle first)."),
    # -- _holes.py: errors, tool, flashes -------------------------------------
    "вычитание не оставило материала":
        ("вычитание не оставило материала", "the subtraction left no material"),
    "Вырезать отверстия в профиле":
        ("Вырезать отверстия в профиле", "Cut holes in the profile"),
    "Вырезать ряд отверстий на конце стального профиля: клик по концу — отверстия вырежутся от этого конца.":
        ("Вырезать ряд отверстий на конце стального профиля: клик по концу — отверстия вырежутся от этого конца.",
         "Cut a row of holes at the end of a steel profile: click an end — the holes are cut from that end."),
    "столбец": ("столбец", "column"),
    "ряд": ("ряд", "row"),
    "вдоль реза": ("вдоль реза", "along the cut"),
    "Ø{dia:g} мм, {mode} {count} шт, шаг {pitch:g} мм: кликните по концу стального профиля  •  Esc — выход":
        ("Ø{dia:g} мм, {mode} {count} шт, шаг {pitch:g} мм: кликните по концу стального профиля  •  Esc — выход",
         "Ø{dia:g} mm, {mode} {count} pcs, pitch {pitch:g} mm: click the end of a steel profile  •  Esc — exit"),
    "Ø{dia:g} мм, {mode} {count} шт: клик  конец профиля  •  Esc  выход":
        ("Ø{dia:g} мм, {mode} {count} шт: клик  конец профиля  •  Esc  выход",
         "Ø{dia:g} mm, {mode} {count} pcs: click  profile end  •  Esc  exit"),
    # -- _cuts.py: combo labels (display text of CUT_AXES / HINGES) ----------
    "вокруг z — наклон в плане (угол виден сверху)":
        ("вокруг z — наклон в плане (угол виден сверху)", "about z — tilt in plan (angle seen from above)"),
    "вокруг y — наклон в фасад (угол виден сбоку)":
        ("вокруг y — наклон в фасад (угол виден сбоку)", "about y — tilt in elevation (angle seen from the side)"),
    "центр сечения": ("центр сечения", "section centre"),
    "верхняя грань (+z)": ("верхняя грань (+z)", "top face (+z)"),
    "нижняя грань (−z)": ("нижняя грань (−z)", "bottom face (−z)"),
    "левая сторона (−y)": ("левая сторона (−y)", "left side (−y)"),
    "правая сторона (+y)": ("правая сторона (+y)", "right side (+y)"),
    # -- _cuts.py: dialog ------------------------------------------------------
    "Обрезать конец под углом": ("Обрезать конец под углом", "Mitre the end"),
    "Обрезать конец": ("Обрезать конец", "Cut the end"),
    "Вернуть прямой торец": ("Вернуть прямой торец", "Restore a square end"),
    "в сторону +y / +z": ("в сторону +y / +z", "towards +y / +z"),
    "в сторону −y / −z": ("в сторону −y / −z", "towards −y / −z"),
    "Действие:": ("Действие:", "Action:"),
    "Угол реза:": ("Угол реза:", "Cut angle:"),
    "Ось поворота реза:": ("Ось поворота реза:", "Cut rotation axis:"),
    "Направление наклона:": ("Направление наклона:", "Tilt direction:"),
    "Опора реза (ось поворота):": ("Опора реза (ось поворота):", "Cut hinge (rotation axis):"),
    "Кликните по концу стального профиля — его торец срежется\nплоскостью под заданным углом. Опора реза — грань, вокруг\nкоторой поворачивается плоскость: для наклона в фасад —\nверх/низ элемента, для наклона в план — левая/правая\nсторона («центр сечения» — как раньше, через ось).\nОтверстия, пластины и болты на этом конце размещаются\nпараллельно отрезу. «Вернуть прямой торец» снимает обрезку.":
        ("Кликните по концу стального профиля — его торец срежется\nплоскостью под заданным углом. Опора реза — грань, вокруг\nкоторой поворачивается плоскость: для наклона в фасад —\nверх/низ элемента, для наклона в план — левая/правая\nсторона («центр сечения» — как раньше, через ось).\nОтверстия, пластины и болты на этом конце размещаются\nпараллельно отрезу. «Вернуть прямой торец» снимает обрезку.",
         "Click the end of a steel profile — its end face is cut by a\nplane at the given angle. The cut hinge is the face the plane\nrotates around: for an elevation tilt — the top/bottom of the\nmember, for a plan tilt — the left/right side (“section centre” —\nas before, through the axis). Holes, plates and bolts at this end\nare placed parallel to the cut. “Restore a square end” removes\nthe trim."),
    # -- _cuts.py: errors, tool, flashes ---------------------------------------
    "подрезка не оставила материала":
        ("подрезка не оставила материала", "the trim left no material"),
    "Обрезать конец профиля под углом":
        ("Обрезать конец профиля под углом", "Mitre the profile end"),
    "Срезать торец стального профиля под углом: клик по концу — плоскость реза проходит через ось профиля на этом конце.":
        ("Срезать торец стального профиля под углом: клик по концу — плоскость реза проходит через ось профиля на этом конце.",
         "Cut the end face of a steel profile at an angle: click an end — the cut plane passes through the profile axis at that end."),
    "Рез {angle:g}° ({axis}): кликните по концу стального профиля  •  Esc — выход":
        ("Рез {angle:g}° ({axis}): кликните по концу стального профиля  •  Esc — выход",
         "Cut {angle:g}° ({axis}): click the end of a steel profile  •  Esc — exit"),
    "Кликните по концу профиля, чтобы вернуть ему прямой торец  •  Esc — выход":
        ("Кликните по концу профиля, чтобы вернуть ему прямой торец  •  Esc — выход",
         "Click the end of the profile to restore its square end  •  Esc — exit"),
    "прямой торец: клик  конец профиля  •  Esc  выход":
        ("прямой торец: клик  конец профиля  •  Esc  выход",
         "square end: click  profile end  •  Esc  exit"),
    "рез {angle:g}°: клик  конец профиля  •  Esc  выход":
        ("рез {angle:g}°: клик  конец профиля  •  Esc  выход",
         "cut {angle:g}°: click  profile end  •  Esc  exit"),
    # -- shared by both dialogs/tools ------------------------------------------
    "Применить": ("Применить", "Apply"),
    "Закрыть": ("Закрыть", "Close"),
    "Отмена": ("Отмена", "Cancel"),
    "Кликните по стальному профилю, созданному расширением «Сталь РФ».":
        ("Кликните по стальному профилю, созданному расширением «Сталь РФ».",
         "Click a steel profile created by the “Steel RF” extension."),
}

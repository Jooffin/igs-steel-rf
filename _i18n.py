# SPDX-License-Identifier: GPL-3.0-or-later
"""Language settings and the translation lookup for the whole plugin.

``tr(key)`` returns the display string for the saved language; the key is
the Russian source text (or, for texts ported from the English upstream,
the English original), so unwrapped strings keep working when a
translation is missing. The language is stored in ``settings.json`` next
to this module, shared by all documents, and applied by the options
dialog: newly opened dialogs follow it at once; menus, the toolbar and
the outliner are rebuilt when IngeTrazo restarts.
"""
from __future__ import annotations

import importlib
import json
import os

LANGS = [("ru", "Русский"), ("en", "English")]
DEFAULT_LANG = "ru"

_cache = None


def settings_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    lang = DEFAULT_LANG
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("lang") in ("ru", "en"):
            lang = data["lang"]
    except Exception:
        pass
    _cache = {"lang": lang}
    return _cache


def save_lang(lang: str) -> None:
    global _cache
    if lang not in ("ru", "en"):
        raise ValueError("unknown language")
    _cache = {"lang": lang}
    try:
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump({"lang": lang}, fh, ensure_ascii=False)
    except Exception:
        pass


def current_lang() -> str:
    return load()["lang"]


def tr(key: str) -> str:
    entry = T.get(key)
    if not entry:
        return key
    ru, en = entry
    return ru if current_lang() == "ru" else en


# key: (russian, english). Merged with the generated batches below.
T = {
    # -- titles, menus, toolbar ------------------------------------------
    "Сталь РФ": ("Сталь РФ", "Steel RF"),
    "Разместить стальной профиль…": ("Разместить стальной профиль…", "Place a steel profile…"),
    "Вытянуть стальной профиль": ("Вытянуть стальной профиль", "Stretch a steel profile"),
    "Изменить стальной профиль…": ("Изменить стальной профиль…", "Edit a steel profile…"),
    "Отверстия на конце профиля…": ("Отверстия на конце профиля…", "Holes at the profile end…"),
    "Обрезать конец под углом…": ("Обрезать конец под углом…", "Mitre the end…"),
    "Обрезать профиль по другому профилю…": ("Обрезать профиль по другому профилю…", "Trim profile by another profile…"),
    "Болты в отверстия на конце профиля…": ("Болты в отверстия на конце профиля…", "Bolts into end holes…"),
    "Пластина на конце профиля…": ("Пластина на конце профиля…", "End plate…"),
    "Отверстия в пластине…": ("Отверстия в пластине…", "Holes in plate…"),
    "Ведомость стали…": ("Ведомость стали…", "Steel schedule…"),
    "Оси стальных сеток…": ("Оси стальных сеток…", "Steel grid axes…"),
    "Оси ферм…": ("Оси ферм…", "Truss axes…"),
    "Настройки…": ("Настройки…", "Options…"),
    "Разместить профиль…": ("Разместить профиль…", "Place profile…"),
    "Вытянуть профиль": ("Вытянуть профиль", "Stretch profile"),
    "Изменить профиль…": ("Изменить профиль…", "Edit profile…"),
    "Обрезать профиль по другому…": ("Обрезать профиль по другому…", "Trim by another profile…"),
    "Показать панель «Сталь РФ»": ("Показать панель «Сталь РФ»", "Show the “Steel RF” toolbar"),
    # -- context menu ------------------------------------------------------
    "Изменить ось сетки…": ("Изменить ось сетки…", "Edit grid axis…"),
    "Удалить ось сетки": ("Удалить ось сетки", "Delete grid axis"),
    "Удалить выбранные оси фермы": ("Удалить выбранные оси фермы", "Delete selected truss axes"),
    "Болты в отверстия…": ("Болты в отверстия…", "Bolts into holes…"),
    "Снять обрезку по профилю": ("Снять обрезку по профилю", "Remove profile trim"),
    # -- guards, dialogs, flashes -------------------------------------------
    "Закройте редактируемую группу, прежде чем размещать или менять стальные профили.":
        ("Закройте редактируемую группу, прежде чем размещать или менять стальные профили.",
         "Close the group being edited before placing or changing steel profiles."),
    "Закройте редактируемую группу, прежде чем менять оси сеток.":
        ("Закройте редактируемую группу, прежде чем менять оси сеток.",
         "Close the group being edited before changing grid axes."),
    "Закройте редактируемую группу, прежде чем вырезать отверстия.":
        ("Закройте редактируемую группу, прежде чем вырезать отверстия.",
         "Close the group being edited before cutting holes."),
    "Закройте редактируемую группу, прежде чем ставить болты.":
        ("Закройте редактируемую группу, прежде чем ставить болты.",
         "Close the group being edited before placing bolts."),
    "Закройте редактируемую группу, прежде чем обрезать профиль.":
        ("Закройте редактируемую группу, прежде чем обрезать профиль.",
         "Close the group being edited before trimming a profile."),
    "Закройте редактируемую группу, прежде чем ставить пластины.":
        ("Закройте редактируемую группу, прежде чем ставить пластины.",
         "Close the group being edited before placing plates."),
    "Закройте редактируемую группу, прежде чем сверлить пластины.":
        ("Закройте редактируемую группу, прежде чем сверлить пластины.",
         "Close the group being edited before drilling plates."),
    "Закройте редактируемую группу, прежде чем резать концы.":
        ("Закройте редактируемую группу, прежде чем резать концы.",
         "Close the group being edited before cutting ends."),
    "Выберите ровно один стальной профиль, созданный этим расширением.":
        ("Выберите ровно один стальной профиль, созданный этим расширением.",
         "Select exactly one steel profile created by this extension."),
    "Неизвестный профиль {label!r} в этом элементе.":
        ("Неизвестный профиль {label!r} в этом элементе.",
         "Unknown profile {label!r} in this element."),
    "Оси сеток": ("Оси сеток", "Grid axes"),
    "Удалить ось {name} с {n} ур.(-ями)?":
        ("Удалить ось {name} с {n} ур.(-ями)?", "Delete axis {name} with {n} level(s)?"),
    "Не удалось сохранить оси сетки: {exc}":
        ("Не удалось сохранить оси сетки: {exc}", "Could not save the grid axes: {exc}"),
    "Профиля больше нет в документе. Выберите его заново.":
        ("Профиля больше нет в документе. Выберите его заново.",
         "The profile is no longer in the document. Select it again."),
    "Не удалось построить профиль: {exc}":
        ("Не удалось построить профиль: {exc}", "Could not build the profile: {exc}"),
    "Не удалось перестроить профиль: {exc}":
        ("Не удалось перестроить профиль: {exc}", "Could not rebuild the profile: {exc}"),
    "Отверстия вырезаются у вытянутого элемента: сначала вытяните профиль (или задайте длину).":
        ("Отверстия вырезаются у вытянутого элемента: сначала вытяните профиль (или задайте длину).",
         "Holes are cut on stretched elements: stretch the profile first (or set a length)."),
    "Ряд отверстий не помещается на длине профиля — уменьшите отступ, шаг или количество.":
        ("Ряд отверстий не помещается на длине профиля — уменьшите отступ, шаг или количество.",
         "The hole row does not fit along the profile length — reduce the edge distance, pitch or count."),
    "Ряд отверстий лежит вне материала сечения — проверьте смещения u/v (они задаются по не повернутому сечению, без учёта крена).":
        ("Ряд отверстий лежит вне материала сечения — проверьте смещения u/v (они задаются по не повернутому сечению, без учёта крена).",
         "The hole row lies outside the section material — check the u/v offsets (offsets are defined on the un-rolled section, ignoring roll)."),
    "Не удалось вырезать отверстия: {exc}":
        ("Не удалось вырезать отверстия: {exc}", "Could not cut the holes: {exc}"),
    "На этом конце нет вырезанных отверстий — сначала прорежьте их («Отверстия на конце профиля…»)":
        ("На этом конце нет вырезанных отверстий — сначала прорежьте их («Отверстия на конце профиля…»)",
         "No holes cut at this end — cut them first (“Holes at the profile end…”)."),
    "Профиль не годится для болтов: {exc}":
        ("Профиль не годится для болтов: {exc}", "The profile is not suitable for bolts: {exc}"),
    "Не удалось собрать болт: {exc}":
        ("Не удалось собрать болт: {exc}", "Could not assemble the bolt: {exc}"),
    "Установлено болтов: {n} — {name}":
        ("Установлено болтов: {n} — {name}", "Bolts placed: {n} — {name}"),
    "Профиль не может обрезать сам себя.":
        ("Профиль не может обрезать сам себя.", "A profile cannot trim itself."),
    "Не удалось обрезать профиль: {exc}":
        ("Не удалось обрезать профиль: {exc}", "Could not trim the profile: {exc}"),
    "Обрезка по профилю применена": ("Обрезка по профилю применена", "Profile trim applied"),
    "Обрезки по профилю сняты": ("Обрезки по профилю сняты", "Profile trims removed"),
    "Пластина ставится на вытянутый элемент — сначала вытяните его.":
        ("Пластина ставится на вытянутый элемент — сначала вытяните его.",
         "A plate is placed on a stretched element — stretch it first."),
    "Не удалось построить пластину: {exc}":
        ("Не удалось построить пластину: {exc}", "Could not build the plate: {exc}"),
    "Установлена пластина {name} мм": ("Установлена пластина {name} мм", "Plate placed {name} mm"),
    "Эта пластина поставлена старой версией — установите её заново.":
        ("Эта пластина поставлена старой версией — установите её заново.",
         "This plate was placed by an older version — place it again."),
    "Ряд отверстий не помещается на пластине — уменьшите шаг, количество или отступ от края.":
        ("Ряд отверстий не помещается на пластине — уменьшите шаг, количество или отступ от края.",
         "The hole row does not fit on the plate — reduce the pitch, count or edge distance."),
    "Не удалось просверлить пластину: {exc}":
        ("Не удалось просверлить пластину: {exc}", "Could not drill the plate: {exc}"),
    "В пластине нет отверстий — сначала вырежьте их («Отверстия в пластине…»)":
        ("В пластине нет отверстий — сначала вырежьте их («Отверстия в пластине…»)",
         "The plate has no holes — cut them first (“Holes in plate…”)."),
    "Пластина не годится для болтов: {exc}":
        ("Пластина не годится для болтов: {exc}", "The plate is not suitable for bolts: {exc}"),
    "Торец режется у вытянутого элемента — сначала вытяните профиль.":
        ("Торец режется у вытянутого элемента — сначала вытяните профиль.",
         "Ends are cut on stretched elements — stretch the profile first."),
    "Не удалось обрезать конец: {exc}":
        ("Не удалось обрезать конец: {exc}", "Could not cut the end: {exc}"),
    "вокруг z": ("вокруг z", "about z"),
    "вокруг y": ("вокруг y", "about y"),
    "Перезагружено из документа": ("Перезагружено из документа", "Reloaded from the document"),
    # -- outliner and BOM kinds ---------------------------------------------
    "Профиль": ("Профиль", "Profile"),
    "Длина": ("Длина", "Length"),
    "Масса": ("Масса", "Weight"),
    "Слой": ("Слой", "Layer"),
    "Обрезки по профилю": ("Обрезки по профилю", "Profile trims"),
    "{n} шт": ("{n} шт", "{n} pcs"),
    "Стальной профиль": ("Стальной профиль", "Steel profile"),
    "Стальной элемент": ("Стальной элемент", "Steel element"),
    "Пластина": ("Пластина", "Plate"),
    "Пластины": ("Пластины", "Plates"),
    "Крепёж": ("Крепёж", "Fasteners"),
    "Прокат": ("Прокат", "Rolled stock"),
    "{label}: торец срезан под {angle:g}° ({side})":
        ("{label}: торец срезан под {angle:g}° ({side})",
         "{label}: end cut at {angle:g}° ({side})"),
    "{label}: торец выправлен (обрезка снята)":
        ("{label}: торец выправлен (обрезка снята)",
         "{label}: end straightened (cut removed)"),
    # -- options dialog --------------------------------------------------------
    "Настройки": ("Настройки", "Options"),
    "Язык интерфейса": ("Язык интерфейса", "Interface language"),
    "Новые диалоги сразу говорят на выбранном языке. Меню, панель инструментов и панель сцены переключатся после перезапуска IngeTrazo.":
        ("Новые диалоги сразу говорят на выбранном языке. Меню, панель инструментов и панель сцены переключатся после перезапуска IngeTrazo.",
         "Newly opened dialogs use the selected language right away. Menus, the toolbar and the scene panel switch after restarting IngeTrazo."),
    "Применить язык": ("Применить язык", "Apply language"),
    "Язык применён. Перезапустите IngeTrazo для меню и панели инструментов.":
        ("Язык применён. Перезапустите IngeTrazo для меню и панели инструментов.",
         "Language applied. Restart IngeTrazo for the menus and the toolbar."),
    # -- anchor bolts ------------------------------------------------------------
    "Анкерные болты…": ("Анкерные болты…", "Anchor bolts…"),
    "Анкерные болты": ("Анкерные болты", "Anchor bolts"),
    "Закройте редактируемую группу, прежде чем ставить анкеры.":
        ("Закройте редактируемую группу, прежде чем ставить анкеры.",
         "Close the group being edited before placing anchors."),
    "Не удалось построить анкер: {exc}":
        ("Не удалось построить анкер: {exc}", "Could not build the anchor: {exc}"),
    "Установлен {name} — ещё клик ставит следующий, Esc — выход":
        ("Установлен {name} — ещё клик ставит следующий, Esc — выход",
         "{name} placed — click again for another anchor, Esc to exit."),
    "Анкерный болт": ("Анкерный болт", "Anchor bolt"),
    "Размер": ("Размер", "Size"),
    "Выступ": ("Выступ", "Projection"),
    "неизвестный диаметр анкера {size}":
        ("неизвестный диаметр анкера {size}", "unknown anchor diameter {size}"),
    "выступ не может превышать длину анкера":
        ("выступ не может превышать длину анкера",
         "the projection cannot exceed the anchor length"),
    "неизвестный тип анкера {type}":
        ("неизвестный тип анкера {type}", "unknown anchor type {type}"),
    "объединение анкера не удалось":
        ("объединение анкера не удалось", "the anchor union failed"),
    "Анкер ставится в точку клика (снап ловит узлы, оси сеток и ферм): поверхность установки — основание гайки и шайбы. Ещё клик — ещё анкер, Esc — выход.":
        ("Анкер ставится в точку клика (снап ловит узлы, оси сеток и ферм): поверхность установки — основание гайки и шайбы. Ещё клик — ещё анкер, Esc — выход.",
         "The anchor is placed at the click point (snapping catches nodes, grid and truss axes): the washer and nut sit on the mounting surface. Click again for another anchor, Esc to exit."),
    "Тип анкера": ("Тип анкера", "Anchor type"),
    "Диаметр": ("Диаметр", "Diameter"),
    "Длина L": ("Длина L", "Length L"),
    "Выступ над поверхностью": ("Выступ над поверхностью", "Projection above surface"),
    "Поворот крюка": ("Поворот крюка", "Hook rotation"),
    "Вертикально вверх": ("Вертикально вверх", "Vertically up"),
    "Вертикально вниз": ("Вертикально вниз", "Vertically down"),
    "Направление": ("Направление", "Direction"),
    "1 — с загнутым концом (крюк)": ("1 — с загнутым концом (крюк)", "1 — bent end (hook)"),
    "2 — с анкерной плитой": ("2 — с анкерной плитой", "2 — with anchor plate"),
    "4 — шпилька, резьба с двух сторон": ("4 — шпилька, резьба с двух сторон", "4 — stud, threaded at both ends"),
    "Поставить анкерный болт": ("Поставить анкерный болт", "Place an anchor bolt"),
    "Поставить анкерный болт (ГОСТ 24379): клик по точке — анкер вертикально, ещё клик — ещё анкер.":
        ("Поставить анкерный болт (ГОСТ 24379): клик по точке — анкер вертикально, ещё клик — ещё анкер.",
         "Place a GOST 24379 anchor bolt: click a point — the anchor stands vertically; click again for another."),
    "Анкер {size}×{L:g} тип {t}: кликните точку установки  •  ещё клик — ещё анкер  •  Esc — выход":
        ("Анкер {size}×{L:g} тип {t}: кликните точку установки  •  ещё клик — ещё анкер  •  Esc — выход",
         "Anchor {size}×{L:g} type {t}: click an installation point  •  click again for another  •  Esc to exit"),
    # -- tools -------------------------------------------------------------------
    "Обрезать профиль по другому профилю":
        ("Обрезать профиль по другому профилю", "Trim profile by another profile"),
    "Обрезать стальной профиль телом другого профиля (например верх колонны — балкой), в том числе под углом.":
        ("Обрезать стальной профиль телом другого профиля (например верх колонны — балкой), в том числе под углом.",
         "Trim a steel profile by the solid of another profile (e.g. a column top by a beam), including at an angle."),
    "Клик 1 — какой профиль обрезать (например колонну); клик 2 — каким профилем (например балкой)  •  Esc — выход":
        ("Клик 1 — какой профиль обрезать (например колонну); клик 2 — каким профилем (например балкой)  •  Esc — выход",
         "Click 1 — the profile to trim (e.g. a column); click 2 — the profile to cut with (e.g. a beam)  •  Esc — exit"),
    "Кликните по стальному профилю расширения «Сталь РФ».":
        ("Кликните по стальному профилю расширения «Сталь РФ».",
         "Click a steel profile of the “Steel RF” extension."),
    "Теперь кликните по профилю-обрезчику — он останется целым.":
        ("Теперь кликните по профилю-обрезчику — он останется целым.",
         "Now click the cutter profile — it stays intact."),
    "Обрезчик не может быть тем же профилем — кликните по другому.":
        ("Обрезчик не может быть тем же профилем — кликните по другому.",
         "The cutter cannot be the same profile — click another one."),
    "Разместить стальной профиль":
        ("Разместить стальной профиль", "Place a steel profile"),
    "Разместить стальной профиль по ГОСТ: клик — начало, затем клик — конец или длина с клавиатуры.":
        ("Разместить стальной профиль по ГОСТ: клик — начало, затем клик — конец или длина с клавиатуры.",
         "Place a GOST steel profile: click the start, then click the end or type a length."),
    "Вытянуть стальной профиль":
        ("Вытянуть стальной профиль", "Stretch a steel profile"),
    "Вытянуть стальной профиль: клик по концу, затем клик или новая длина с клавиатуры.":
        ("Вытянуть стальной профиль: клик по концу, затем клик или новая длина с клавиатуры.",
         "Stretch a steel profile: click an end, then click or type a new length."),
    "Длина": ("Длина", "Length"),
    "{label}: элемент создан ({length}). Клик — разместить ещё, Esc — выход":
        ("{label}: элемент создан ({length}). Клик — разместить ещё, Esc — выход",
         "{label}: element created ({length}). Click to place another, Esc to exit."),
    # -- grid host flashes ------------------------------------------------------
    "Grid {name}: {n} level(s). Delete removes it.":
        ("Ось «{name}»: уровней {n}. Удаление — клавишей Delete.",
         "Grid {name}: {n} level(s). Delete removes it."),
    "Не удалось удалить ось сетки":
        ("Не удалось удалить ось сетки", "Could not delete the grid axis"),
    # -- truss dialog ------------------------------------------------------------
    "Оси ферм": ("Оси ферм", "Truss axes"),
    "Имя": ("Имя", "Name"),
    "Тип фермы": ("Тип фермы", "Truss type"),
    "Пролёт L": ("Пролёт L", "Span L"),
    "Высота H": ("Высота H", "Height H"),
    "Скос трапеции a": ("Скос трапеции a", "Trapezoid haunch a"),
    "Панелей": ("Панелей", "Panels"),
    "Решётка": ("Решётка", "Lattice"),
    "Размещение": ("Размещение", "Placement"),
    "Левая опора": ("Левая опора", "Left support"),
    "Поворот вокруг Z": ("Поворот вокруг Z", "Rotation about Z"),
    "Допуски на установку профилей (для «Молодечно» обязательны)":
        ("Допуски на установку профилей (для «Молодечно» обязательны)",
         "Profile installation tolerances (required for “Molodcheno”)"),
    "Высота верхнего пояса": ("Высота верхнего пояса", "Top chord height"),
    "Высота нижнего пояса": ("Высота нижнего пояса", "Bottom chord height"),
    "Зазор g": ("Зазор g", "Gap g"),
    "Сдвиг раскосов в плане e": ("Сдвиг раскосов в плане e", "Web members plan offset e"),
    "Добавить ферму": ("Добавить ферму", "Add truss"),
    "Удалить выбранные": ("Удалить выбранные", "Delete selected"),
    "Балка (параллельные пояса)": ("Балка (параллельные пояса)", "Beam (parallel chords)"),
    "Молодечно (пояса параллельны, с допусками)":
        ("Молодечно (пояса параллельны, с допусками)", "Molodcheno (parallel chords, with tolerances)"),
    "Треугольная": ("Треугольная", "Triangular"),
    "Трапецеидальная": ("Трапецеидальная", "Trapezoidal"),
    "треугольная решётка (раскосы в шахматном порядке)":
        ("треугольная решётка (раскосы в шахматном порядке)", "triangular lattice (alternating diagonals)"),
    "раскосная решётка (раскосы + стойки)":
        ("раскосная решётка (раскосы + стойки)", "diagonal lattice (diagonals + posts)"),
    "вертикальная решётка (только стойки)":
        ("вертикальная решётка (только стойки)", "vertical lattice (posts only)"),
    # -- truss axes -----------------------------------------------------------
    "Оси фермы «{name}»: {n} линий. Delete удаляет оси.":
        ("Оси фермы «{name}»: {n} линий. Delete удаляет оси.",
         "Truss axes “{name}”: {n} lines. Delete removes them."),
    "Линий: {total}  (поясов {chords}, раскосов {diags}, стоек {posts})":
        ("Линий: {total}  (поясов {chords}, раскосов {diags}, стоек {posts})",
         "Lines: {total}  (chords {chords}, diagonals {diags}, posts {posts})"),
}

# merge the generated translation batches
for _name in ("_i18n_x1", "_i18n_x2", "_i18n_x3", "_i18n_x4"):
    try:
        _mod = importlib.import_module("." + _name, __package__)
    except Exception:
        continue
    for _k, _v in (getattr(_mod, "T_EXTRA", {}) or {}).items():
        T.setdefault(_k, _v)

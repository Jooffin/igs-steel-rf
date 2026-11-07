# SPDX-License-Identifier: GPL-3.0-or-later
"""igz_steel_rf — стальные профили по ГОСТ РФ для IngeTrazo.

Ветко (fork) расширения igz_steel (© dns-0, GPL-3.0-or-later): архитектура,
инструменты размещения/вытягивания, BOM и оси сеток — из igz_steel; каталог
профилей заменён на российский сортамент (6019 профилей: двутавры ГОСТ 8239-89,
26020-83, Р 57837-2017, СТО АСЧМ 20-93 и ТУ; швеллеры ГОСТ 8240-89/97, 5267.1-90;
уголки ГОСТ 8509-93, 8510-86; тавры ТУ 14-2-685-86; трубы ГОСТ 8732-78, 10704-91,
8639-82, 8645-68, 30245-2012, 32931-2015; круг/квадрат/полоса ГОСТ 2590, 2591,
7417, 103, 82). Источник данных — ViewProf.

Entry point only. IngeTrazo instantiates every ``Tool`` subclass defined in
this module with no arguments, so no Tool lives here: the tools are in
``_tools.py`` and the wiring in ``_core.py``.
"""
from __future__ import annotations

KEY = "igz_steel_rf"
EXT_VERSION = 1
__version__ = "0.1"


def setup(app):
    """Extension API v2 entry point, called once when the main window exists."""
    from ._core import setup as _setup
    _setup(app)

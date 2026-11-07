# Third-Party Notices

This project is distributed under **GPL-3.0-or-later** — see [LICENSE](LICENSE).

## 1. IngeTrazo

The extension API used here belongs to **IngeTrazo** by the Ingelibre project —
<https://github.com/ingelibre/ingetrazo> — licensed **GPL-3.0-or-later**. No
IngeTrazo source code is vendored here; the plugin calls its runtime API.

## 2. igz_steel (upstream fork source)

This extension is a fork of **igz_steel** by dns-0 —
<https://github.com/dns-0/igz_steel> — licensed **GPL-3.0-or-later**. The
architecture, placement/stretch tools, Bill of Materials and grid axes are
inherited from it; the AISC catalog has been removed and replaced.

## 3. Russian rolled-section catalog (ГОСТ / СТО / ТУ)

`data/gost_rf.json` is compiled from published Russian rolled-stock tables
(ГОСТ 8239-89, 26020-83, Р 57837-2017, СТО АСЧМ 20-93, ГОСТ 19425-74,
8240-89/97, 5267.1-90, 8509-93, 8510-86, 8732-78, 10704-91, 8639-82,
8645-68, 30245-2012, 32931-2015, 2590, 2591, 7417, 103, 82 and various ТУ),
as collected by the **ViewProf** reference tables
(<http://www.metalodvetov.com>). Only dimensional and cross-section data is
reproduced. Standard disclaimers apply: the data is believed accurate but
must not be relied upon for any specific application without verification
by a licensed engineer; this extension is a modelling aid, not a design
tool.

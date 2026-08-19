#!/usr/bin/env python3
"""Split the four finance domains out of app.js into their own files.

app.js is edited by several parallel sessions at once, and a squash merge
replaces whole regions instead of diffing them -- which is how the trade panel
silently vanished from main once already (see trade.js's header). The macro
monitor, market microstructure, company calculator, and portfolio lab never
call into each other beyond four calls, so keeping them in one 9.4k-line file
buys nothing and costs a collision surface.

Extraction is positional, not a rewrite: each top-level declaration keeps its
own bytes, and the leading comment block above it travels with it so the "why"
stays attached to the code it explains. The script asserts that header plus
every span concatenates back to the original file before writing anything --
if that fails, nothing is written.

Load order matters and is enforced by index.html, not by imports: these are
plain scripts sharing one global scope. macro.js must precede
market-microstructure.js and calculator.js (both call mmFmt/mmLineChart), and
all four must precede app.js, whose render* entry points call into them.
"""

from __future__ import annotations

import bisect
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
UI = HERE.parents[2]
APP = UI / "app.js"

# Written in load order: macro first, since two other domains call into it.
DOMAINS = [
    ("macro", "macro.js", "매크로 모니터"),
    ("ms", "market-microstructure.js", "시장 미시구조"),
    ("calc", "calculator.js", "기업가치 계산기"),
    ("pf", "portfolio.js", "포트폴리오 랩"),
]

HEADERS = {
    "macro": """// Macro monitor for Global Trade Dashboard -- world map, per-country
// indicator chips, and the drawer with history charts and status panels.
//
// Split out of app.js (2026-08-20). app.js is shared by several parallel
// sessions, and a squash merge replaces whole regions rather than diffing
// them, which has silently deleted unrelated work from main before (see
// trade.js). This domain calls nothing outside itself.
//
// Loaded BEFORE market-microstructure.js and calculator.js, which call
// mmLineChart and mmFmt from here. Non-module scripts share one global scope,
// so these top-level declarations are visible to them the same as before.
// Relies on globals still in app.js: finEsc, finFmt, and the DOM helpers.""",
    "ms": """// Market microstructure for Global Trade Dashboard -- order-book pressure,
// funding and credit, price levels, and the derivatives/short-selling views.
//
// Named for what it shows rather than "derivatives", which described only one
// of its tabs. Split out of app.js (2026-08-20) for the same reason as the
// other finance domains: app.js is shared by parallel sessions and squash
// merges overwrite whole regions.
//
// Loaded AFTER macro.js -- msHistChart and msModalFor draw with mmLineChart.
// Relies on globals still in app.js: finEsc, finFmt, and the DOM helpers.""",
    "calc": """// Company valuation calculator for Global Trade Dashboard -- DART filing
// cards, DCF and reverse-DCF panels, sensitivity, and the level-by-level
// breakdown.
//
// Split out of app.js (2026-08-20). app.js is shared by parallel sessions and
// a squash merge replaces whole regions instead of diffing them.
//
// Loaded AFTER macro.js -- coDcfPanel and coReversePanel format with mmFmt.
// Relies on globals still in app.js: finEsc, finFmt, FIN_SERIES_MODE, and the
// DOM helpers. Shows no price target by design.""",
    "pf": """// Portfolio lab for Global Trade Dashboard -- holdings input, covariance and
// correlation, HRP/IVP allocation, and the risk views.
//
// Split out of app.js (2026-08-20). app.js is shared by parallel sessions and
// a squash merge replaces whole regions instead of diffing them. This domain
// calls nothing outside itself.
//
// Relies on globals still in app.js: finEsc, finFmt, and the DOM helpers.""",
}


def domain_of(name: str) -> str | None:
    if re.match(r"^mm[A-Z]", name) or name.startswith("MM_"):
        return "macro"
    if re.match(r"^ms[A-Z]", name) or name.startswith("MS_"):
        return "ms"
    if re.match(r"^pf[A-Z]", name) or name.startswith("PF_"):
        return "pf"
    if re.match(r"^kfa[A-Z]", name, re.I) or "Kfa" in name or name.startswith("KFA"):
        return "calc"
    if re.match(r"^co[A-Z]", name) or name.startswith("CO_"):
        return "calc"
    return None


def main() -> int:
    src = APP.read_text(encoding="utf-8")
    lines = src.split("\n")

    offsets = [0]
    for ln in lines[:-1]:
        offsets.append(offsets[-1] + len(ln) + 1)

    decls = list(re.finditer(r"^(?:const|function|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)", src, re.M))
    if not decls:
        print("no top-level declarations found -- refusing to write")
        return 1

    # A declaration owns the comment block directly above it: walk back over
    # blank and //-comment lines so the rationale moves with the code.
    starts: list[int] = []
    for d in decls:
        li = bisect.bisect_right(offsets, d.start()) - 1
        j = li
        while j > 0:
            prev = lines[j - 1].strip()
            if prev == "" or prev.startswith("//"):
                j -= 1
            else:
                break
        starts.append(offsets[j])

    spans = []
    for i, d in enumerate(decls):
        end = starts[i + 1] if i + 1 < len(decls) else len(src)
        spans.append((d.group(1), domain_of(d.group(1)), starts[i], end))

    header = src[: starts[0]]
    if header + "".join(src[s:e] for _, _, s, e in spans) != src:
        print("partition does not reconstruct app.js -- refusing to write")
        return 1

    kept = [(n, s, e) for n, dom, s, e in spans if dom is None]
    new_app = header + "".join(src[s:e] for _, s, e in kept)

    total_moved = 0
    for key, filename, label_ko in DOMAINS:
        picked = [(n, s, e) for n, dom, s, e in spans if dom == key]
        if not picked:
            print(f"{filename}: nothing matched -- refusing to write an empty file")
            return 1
        body = "".join(src[s:e] for _, s, e in picked)
        (UI / filename).write_text(HEADERS[key] + "\n\n" + body.lstrip("\n"), encoding="utf-8")
        total_moved += len(picked)
        print(f"  {filename:28s} {len(picked):3d} declarations  ({label_ko})")

    APP.write_text(new_app, encoding="utf-8")
    print(f"\napp.js: {len(spans)} → {len(kept)} declarations ({total_moved} moved out)")
    print(f"        {len(src.splitlines())} → {len(new_app.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())

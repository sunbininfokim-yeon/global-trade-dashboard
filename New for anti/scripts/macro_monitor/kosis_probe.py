#!/usr/bin/env python3
"""Discovery run for the KOSIS-backed Korean series: which tables exist, what their classification
values and items are called, and what the newest rows look like. Read-only; prints, writes nothing.

    KOSIS_API_KEY=... python3 kosis_probe.py

The key is read from the environment and never printed. Output is meant to be read once, to fix the
table ids and names in kosis_kr.py, and to record real responses as test fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import kosis  # noqa: E402

SEARCHES = [
    ("소비자물가지수 품목성질별", "101"),
    ("소비자물가지수", "101"),
    ("산업활동동향 전산업생산지수", "101"),
    ("전산업생산지수 계절조정", "101"),
    ("수출입 총괄 수출금액", "134"),
    ("수출입총괄", None),
    ("반도체 수출", None),
    ("국내총생산 실질 원계열", "301"),
    ("국내총생산 실질 계절조정 전기대비", "301"),
    ("국민계정 분기 국내총생산", None),
]
DIRECT = [("101", "DT_1J22003", "M"), ("101", "DT_1J22001", "M")]
OUT_LINES: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def summarize(rows: list[dict], prd_se: str) -> None:
    say(f"    rows={len(rows)} keys={sorted(rows[0].keys()) if rows else '-'}")
    c1 = {}
    for r in rows:
        c1.setdefault((r.get("C1"), r.get("C1_NM")), 0)
        c1[(r.get("C1"), r.get("C1_NM"))] += 1
    say(f"    C1 ({len(c1)}): " + " | ".join(f"{c}={n}" for (c, n) in list(c1)[:45]))
    itm = {(r.get("ITM_ID"), r.get("ITM_NM"), r.get("UNIT_NM")) for r in rows}
    say(f"    ITM ({len(itm)}): " + " | ".join(f"{a}={b}[{u}]" for a, b, u in sorted(itm, key=str)[:20]))
    periods = sorted({r.get("PRD_DE") for r in rows})
    say(f"    periods: {periods[:1]}..{periods[-1:]}  (prdSe {prd_se})")
    for r in rows[:4]:
        say(f"    e.g. {r.get('C1_NM')} / {r.get('ITM_NM')} / {r.get('PRD_DE')} = {r.get('DT')} {r.get('UNIT_NM')}")


def try_table(org: str, tbl: str, prd_se: str | None = None) -> None:
    for se in ([prd_se] if prd_se else ["M", "Q", "Y"]):
        try:
            rows = kosis.data(org, tbl, prd_se=se, newest=2)
        except kosis.KosisError as exc:
            say(f"    [{org}/{tbl} {se}] {exc}")
            continue
        say(f"  DATA {org}/{tbl} ({rows[0].get('TBL_NM') if rows else '-'}) prdSe={se}")
        summarize(rows, se)
        return


def main() -> int:
    try:
        kosis.api_key()
    except kosis.KosisError as exc:
        say(str(exc))
        return 2

    say("=== direct tables ===")
    for org, tbl, se in DIRECT:
        try_table(org, tbl, se)

    say("\n=== searches ===")
    seen: set[tuple[str, str]] = set()
    for kw, org in SEARCHES:
        say(f"\n# {kw!r} org={org}")
        try:
            hits = kosis.search(kw, org_id=org, count=8)
        except kosis.KosisError as exc:
            say(f"  search failed: {exc}")
            continue
        if hits:
            say(f"  hit keys: {sorted(hits[0].keys())}")
        for h in hits:
            say(f"  - {h.get('ORG_ID')}/{h.get('TBL_ID')} {h.get('TBL_NM')} | {h.get('STAT_NAME')} | {h.get('STRT_PRD_DE')}~{h.get('END_PRD_DE')} | {h.get('PRD_SE') or h.get('REC_TBL_SE') or ''}")
        for h in hits[:3]:
            key = (str(h.get("ORG_ID")), str(h.get("TBL_ID")))
            if key in seen or not all(key):
                continue
            seen.add(key)
            try_table(*key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

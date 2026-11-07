#!/usr/bin/env python3
"""Korean non-bank credit cards: 저축은행 / 카드사 / 캐피탈 연체율 (see macro_monitor/kr_nonbank_credit.py).

    FISIS_API_KEY=... python3 wire_kr_nonbank_credit.py

FISIS is read on every run (about 1,500 calls, under a minute) and older quarters FISIS no longer
returns are kept. Without the key, or when FISIS is down, the cache
serves. Exit status 1 when FISIS was due but could not be read.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import kr_bank_credit as kbc  # noqa: E402
from macro_monitor import kr_nonbank_credit as knb  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import world_public_series as wps  # noqa: E402
from macro_monitor import free_cards  # noqa: E402,F401 -- registers display formats

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SOURCE = "fss:fisis"
URL = "https://fisis.fss.or.kr/"


def main() -> int:
    prev = json.loads(knb.CACHE.read_text(encoding="utf-8")) if knb.CACHE.exists() else None
    doc, failed = prev, None
    if os.environ.get("FISIS_API_KEY"):
        try:
            doc = knb.fetch()
            for sec, series in ((prev or {}).get("stock") or {}).items():
                for k, pts in series.items():
                    for ym, v in pts.items():
                        doc["stock"].setdefault(sec, {}).setdefault(k, {}).setdefault(ym, v)
            text = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            if not knb.CACHE.exists() or knb.CACHE.read_text(encoding="utf-8") != text:
                knb.CACHE.write_text(text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 -- fall back to the cache
            failed, doc = str(exc)[:200], prev
    if doc is None:
        print(f"KOR non-bank credit: no data ({failed or 'FISIS_API_KEY not set'}) and no cache")
        return 1

    bank = None
    if kbc.CACHE.exists():
        b = json.loads(kbc.CACHE.read_text(encoding="utf-8"))["stock"]
        bank = kbc.ratio(b.get("SA040.A2") or {}, b.get("SA040.A1") or {})
    built = knb.build(doc, bank)

    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    kor = next(c for c in pack["countries"] if c["iso3"] == "KOR")
    now = ups.now_iso()
    cards, patches = [], {}
    for cid, b in built.items():
        pts = b["points"]
        c = wps.card(cid, "quarterly", b["unit"], b["format"], b["label"], b["note_ko"], SOURCE, URL,
                     lambda f, p=pts: p, category="liquidity", chart="bar")
        cards.append(c)
        patches[cid] = wps.build_patch(c, pts, retrieved_at=now)
    result = wps.apply_country(kor, cards, patches, retrieved_at=now)
    by_id = {i["id"]: i for i in kor["indicators"]}
    for cid, b in built.items():
        ind = by_id[cid]
        ind["label_ko"], ind["note_ko"], ind["chart_type"], ind["panels"] = b["label"], b["note_ko"], "bar", b["panels"]
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"KOR non-bank credit: {len(patches)} cards, changed {result['changed'] or 'none'}"
          f"{' (FISIS failed, cache used: ' + failed + ')' if failed else ''}")
    for cid, p in patches.items():
        print(f"  {cid:16s} {p['display']:>10s}  {p['reference_period']}  panels: {', '.join(x['label'] for x in built[cid]['panels'])}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

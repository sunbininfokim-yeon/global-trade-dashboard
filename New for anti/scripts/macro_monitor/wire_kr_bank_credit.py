#!/usr/bin/env python3
"""Korean bank credit cards with their detail panels (see macro_monitor/kr_bank_credit.py).

    FISIS_API_KEY=... python3 wire_kr_bank_credit.py

With the key, FISIS is read and the sums are cached in config/kr_bank_credit_v1.json; without it, or
when FISIS is down, the cache is used, so the cards never disappear. Cards: 대출 연체율, 신규연체율,
부실채권비율, 손실흡수력 -- each with panels (부문별, 연체 흐름, 건전성 단계, 은행별, ...). The per-segment
delinquency cards and the 요주의 card this replaces are removed: they live in the panels now.
Exit status 1 when FISIS could not be read (the cache still served).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import kr_bank_credit as kbc  # noqa: E402
from macro_monitor import kr_npl_release as rel  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import world_public_series as wps  # noqa: E402
from macro_monitor import free_cards  # noqa: E402,F401 -- registers display formats

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SOURCE = "fss:fisis"
URL = "https://fisis.fss.or.kr/"
REPLACED = ("delinq_household", "delinq_corporate", "delinq_sme", "delinq_soho", "precaution_ratio")
CARDS = {   # id -> label, unit, format, note (for cards whose label/note the free-card registry set before)
    "delinq_all": ("대출 연체율", "%", "pct2",
                   "국내은행 연체대출잔액 / 대출잔액(%, 분기말, 1개월 이상 원리금 연체). 눌러서 부문별·연체 흐름(신규·상각·정상화)·은행별을 볼 수 있습니다. 금융감독원 FISIS, 은행별 합산."),
    "npl_ratio": ("부실채권비율(고정이하여신)", "%", "pct2",
                  "국내은행 고정이하여신 / 총여신(%, 분기말). 눌러서 건전성 단계(요주의~추정손실), 분기 중 신규 부실과 정리(상각·매각·정상화), 부문별 부실비율(주담대·신용대출 포함), 은행별을 볼 수 있습니다. 금융감독원 FISIS(은행별 합산)와 분기 보도자료."),
}


def main() -> int:
    failed = None
    doc = None
    if os.environ.get("FISIS_API_KEY"):
        try:
            doc = kbc.fetch()
            text = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            old = kbc.CACHE.read_text(encoding="utf-8") if kbc.CACHE.exists() else ""
            # keep quarters FISIS no longer returns (it serves 40 at most)
            if old:
                prev = json.loads(old)
                for part in ("stock", "flow"):
                    for k, series in prev.get(part, {}).items():
                        for ym, v in series.items():
                            doc[part].setdefault(k, {}).setdefault(ym, v)
                text = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if text != old:
                kbc.CACHE.write_text(text + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 -- fall back to the cache
            failed = str(exc)[:200]
    if doc is None:
        if not kbc.CACHE.exists():
            print(f"KOR bank credit: no data ({failed or 'FISIS_API_KEY not set'}) and no cache")
            return 1
        doc = json.loads(kbc.CACHE.read_text(encoding="utf-8"))

    built = kbc.build(doc)

    # NPL flows from the FSS press-release PDFs (new NPLs, write-offs, sales, segment ratios)
    rdoc = rel.load()
    try:
        added = rel.update(rdoc, pages=1)
        if rel.save(rdoc) and added:
            print(f"FSS NPL release: added {', '.join(added)}")
    except Exception as exc:  # noqa: BLE001 -- the cached releases still serve
        print(f"FSS NPL release: fetch failed ({str(exc)[:160]}), cache used")
    extra = rel.panels(rdoc)
    if extra:
        npl = built["npl_ratio"]["panels"]
        npl[1:1] = extra                      # after 건전성 단계, before 은행별
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    kor = next(c for c in pack["countries"] if c["iso3"] == "KOR")
    now = ups.now_iso()

    kor["indicators"] = [i for i in kor["indicators"] if i["id"] not in REPLACED]
    for cat, chips in (kor.get("categories") or {}).items():
        kor["categories"][cat] = [c for c in chips if c.get("id") not in REPLACED]

    cards, patches = [], {}
    for cid, b in built.items():
        label, unit, fmt, note = CARDS.get(cid) or (b["label"], b["unit"], b["format"], b["note_ko"])
        pts = b["points"]
        c = wps.card(cid, "quarterly", unit, fmt, label, note, SOURCE, URL, lambda f, p=pts: p,
                     category="liquidity", chart="bar")
        cards.append(c)
        patches[cid] = wps.build_patch(c, pts, retrieved_at=now)
    result = wps.apply_country(kor, cards, patches, retrieved_at=now)
    by_id = {i["id"]: i for i in kor["indicators"]}
    for cid, b in built.items():
        ind = by_id[cid]
        ind["label_ko"], ind["note_ko"] = (CARDS.get(cid) or (b["label"], None, None, b["note_ko"]))[0], \
            (CARDS.get(cid) or (None, None, None, b["note_ko"]))[3]
        ind["chart_type"] = "bar"
        ind["panels"] = b["panels"]
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"KOR bank credit: {len(patches)} cards, changed {result['changed'] or 'none'}"
          f"{' (FISIS failed, cache used: ' + failed + ')' if failed else ''}")
    for cid, p in patches.items():
        print(f"  {cid:18s} {p['display']:>10s}  {p['reference_period']}  panels: {', '.join(x['label'] for x in built[cid]['panels'])}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

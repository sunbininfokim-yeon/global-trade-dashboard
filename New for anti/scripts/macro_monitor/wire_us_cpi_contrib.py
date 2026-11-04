#!/usr/bin/env python3
"""US CPI contributions by item (see macro_monitor/us_cpi_contrib.py) -> public/data/us_cpi_contrib_v1.json,
and the headline/core CPI cards point their '기여도' tab at it.

    BLS_API_KEY=... python3 wire_us_cpi_contrib.py      # recompute when BLS has a new month
    python3 wire_us_cpi_contrib.py --offline            # re-attach the stored file only

The indexes come from the BLS API (about 11 requests with a key). The December weights are kept in
config/us_cpi_weights_v1.json, one table a year: a new table is fetched from www.bls.gov only when
BLS_CONTACT_EMAIL is set (that site wants a contact address); otherwise the newest stored table is carried
forward, which is what BLS itself does until it publishes the next one.

Also shapes the two CPI cards as two blocks: 헤드라인 CPI and 근원 CPI, each with its own YoY/MoM switch.
The headline/core switch inside the drawer repeated the two blocks, so it goes, as does the old
`components` breakdown (round placeholder numbers no pipeline wrote).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_cpi_contrib as uc  # noqa: E402

DATA = ROOT.parent.parent / "public" / "data"
PACK = DATA / "macro_monitor_v1.json"
OUT = DATA / "us_cpi_contrib_v1.json"
API_HISTORY = DATA / "us_cpi_api_history_v1.json"
WEIGHTS = ROOT / "config" / "us_cpi_weights_v1.json"
MONTHS = 25
CARDS = {"cpi_yoy": ("headline", "헤드라인 CPI"), "core_cpi_yoy": ("core", "근원 CPI")}


def latest_published_month() -> str | None:
    """The newest month the BLS API refresh (build_us_cpi_api_history.py) has seen."""
    try:
        doc = json.loads(API_HISTORY.read_text(encoding="utf-8"))
        return (doc.get("coverage") or {}).get("latest_reference_period")
    except (OSError, ValueError):
        return None


def load_weights(years: list[int]) -> dict:
    doc = json.loads(WEIGHTS.read_text(encoding="utf-8")) if WEIGHTS.exists() else {"tables": {}}
    changed = False
    contact = bool(os.environ.get("BLS_CONTACT_EMAIL", "").strip())
    for y in years:
        if str(y) in doc["tables"]:
            continue
        if not contact:
            print(f"  weights: December {y} not stored; BLS_CONTACT_EMAIL not set, carrying the newest stored table")
            continue
        try:
            doc["tables"][str(y)] = uc.parse_relative_importance(uc._get(uc.RI_URL.format(year=y)))
            changed = True
            print(f"  weights: December {y} fetched ({len(doc['tables'][str(y)])} rows)")
        except Exception as exc:  # noqa: BLE001 -- next January's table simply is not out yet
            print(f"  weights: December {y} not available ({str(exc)[:80]})")
    if contact and (changed or "items" not in doc):
        doc["items"] = uc.parse_items(uc._get(uc.FILES.format(name="cu.item")))
        changed = True
    if changed:
        doc["source"] = "BLS relative importance of CPI components (CPI-U, U.S. city average), cu.item"
        WEIGHTS.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


def compute(latest: str) -> dict:
    y = int(latest[:4])
    weights = load_weights([y - 3, y - 2, y - 1])
    years = sorted(int(k) for k in weights["tables"])
    newest = weights["tables"][str(years[-1])]
    nodes = uc.build_tree(newest, weights["items"])
    keep = {f"{p}0000{n['code']}" for n in nodes if n["code"] for p in ("CUSR", "CUUR")}
    keep |= {"CUSR0000SA0L1E", "CUUR0000SA0L1E"}
    data = uc.api_data(sorted(keep), y - 3, y)
    print(f"  BLS API: {len(data)} of {len(keep)} series")
    ri_by_year = {yr: uc._align(nodes, weights["tables"][str(yr)]) for yr in years}

    months, m = [], latest
    for _ in range(MONTHS):
        months.append(m)
        m = uc._prev_month(m)
    months.reverse()
    out = {"headline": {}, "core": {}}
    for month in months:
        for basket, exclude, code in (("headline", (), "SA0"), ("core", uc.CORE_EXCLUDE, "SA0L1E")):
            row = {}
            for mode in ("mom", "yoy"):
                pub = uc.published(data, code, month, mode)
                if pub is None:                   # no published figure (2025-10: BLS skipped it in the shutdown)
                    continue
                got = uc.contributions(nodes, ri_by_year, data, month, mode, exclude)
                if got is None:
                    continue
                row[mode] = {"published_pct": pub, "sum_pp": got["sum_pp"],
                             "residual_pp": round(pub - got["sum_pp"], 3),
                             "rows": {str(k): v for k, v in got["by_node"].items()}}
            if row:
                out[basket][month] = row
    return {
        "schema_version": "us_cpi_contrib_v1",
        "latest_month": latest,
        "months": [m for m in months if m in out["headline"]],
        "nodes": [{"name": n["name"], "name_ko": n["name_ko"], "level": n["level"], "parent": n["parent"],
                   "code": n["code"], "core": not _under(nodes, k, uc.CORE_EXCLUDE)}
                  for k, n in enumerate(nodes)],
        "weights_december": years[-1],
        "baskets": out,
        "source": "BLS CPI-U U.S. city average indexes (BLS public data API) and relative importance tables",
        "method_ko": ("기여도 = 항목 가중치(직전 12월 상대중요도를 해당 월까지 가격 변화로 이월) × 항목 변동률. "
                      "전월비는 계절조정 지수(없으면 원지수), 전년비는 원지수. 하위 항목 기여도를 위로 더해 각 묶음 값이 "
                      "됩니다. 전년비는 12월 가중치 교체를 한 번 건너가므로 공표치와 조금 어긋나고, 그 차이를 '잔차'로 "
                      "표시합니다. 지수가 따로 공표되지 않는 작은 항목(unsampled 등)은 상위 항목의 변동을 따릅니다."),
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _under(nodes: list, k: int, names: tuple) -> bool:
    while k is not None:
        if nodes[k]["name"] in names:
            return True
        k = nodes[k]["parent"]
    return False


def shape_cards(pack: dict, doc: dict | None) -> list[str]:
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    by_id = {i["id"]: i for i in usa["indicators"]}
    done = []
    for cid, (basket, label) in CARDS.items():
        ind = by_id.get(cid)
        if not ind:
            continue
        ind["label_ko"] = label
        ind.pop("peers", None)
        ind.pop("components", None)
        if doc and doc["baskets"].get(basket, {}).get(doc["latest_month"]):
            latest = doc["baskets"][basket][doc["latest_month"]]
            ind["cpi_contrib"] = {
                "file": "public/data/us_cpi_contrib_v1.json",
                "basket": basket,
                "latest_month": doc["latest_month"],
                "months": doc["months"],
                "published_pct": {m: v["published_pct"] for m, v in latest.items()},
            }
        done.append(cid)
    for group in [*(usa.get("categories") or {}).values(), usa.get("headlines") or []]:
        for ch in group:
            if ch.get("id") in CARDS:
                ch["label_ko"] = CARDS[ch["id"]][1]
                ch.pop("peers", None)
    return done


def main(argv: list[str]) -> int:
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    if "--offline" not in argv:
        latest = latest_published_month()
        if latest and (doc is None or doc.get("latest_month") != latest):
            try:
                doc = compute(latest)
                OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
                for b in ("headline", "core"):
                    for mode, v in doc["baskets"][b][latest].items():
                        print(f"{b} {mode} {latest}: published {v['published_pct']}%, sum of items {v['sum_pp']}pp, "
                              f"residual {v['residual_pp']}pp")
            except Exception as exc:  # noqa: BLE001
                print(f"  contributions not recomputed: {str(exc)[:200]}", file=sys.stderr)
        else:
            print(f"contributions already at {latest}" if latest else "no BLS API history to compare with")
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    print(f"shaped {shape_cards(pack, doc)}")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

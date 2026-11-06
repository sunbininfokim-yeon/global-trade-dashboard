#!/usr/bin/env python3
"""Korea CPI contributions by item (see macro_monitor/kr_cpi_contrib.py) -> public/data/kr_cpi_contrib_v1.json,
and the two Korean CPI cards become '헤드라인 CPI' / '근원 CPI', each with YoY/MoM and a '기여도' tab.

    set -a; . ~/.config/ecos.env; set +a
    python3 wire_kr_cpi_contrib.py              # recompute when ECOS has a month the stored file lacks
    python3 wire_kr_cpi_contrib.py --force      # recompute anyway
    python3 wire_kr_cpi_contrib.py --offline    # re-attach the stored files only

Needs ECOS_API_KEY (already used by wire_kr_public_series.py); about eight ECOS requests when a new
month is out, one otherwise. Without the key the cards keep what the stored files give them.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ecos  # noqa: E402
from macro_monitor import kr_cpi_contrib as kc  # noqa: E402

DATA = ROOT.parent.parent / "public" / "data"
PACK = DATA / "macro_monitor_v1.json"
OUT = DATA / "kr_cpi_contrib_v1.json"
INDEX = ROOT / "config" / "kr_cpi_index_v1.json"          # total and core index, for the YoY/MoM cards
MONTHS = 25
CARDS = {"cpi_yoy": ("headline", "헤드라인 CPI"), "core_cpi_yoy": ("core", "근원 CPI")}


def _ym(m: str) -> str:
    return m.replace("-", "")


def compute(latest: str) -> tuple[dict, dict]:
    months = [kc.prev_month(latest, n) for n in range(MONTHS - 1, -1, -1)]
    first = kc.prev_month(months[0], 12)
    y = int(latest[:4])
    items = kc.fetch_items()
    monthly, weights = kc.parse(kc._rows(kc.STAT, "M", _ym(first), _ym(latest)), True)
    annual, _ = kc.parse(kc._rows(kc.STAT, "A", str(y - 7), str(y - 1)), False)
    core_m, core_w = kc.parse(kc._rows(kc.STAT_CORE, "M", _ym(first), _ym(latest), kc.CORE_CODE), True)
    nodes = kc.build_nodes(items, weights)
    ref, miss = kc.reference_year(nodes, monthly, annual, months)
    print(f"  {len(kc.leaves(nodes))} items, weights sum {sum(n['weight'] or 0 for k, n in enumerate(nodes) if not n['children']):.1f}; "
          f"price reference {ref} (total index reproduced within {miss:.3f})")
    members = kc.core_members(nodes)
    core_ok, why = kc.core_check(nodes, members, monthly, annual, ref, core_m.get(kc.CORE_CODE, {}),
                                 core_w.get(kc.CORE_CODE), months)
    print(f"  {why}")

    out: dict = {"headline": {}, "core": {}}
    for month in months:
        for basket, mem, pub_series in (("headline", None, monthly.get("0", {})),
                                        ("core", members, core_m.get(kc.CORE_CODE, {}))):
            if basket == "core" and not core_ok:
                continue
            row = {}
            for mode, lag in (("mom", 1), ("yoy", 12)):
                pub = kc.published(pub_series, month, lag)
                got = kc.contributions(nodes, monthly, annual, ref, month, lag, mem)
                if pub is None or got is None:
                    continue
                row[mode] = {"published_pct": pub, "sum_pp": got["sum_pp"],
                             "residual_pp": round(pub - got["sum_pp"], 3),
                             "rows": {str(k): v for k, v in got["by_node"].items()}}
            if row:
                out[basket][month] = row
    doc = {
        "schema_version": "kr_cpi_contrib_v1",
        "latest_month": latest,
        "months": [m for m in months if m in out["headline"]],
        "nodes": [{"name": n["name"], "name_ko": n["name"], "level": n["level"], "parent": n["parent"],
                   "code": n["code"], "core": _in_core(nodes, k, members)} for k, n in enumerate(nodes)],
        "price_reference_year": ref,
        "core_available": core_ok,
        "baskets": out,
        "source": "통계청 소비자물가지수(한국은행 ECOS 901Y009 지출목적별, 901Y010 근원)",
        "method_ko": (f"기여도 = 품목 가중치 × 품목 지수 변화 ÷ {ref}년 평균 지수 ÷ 비교 시점 총지수(같은 방식). "
                      f"통계청이 지수를 만드는 방식과 같아(현행 가중치, {ref}년 가격 기준) 품목 기여도를 더하면 공표 "
                      "등락률과 반올림 범위 안에서 맞습니다. 전월비·전년비 모두 원지수(계절조정 아님)입니다."),
        "core_note_ko": "근원은 통계청 '농산물 및 석유류 제외지수'와 같은 품목(곡물 외 농산물·석유류·도시가스 제외, "
                        "401개)을 근원 지수 안의 비중으로 다시 나눈 값입니다.",
        "weights_note_ko": f"가중치는 통계청 현행 가중치(1,000분비)의 비교 시점 비중. 출처: 통계청(ECOS).",
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return doc, {"total": monthly.get("0", {}), "core": core_m.get(kc.CORE_CODE, {})}


def _in_core(nodes: list, k: int, members: set) -> bool:
    if not nodes[k]["children"]:
        return k in members
    stack = list(nodes[k]["children"])
    while stack:
        c = stack.pop()
        if not nodes[c]["children"] and c in members:
            return True
        stack += nodes[c]["children"]
    return False


def fetch_index_history(latest: str) -> dict:
    start = kc.prev_month(latest, 12 * 11 + 1)
    total, _ = kc.parse(kc._rows(kc.STAT, "M", _ym(start), _ym(latest), "0"), True)
    core, _ = kc.parse(kc._rows(kc.STAT_CORE, "M", _ym(start), _ym(latest), kc.CORE_CODE), True)
    return {"total": total.get("0", {}), "core": core.get(kc.CORE_CODE, {})}


def month_end(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1).isoformat()


def mode_block(series: dict[str, float], lag: int, label: str, note: str | None = None) -> dict:
    pts = [(m, kc.published(series, m, lag)) for m in sorted(series)]
    pts = [(m, v) for m, v in pts if v is not None]
    hist = {key: {"dates": [month_end(m) for m, _ in pts[-n:]], "values": [round(v, 4) for _, v in pts[-n:]]}
            for key, n in (("5y", 60), ("10y", 120))}
    val = round(pts[-1][1], 2) if pts else None
    out = {"label_ko": label, "value": val, "display": "—" if val is None else f"{val:.2f}%", "unit": "%",
           "history": hist}
    if note:
        out["note_ko"] = note
    return out


def shape_cards(pack: dict, doc: dict | None, index: dict | None) -> list[str]:
    kor = next(c for c in pack["countries"] if c["iso3"] == "KOR")
    by_id = {i["id"]: i for i in kor["indicators"]}
    done = []
    for cid, (basket, label) in CARDS.items():
        ind = by_id.get(cid)
        if not ind:
            continue
        ind["label_ko"] = label
        series = (index or {}).get("total" if basket == "headline" else "core") or {}
        if len(series) > 13:
            yoy = mode_block(series, 12, "YoY")
            mom = mode_block(series, 1, "MoM", "전월 대비 %. 원지수(계절조정 아님)라 계절 품목의 움직임이 그대로 들어갑니다.")
            ind["modes"] = {"yoy": {**yoy, "id": f"{cid}:yoy"}, "mom": {**mom, "id": f"{cid}:mom"}}
            ind["ui"] = {**(ind.get("ui") or {}), "dual": ["yoy", "mom"], "default": "yoy"}
        if doc and doc["baskets"].get(basket, {}).get(doc["latest_month"]):
            latest = doc["baskets"][basket][doc["latest_month"]]
            ind["cpi_contrib"] = {
                "file": "public/data/kr_cpi_contrib_v1.json",
                "basket": basket,
                "latest_month": doc["latest_month"],
                "months": doc["months"],
                "published_pct": {m: v["published_pct"] for m, v in latest.items()},
            }
        else:
            ind.pop("cpi_contrib", None)
        done.append(cid)
    for group in [*(kor.get("categories") or {}).values(), kor.get("headlines") or []]:
        for ch in group:
            if ch.get("id") in CARDS:
                ch["label_ko"] = CARDS[ch["id"]][1]
                src = by_id[ch["id"]]
                if src.get("modes"):
                    ch["modes"] = {k: {kk: vv for kk, vv in v.items() if kk != "history"}
                                   for k, v in src["modes"].items()}
    return done


def main(argv: list[str]) -> int:
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else None
    if "--offline" not in argv:
        try:
            latest = kc.latest_month()
            if latest and ("--force" in argv or doc is None or doc.get("latest_month") != latest):
                doc, _ = compute(latest)
                OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
                index = {**fetch_index_history(latest), "source": "ECOS 901Y009 총지수, 901Y010 QB",
                         "latest_month": latest}
                INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                for b in ("headline", "core"):
                    for mode, v in (doc["baskets"][b].get(latest) or {}).items():
                        print(f"{b} {mode} {latest}: published {v['published_pct']}%, sum of items {v['sum_pp']}pp, "
                              f"residual {v['residual_pp']}pp")
            else:
                print(f"contributions already at {latest}")
        except ecos.MissingKey:
            print("ECOS_API_KEY not set: keeping the stored contributions")
        except Exception as exc:  # noqa: BLE001 -- a failed refresh keeps yesterday's file
            print(f"  contributions not recomputed: {str(exc)[:200]}", file=sys.stderr)
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    print(f"shaped {shape_cards(pack, doc, index)}")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

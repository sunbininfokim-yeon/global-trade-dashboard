#!/usr/bin/env python3
"""Replace the USA inflation block's fixtures with observed BLS/BEA series.

Before this, USA cpi_yoy read 2.9% from fixture_synth while the actual BLS
print for the same period was 3.46% -- not merely "synthetic", materially
wrong, on the one number the inflation tab exists to show. Same for core CPI
and core PCE, and headline PCE had no indicator at all.

Reads two observed artifacts:
  us_cpi_api_history_v1.json  (BLS public API, 21 series incl. detail items)
  us_pce_history_v1.json      (FRED/BEA, PCEPI + PCEPILFE)

and writes, per indicator, both the YoY and MoM series under the same
`modes`/`ui.dual` contract GDP already uses for YoY/QoQ -- so the drawer's
existing mode switch drives it with no new UI concept.

Consensus/forecast is deliberately absent: no free public source publishes it
(checked Cleveland Fed nowcast, FRED, and the Codex branch itself), and the
brief's own rule is not to invent expected values. The fields are emitted as
null with a reason so the UI can show an empty slot honestly rather than a
fabricated one.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
CPI = ROOT / "us_cpi_api_history_v1.json"
PCE = ROOT / "us_pce_history_v1.json"

# indicator id -> (artifact, series id, Korean label)
TARGETS = {
    "cpi_yoy":      ("cpi", "all_items", "CPI"),
    "core_cpi_yoy": ("cpi", "core", "근원 CPI"),
    "pce_yoy":      ("pce", "headline", "PCE"),
    "core_pce_yoy": ("pce", "core", "근원 PCE"),
}

# Detail items used for the contribution ranking. Weights are not published in
# this artifact, so the ranking is by the item's own MoM move, and is labelled
# as such -- an unweighted mover list, not a contribution-to-headline figure.
DETAIL_ITEMS = [
    "food", "food_at_home", "energy", "core_goods", "core_services", "shelter",
    "rent_primary", "owners_equivalent_rent", "new_vehicles", "used_cars_and_trucks",
    "motor_vehicle_parts", "motor_vehicle_maintenance", "motor_vehicle_insurance",
    "motor_fuel", "medical_care", "medical_care_commodities",
    "education_communication", "college_tuition", "public_transportation",
]

LABELS_KO = {
    "food": "식품", "food_at_home": "가정식품", "energy": "에너지",
    "core_goods": "근원 상품", "core_services": "근원 서비스", "shelter": "주거",
    "rent_primary": "주택 임차료", "owners_equivalent_rent": "자가주거비(OER)",
    "new_vehicles": "신차", "used_cars_and_trucks": "중고차",
    "motor_vehicle_parts": "차량 부품", "motor_vehicle_maintenance": "차량 정비",
    "motor_vehicle_insurance": "자동차 보험", "motor_fuel": "차량 연료",
    "medical_care": "의료", "medical_care_commodities": "의약품",
    "education_communication": "교육·통신", "college_tuition": "대학 등록금",
    "public_transportation": "대중교통",
}


def month_end(ym: str) -> str:
    y, m = (int(x) for x in ym.split("-"))
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return f"{y:04d}-{m:02d}-{last:02d}"


def series_map(doc: dict) -> dict[str, list[dict]]:
    return {s["id"]: s["observations"] for s in doc.get("series", [])}


def build_history(obs: list[dict], field: str, years: int) -> dict:
    tail = obs[-(years * 12):]
    rows = [(o["date"], o.get(field)) for o in tail]
    return {
        "dates": [month_end(d) for d, _ in rows],
        "values": [None if v is None else round(float(v), 4) for _, v in rows],
    }


def mode_block(obs: list[dict], field: str, label_ko: str, note: str | None = None) -> dict:
    latest = obs[-1]
    val = latest.get(field)
    out = {
        "label_ko": label_ko,
        "value": None if val is None else round(float(val), 2),
        "display": "—" if val is None else f"{float(val):.2f}%",
        "unit": "%",
        "history": {"5y": build_history(obs, field, 5), "10y": build_history(obs, field, 10)},
    }
    if note:
        out["note_ko"] = note
    return out


def movers(cpi_series: dict[str, list[dict]], month: str) -> dict:
    rows = []
    for item in DETAIL_ITEMS:
        obs = cpi_series.get(item) or []
        hit = next((o for o in reversed(obs) if o["date"] == month), None)
        if not hit or hit.get("mom_pct") is None:
            continue
        rows.append({
            "id": item,
            "label_ko": LABELS_KO.get(item, item),
            "mom_pct": round(float(hit["mom_pct"]), 3),
            "yoy_pct": None if hit.get("yoy_pct") is None else round(float(hit["yoy_pct"]), 3),
        })
    rows.sort(key=lambda r: r["mom_pct"], reverse=True)
    return {
        "reference_period": month,
        "basis": "item_mom_percent_change_unweighted",
        "note_ko": ("항목 자체의 전월비 변동 순위입니다. BLS 가중치를 곱한 "
                    "헤드라인 기여도(contribution)가 아니므로, 큰 폭으로 움직인 "
                    "작은 항목이 상위에 올 수 있습니다."),
        "up": rows[:3],
        "down": rows[-3:][::-1],
    }


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    cpi_doc = json.loads(CPI.read_text(encoding="utf-8"))
    pce_doc = json.loads(PCE.read_text(encoding="utf-8"))
    cpi_s, pce_s = series_map(cpi_doc), series_map(pce_doc)

    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    by_id = {i["id"]: i for i in usa["indicators"]}

    latest_month = cpi_s["all_items"][-1]["date"]
    mv = movers(cpi_s, latest_month)
    touched = []

    for ind_id, (which, sid, label) in TARGETS.items():
        obs = (cpi_s if which == "cpi" else pce_s).get(sid)
        if not obs:
            print(f"  skip {ind_id}: {sid} not in {which} artifact")
            continue

        ind = by_id.get(ind_id)
        if ind is None:
            # headline PCE has no fixture to replace -- create it next to core.
            ind = {
                "id": ind_id, "category": "inflation", "label_ko": f"{label} YoY",
                "unit": "%", "format": "pct1", "refresh_tier": "monthly",
            }
            anchor = usa["indicators"].index(by_id["core_pce_yoy"])
            usa["indicators"].insert(anchor, ind)
            by_id[ind_id] = ind

        yoy = mode_block(obs, "yoy_pct", "YoY")
        mom = mode_block(obs, "mom_pct", "MoM", "전월 대비 %. 계절조정 여부는 원 시리즈 정의를 따른다.")

        ind.update({
            "value": yoy["value"],
            "display": yoy["display"],
            "display_chip": yoy["display"],
            "asof": month_end(obs[-1]["date"]),
            "observed_at": month_end(obs[-1]["date"]),
            "reference_period": obs[-1]["date"],
            "source": cpi_doc.get("source") if which == "cpi" else pce_doc.get("source"),
            "quality": "live",
            "data_status": "live",
            "chart_type": "bar",
            "history": yoy["history"],
            "modes": {"yoy": {**yoy, "id": f"{ind_id}:yoy"}, "mom": {**mom, "id": f"{ind_id}:mom"}},
            "ui": {**(ind.get("ui") or {}), "dual": ["yoy", "mom"], "default": "yoy"},
            # No free public source publishes consensus; the slot stays empty
            # rather than carrying a number nobody published.
            "forecast": {
                "yoy_pct": None, "mom_pct": None,
                "reason": "missing:no_free_consensus_source",
                "note_ko": "시장 예상치는 무료 공개 출처가 없어 비워 둡니다. 추정하지 않습니다.",
            },
        })
        if which == "cpi":
            ind["movers"] = mv
        touched.append(ind_id)

    # Headline PCE is new and core PCE was never chipped, so the inflation tab
    # would show CPI observed while PCE stayed invisible. Insert them ahead of
    # the CPI chips so the tab leads with the Fed's own target measure.
    infl = usa.setdefault("categories", {}).setdefault("inflation", [])
    have = {c.get("id") for c in infl}
    for pos, ind_id in enumerate(("pce_yoy", "core_pce_yoy")):
        if ind_id in have or ind_id not in by_id:
            continue
        src = by_id[ind_id]
        infl.insert(pos, {
            "id": ind_id, "label_ko": src["label_ko"], "unit": src.get("unit"),
            "value": src.get("value"), "display": src.get("display"),
            "change_1m_pct": None, "change_1y_pct": None,
            "asof": src.get("asof"), "note_ko": src.get("note_ko"),
        })

    # chips/headlines are projections of indicators -- resync the ones we moved
    for cat, chips in (usa.get("categories") or {}).items():
        for ch in chips:
            src = by_id.get(ch.get("id"))
            if src and ch["id"] in touched:
                for k in ("value", "display", "asof", "observed_at", "source", "data_status"):
                    ch[k] = src.get(k)
                ch["forecast"] = src.get("forecast")
                ch["chart_type"] = src.get("chart_type")
                # The chip renders actual-vs-expected for both windows, so it
                # needs the mode headline values -- but not their histories,
                # which would multiply the pack size for data the chip never
                # draws (the drawer re-reads those off the indicator).
                ch["modes"] = {
                    k: {kk: vv for kk, vv in v.items() if kk != "history"}
                    for k, v in (src.get("modes") or {}).items()
                }
    for h in usa.get("headlines") or []:
        src = by_id.get(h.get("id"))
        if src and h["id"] in touched:
            h["display"] = src.get("display")
            h["data_status"] = src.get("data_status")

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wired {len(touched)} observed inflation indicators: {', '.join(touched)}")
    print(f"  reference period {latest_month}")
    print(f"  movers up   {[r['label_ko'] for r in mv['up']]}")
    print(f"  movers down {[r['label_ko'] for r in mv['down']]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

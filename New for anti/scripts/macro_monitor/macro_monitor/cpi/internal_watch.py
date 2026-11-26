"""Release-month surveillance, independent of movers, external prices and UI."""
from math import ceil
from statistics import mean

from .forward_validation import monthly_changes, shift

NEW, USED, PARTS, REPAIR, INS = AUTO = (
    "new_vehicles", "used_cars_and_trucks", "motor_vehicle_parts",
    "motor_vehicle_maintenance", "motor_vehicle_insurance",
)


def features(series, month):
    now = series.get(month)
    prior = [series[m] for i in range(-36, 0) if (m := shift(month, i)) in series]
    threshold = sorted(prior)[ceil(.9 * len(prior))-1] if len(prior) >= 24 else None
    trio = [series.get(shift(month, i)) for i in (-2, -1, 0)]
    return {"mom_pct": now, "prior_months": len(prior), "prior_p90_pct": threshold,
            "positive_spike": (now > max(0, threshold)) if None not in (now, threshold) else None,
            "avg_3m_mom_pct": mean(trio) if None not in trio else None}


def vehicle(items):
    if any(items.get(k, {}).get("positive_spike") is None or
           items[k]["avg_3m_mom_pct"] is None for k in AUTO):
        return "insufficient_data"
    spike = lambda k: items[k]["positive_spike"]
    if spike(NEW):
        return "vehicle_price_pressure_watch"
    if spike(INS):
        if (all(not spike(k) for k in AUTO[:-1])
                and all(items[k]["avg_3m_mom_pct"] <= 0 for k in (NEW, USED))
                and all(items[k]["mom_pct"] <= items[k]["avg_3m_mom_pct"] for k in (REPAIR, PARTS))):
            return "possible_residual_insurance_pressure"
        return "insurance_spike_unresolved"
    return "no_defined_pattern"


GUIDE = {
    "vehicle_price_pressure_watch": ("신차 가격 압력 주의", [USED, PARTS, REPAIR],
                                     "다음 발표에서 차량 구입·정비 가격으로 상승 범위가 넓어지는지 확인."),
    "possible_residual_insurance_pressure": ("보험료에 남은 압력 후보", [INS, REPAIR, NEW],
                                            "차량 가격은 최근 3개월 평균 비상승, 부품·수리도 가속하지 않음. 보험료 둔화와 신차 재반등 여부를 확인."),
    "insurance_spike_unresolved": ("보험료 급등 · 단계 미정", [NEW, USED, REPAIR, INS],
                                   "보험료만 보고 끝물로 판단할 수 없음. 차량가·수리비와 다음 보험료를 함께 확인."),
    "no_defined_pattern": ("정의한 자동차 패턴 없음", [], "이번 관측이 지정 조건에 해당하지 않음."),
    "insufficient_data": ("자동차 단계 판정 보류", [], "기준월·비교 이력이 부족함."),
}


def replay(auto, month):
    # Compare residual candidates to other insurance spikes; new-car spikes to
    # other eligible months. No model fitting, no overlapping-window inference.
    out = {k: {"flagged": [0, 0], "comparison": [0, 0]} for k in ("new", "residual")}
    for t in sorted(set.intersection(*(set(auto[k]) for k in AUTO)) if all(k in auto for k in AUTO) else []):
        if shift(t, 3) > month:
            continue
        f = {k: features(auto[k], t) for k in AUTO}
        state = vehicle(f)
        if state == "insufficient_data":
            continue
        following = {k: [auto[k].get(shift(t, i)) for i in (1, 2, 3)] for k in AUTO}
        if any(None in seq for seq in following.values()):
            continue
        # Breadth is a pick-up vs each item's own preceding three-month pace,
        # not a weighted CPI contribution and not proof of transmission.
        broader = sum(mean(following[k]) > max(0, f[k]["avg_3m_mom_pct"])
                      for k in (USED, PARTS, REPAIR)) >= 2
        for key, flag, eligible, outcome in (
            ("new", f[NEW]["positive_spike"], True, broader),
            ("residual", state == "possible_residual_insurance_pressure",
             f[INS]["positive_spike"], mean(following[INS]) < f[INS]["avg_3m_mom_pct"]),
        ):
            if eligible:
                cell = out[key]["flagged" if flag else "comparison"]
                cell[0] += int(outcome)
                cell[1] += 1
    return {"basis": "latest_vintage_descriptive_overlapping_months_not_forecast",
            "counts": "outcome_months / eligible_months", "horizon_months": 3, "results": out}


def assess(history, mapping, month):
    items = {}
    auto = {}
    for row in history.get("series", []):
        if not row["series_id"].startswith("CUSR"):
            continue
        changes = monthly_changes((o["date"], o["index"]) for o in row["observations"]
                                  if o["data_status"] == "observed" and o["date"] <= month)
        items[row["id"]] = {"series_id": row["series_id"], **features(changes, month)}
        if row["id"] in AUTO:
            auto[row["id"]] = changes
    paths = []
    for row in mapping["relationships"]:
        if row["type"] == "external_input_required":
            continue
        ids = list(dict.fromkeys(row["source_ids"] + row["target_ids"]))
        available = [k for k in ids if items.get(k, {}).get("positive_spike") is not None]
        spikes = [k for k in available if items[k]["positive_spike"]]
        paths.append({"relationship_id": row["id"], "type": row["type"], "spiking_ids": spikes,
                      "missing_ids": [k for k in ids if k not in available],
                      "compare_ids": [k for k in ids if k not in spikes] if spikes else [],
                      "observed_compare_ids": [k for k in available if k not in spikes] if spikes else []})
    stage = vehicle(items)
    label, follow, note = GUIDE[stage]
    return {"reference_period": month, "basis": "seasonally_adjusted_mom_pct",
            "policy": "positive MoM strictly above own prior 36-calendar-month P90; min 24 valid; editorial",
            "forecast_active": False, "items": items, "internal_paths": paths,
            "vehicle_replay": replay(auto, month),
            "vehicle_watch": {"state": stage, "label_ko": label, "check_next": follow, "note_ko": note}}

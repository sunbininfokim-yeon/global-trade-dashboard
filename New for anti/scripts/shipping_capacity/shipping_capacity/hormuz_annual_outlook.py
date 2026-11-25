"""Conditional calendar-year totals from a single EIA quarterly release."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from shipping_capacity.official_cargo import CARGO_LABELS, EIA_URL, quarter_dates


SCOPE = "strait_of_hormuz"
UNITS = {
    "crude_condensate": ("barrels_per_day", "barrels"),
    "lng": ("billion_cubic_feet_per_day", "billion_cubic_feet"),
}
WARNING_KO = (
    "연간 조건부 시나리오는 발표된 EIA 분기 일평균으로 환산한 누적에, "
    "미발표 기간의 가정 물량을 더한 초크모니터 계산입니다. EIA 전망·실측·신뢰구간이 아닙니다. "
    "미발표 기간에는 아직 수치가 발표되지 않은 과거 날짜도 포함될 수 있습니다. "
    "호르무즈를 통과한 기관 추정 물량 기준이며 우회항 선적은 더하지 않습니다."
)


def _valid_rate(row: dict[str, Any]) -> bool:
    value = row.get("value")
    return (
        row.get("status") == "reported" and type(value) in (int, float)
        and math.isfinite(value) and value >= 0
    )


def build_hormuz_annual_outlook(official_cargo: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Use only contiguous complete in-year quarters in a single dated edition."""
    eia = official_cargo.get("sources", {}).get("eia", {})
    result = {
        "contract_version": "hormuz-annual-outlook-v1",
        "method_id": "single_eia_release_fixed_quarter_daily_rate_to_year_end",
        "status": "unavailable",
        "publisher": "EIA",
        "source_url": EIA_URL,
        "source_status": eia.get("status", "not_fetched"),
        "source_published_at": None,
        "as_of": as_of.isoformat(),
        "cards": [],
        "warning_ko": WARNING_KO,
    }
    try:
        published = date.fromisoformat(eia.get("source_published_at", ""))
    except (TypeError, ValueError):
        return result
    if published > as_of:
        return result
    result["source_published_at"] = published.isoformat()
    result["attribution"] = f"Source: U.S. Energy Information Administration ({published}); EIA analysis based on Vortexa. Annual scenarios calculated by Chokemonitor."
    by_category: dict[str, dict[str, list[dict[str, Any]]]] = {key: {} for key in UNITS}
    for row in eia.get("records", {}).get("hormuz", []):
        category = row.get("cargo_category")
        if category not in UNITS or not (
            row.get("chokepoint_id") == "hormuz" and row.get("geography_scope") == SCOPE
            and row.get("unit") == UNITS[category][0] and row.get("publisher") == "EIA"
            and row.get("source_published_at") == result["source_published_at"]
            and row.get("frequency") == "quarterly" and row.get("statistic") == "period_daily_mean"
            and row.get("evidence_class") == "institution_estimate"
            and row.get("direction") == "source_aggregate_not_direction_resolved"
        ):
            continue
        try:
            start, end = quarter_dates(row.get("period", ""))
        except (TypeError, ValueError):
            continue
        if (row.get("period_start"), row.get("period_end")) != (start, end) or end > published.isoformat():
            continue
        by_category[category].setdefault(start, []).append(row)
    # Do not move the cut-off earlier to hide a missing commodity cell.
    starts = {date.fromisoformat(start) for group in by_category.values() for start in group}
    latest = max(starts, default=None)
    if latest is None or latest.year < as_of.year - 1:
        return result
    result["status"] = "reference_available"
    year, last_q = latest.year, (latest.month + 2) // 3
    bounds = [quarter_dates(f"{q}Q{year:04d}") for q in range(1, last_q + 1)]
    cut_off = date.fromisoformat(bounds[-1][1])
    year_end = date(year, 12, 31)
    remaining_days = (year_end - cut_off).days
    for category, (daily_unit, unit) in UNITS.items():
        selected = []
        missing = []
        for start, end in bounds:
            matches = by_category[category].get(start, [])
            if len(matches) != 1 or not _valid_rate(matches[0]):
                missing.append(start)
                continue
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            selected.append((matches[0], days))
        cumulative = None if missing else round(math.fsum(row["value"] * days for row, days in selected), 3)
        scenarios = []
        actual = None
        if missing:
            status = "insufficient_reported_quarters"
        elif remaining_days == 0:
            status = "full_year_institution_estimate"
            actual = cumulative
        elif year < as_of.year:
            status = "past_year_awaiting_final_quarter"
        elif last_q < 2:
            status = "awaiting_second_quarter"
        else:
            status = "conditional_outlook"
            last, previous = selected[-1][0], selected[-2][0]
            cases = [("latest_quarter_pace", "최근 발표 분기의 하루 통항 물량 유지", last)]
            if previous["value"] != last["value"]:
                cases.append(("previous_quarter_pace", "그 직전 분기의 하루 통항 물량을 적용", previous))
            for case_id, label, row in cases:
                balance = round(row["value"] * remaining_days, 3)
                scenarios.append({
                    "id": case_id, "label_ko": label,
                    "reference_period_start": row["period_start"], "reference_period_end": row["period_end"],
                    "assumed_daily_rate": row["value"],
                    "unreported_period_estimate": balance,
                    "annual_total": round(cumulative + balance, 3),
                })
        result["cards"].append({
            "cargo_category": category,
            "label_ko": CARGO_LABELS[category],
            "geography_scope": SCOPE,
            "status": status,
            "unit": unit,
            "daily_rate_unit": daily_unit,
            "year": year,
            "period_start": bounds[0][0],
            "period_end": year_end.isoformat(),
            "published_period_end": cut_off.isoformat(),
            "missing_quarter_starts": missing,
            "reported_cumulative": cumulative,
            "unreported_period_start": (cut_off + timedelta(days=1)).isoformat() if remaining_days else None,
            "unreported_days": remaining_days,
            "unreported_elapsed_days": min(remaining_days, (as_of - cut_off).days),
            "full_year_institution_total": actual,
            "scenarios": scenarios,
        })
    return result

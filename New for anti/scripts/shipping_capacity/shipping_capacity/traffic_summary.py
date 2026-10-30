"""Calendar-aligned, observed-only chokepoint traffic presentation contract.

All percentages are precomputed here. Ship-type weights are not TEU, barrels,
vessel counts, success probabilities or physical closure percentages.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import math
import statistics
from typing import Any


CONTRACT_VERSION = "chokepoint-traffic-v1"
UNIT = "estimated_trade_tonnes_per_day"
TYPE_LABELS = {"tanker": "유조선", "dry_bulk": "벌크선", "container": "컨테이너선", "general_cargo": "일반화물선"}


def _valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _dated_values(history: Any) -> dict[date, float | None]:
    result: dict[date, float | None] = {}
    for row in history if isinstance(history, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            day = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        value = float(row["value"]) if _valid_number(row.get("value")) else None
        # Conflicting duplicate dates cannot be silently counted or selected.
        if day in result and result[day] != value:
            result[day] = None
        else:
            result[day] = value
    return result


def _window(values: dict[date, float | None], end: date | None) -> dict[str, Any]:
    days = [end - timedelta(days=offset) for offset in reversed(range(7))] if end else []
    observations = [values.get(day) for day in days]
    available = sum(value is not None for value in observations)
    return {
        "status": "available" if available == 7 else "insufficient_daily_coverage",
        "value": round(statistics.fmean(observations), 6) if available == 7 else None,
        "start_date": days[0].isoformat() if days else None,
        "end_date": end.isoformat() if end else None,
        "observed_days": available,
        "required_days": 7,
    }


def _previous_month(day: date) -> date:
    year, month = (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _metric(values: dict[date, float | None], end: date | None) -> dict[str, Any]:
    current = _window(values, end)
    comparisons = {}
    for key, label, prior_end in (
        ("week", "전주 같은 7일", end - timedelta(days=7) if end else None),
        ("month", "전월 같은 시점 7일", _previous_month(end) if end else None),
        ("year", "전년 같은 요일 7일", end - timedelta(days=364) if end else None),
    ):
        baseline = _window(values, prior_end)
        comparable = current["value"] is not None and baseline["value"] is not None
        status = "available" if comparable and baseline["value"] > 0 else "zero_baseline" if comparable else "insufficient_daily_coverage"
        comparisons[key] = {
            "label_ko": label,
            "status": status,
            "change_pct": round((current["value"] / baseline["value"] - 1) * 100, 1) if status == "available" else None,
            "baseline": baseline,
        }
    return {"current": current, "comparisons": comparisons}


def build_traffic_summary(status: dict[str, Any]) -> dict[str, Any]:
    histories = status.get("metric_histories", {})
    values = {key: _dated_values(histories.get(key, {}).get("history", [])) for key in ("all", *TYPE_LABELS)}
    # A legacy representative tanker history must not become an all-ship one.
    if not values["all"] and status.get("history_metric_key") == "all":
        values["all"] = _dated_values(status.get("history", []))
    try:
        end = date.fromisoformat(str(status.get("latest_date")))
    except ValueError:
        end = max(values["all"], default=None)
    metrics = {key: _metric(history, end) for key, history in values.items()}
    total = metrics["all"]["current"]["value"]
    types = [{"metric_key": key, "label_ko": label, **metrics[key]} for key, label in TYPE_LABELS.items()]
    types.sort(key=lambda row: (row["current"]["value"] is not None, row["current"]["value"] or 0), reverse=True)
    known_sum = sum(row["current"]["value"] or 0 for row in types)
    composition_status = "available"
    if total is None or total <= 0:
        composition_status = "unavailable_total"
    elif any(row["current"]["value"] is None for row in types):
        composition_status = "incomplete_ship_types"
    elif known_sum > total + max(1, total * 0.001):
        composition_status = "non_additive_source_totals"
    for row in types:
        row["share_pct"] = round(row["current"]["value"] / total * 100, 1) if composition_status == "available" else None
    return {
        "contract_version": CONTRACT_VERSION,
        "unit": UNIT,
        "basis": "same_calendar_7d_mean_observed_only_no_imputation",
        "source": "IMF PortWatch",
        **metrics["all"],
        "composition_status": composition_status,
        "ship_types": types,
        "remaining_types_share_pct": round(max(0, (total - sum(row["current"]["value"] for row in types[:3])) / total * 100), 1) if composition_status == "available" else None,
        "comparison_policy_ko": "최근 7일 일평균 대비 전주 7일·전월 같은 시점에 끝나는 7일·52주 전 같은 요일 7일. 전월 말일 초과는 말일로 조정. 달 전체 평균 비교가 아닙니다.",
        "warning_ko": "AIS 포착 기반 추정 화물중량입니다. 선종별 중량 비중은 실제 품목 구성·TEU·원유 배럴·봉쇄율이 아니며 미포착 선박은 포함하지 못합니다.",
    }

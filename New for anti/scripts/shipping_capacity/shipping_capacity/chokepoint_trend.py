"""Year-over-year trend per chokepoint, and official-vs-AIS divergence.

The screen compares chokepoints of very different size, so it plots each
one's own change against the same 7 weekdays 52 weeks earlier, not tonnes.
Rises are kept as rises (no floor at zero).

PortWatch counts what AIS shows. Where an official estimate exists for the
same strait, both are turned into their own year-over-year change for the
same calendar quarter and compared as shares of last year. Tonnes and
barrels are never converted into each other.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

SHIFT_DAYS = 364
WINDOW_DAYS = 182
ROLLING_DAYS = 7
MIN_QUARTER_COVERAGE = 0.8
# AIS keeps less than half the share the official estimate keeps.
UNDERCOUNT_RATIO = 0.5
OVERCOUNT_RATIO = 1.5
COMPARISON_METRIC = "tanker"  # official figures are oil, so compare tankers


def _series(history: list[dict[str, Any]]) -> dict[date, float]:
    out: dict[date, float] = {}
    for row in history or []:
        try:
            day = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        value = row.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[day] = float(value)
    return out


def _window_mean(values: dict[date, float], end: date, days: int = ROLLING_DAYS) -> float | None:
    window = [values.get(end - timedelta(days=offset)) for offset in range(days)]
    if any(value is None for value in window):
        return None
    return sum(window) / days


def rolling_yoy(history: list[dict[str, Any]], window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    values = _series(history)
    if not values:
        return {"dates": [], "yoy_pct": []}
    last = max(values)
    dates, yoy = [], []
    for offset in range(window_days - 1, -1, -1):
        day = last - timedelta(days=offset)
        current = _window_mean(values, day)
        prior = _window_mean(values, day - timedelta(days=SHIFT_DAYS))
        dates.append(day.isoformat())
        # A gap on either side, or a zero base, leaves a gap -- never a fill.
        yoy.append(round((current / prior - 1) * 100, 1) if current is not None and prior else None)
    return {"dates": dates, "yoy_pct": yoy}


def _quarter_bounds(period_start: str) -> tuple[date, date]:
    start = date.fromisoformat(period_start)
    month = start.month + 3
    end = date(start.year + (month > 12), (month - 1) % 12 + 1, 1) - timedelta(days=1)
    return start, end


def _period_mean(values: dict[date, float], start: date, end: date) -> float | None:
    days = (end - start).days + 1
    hits = [values[start + timedelta(days=offset)] for offset in range(days) if start + timedelta(days=offset) in values]
    if len(hits) < MIN_QUARTER_COVERAGE * days:
        return None
    return sum(hits) / len(hits)


def official_vs_ais(official_point: dict[str, Any] | None, tanker_history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest EIA quarter with a prior-year quarter, against AIS tankers for the same quarters."""
    if not official_point:
        return None
    rows = sorted(
        (row for row in official_point.get("reported_series", [])
         if row.get("publisher") == "EIA" and row.get("frequency") == "quarterly"
         and row.get("cargo_category") == "total_oil" and row.get("value") is not None),
        key=lambda row: row["period_start"],
    )
    by_start = {row["period_start"]: row for row in rows}
    values = _series(tanker_history)
    for row in reversed(rows):
        start, end = _quarter_bounds(row["period_start"])
        prior_start = start.replace(year=start.year - 1)
        prior = by_start.get(prior_start.isoformat())
        if not prior or not prior["value"]:
            continue
        prior_end = _quarter_bounds(prior_start.isoformat())[1]
        ais_now, ais_then = _period_mean(values, start, end), _period_mean(values, prior_start, prior_end)
        official_share = row["value"] / prior["value"]
        result = {
            "period": row["period"],
            "prior_period": prior["period"],
            "publisher": "EIA",
            "official_cargo_category": "total_oil",
            "official_yoy_pct": round((official_share - 1) * 100, 1),
            "ais_metric": COMPARISON_METRIC,
            "ais_yoy_pct": None,
            "ais_to_official_share_ratio": None,
            "status": "ais_coverage_insufficient",
        }
        if ais_now is None or not ais_then:
            return result
        ais_share = ais_now / ais_then
        ratio = ais_share / official_share if official_share > 0 else None
        result.update({
            "ais_yoy_pct": round((ais_share - 1) * 100, 1),
            "ais_to_official_share_ratio": round(ratio, 2) if ratio is not None else None,
            "status": (
                "ais_undercount_likely" if ratio is not None and ratio < UNDERCOUNT_RATIO
                else "ais_above_official" if ratio is not None and ratio > OVERCOUNT_RATIO
                else "consistent"
            ),
        })
        return result
    return None


def official_latest(official_point: dict[str, Any] | None) -> dict[str, Any] | None:
    """Newest published total-oil figure for the strait, from any publisher, as is."""
    if not official_point:
        return None
    cards = [card for card in official_point.get("reference_cards", []) + official_point.get("supplementary_reference_cards", [])
             if card.get("cargo_category") == "total_oil" and card.get("value") is not None]
    if not cards:
        return None
    card = max(cards, key=lambda item: item["period_end"])
    return {key: card.get(key) for key in ("publisher", "period", "frequency", "value", "unit", "geography_scope", "source_published_at", "source_url")}


def build_chokepoint_trend(
    chokepoints: list[dict[str, Any]],
    live_status: dict[str, dict[str, Any]],
    live_display: list[dict[str, Any]],
    official_cargo: dict[str, Any] | None,
) -> dict[str, Any]:
    display = {row.get("chokepoint_id"): row for row in live_display or []}
    official_points = (official_cargo or {}).get("chokepoints") or {}
    points = []
    for chokepoint in chokepoints:
        point_id = chokepoint["id"]
        status = live_status.get(point_id) or {}
        histories = status.get("metric_histories") or {}
        metric_key = (display.get(point_id) or {}).get("metric_key") or "all"
        series = rolling_yoy((histories.get(metric_key) or {}).get("history", []))
        latest = next((value for value in reversed(series["yoy_pct"]) if value is not None), None)
        points.append({
            "chokepoint_id": point_id,
            "metric_key": metric_key,
            "latest_yoy_pct": latest,
            "latest_date": series["dates"][-1] if series["dates"] else None,
            "yoy_pct": series["yoy_pct"],
            "dates": series["dates"],
            "official_latest": official_latest(official_points.get(point_id)),
            "official_vs_ais": official_vs_ais(official_points.get(point_id), (histories.get(COMPARISON_METRIC) or {}).get("history", [])),
        })
    return {
        "contract_version": "chokepoint-trend-v1",
        "basis": "7_day_mean_vs_same_7_weekdays_52_weeks_earlier",
        "shift_days": SHIFT_DAYS,
        "rolling_days": ROLLING_DAYS,
        "window_days": WINDOW_DAYS,
        "undercount_ratio_threshold": UNDERCOUNT_RATIO,
        "points": points,
        "warning_ko": "PortWatch AIS로 포착된 통항의 전년 대비 변화다. 위협 해역에서 AIS를 끄면 실제 통항보다 크게 줄어 보일 수 있다. 공식 추정과의 비교는 각자의 전년 대비 비율끼리만 하며, 톤과 배럴을 서로 환산하지 않는다.",
    }

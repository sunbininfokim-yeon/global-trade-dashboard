"""Historical LETF trading-share points from end-of-day KRX rows.

This is an observed daily turnover series, not an intraday position or flow
series.  A point is emitted only when both the KOSPI cash and levered/inverse
ETF trading values are available for the same business date.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fetch_kr_public_extras import classify_letf_direction, classify_letf_name


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return None


def point_from_krx_rows(
    *, date: str, stock_rows: list[dict[str, Any]], etf_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Aggregate one KRX end-of-day date into the chart contract."""
    cash_tv = sum(_num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT") or 0.0 for row in stock_rows)
    if cash_tv <= 0:
        return None

    by_direction: dict[str, float] = {}
    by_category: dict[str, float] = {}
    levered_tv = 0.0
    for row in etf_rows:
        name = str(row.get("ISU_NM") or row.get("ISU_ABBRV") or "")
        if not any(token in name for token in ("레버리지", "인버스", "곱버스")):
            continue
        value = _num(row, "ACC_TRDVAL", "ACC_TRDVAL_AMT")
        if value is None or value < 0:
            continue
        direction = classify_letf_direction(name)
        category = classify_letf_name(name)
        levered_tv += value
        by_direction[direction] = by_direction.get(direction, 0.0) + value
        by_category[category] = by_category.get(category, 0.0) + value

    if levered_tv <= 0:
        return None
    inverse_tv = sum(v for k, v in by_direction.items() if "inverse" in k or k == "gobus_inverse_2x")
    return {
        "date": date,
        "levered_inverse_etf_tv_krw": levered_tv,
        "levered_inverse_etf_tv_jo": round(levered_tv / 1e12, 4),
        "kospi_cash_tv_krw": cash_tv,
        "kospi_cash_tv_jo": round(cash_tv / 1e12, 4),
        "levered_inverse_etf_tv_over_kospi_cash_tv_pct": round(100.0 * levered_tv / cash_tv, 4),
        "inverse_share_of_lev_tv_pct": round(100.0 * inverse_tv / levered_tv, 4),
        "long_tv_jo": round(by_direction.get("long", 0.0) / 1e12, 4),
        "inverse_tv_jo": round(
            sum(v for k, v in by_direction.items() if k.startswith("inverse") or k == "gobus_inverse_2x")
            / 1e12,
            4,
        ),
        "gobus_tv_jo": round(by_direction.get("gobus_inverse_2x", 0.0) / 1e12, 4),
        "by_direction": {
            key: {"trading_value_jo": round(value / 1e12, 4)}
            for key, value in sorted(by_direction.items())
        },
        "by_category": {
            key: {"trading_value_jo": round(value / 1e12, 4)}
            for key, value in sorted(by_category.items())
        },
        "quality": "observed",
        "source": "KRX OpenAPI sto/stk_bydd_trd + etp/etf_bydd_trd",
    }


def point_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Convert the current market snapshot into one append-only point."""
    ratio = snapshot.get("market_letf_derivatives_ratios") or {}
    category = snapshot.get("letf_category_share") or {}
    ratio_pct = ratio.get("levered_inverse_etf_tv_over_kospi_cash_tv_pct")
    cash_jo = category.get("kospi_cash_tv_jo")
    lev_jo = category.get("levered_inverse_tv_jo")
    if ratio_pct is None or cash_jo is None or lev_jo is None:
        return None
    return {
        "date": snapshot.get("as_of"),
        "levered_inverse_etf_tv_jo": lev_jo,
        "kospi_cash_tv_jo": cash_jo,
        "levered_inverse_etf_tv_over_kospi_cash_tv_pct": ratio_pct,
        "inverse_share_of_lev_tv_pct": ratio.get("inverse_share_of_lev_tv_pct"),
        "long_tv_jo": ratio.get("long_tv_jo"),
        "inverse_tv_jo": ratio.get("inverse_tv_jo"),
        "gobus_tv_jo": ratio.get("gobus_tv_jo"),
        "quality": category.get("quality") or "observed",
        "source": category.get("source") or "snapshot",
    }


def append_point(history: dict[str, Any], point: dict[str, Any]) -> dict[str, Any]:
    points = [p for p in (history.get("points") or []) if p.get("date") != point.get("date")]
    points.append(point)
    points.sort(key=lambda p: str(p.get("date") or ""))
    out = dict(history)
    out.update(
        {
            "schema_version": "market-microstructure-history-v1",
            "as_of": point.get("date"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "points": points,
            "n_points": len(points),
            "note_ko": "장 마감 기준 KRX 거래대금 관측 시계열. 고객 포지션·장중 체결 방향 아님.",
            "disclaimer_ko": "과거 시계열은 KRX 일별 거래대금 기준이며 투자 권유가 아닙니다.",
        }
    )
    return out


def business_dates(months: int = 6) -> list[str]:
    start = datetime.now() - timedelta(days=int(months * 31))
    today = datetime.now()
    dates: list[str] = []
    cursor = start
    while cursor.date() <= today.date():
        if cursor.weekday() < 5:
            dates.append(cursor.strftime("%Y%m%d"))
        cursor += timedelta(days=1)
    return dates

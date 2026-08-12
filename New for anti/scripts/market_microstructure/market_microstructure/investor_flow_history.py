"""Append-only KOSPI cash-market investor net-flow history.

The source reports each investor class's market-wide daily net purchase after
the close.  It does not identify trades, holdings, programme flow, or the
investor behind a specific ETF/derivatives transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


FLOW_FIELDS = ("foreign_net_eok", "retail_net_eok", "institution_net_eok")


def _iso_date(value: Any) -> str | None:
    text = str(value or "").strip().replace(".", "-").replace("/", "-")
    parts = text.split("-")
    if len(parts) != 3 or not all(parts):
        return None
    year, month, day = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except ValueError:
        return None


def point_from_row(row: dict[str, Any], *, source: str | None = None) -> dict[str, Any] | None:
    date = _iso_date(row.get("observed_as_of") or row.get("date") or row.get("date_raw"))
    if not date:
        return None
    values: dict[str, float | None] = {}
    for field in FLOW_FIELDS:
        raw = row.get(field)
        try:
            values[field] = None if raw is None else float(raw)
        except (TypeError, ValueError):
            values[field] = None
    if not any(value is not None for value in values.values()):
        return None
    return {
        "date": str(date),
        **values,
        "quality": "observed",
        "source": source,
    }


def append_points(history: dict[str, Any], rows: list[dict[str, Any]], *, source: str | None = None) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for point in history.get("points") or []:
        if not isinstance(point, dict):
            continue
        date = _iso_date(point.get("date"))
        if date:
            merged[date] = {**point, "date": date}
    for row in rows:
        point = point_from_row(row, source=source)
        if point:
            merged[point["date"]] = point
    points = [merged[key] for key in sorted(merged)]
    return {
        "schema_version": "kospi-investor-flow-history-v1",
        "as_of": points[-1]["date"] if points else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "unit": "억원 (당일 순매수; 음수=순매도)",
        "quality": "observed" if points else "missing",
        "points": points,
        "n_points": len(points),
        "note_ko": "KOSPI 현물 시장 전체 투자자별 장마감 순매수 시계열. 매수·매도 총액, 종목별 체결, 보유 포지션, 프로그램 매매가 아님.",
    }

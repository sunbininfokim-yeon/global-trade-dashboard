"""BLS API collector for observed CPI index histories.

This module intentionally handles index levels only.  BLS API values cannot
replace same-vintage Table 6/7 effects or relative importances, so it does not
calculate headline contribution rankings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen


ENDPOINT = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


class BLSApiError(RuntimeError):
    """Raised for a non-successful BLS Public Data API response."""


def _chunks(values: list[str], size: int = 50) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_series(
    series_ids: list[str],
    *,
    registration_key: str,
    start_year: int,
    end_year: int,
    opener=urlopen,
) -> dict[str, Any]:
    """Fetch up to 20 years per request from BLS v2 without persisting the key."""
    if not registration_key:
        raise ValueError("BLS_API_KEY is required")
    if end_year < start_year or end_year - start_year >= 20:
        raise ValueError("BLS v2 requests may span at most 20 calendar years")
    out: dict[str, Any] = {}
    for batch in _chunks(series_ids):
        payload = {
            "seriesid": batch,
            "startyear": str(start_year),
            "endyear": str(end_year),
            "catalog": True,
            "registrationkey": registration_key,
        }
        request = Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with opener(request, timeout=45) as response:
            doc = json.loads(response.read().decode("utf-8"))
        if doc.get("status") != "REQUEST_SUCCEEDED":
            raise BLSApiError(f"BLS API request failed: {doc.get('message')}")
        messages = doc.get("message") or []
        invalid = [message for message in messages if "Series does not exist" in message]
        if invalid:
            raise BLSApiError(f"BLS API contains invalid configured series: {invalid}")
        for series in doc.get("Results", {}).get("series", []):
            out[series["seriesID"]] = series
    missing = [series_id for series_id in series_ids if series_id not in out]
    if missing:
        raise BLSApiError(f"BLS API did not return configured series: {missing}")
    return out


def _observations(series: Mapping[str, Any]) -> list[dict[str, Any]]:
    points: dict[str, dict[str, Any]] = {}
    for row in series.get("data", []):
        period = str(row.get("period", ""))
        if not (period.startswith("M") and period[1:].isdigit() and 1 <= int(period[1:]) <= 12):
            continue
        date = f"{row['year']}-{int(period[1:]):02d}"
        raw_value = str(row.get("value", "")).strip()
        try:
            index_value = float(raw_value)
        except ValueError:
            index_value = None
        points[date] = {
            "date": date,
            "index": index_value,
            "data_status": "observed" if index_value is not None else "not_published",
            "footnotes": [note.get("text") for note in row.get("footnotes", []) if note.get("text")],
        }
    ordered = [points[key] for key in sorted(points)]
    by_date = {row["date"]: row for row in ordered}
    for index, row in enumerate(ordered):
        previous = ordered[index - 1] if index else None
        year_ago = by_date.get(f"{int(row['date'][:4]) - 1:04d}-{row['date'][5:]}")
        row["mom_pct"] = (
            round((row["index"] / previous["index"] - 1) * 100, 4)
            if previous and row["index"] is not None and previous["index"] is not None
            else None
        )
        row["yoy_pct"] = (
            round((row["index"] / year_ago["index"] - 1) * 100, 4)
            if year_ago and row["index"] is not None and year_ago["index"] is not None
            else None
        )
    return ordered


def build_cpi_api_history(
    config: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict[str, Any]:
    """Normalize BLS API output and retain exact source-series provenance."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    items = []
    for spec in config["series"]:
        raw = response[spec["series_id"]]
        catalog = raw.get("catalog") or {}
        items.append({
            **spec,
            "official_series_title": catalog.get("series_title"),
            "observations": _observations(raw),
        })
    latest_dates = [item["observations"][-1]["date"] for item in items if item["observations"]]
    return {
        "schema_version": "us-cpi-api-history-v1",
        "model": "us_cpi_observed_series",
        "retrieved_at": retrieved_at,
        "source": {
            **config["source"],
            "vintage_policy": "current BLS database vintage; revisions may occur",
            "data_status": "official_observed",
        },
        "coverage": {
            "configured_series": len(config["series"]),
            "returned_series": len(items),
            "latest_reference_period": min(latest_dates) if latest_dates else None,
        },
        "series": items,
        "limitations": [
            "이 파일은 BLS API의 현행 개정 빈티지 지수 수준이다. 발표 당시 빈티지는 별도 보관이 필요하다.",
            "BLS API에는 Table 6/7의 All Items 기여도(effect)와 동일 빈티지 상대가중치가 없으므로, 이 파일로 기여도 순위를 만들지 않는다.",
            "MoM·YoY는 수집된 지수 수준에서 재계산한 관측값이며 예측·신호·인과판정이 아니다."
        ],
    }

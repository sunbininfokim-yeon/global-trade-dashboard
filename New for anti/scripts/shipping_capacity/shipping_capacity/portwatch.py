"""Keyless IMF PortWatch ArcGIS client and baseline anomaly calculation."""

from __future__ import annotations

import json
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


PORTWATCH_QUERY_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Chokepoints_Data/FeatureServer/0/query"
)

CAPACITY_FIELDS = {
    "container": "capacity_container",
    "dry_bulk": "capacity_dry_bulk",
    "general_cargo": "capacity_general_cargo",
    "tanker": "capacity_tanker",
    "all": "capacity",
}


def _date_key(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float("-inf")
    return float("-inf")


def _iso_date(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).date().isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None
    return None


def _mean(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
    return statistics.fmean(values) if values else None


class PortWatchClient:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_series(self, portwatch_id: str, record_count: int = 120) -> list[dict[str, Any]]:
        params = {
            "where": f"portid='{portwatch_id}'",
            "outFields": "date,portid,portname,n_total,capacity,capacity_container,capacity_dry_bulk,capacity_general_cargo,capacity_tanker",
            "returnGeometry": "false",
            "orderByFields": "date DESC",
            "resultRecordCount": str(record_count),
            "f": "json",
        }
        url = PORTWATCH_QUERY_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard/1.0"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(f"PortWatch API error: {payload['error']}")
        rows = [feature["attributes"] for feature in payload.get("features", [])]
        rows.sort(key=lambda row: _date_key(row.get("date")))
        return rows

    def fetch_status(self, portwatch_id: str) -> dict[str, Any]:
        return summarize_series(self.fetch_series(portwatch_id), portwatch_id)


def summarize_series(rows: list[dict[str, Any]], portwatch_id: str) -> dict[str, Any]:
    """Compare latest seven observations with the preceding 28 observations."""

    valid = [row for row in rows if _date_key(row.get("date")) != float("-inf")]
    valid.sort(key=lambda row: _date_key(row.get("date")))
    if len(valid) < 14:
        return {
            "portwatch_id": portwatch_id,
            "quality": "insufficient_history",
            "observation_count": len(valid),
            "metrics": {},
        }
    current = valid[-7:]
    baseline = valid[-35:-7] if len(valid) >= 35 else valid[:-7]
    metrics: dict[str, Any] = {}
    for ship_type, field in CAPACITY_FIELDS.items():
        current_mean = _mean(current, field)
        baseline_mean = _mean(baseline, field)
        if current_mean is None or baseline_mean in (None, 0):
            continue
        ratio = current_mean / baseline_mean
        metrics[ship_type] = {
            "field": field,
            "current_7d_mean_dwt": current_mean,
            "prior_28d_mean_dwt": baseline_mean,
            "capacity_ratio": ratio,
            "observed_shortfall_fraction": max(0.0, min(1.0, 1.0 - ratio)),
            "change_pct": (ratio - 1.0) * 100.0,
        }
    latest_date = _iso_date(valid[-1]["date"])
    return {
        "portwatch_id": portwatch_id,
        "portname": valid[-1].get("portname"),
        "latest_date": latest_date,
        "quality": "observed_capacity_shortfall_7d_vs_prior_28d",
        "interpretation": "Short-term capacity anomaly used as a shock proxy; not proof of literal closure.",
        "observation_count": len(valid),
        "metrics": metrics,
    }

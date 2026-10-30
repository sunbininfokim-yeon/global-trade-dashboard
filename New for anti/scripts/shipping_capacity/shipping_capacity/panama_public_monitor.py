"""Public-safe Panama Canal rainfall monitor based only on NASA GPM IMERG.

This module deliberately has no ACP import, request, field name, or derived
output.  It is suitable for a public portfolio artifact because it publishes
only an openly sourced satellite-rainfall monitor and a matching-calendar-day
year-over-year comparison.  It does not estimate canal water levels, draft
limits, booking slots, transit counts, or vessel capacity.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import tempfile
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


GPM_SHORT_NAME = "GPM_3IMERGDL"
GPM_VERSION = "07"
GPM_COLLECTION_URL = "https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDL_07/summary"
# This is a transparent monitoring rectangle, not an official Panama Canal
# watershed polygon or a water-balance boundary.
PANAMA_CANAL_MONITORING_BBOX = (8.6, -80.3, 9.7, -79.1)  # south, west, north, east


class PublicMonitorError(ValueError):
    """Raised when a public-monitor input cannot be safely interpreted."""


@dataclass(frozen=True)
class DailySatelliteRainfall:
    observation_date: str
    precipitation_mm: float
    source_url: str


def _earthdata_token() -> str:
    token = os.environ.get("NASA_EARTHDATA") or os.environ.get("EARTHDATA_TOKEN")
    if not token:
        raise PublicMonitorError("NASA_EARTHDATA or EARTHDATA_TOKEN is required for GPM collection")
    return token


def _request(url: str, token: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "GlobalTradeDashboardPublicMonitor/1.0 (+noncommercial)",
        },
    )


def _granules(start_date: str, end_date: str, token: str) -> list[tuple[str, str]]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise PublicMonitorError("GPM dates must use YYYY-MM-DD") from exc
    if end < start:
        raise PublicMonitorError("end date precedes start date")
    if (end - start).days + 1 > 31:
        raise PublicMonitorError("public monitor is limited to 31 days per run")
    query = urllib.parse.urlencode({
        "short_name": GPM_SHORT_NAME,
        "version": GPM_VERSION,
        "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
        "page_size": "2000",
    })
    try:
        with urllib.request.urlopen(
            _request(f"https://cmr.earthdata.nasa.gov/search/granules.json?{query}", token), timeout=60
        ) as response:
            entries = json.loads(response.read().decode("utf-8"))["feed"]["entry"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise PublicMonitorError("Earthdata CMR did not return GPM granules") from exc
    rows = []
    for entry in entries:
        stamp = str(entry.get("time_start", ""))[:10]
        href = next(
            (str(link["href"]) for link in entry.get("links", []) if str(link.get("href", "")).endswith(".nc4")),
            None,
        )
        if href and re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            rows.append((stamp, href))
    if not rows:
        raise PublicMonitorError("no downloadable GPM IMERG daily files found")
    if len({stamp for stamp, _ in rows}) != len(rows):
        raise PublicMonitorError("GPM query returned duplicate observation dates")
    return sorted(rows)


def gpm_window_mean_mm(path: Path, bbox: tuple[float, float, float, float] = PANAMA_CANAL_MONITORING_BBOX) -> float:
    """Calculate a latitude-weighted mean from one GPM daily NetCDF4 file."""

    try:
        import h5py
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency check
        raise PublicMonitorError("h5py and numpy are required to read GPM IMERG NetCDF4") from exc
    south, west, north, east = bbox
    if not (south < north and west < east):
        raise PublicMonitorError("bbox must be south, west, north, east")
    with h5py.File(path, "r") as handle:
        if not {"lat", "lon", "precipitation"}.issubset(handle):
            raise PublicMonitorError("GPM file lacks lat, lon, or precipitation")
        lat = np.asarray(handle["lat"][:], dtype=float)
        lon = np.asarray(handle["lon"][:], dtype=float)
        precipitation = np.asarray(handle["precipitation"][:], dtype=float)
    if precipitation.ndim != 3 or precipitation.shape[0] != 1:
        raise PublicMonitorError("expected one daily GPM precipitation grid")
    lat_mask = (lat >= south) & (lat <= north)
    lon_mask = (lon >= west) & (lon <= east)
    if not lat_mask.any() or not lon_mask.any():
        raise PublicMonitorError("monitoring rectangle contains no GPM grid cells")
    values = precipitation[0]
    latitude_weights = np.cos(np.deg2rad(lat[lat_mask]))
    if values.shape == (len(lon), len(lat)):
        window = values[lon_mask, :][:, lat_mask]
        weights = np.broadcast_to(latitude_weights, window.shape)
    elif values.shape == (len(lat), len(lon)):
        window = values[lat_mask, :][:, lon_mask]
        weights = np.broadcast_to(latitude_weights[:, None], window.shape)
    else:
        raise PublicMonitorError("GPM coordinate dimensions do not match precipitation grid")
    valid = np.isfinite(window) & (window >= 0)
    if not valid.any():
        raise PublicMonitorError("no valid precipitation cells in monitoring rectangle")
    return float(np.average(window[valid], weights=weights[valid]))


def fetch_gpm_monitor(start_date: str, end_date: str) -> list[DailySatelliteRainfall]:
    """Fetch a short GPM window; raw files exist only inside a temporary directory."""

    token = _earthdata_token()
    rows = []
    with tempfile.TemporaryDirectory(prefix="panama-public-gpm-") as directory:
        temporary_dir = Path(directory)
        for stamp, source_url in _granules(start_date, end_date, token):
            path = temporary_dir / f"{stamp}.nc4"
            try:
                with urllib.request.urlopen(_request(source_url, token), timeout=180) as response:
                    path.write_bytes(response.read())
            except OSError as exc:
                raise PublicMonitorError(f"could not download GPM IMERG file for {stamp}") from exc
            rows.append(DailySatelliteRainfall(stamp, round(gpm_window_mean_mm(path), 4), source_url))
    return rows


def summarize_rainfall(rows: list[DailySatelliteRainfall]) -> dict[str, Any]:
    if not rows:
        return {"status": "not_supplied"}
    ordered = sorted(rows, key=lambda row: row.observation_date)
    if len({row.observation_date for row in ordered}) != len(ordered):
        raise PublicMonitorError("duplicate GPM observation dates")
    values = [row.precipitation_mm for row in ordered]
    return {
        "status": "observed_satellite_precipitation",
        "product_id": f"{GPM_SHORT_NAME}.{GPM_VERSION}",
        "monitoring_geometry": {
            "type": "rectangular_monitoring_proxy_not_official_watershed_boundary",
            "bbox_south_west_north_east": list(PANAMA_CANAL_MONITORING_BBOX),
        },
        "observation_range": [ordered[0].observation_date, ordered[-1].observation_date],
        "observed_day_count": len(ordered),
        "total_precipitation_mm": round(sum(values), 3),
        "mean_precipitation_mm_per_day": round(statistics.fmean(values), 3),
        "daily_rows": [asdict(row) for row in ordered],
        "interpretation_ko": "공개 위성 강수 관측치이며 운하 수위·통항량·선복량 예측값이 아닙니다.",
    }


def compare_same_calendar_days(
    current_rows: list[DailySatelliteRainfall], previous_year_rows: list[DailySatelliteRainfall]
) -> dict[str, Any]:
    if not current_rows or not previous_year_rows:
        return {"status": "comparison_not_supplied"}
    current = sorted(current_rows, key=lambda row: row.observation_date)
    previous = {row.observation_date: row for row in previous_year_rows}
    expected = []
    for row in current:
        try:
            expected.append(date.fromisoformat(row.observation_date).replace(year=date.fromisoformat(row.observation_date).year - 1).isoformat())
        except ValueError:
            return {"status": "withheld_leap_day_not_comparable"}
    if any(stamp not in previous for stamp in expected):
        return {"status": "withheld_missing_matching_previous_year_observation", "required_dates": expected}
    current_total = sum(row.precipitation_mm for row in current)
    prior_total = sum(previous[stamp].precipitation_mm for stamp in expected)
    difference = current_total - prior_total
    return {
        "status": "comparable_observed_same_calendar_days",
        "current_observation_range": [current[0].observation_date, current[-1].observation_date],
        "previous_year_observation_range": [expected[0], expected[-1]],
        "observed_day_count": len(current),
        "current_total_precipitation_mm": round(current_total, 3),
        "previous_year_total_precipitation_mm": round(prior_total, 3),
        "difference_mm": round(difference, 3),
        "change_pct": None if prior_total == 0 else round(100 * difference / prior_total, 2),
        "interpretation_ko": "동일 달·일의 위성 강수량 비교일 뿐, 운하 통항량 또는 저수량의 전년비가 아닙니다.",
    }


def build_public_monitor(
    current_rows: list[DailySatelliteRainfall], previous_year_rows: list[DailySatelliteRainfall]
) -> dict[str, Any]:
    """Create the public artifact with explicit exclusions, not hidden provenance."""

    return {
        "schema_version": "panama_climate_monitor_v1",
        "status": "public_portfolio_monitor",
        "scope_ko": "파나마 운하 주변 강수 관측 모니터",
        "public_boundary_ko": (
            "이 산출물은 NASA GPM 위성 강수 관측만 사용합니다. 운하 운영기관 자료, 수위, 흘수제한, "
            "예약슬롯, 통항량, 선복량 또는 이들의 예측값은 포함하지 않습니다."
        ),
        "rainfall": summarize_rainfall(current_rows),
        "year_over_year": compare_same_calendar_days(current_rows, previous_year_rows),
        "data_sources": [
            {
                "id": "nasa_gpm_imerg_late",
                "name": "NASA GPM IMERG daily Late Run",
                "role_ko": "최근 위성 강수 관측",
                "url": GPM_COLLECTION_URL,
                "attribution_ko": "NASA GPM IMERG 자료를 재가공했습니다. NASA의 공식 예보·보증이 아닙니다.",
            }
        ],
        "not_included": [
            "canal_water_level",
            "draft_limit",
            "booking_slots",
            "vessel_transits",
            "shipping_capacity",
            "acp_data_or_derived_outputs",
        ],
    }

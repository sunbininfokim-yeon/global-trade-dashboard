"""Research-only A/B benchmark for Panama Canal hydrology inputs.

The ACP water-level endpoint is publicly reachable but its page does not grant
an open reuse licence.  This module never writes ACP source rows to the
repository or to a published snapshot.  It is deliberately opt-in and is for
local research comparison only: open hydrometeorology versus the same model
with an observed Gatún water-level state.

It does *not* claim that ACP's own forward projection has been backtested;
historical issued projections are not available in the source endpoint.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


ACP_HISTORY_URL = (
    "https://evtms-rpts.pancanal.com/eng/h2o/"
    "Download_Gatun_Lake_Water_Level_History.csv"
)
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PANAMA_WATERSHED_POINT = {"latitude": 9.2, "longitude": -79.9}
OPEN_PARAMETERS = ("PRECTOTCORR", "T2M", "RH2M", "WS2M")
NASA_POWER_START = date(1981, 1, 1)

# The open-only path deliberately uses sources whose public data terms are
# documented by the publisher.  URLs are provenance metadata, not download
# instructions for a published snapshot.
OPEN_SOURCE_PROVENANCE = {
    "nasa_power": {
        "role": "daily meteorology",
        "url": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
        "reuse": "NASA open data policy; attribution requested",
    },
    "chirps": {
        "role": "historical gridded precipitation",
        "url": "https://www.chc.ucsb.edu/data/chirps",
        "reuse": "public domain according to the Climate Hazards Center",
    },
    "chirps_gefs": {
        "role": "1-16 day precipitation outlook",
        "url": "https://www.chc.ucsb.edu/data/chirps-gefs",
        "reuse": "public data access; retain source attribution",
    },
    "noaa_gfs": {
        "role": "open numerical weather forecast",
        "url": "https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast",
        "reuse": "NOAA open data",
    },
}


class ResearchDataBoundaryError(ValueError):
    """Raised when the explicit local-research boundary is not accepted."""


@dataclass(frozen=True)
class BenchmarkResult:
    horizon_days: int
    test_start: str
    test_end: str
    open_hydromet_mae_ft: float
    observed_acp_state_mae_ft: float
    open_hydromet_rmse_ft: float
    observed_acp_state_rmse_ft: float
    mae_improvement_fraction: float
    method_boundary: str


@dataclass(frozen=True)
class OpenOnlyHydrometSignal:
    """ACP-free operational proxy; never represented as an official lake level."""

    as_of: str
    horizon_days: int
    rainfall_mm: float
    seasonal_rainfall_mm: float
    rainfall_deficit_fraction: float
    dryness_anomaly: float
    hydrology_stress_index: float
    capacity_retention_proxy: float
    forecast_status: str
    forecast_use: str
    source_ids: tuple[str, ...]
    caveat: str


def _fetch_text(url: str, timeout_seconds: int = 30) -> str:
    with urlopen(url, timeout=timeout_seconds) as response:  # nosec B310 - fixed public URLs
        return response.read().decode("utf-8-sig")


def fetch_acp_history(*, allow_research_fetch: bool) -> dict[date, float]:
    """Fetch ACP history only after an explicit local-research acknowledgement.

    The returned mapping remains in process memory. Callers must not persist or
    publish the ACP source rows without separate reuse permission from ACP.
    """

    if not allow_research_fetch:
        raise ResearchDataBoundaryError(
            "ACP fetch is research-only; pass explicit acknowledgement before fetching"
        )
    rows = csv.DictReader(io.StringIO(_fetch_text(ACP_HISTORY_URL)))
    output: dict[date, float] = {}
    for row in rows:
        value = row.get("GATUN_LAKE_LEVEL(FEET)")
        if not value:
            continue
        output[date.fromisoformat(row["DATE_LOG"])] = float(value)
    if len(output) < 365 * 10:
        raise ValueError("ACP history is unexpectedly short")
    return output


def fetch_nasa_power_daily(
    start: date,
    end: date,
    *,
    latitude: float = PANAMA_WATERSHED_POINT["latitude"],
    longitude: float = PANAMA_WATERSHED_POINT["longitude"],
) -> dict[date, dict[str, float]]:
    """Fetch open daily meteorology without storing raw responses."""

    query = urlencode(
        {
            "parameters": ",".join(OPEN_PARAMETERS),
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "UTC",
        }
    )
    payload = json.loads(_fetch_text(f"{NASA_POWER_URL}?{query}"))
    parameters = payload["properties"]["parameter"]
    output: dict[date, dict[str, float]] = {}
    for raw_day in parameters[OPEN_PARAMETERS[0]]:
        values = {name: float(parameters[name][raw_day]) for name in OPEN_PARAMETERS}
        if any(value <= -900 for value in values.values()):
            continue
        output[date.fromisoformat(f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:]}")] = values
    return output


def _complete_window(
    weather: dict[date, dict[str, float]],
    end: date,
    days: int,
    parameter: str,
) -> list[float] | None:
    values = [
        weather.get(end - timedelta(days=offset), {}).get(parameter)
        for offset in range(days)
    ]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values]


def _seasonal_window_mean(
    weather: dict[date, dict[str, float]],
    anchor: date,
    days: int,
    parameter: str,
    *,
    day_tolerance: int = 21,
) -> float | None:
    """Estimate a same-season normal from earlier complete windows.

    This is intentionally a transparent climatological normal.  It is not a
    reservoir model and does not imply that rainfall maps one-to-one to lake
    level or Canal capacity.
    """

    candidates: list[float] = []
    for candidate in sorted(weather):
        if candidate >= anchor:
            break
        day_delta = abs(candidate.timetuple().tm_yday - anchor.timetuple().tm_yday)
        day_delta = min(day_delta, 366 - day_delta)
        if day_delta > day_tolerance:
            continue
        window = _complete_window(weather, candidate, days, parameter)
        if window is not None:
            candidates.append(float(sum(window)))
    if len(candidates) < 3:
        return None
    return float(np.median(candidates))


def build_open_only_hydromet_signal(
    weather: dict[date, dict[str, float]],
    *,
    as_of: date,
    horizon_days: int,
    capacity_sensitivity: float = 0.35,
    forecast_weather: dict[date, dict[str, float]] | None = None,
) -> OpenOnlyHydrometSignal:
    """Build an ACP-free rainfall/dryness signal.

    If ``forecast_weather`` contains a complete forward window, it is used for
    the rainfall term.  Otherwise the most recent observed window is used and
    the result is explicitly labelled as a descriptive leading indicator.
    No lake level in feet, draft, slot count, or DWT is fabricated here.
    ``capacity_sensitivity`` is a scenario prior and must not be presented as
    an observed Canal response coefficient.
    """

    if horizon_days not in (7, 28):
        raise ValueError("open-only signal supports 7- or 28-day horizons")
    if not 0 <= capacity_sensitivity <= 1:
        raise ValueError("capacity_sensitivity must be between 0 and 1")
    observed_window = _complete_window(weather, as_of, horizon_days, "PRECTOTCORR")
    if observed_window is None:
        raise ValueError("weather history is missing the requested trailing window")

    forward_end = as_of + timedelta(days=horizon_days)
    forward_window = None
    if forecast_weather is not None:
        forward_window = _complete_window(
            forecast_weather, forward_end, horizon_days, "PRECTOTCORR"
        )
    if forward_window is None:
        rainfall_mm = float(sum(observed_window))
        forecast_status = "no_open_forecast_window; trailing_observation_proxy"
    else:
        rainfall_mm = float(sum(forward_window))
        forecast_status = "open_forecast_window"

    seasonal_rainfall = _seasonal_window_mean(
        weather, as_of, horizon_days, "PRECTOTCORR"
    )
    if seasonal_rainfall is None or seasonal_rainfall <= 0:
        raise ValueError("at least three complete same-season rainfall windows are required")
    rainfall_deficit = max(0.0, min(1.0, (seasonal_rainfall - rainfall_mm) / seasonal_rainfall))

    dry_window = _complete_window(weather, as_of, min(28, len(observed_window)), "T2M")
    humidity_window = _complete_window(weather, as_of, min(28, len(observed_window)), "RH2M")
    if dry_window is None or humidity_window is None:
        raise ValueError("weather history is missing temperature or humidity")
    dryness = float(np.mean([temperature * (1 - humidity / 100.0) for temperature, humidity in zip(dry_window, humidity_window)]))
    seasonal_dryness_sum = _seasonal_window_mean(weather, as_of, len(dry_window), "T2M")
    seasonal_dryness = (
        seasonal_dryness_sum / len(dry_window)
        if seasonal_dryness_sum is not None
        else None
    )
    if seasonal_dryness is None or seasonal_dryness <= 0:
        seasonal_dryness = max(1.0, dryness)
    dryness_anomaly = max(0.0, min(1.0, (dryness - seasonal_dryness) / seasonal_dryness))
    stress = max(0.0, min(1.0, 0.7 * rainfall_deficit + 0.3 * dryness_anomaly))
    retention = max(0.0, min(1.0, 1.0 - capacity_sensitivity * stress))
    return OpenOnlyHydrometSignal(
        as_of=as_of.isoformat(),
        horizon_days=horizon_days,
        rainfall_mm=rainfall_mm,
        seasonal_rainfall_mm=seasonal_rainfall,
        rainfall_deficit_fraction=rainfall_deficit,
        dryness_anomaly=dryness_anomaly,
        hydrology_stress_index=stress,
        capacity_retention_proxy=retention,
        forecast_status=forecast_status,
        forecast_use="descriptive_proxy_only",
        source_ids=("nasa_power", "chirps", "chirps_gefs", "noaa_gfs"),
        caveat=(
            "ACP-free open hydrometeorology proxy; not an official Gatun lake "
            "level, draft, transit-slot, traffic-DWT, or ACP forecast."
        ),
    )


def _rolling_mean(
    weather: dict[date, dict[str, float]], anchor: date, parameter: str, days: int
) -> float | None:
    values = [
        weather.get(anchor - timedelta(days=offset), {}).get(parameter)
        for offset in range(days)
    ]
    if any(value is None for value in values):
        return None
    return float(sum(values) / len(values))


def _feature_row(
    anchor: date,
    weather: dict[date, dict[str, float]],
    levels: dict[date, float],
    *,
    include_observed_acp_state: bool,
) -> list[float] | None:
    current = weather.get(anchor)
    if not current:
        return None
    features: list[float] = []
    for parameter in OPEN_PARAMETERS:
        features.append(current[parameter])
        for days in (7, 28, 90):
            value = _rolling_mean(weather, anchor, parameter, days)
            if value is None:
                return None
            features.append(value)
    day_of_year = anchor.timetuple().tm_yday
    features.extend(
        [
            math.sin(2 * math.pi * day_of_year / 365.25),
            math.cos(2 * math.pi * day_of_year / 365.25),
        ]
    )
    if include_observed_acp_state:
        state = levels.get(anchor)
        if state is None:
            return None
        features.extend([state, levels.get(anchor - timedelta(days=7), state)])
    return features


def _make_dataset(
    levels: dict[date, float],
    weather: dict[date, dict[str, float]],
    horizon_days: int,
    *,
    include_observed_acp_state: bool,
) -> tuple[np.ndarray, np.ndarray, list[date]]:
    rows: list[list[float]] = []
    targets: list[float] = []
    anchors: list[date] = []
    for anchor in sorted(weather):
        target = levels.get(anchor + timedelta(days=horizon_days))
        if target is None:
            continue
        row = _feature_row(
            anchor,
            weather,
            levels,
            include_observed_acp_state=include_observed_acp_state,
        )
        if row is not None:
            rows.append(row)
            targets.append(target)
            anchors.append(anchor)
    if len(rows) < 365 * 5:
        raise ValueError("not enough overlapping daily records for benchmark")
    return np.asarray(rows), np.asarray(targets), anchors


def _fit_and_score(
    features: np.ndarray,
    targets: np.ndarray,
    anchors: list[date],
    *,
    test_days: int,
) -> tuple[float, float, date, date]:
    split = len(features) - test_days
    if split < 365 * 5:
        raise ValueError("test window leaves too little training history")
    model = HistGradientBoostingRegressor(
        learning_rate=0.08,
        max_leaf_nodes=24,
        l2_regularization=1.0,
        random_state=7,
    )
    model.fit(features[:split], targets[:split])
    predicted = model.predict(features[split:])
    actual = targets[split:]
    return (
        float(mean_absolute_error(actual, predicted)),
        float(math.sqrt(mean_squared_error(actual, predicted))),
        anchors[split],
        anchors[-1],
    )


def benchmark_open_vs_observed_acp_state(
    levels: dict[date, float],
    weather: dict[date, dict[str, float]],
    *,
    horizon_days: int,
    test_days: int = 365,
) -> BenchmarkResult:
    """Chronologically compare open hydromet and observed-state model errors.

    This measures the incremental value of a current observed lake-level state,
    not ACP's unpublished hydrological operations or its historical forecasts.
    """

    open_x, open_y, open_dates = _make_dataset(
        levels, weather, horizon_days, include_observed_acp_state=False
    )
    state_x, state_y, state_dates = _make_dataset(
        levels, weather, horizon_days, include_observed_acp_state=True
    )
    open_mae, open_rmse, start, end = _fit_and_score(
        open_x, open_y, open_dates, test_days=test_days
    )
    state_mae, state_rmse, state_start, state_end = _fit_and_score(
        state_x, state_y, state_dates, test_days=test_days
    )
    if (start, end) != (state_start, state_end):
        raise ValueError("A/B test windows must match")
    return BenchmarkResult(
        horizon_days=horizon_days,
        test_start=start.isoformat(),
        test_end=end.isoformat(),
        open_hydromet_mae_ft=open_mae,
        observed_acp_state_mae_ft=state_mae,
        open_hydromet_rmse_ft=open_rmse,
        observed_acp_state_rmse_ft=state_rmse,
        mae_improvement_fraction=(open_mae - state_mae) / open_mae if open_mae else 0.0,
        method_boundary=(
            "Research-only local A/B. ACP source rows are neither persisted nor published. "
            "This compares observed lake-state uplift, not ACP official forecast skill."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-acp-research-fetch", action="store_true")
    parser.add_argument(
        "--open-only",
        action="store_true",
        help="run the ACP-free open hydrometeorology proxy",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        help="open-only signal date (defaults to the latest available weather day)",
    )
    parser.add_argument("--test-days", type=int, default=365)
    args = parser.parse_args()
    if args.open_only:
        weather = fetch_nasa_power_daily(NASA_POWER_START, date.today())
        as_of = args.as_of or max(weather)
        results = [
            build_open_only_hydromet_signal(
                weather, as_of=as_of, horizon_days=horizon
            ).__dict__
            for horizon in (7, 28)
        ]
        print(
            json.dumps(
                {
                    "mode": "open_only",
                    "source_provenance": OPEN_SOURCE_PROVENANCE,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    levels = fetch_acp_history(allow_research_fetch=args.allow_acp_research_fetch)
    weather = fetch_nasa_power_daily(max(min(levels), NASA_POWER_START), max(levels))
    results = [
        benchmark_open_vs_observed_acp_state(
            levels, weather, horizon_days=horizon, test_days=args.test_days
        ).__dict__
        for horizon in (7, 28)
    ]
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

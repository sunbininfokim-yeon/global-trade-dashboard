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
    parser.add_argument("--test-days", type=int, default=365)
    args = parser.parse_args()
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

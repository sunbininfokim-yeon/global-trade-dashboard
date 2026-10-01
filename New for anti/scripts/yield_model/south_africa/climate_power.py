"""NASA POWER seasonal climate features for the South African maize belt.

Same columns and windows as the Earth Engine version in climate.py (CHIRPS +
ERA5-Land), computed from POWER daily point data so the weekly refresh runs
in CI without a Google credential. Select the source with CLIMATE_SOURCE
(default "power"; "gee" uses climate.py).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

import power_daily
import seasonal_history

from .regions import POINTS

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

# name -> (daily variable, aggregation, window start, window end); a window
# bound is (year offset from the season year, month), end exclusive.
SPECS = {
    "rain_planting_mm": ("precip", "sum", (-1, 10), (0, 1)),
    "rain_critical_mm": ("precip", "sum", (0, 1), (0, 3)),
    "edd29_critical_c_days": ("tmax", "edd29", (0, 1), (0, 3)),
    "root_sm_critical": ("root_sm", "mean", (0, 1), (0, 3)),
    "vpd_critical_kpa": ("vpd", "mean", (0, 1), (0, 3)),
}

_weather = power_daily.PointWeather(POINTS, CACHE)


def latest_source_dates() -> dict:
    """Last day every point has data; keys kept for the Earth Engine callers."""
    _weather.daily(date(date.today().year - 1, 1, 1))
    latest = _weather.latest_date()
    return {"chirps": latest, "era5_land": latest, "source": power_daily.SOURCE}


def collect_seasonal(
    start_year: int = 1982, end_year: int = None, refresh: bool = False
) -> pd.DataFrame:
    end_year = end_year or date.today().year
    return seasonal_history.collect_incremental(
        lambda year: power_daily.season_features(_weather, SPECS, year),
        start_year,
        end_year,
        HERE / "training" / "commercial_maize_belt.csv",
        source=power_daily.SOURCE,
        refresh=refresh,
    )


if __name__ == "__main__":
    print(collect_seasonal().tail().to_string(index=False))

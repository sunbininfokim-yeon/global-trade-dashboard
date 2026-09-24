"""NASA POWER seasonal climate features for Ethiopia's coffee regions.

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
    "rain_prev_aug_dec_mm": ("precip", "sum", (-1, 8), (0, 1)),
    "rain_flowering_mar_may_mm": ("precip", "sum", (0, 3), (0, 6)),
    "rain_filling_jun_jul_mm": ("precip", "sum", (0, 6), (0, 8)),
    "hot30_mar_jul_c_days": ("tmax", "edd30", (0, 3), (0, 8)),
    "root_sm_mar_jul": ("root_sm", "mean", (0, 3), (0, 8)),
    "vpd_mar_jul_kpa": ("vpd", "mean", (0, 3), (0, 8)),
}

_weather = power_daily.PointWeather(POINTS, CACHE)


def latest_source_dates() -> dict:
    """Last day every point has data; keys kept for the Earth Engine callers."""
    _weather.daily(date(date.today().year - 1, 1, 1))
    latest = _weather.latest_date()
    return {"chirps": latest, "era5_land": latest, "source": power_daily.SOURCE}


def collect_seasonal(
    start_year: int = 1993, end_year: int = None, refresh: bool = False
) -> pd.DataFrame:
    end_year = end_year or date.today().year
    return seasonal_history.collect_incremental(
        lambda year: power_daily.season_features(_weather, SPECS, year),
        start_year,
        end_year,
        HERE / "training" / "national_arabica_belt.csv",
        source=power_daily.SOURCE,
        refresh=refresh,
    )


if __name__ == "__main__":
    print(collect_seasonal().tail().to_string(index=False))

"""
Dry-run / unit checks without network.

Usage: python3 -m latam_banana.test_dry_run
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import climate as C
from . import labels as L
from .regions import ALL, BY_KEY


def synthetic_daily(year_start=1995, year_end=2005):
    dates = pd.date_range(f"{year_start}-01-01", f"{year_end}-12-31", freq="D")
    n = len(dates)
    rng = np.random.default_rng(1)
    tmean = 26 + 2 * np.sin(2 * np.pi * (dates.dayofyear - 50) / 365)
    df = pd.DataFrame({
        "date": dates,
        "tmean": tmean,
        "tmax": tmean + 4 + rng.normal(0, 0.5, n),
        "tmin": tmean - 4 + rng.normal(0, 0.5, n),
        "precip": rng.exponential(6.0, n),
        "rh_mean": 85 + rng.normal(0, 8, n),
        "wind": 2 + rng.exponential(1.0, n),
        "gwetroot": 0.55 + 0.1 * np.sin(2 * np.pi * dates.dayofyear / 365),
        "tdew": tmean - 2,
    })
    # Inject a humid spell and a storm day.
    mask = (df.date >= "2000-06-01") & (df.date <= "2000-06-10")
    df.loc[mask, "rh_mean"] = 95.0
    storm = df.date == "1998-10-28"
    df.loc[storm, "wind"] = 15.0
    df["vpd_max"] = (
        0.6108 * np.exp(17.27 * df.tmax / (df.tmax + 237.3))
        - 0.6108 * np.exp(17.27 * df.tdew / (df.tdew + 237.3))
    ).clip(lower=0)
    return df


def main():
    daily = synthetic_daily()
    ec = C.ecuador_features(daily, 2000)
    assert ec["sigatoka_rh_days"] > 0
    assert ec["humid_spell_max"] >= 10
    print("[test] ecuador features OK:",
          {k: round(v, 2) for k, v in list(ec.items())[:5]})

    car = C.caribbean_features(daily, 1998)
    assert car["wind_storm_days"] >= 1
    print("[test] caribbean storm proxy OK:",
          round(car["wind_storm_days"], 1), "days")

    assert C.blowdown_factor(25.0) == 0.1
    assert C.blowdown_factor(10.0) == 1.0
    assert C.blowdown_factor(None) == 1.0
    print("[test] blowdown hard-cut OK")

    assert set(BY_KEY) == {r.key for r in ALL}
    assert len(ALL) == 4
    print(f"[test] {len(ALL)} configs: {[r.key for r in ALL]}")

    assert not L.province_available()
    for cfg in ALL:
        assert cfg.label_resolution == "blocked"
    try:
        L.ecuador_yield_kg_ha()
        raise AssertionError("expected FileNotFoundError without province CSV")
    except FileNotFoundError as exc:
        print(f"[test] label gate OK: {type(exc).__name__}")

    print("[test] dry-run passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

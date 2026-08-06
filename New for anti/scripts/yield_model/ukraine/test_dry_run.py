"""
Dry-run / unit checks without network.

Usage: python3 -m ukraine.test_dry_run
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import climate as C
from . import labels as L
from .regions import ALL, BY_KEY


def synthetic_daily(year_start=1990, year_end=2000):
    dates = pd.date_range(f"{year_start}-01-01", f"{year_end}-12-31", freq="D")
    n = len(dates)
    rng = np.random.default_rng(0)
    tmean = 5 + 15 * np.sin(2 * np.pi * (dates.dayofyear - 100) / 365)
    df = pd.DataFrame({
        "date": dates,
        "tmean": tmean,
        "tmax": tmean + 5 + rng.normal(0, 1, n),
        "tmin": tmean - 5 + rng.normal(0, 1, n),
        "precip": rng.exponential(1.2, n),
        "rh_mean": 60 + rng.normal(0, 5, n),
        "wind": 2 + rng.random(n),
        "rs": 12 + 6 * np.sin(2 * np.pi * dates.dayofyear / 365),
        "gwetroot": 0.4 + 0.1 * np.sin(2 * np.pi * dates.dayofyear / 365),
        "tdew": tmean - 3,
    })
    mask = ((df.date >= "1994-12-01") & (df.date <= "1995-02-28"))
    df.loc[mask, "tmin"] = -20.0
    df.loc[mask, "tmax"] = -10.0
    df["vpd_max"] = (C._svp(df.tmax) - C._svp(df.tdew)).clip(lower=0)
    df["et0"] = 2.0
    return df


def main():
    daily = synthetic_daily()
    feats = C.winter_wheat_features(
        daily, 1995, grainfill_months=[(5, 0), (6, 0)])
    assert feats["winterkill_days"] is not None
    assert feats["winterkill_days"] > 0
    assert feats["sm_april"] is not None
    print("[test] climate features OK:",
          {k: round(v, 2) if v is not None else None
           for k, v in list(feats.items())[:6]})

    sun = C.sunflower_features(daily, 1995)
    assert sun["edd_flower"] is not None
    print("[test] sunflower features OK")

    assert set(BY_KEY) == {r.key for r in ALL}
    wheat = [r.key for r in ALL if "wheat" in r.key]
    sun_keys = [r.key for r in ALL if "sunflower" in r.key]
    print(f"[test] {len(ALL)} configs: wheat={wheat} sunflower={sun_keys}")

    assert L.LABEL_MAX_YEAR == 2021

    if L.wheat_oblast_available():
        y = L.central_wheat_yield_kg_ha()
        assert len(y) >= 1
        assert y.year.min() >= 1980
        assert y.year.max() <= L.LABEL_MAX_YEAR
        assert y.target.min() > 0
        wheat_cfgs = [r for r in ALL if "wheat" in r.key]
        assert all(r.label_resolution == "oblast" for r in wheat_cfgs)
        print(f"[test] wheat labels OK: {len(y)} zone-yrs "
              f"{int(y.year.min())}-{int(y.year.max())}")
        if len(y) < 21:
            print("[test] NOTE: <21 seasons — train will skip (min_train=16)")
    else:
        blocked = [r for r in ALL if r.label_resolution == "blocked"]
        assert len(blocked) == len(ALL), "all configs blocked until oblast CSV"
        try:
            L.central_wheat_yield_kg_ha()
            raise AssertionError("expected FileNotFoundError without oblast CSV")
        except FileNotFoundError as e:
            print(f"[test] label gate OK: {e}")

    print("[test] dry-run passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

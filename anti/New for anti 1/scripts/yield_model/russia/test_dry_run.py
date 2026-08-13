"""
Dry-run / unit checks without network.

Usage: python3 -m russia.test_dry_run
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import climate as C
from .regions import ALL, BY_KEY


def synthetic_daily(year_start=1990, year_end=2000, lat=45.0):
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
    # Inject a hard freeze winter for 1995 harvest
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
    assert feats["winterkill_days"] > 0, "injected freeze should register"
    assert feats["sm_april"] is not None
    assert feats["edd_grainfill"] is not None
    print("[test] climate features OK:",
          {k: round(v, 2) if v is not None else None
           for k, v in list(feats.items())[:6]})

    # With snow cover, bare frost should drop
    daily2 = daily.copy()
    daily2["snow_depth"] = 0.15
    bf_bare = C.winterkill_bare_frost(
        daily, [(12, -1), (1, 0), (2, 0)], 1995)
    bf_snow = C.winterkill_bare_frost(
        daily2, [(12, -1), (1, 0), (2, 0)], 1995)
    assert bf_snow == 0.0, "deep snow should zero bare-frost score"
    assert bf_bare > 0
    print(f"[test] bare frost {bf_bare:.1f} vs snow-insulated {bf_snow:.1f}")

    assert set(BY_KEY) == {r.key for r in ALL}
    print(f"[test] {len(ALL)} region configs: {list(BY_KEY)}")
    print("[test] dry-run passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

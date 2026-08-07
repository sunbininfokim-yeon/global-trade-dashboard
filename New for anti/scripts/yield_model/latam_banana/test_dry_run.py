"""Offline unit checks."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import climate as C
from .regions import ALL, BY_KEY


def synthetic_daily():
    dates = pd.date_range("2000-01-01", "2005-12-31", freq="D")
    n = len(dates)
    rng = np.random.default_rng(2)
    tmean = 26 + 2 * np.sin(2 * np.pi * dates.dayofyear / 365)
    df = pd.DataFrame({
        "date": dates,
        "tmean": tmean,
        "tmax": tmean + 4,
        "tmin": tmean - 4,
        "precip": rng.exponential(6.0, n),
        "rh_mean": 80 + rng.normal(0, 10, n),
        "wind": 2 + rng.exponential(1.0, n),
    })
    mask = (df.date >= "2002-06-01") & (df.date <= "2002-06-12")
    df.loc[mask, "rh_mean"] = 95.0
    return df


def main() -> int:
    daily = synthetic_daily()
    feats = C.ecuador_features(daily, 2002)
    assert feats["humid_spell_max"] >= 12
    assert feats["sigatoka_rh_days"] > 0
    car = C.caribbean_features(daily, 2002)
    assert "wind_storm_days" in car
    assert len(ALL) == 4
    assert set(BY_KEY) == {b.key for b in ALL}
    print("[test] climate + regions OK")
    print("[test] dry-run passed (YLWS not required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

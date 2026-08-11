"""
Derived climate variables for Thailand region-crops.

Daily frame from collect.point_weather:

    date, tmax, tmin, tmean, precip, et0, rh_mean, vpd_max, gwetroot

Dam storage for Chao Phraya off-season rice is **never** measured here.
`dam_recharge_proxy` is upstream wet-season precip × ENSO memory — not RID
Nov-1 live storage (Bhumibol / Sirikit). Wire Thaiwater / RID before claiming
irrigation allocation skill.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from brazil.climate import fao56_et0, _svp  # re-export for collect


def _mask(daily: pd.DataFrame, months: list, year: int) -> pd.Series:
    m = pd.Series(False, index=daily.index)
    for month, off in months:
        m |= (daily.date.dt.year == year + off) & (daily.date.dt.month == month)
    return m


def window_sum(daily, col, months, year):
    sub = daily.loc[_mask(daily, months, year), col]
    return float(sub.sum()) if len(sub) else float("nan")


def window_mean(daily, col, months, year):
    sub = daily.loc[_mask(daily, months, year), col]
    return float(sub.mean()) if len(sub) else float("nan")


def heat_days(daily, months, year, thresh=35.0):
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float((sub.tmax > thresh).sum())


def edd(daily, months, year, thresh=33.0):
    """Extreme degree-days above thresh (°C·day)."""
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float(np.maximum(0.0, sub.tmax.values - thresh).sum())


def water_deficit(daily, months, year):
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float(np.maximum(0.0, sub.et0.values - sub.precip.values).sum())


def rainy_days(daily, months, year, mm=1.0):
    """Count of days with precip >= mm (Makkaew & Sdoodee 2015 use ≥1 mm)."""
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float((sub.precip >= mm).sum())


def rainy_days_tapping(daily, months, year, mm=5.0):
    """
    Days with precip ≥ 5 mm — Regions rubber note tapping-loss threshold.
    Complements ≥1 mm rainy-day counts from Songkhla field studies.
    """
    return rainy_days(daily, months, year, mm=mm)


def max_dry_spell(daily, months, year, dry_mm=1.0):
    sub = daily.loc[_mask(daily, months, year)].sort_values("date")
    if sub.empty:
        return float("nan")
    dry = (sub.precip.values < dry_mm).astype(int)
    best = run = 0
    for v in dry:
        run = run + 1 if v else 0
        best = max(best, run)
    return float(best)


def monsoon_onset_doy(daily, year, start_month=5, end_month=7, thresh_3day=20.0):
    """
    First day-of-year in May–Jul where rolling 3-day precip sum ≥ thresh.
    Delay vs climatology is computed later as anomaly of this DOY.
    """
    mask = ((daily.date.dt.year == year)
            & (daily.date.dt.month >= start_month)
            & (daily.date.dt.month <= end_month))
    sub = daily.loc[mask].sort_values("date")
    if len(sub) < 3:
        return float("nan")
    roll = sub.precip.rolling(3, min_periods=3).sum()
    hit = sub.loc[roll >= thresh_3day]
    if hit.empty:
        return float("nan")
    return float(hit.date.dt.dayofyear.iloc[0])


def heat_x_drought_days(daily, months, year, sm_thresh=0.3, tmax_thresh=35.0):
    """
    Joint heat+dry stress days (Claude TH work note §C sugarcane).
    Uses POWER GWETROOT (0–1), not SMAP.
    """
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty or "gwetroot" not in sub.columns:
        return float("nan")
    hit = (sub.gwetroot < sm_thresh) & (sub.tmax > tmax_thresh)
    return float(hit.sum())


def dam_recharge_proxy(wet_precip_mm: float, oni_djf: float) -> float:
    """
    Upstream wet-season moisture × El Niño penalty as a stand-in for Nov-1
    Bhumibol+Sirikit storage (TDRI / RID mechanism).

    Higher wet precip → higher proxy; positive ONI → lower proxy.
    NOT observed reservoir MCM or % live storage.
    """
    wet = max(float(wet_precip_mm), 0.0)
    oni = float(oni_djf) if oni_djf is not None and not np.isnan(oni_djf) else 0.0
    # Soft El Niño drawdown; scale wet mm into a ~0–1 storage-like index.
    base = 1.0 - np.exp(-wet / 900.0)
    elnino_cut = 1.0 / (1.0 + 0.45 * max(oni, 0.0))
    return float(base * elnino_cut)

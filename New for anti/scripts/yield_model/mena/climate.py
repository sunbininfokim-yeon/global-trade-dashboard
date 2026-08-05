"""
Derived climate variables for MENA winter wheat (Regions/중동_북아프리카_MENA).

Expects a daily frame from collect.point_weather:

    date, tmax, tmin, tmean, precip, et0, rh_mean, vpd_max, gwetroot

Salinity and Nile inflow are **proxies** — not field EC (dS/m) or G-REALM
stage. French–Schultz yield-water is a rainfall + stored-soil scaffold, not
a calibrated APSIM potential yield.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from brazil.climate import fao56_et0, _svp  # re-export for collect

EC_MM = 110.0          # French–Schultz evaporation constant (mm)
WUE_KG_HA_MM = 20.0    # literature WUE scale; ridge reweights


def _mask(daily: pd.DataFrame, months: list, year: int) -> pd.Series:
    """months: list of (month, year_offset) relative to harvest year `year`."""
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


def heat_days(daily, months, year, thresh=32.0):
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float((sub.tmax > thresh).sum())


def edd(daily, months, year, thresh=32.0):
    """Excess degree-days: sum max(0, Tmax − thresh) — Schlenker-style."""
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float((sub.tmax - thresh).clip(lower=0).sum())


def water_deficit(daily, months, year):
    """Sum of daily max(0, ET0 − P) over a window (mm)."""
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float(np.maximum(0.0, sub.et0.values - sub.precip.values).sum())


def irrigation_buffer_proxy(daily, months, year, sm_col="gwetroot"):
    """
    Days in the window with root-zone wetness above this point's DOY median.

    Proxy for irrigated moisture maintenance — not canal depth or AQUASTAT area.
    """
    if sm_col not in daily.columns:
        return 0.0
    doy = daily.date.dt.dayofyear
    clim = daily.groupby(doy)[sm_col].transform("median")
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    above = (sub[sm_col].values >= clim.loc[sub.index].values).sum()
    return float(above)


def effective_awc_mm(awc_mm: float, sand_fraction: float) -> float:
    """Point AWC discounted by sand fraction (SoilGrids/HWSD scale)."""
    return float(awc_mm) * (1.0 - 0.45 * float(sand_fraction))


def french_schultz_yw(gsr_mm: float, stored_mm: float,
                      wue: float = WUE_KG_HA_MM, ec: float = EC_MM) -> float:
    """Rainfall-only yield-water proxy: WUE × max(0, GSR + stored − Ec)."""
    if np.isnan(gsr_mm) or np.isnan(stored_mm):
        return float("nan")
    return float(wue * max(0.0, gsr_mm + stored_mm - ec))


def delta_salt_proxy(coast_km: float, dry_flow_proxy: float,
                     oni_djf: float, wet_recharge: float = 0.0) -> dict:
    """
    Nile Delta coastal salinity intrusion proxy.

    Not measured EC. Monotonic with coast proximity, weak dry moisture, and
    positive ENSO (reduced upstream inflow memory).
    """
    dry_scale = 1.0 / (1.0 + max(dry_flow_proxy, 0.0) / 60.0)
    wet_scale = 1.0 / (1.0 + max(wet_recharge, 0.0) / 800.0)
    oni_boost = 1.0 + 0.30 * max(float(oni_djf), 0.0)
    coast_f = 1.0 / (1.0 + max(coast_km, 1.0) / 30.0)
    salt = coast_f * dry_scale * wet_scale * oni_boost
    return {
        "salt_proxy": float(salt),
        "delta_salt": float(salt - 0.5),
        "coast_km": float(coast_km),
    }


def _monthly_balance(daily: pd.DataFrame, year: int,
                     months: list) -> list[float]:
    """Monthly P − ET0 for SPEI-like scoring."""
    rows = []
    for month, off in months:
        sub = daily[(daily.date.dt.year == year + off)
                    & (daily.date.dt.month == month)]
        if sub.empty:
            continue
        rows.append(float(sub.precip.sum() - sub.et0.sum()))
    return rows


def spei_like_min(daily, end_year: int, window_months: list | None = None
                  ) -> float:
    """
    Minimum z-scored monthly (P−ET0) over a 6-month window — SPEI-6 analogue.

    Default window: Nov(y−1) through Apr(y) for Maghreb winter wheat.
    """
    window_months = window_months or [
        (11, -1), (12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
    n_months = len(window_months)
    series = []
    for y in range(end_year - 40, end_year + 1):
        bal = _monthly_balance(daily, y, window_months)
        if len(bal) == n_months:
            series.append((y, float(min(bal))))
    if not series:
        return float("nan")
    vals = pd.Series([v for _, v in series])
    mu, sd = vals.mean(), vals.std()
    cur = next((v for yy, v in series if yy == end_year), float("nan"))
    if sd == 0 or np.isnan(sd) or np.isnan(cur):
        return float("nan")
    return float((cur - mu) / sd)


def spi_like_window(daily, months, year, history_start: int = 1981) -> float:
    """Z-score of window precip total vs same-window climatology."""
    totals = []
    for y in range(history_start, year + 1):
        t = window_sum(daily, "precip", months, y)
        if not np.isnan(t):
            totals.append((y, t))
    if len(totals) < 8:
        return float("nan")
    vals = pd.Series([v for _, v in totals])
    mu, sd = vals.mean(), vals.std()
    cur = next((v for yy, v in totals if yy == year), float("nan"))
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float((cur - mu) / sd)

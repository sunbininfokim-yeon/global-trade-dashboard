"""
Derived climate variables for Vietnam guides under Regions/베트남.

Expects a daily frame from collect.point_weather:

    date, tmax, tmin, tmean, precip, et0, rh_mean, vpd_max, gwetroot

Salinity is **never** measured here. `ec_proxy` and `salt_stress` are coastal
distance × dry-season hydrologic proxies × ENSO memory — not field EC (dS/m).
True Maas–Hoffman needs observed ECe; we only reuse the functional form on a
scaled proxy so the feature vocabulary matches the methodology notes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from brazil.climate import fao56_et0, _svp  # re-export for collect

# Maas–Hoffman rice defaults (methodology master note §1.3). Applied only to
# the invented `ec_proxy` scale, never claimed as true ECe.
EC_THRESH = 3.0
BETA_SALT = 0.12

# Kath et al. (2020) robusta temperature thresholds (°C).
KATH_TMIN = 16.2
KATH_TMAX = 24.1


def _mask(daily: pd.DataFrame, months: list, year: int) -> pd.Series:
    """
    months: list of (month, year_offset) relative to harvest year `year`.
    """
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


def water_deficit(daily, months, year):
    """Sum of daily max(0, ET0 − P) over a window (mm)."""
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float(np.maximum(0.0, sub.et0.values - sub.precip.values).sum())


def irrigation_buffer_proxy(daily, months, year, sm_col="gwetroot"):
    """
    Proxy for irrigated moisture maintenance in the dry flowering window.

    Counts how many dry-window days sit above this point's long-run day-of-year
    median root-zone wetness. High values imply soil kept wet when rainfall is
    scarce — the operating signature of Central Highlands robusta irrigation.
    This is **not** irrigated depth or canal delivery; gamma/I_proxy in the
    master note would use province irrig fractions when available.
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


def kath_temp_penalty(daily, months, year, k1=0.05, k2=0.05):
    """
    Linear overshoot of growing-season means above Kath min/max thresholds.
    Coefficients are unit-scale placeholders; the ridge model reweights them.
    """
    tmin = window_mean(daily, "tmin", months, year)
    tmax = window_mean(daily, "tmax", months, year)
    if np.isnan(tmin) or np.isnan(tmax):
        return float("nan"), float("nan"), float("nan")
    pen = k1 * max(0.0, tmin - KATH_TMIN) + k2 * max(0.0, tmax - KATH_TMAX)
    return float(pen), float(tmin), float(tmax)


def coastal_exposure(coast_km: float) -> float:
    """Coast proximity weight: ~1 near shore, ~0.2 at ~80 km (inland delta)."""
    return 1.0 / (1.0 + max(float(coast_km), 1.0) / 25.0)


def salinity_proxy(coast_km: float, dry_flow_proxy: float, oni_djf: float,
                   wet_recharge: float, q_upstream: float | None = None) -> dict:
    """
    Coastal salinity intrusion proxy for Mekong / coastal rice.

    Not EC, not gauged L_s from MRC discharge. Form intended to be monotonic with:
      · proximity to coast (small coast_km)
      · weak dry-season local moisture (low dry_flow_proxy)
      · El Niño (positive ONI → reduced upstream inflow memory)
      · weak preceding wet-season recharge
      · weak upstream dry-season inflow proxy (q_upstream; stand-in for Q_TCmin
        when MRC Tan Chau discharge is unavailable — Yen et al. 2024 IOP)

    `ec_proxy` is scaled into a Maas–Hoffman-like range purely for terminology
    alignment — **do not report it as dS/m**.
    """
    # Normalise loosely: dry precip ~0–400 mm WS dry months at coastal stations.
    dry_scale = 1.0 / (1.0 + max(dry_flow_proxy, 0.0) / 80.0)
    wet_scale = 1.0 / (1.0 + max(wet_recharge, 0.0) / 1200.0)
    oni_boost = 1.0 + 0.35 * max(float(oni_djf), 0.0)
    coast_f = coastal_exposure(coast_km)
    # Upstream Q: higher → less intrusion (Yen QTCmin / Eslami et al. SWI).
    if q_upstream is None or (isinstance(q_upstream, float) and np.isnan(q_upstream)):
        q_scale = 1.0
    else:
        q_scale = 1.0 / (1.0 + max(float(q_upstream), 0.0) / 1.0)
    salt = coast_f * dry_scale * wet_scale * oni_boost * q_scale
    # Map salt in ~[0, 1.5] onto a pseudo-EC span that can exceed 3.0 in crises.
    ec_proxy = 1.5 + 4.0 * salt
    y_rel = max(0.0, 1.0 - BETA_SALT * max(0.0, ec_proxy - EC_THRESH))
    return {
        "salt_proxy": float(salt),
        "ec_proxy": float(ec_proxy),
        "y_rel_salt": float(y_rel),
        "coast_km": float(coast_km),
        "coastal_exposure": float(coast_f),
    }


def _monthly_cwb(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly climatic water balance P − ET0 (mm) for SPEI-like features."""
    d = daily.copy()
    d["year"] = d.date.dt.year
    d["month"] = d.date.dt.month
    g = (d.groupby(["year", "month"], as_index=False)
         .agg(precip=("precip", "sum"), et0=("et0", "sum")))
    g["cwb"] = g.precip - g.et0
    return g


def spei_like_min(daily: pd.DataFrame, year: int,
                  peak_months: tuple = (1, 2, 3, 4),
                  timescale: int = 4) -> float:
    """
    Point-level SPEI-*approximation*: rolling `timescale`-month sum of (P−ET0),
    z-scored by calendar month across the full record, then **min** over
    `peak_months` of harvest `year`.

    Mirrors Yen et al. (2024) SPEI-4min for Ben Tre WS (Jan–Apr growth window).
    Not a full log-logistic SPEI — Gamma/log-logistic fit needs longer station
    series; this keeps the season window and min aggregation from the paper.
    """
    g = _monthly_cwb(daily)
    if g.empty:
        return float("nan")
    g = g.sort_values(["year", "month"]).reset_index(drop=True)
    g["cwb_roll"] = g.cwb.rolling(timescale, min_periods=timescale).sum()
    # Month-wise z across years (SPEI-like standardization).
    g["spei_like"] = g.groupby("month")["cwb_roll"].transform(
        lambda s: (s - s.mean()) / (s.std(ddof=0) or 1.0))
    vals = g.loc[(g.year == year) & (g.month.isin(peak_months)), "spei_like"]
    if vals.empty or vals.isna().all():
        return float("nan")
    return float(vals.min())


def spi_like_window(daily: pd.DataFrame, months: list, year: int) -> float:
    """
    Window precip z-score vs the same calendar window across years at this point.

    Lightweight SPI-season analogue for WS dry months (Water 2022 SPI_WS;
    Climate 2023 SPI-3/6 season defs) without a full Gamma SPI library.
    """
    target = window_sum(daily, "precip", months, year)
    if np.isnan(target):
        return float("nan")
    # Build climatology over available years in the daily frame.
    years = sorted({int(y) for y in daily.date.dt.year.unique()})
    series = []
    for y in years:
        v = window_sum(daily, "precip", months, y)
        if not np.isnan(v):
            series.append(v)
    if len(series) < 8:
        return float("nan")
    arr = np.asarray(series, dtype=float)
    sd = float(arr.std(ddof=0)) or 1.0
    return float((target - arr.mean()) / sd)


def extreme_rain_days(daily, months, year, mm=50.0):
    sub = daily.loc[_mask(daily, months, year)]
    if sub.empty:
        return float("nan")
    return float((sub.precip >= mm).sum())


def consecutive_wet_spell(daily, months, year, mm_day=20.0):
    """Longest run of days with precip >= mm_day in the window (flood proxy)."""
    sub = daily.loc[_mask(daily, months, year)].sort_values("date")
    if sub.empty:
        return float("nan")
    wet = (sub.precip.values >= mm_day).astype(int)
    best = run = 0
    for v in wet:
        run = run + 1 if v else 0
        best = max(best, run)
    return float(best)

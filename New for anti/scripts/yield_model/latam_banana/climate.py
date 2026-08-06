"""
Climate / disease-proxy features for LatAm Cavendish banana.

Phase-1 uses NASA POWER daily as *weather proxies* for Black Sigatoka
pressure and storm stress. They do not replace farm YLWS/YLS scores
(Jiménez et al. 2022) or UAV NDVI (Garcés-Fiallos et al. 2025).

Thresholds follow the local 중남미 guide + common Sigatoka literature:
  - humid / infection-friendly: RH2M ≥ 90%
  - blowdown hard cut (IBTrACS): max wind ≥ 80 km/h ≈ 22.2 m/s
  - POWER WS2M daily-mean storm proxy: ≥ 12 m/s (soft count only)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RH_SIGATOKA = 90.0          # %
RAIN_WET_DAY = 1.0          # mm
WIND_STORM_MS = 12.0        # m/s daily-mean proxy (not IBTrACS max)
WIND_BLOWDOWN_MS = 22.2     # 80 km/h hard cut-off when max wind known
HEAT_TMAX = 34.0            # °C


def _between(daily: pd.DataFrame, start: pd.Timestamp,
             end: pd.Timestamp) -> pd.DataFrame:
    return daily[(daily.date >= start) & (daily.date <= end)]


def _sum(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].sum()) if not frame.empty else float("nan")


def _mean(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].mean()) if not frame.empty else float("nan")


def _max(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].max()) if not frame.empty else float("nan")


def _season(frame: pd.DataFrame, start_m: int, end_m: int) -> pd.DataFrame:
    """Inclusive month window; supports wrap (e.g. Dec–Apr = 12..4)."""
    m = frame.date.dt.month
    if start_m <= end_m:
        return frame[(m >= start_m) & (m <= end_m)]
    return frame[(m >= start_m) | (m <= end_m)]


def humid_spell_days(rh: pd.Series, threshold: float = RH_SIGATOKA) -> float:
    """Longest consecutive streak of RH ≥ threshold (days)."""
    if rh.empty:
        return float("nan")
    wet = (rh >= threshold).to_numpy(dtype=bool)
    best = cur = 0
    for flag in wet:
        if flag:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return float(best)


def blowdown_factor(max_wind_ms: float | None,
                    threshold_ms: float = WIND_BLOWDOWN_MS,
                    factor: float = 0.1) -> float:
    """
    Hard switch from the 중남미 guide: if belt max wind exceeds ~80 km/h,
    multiply biological yield by ``factor`` (default 0.1).
    Missing IBTrACS → 1.0 (no cut).
    """
    if max_wind_ms is None or not np.isfinite(max_wind_ms):
        return 1.0
    return factor if max_wind_ms >= threshold_ms else 1.0


def banana_year_features(daily: pd.DataFrame, harvest_year: int,
                         *,
                         wet_season: tuple[int, int] = (1, 6),
                         dry_season: tuple[int, int] = (7, 12),
                         ) -> dict[str, float]:
    """Calendar-year features for continuously harvested Cavendish."""
    y = harvest_year
    year = _between(daily, pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31))
    empty_keys = (
        "rain_year", "rain_wet", "rain_dry", "tmean_year",
        "heat_days_34", "heat_excess_34", "sigatoka_rh_days",
        "humid_spell_max", "wet_days", "wind_storm_days",
        "wind_max_daily", "sm_year", "vpd_year",
    )
    if year.empty:
        return {k: float("nan") for k in empty_keys}

    wet = _season(year, *wet_season)
    dry = _season(year, *dry_season)
    rh = year["rh_mean"] if "rh_mean" in year.columns else pd.Series(dtype=float)
    wind = year["wind"] if "wind" in year.columns else pd.Series(dtype=float)
    heat = (year.tmax - HEAT_TMAX).clip(lower=0) if "tmax" in year else None

    return {
        "rain_year": _sum(year, "precip"),
        "rain_wet": _sum(wet, "precip"),
        "rain_dry": _sum(dry, "precip"),
        "tmean_year": _mean(year, "tmean"),
        "heat_days_34": (
            float(year.tmax.gt(HEAT_TMAX).sum()) if "tmax" in year
            else float("nan")),
        "heat_excess_34": (
            float(heat.sum()) if heat is not None else float("nan")),
        "sigatoka_rh_days": (
            float(rh.ge(RH_SIGATOKA).sum()) if len(rh) else float("nan")),
        "humid_spell_max": (
            humid_spell_days(rh) if len(rh) else float("nan")),
        "wet_days": float(year.precip.ge(RAIN_WET_DAY).sum()),
        "wind_storm_days": (
            float(wind.ge(WIND_STORM_MS).sum()) if len(wind) else float("nan")),
        "wind_max_daily": (
            _max(year, "wind") if "wind" in year else float("nan")),
        "sm_year": (
            _mean(year, "gwetroot") if "gwetroot" in year else float("nan")),
        "vpd_year": (
            _mean(year, "vpd_max") if "vpd_max" in year else float("nan")),
    }


def ecuador_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Coastal Ecuador: wet roughly Jan–May; ENSO-sensitive dry half."""
    feats = banana_year_features(
        daily, harvest_year, wet_season=(1, 5), dry_season=(6, 12))
    feats.setdefault("oni_amj", float("nan"))
    return feats


def caribbean_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Caribbean / Atlantic belts (Limón, Izabal, north Honduras)."""
    return banana_year_features(
        daily, harvest_year, wet_season=(5, 11), dry_season=(12, 4))


def pacific_guatemala_features(daily: pd.DataFrame,
                               harvest_year: int) -> dict[str, float]:
    """Pacific south Guatemala (Escuintla) — sharper dry season."""
    return banana_year_features(
        daily, harvest_year, wet_season=(5, 10), dry_season=(11, 4))

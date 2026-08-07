"""Weather risk proxies for Cavendish belts (not yield features for training)."""

from __future__ import annotations

import pandas as pd

RH_SIGATOKA = 90.0
RAIN_WET_DAY = 1.0
WIND_STORM_MS = 12.0
HEAT_TMAX = 34.0


def _between(daily: pd.DataFrame, start: pd.Timestamp,
             end: pd.Timestamp) -> pd.DataFrame:
    return daily[(daily.date >= start) & (daily.date <= end)]


def _season(frame: pd.DataFrame, start_m: int, end_m: int) -> pd.DataFrame:
    m = frame.date.dt.month
    if start_m <= end_m:
        return frame[(m >= start_m) & (m <= end_m)]
    return frame[(m >= start_m) | (m <= end_m)]


def _sum(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].sum()) if not frame.empty else float("nan")


def _mean(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].mean()) if not frame.empty else float("nan")


def humid_spell_days(rh: pd.Series, threshold: float = RH_SIGATOKA) -> float:
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


def banana_year_features(daily: pd.DataFrame, year: int,
                         *, wet_season: tuple[int, int],
                         dry_season: tuple[int, int]) -> dict[str, float]:
    frame = _between(daily, pd.Timestamp(year, 1, 1), pd.Timestamp(year, 12, 31))
    empty = {
        "rain_year": float("nan"), "rain_wet": float("nan"),
        "rain_dry": float("nan"), "tmean_year": float("nan"),
        "heat_days_34": float("nan"), "sigatoka_rh_days": float("nan"),
        "humid_spell_max": float("nan"), "wet_days": float("nan"),
        "wind_storm_days": float("nan"), "wind_max_daily": float("nan"),
    }
    if frame.empty:
        return empty
    wet = _season(frame, *wet_season)
    dry = _season(frame, *dry_season)
    rh = frame["rh_mean"] if "rh_mean" in frame else pd.Series(dtype=float)
    wind = frame["wind"] if "wind" in frame else pd.Series(dtype=float)
    return {
        "rain_year": _sum(frame, "precip"),
        "rain_wet": _sum(wet, "precip"),
        "rain_dry": _sum(dry, "precip"),
        "tmean_year": _mean(frame, "tmean"),
        "heat_days_34": (
            float(frame.tmax.gt(HEAT_TMAX).sum()) if "tmax" in frame
            else float("nan")),
        "sigatoka_rh_days": (
            float(rh.ge(RH_SIGATOKA).sum()) if len(rh) else float("nan")),
        "humid_spell_max": (
            humid_spell_days(rh) if len(rh) else float("nan")),
        "wet_days": float(frame.precip.ge(RAIN_WET_DAY).sum()),
        "wind_storm_days": (
            float(wind.ge(WIND_STORM_MS).sum()) if len(wind) else float("nan")),
        "wind_max_daily": (
            float(wind.max()) if len(wind) else float("nan")),
    }


def ecuador_features(daily: pd.DataFrame, year: int) -> dict[str, float]:
    return banana_year_features(
        daily, year, wet_season=(1, 5), dry_season=(6, 12))


def caribbean_features(daily: pd.DataFrame, year: int) -> dict[str, float]:
    return banana_year_features(
        daily, year, wet_season=(5, 11), dry_season=(12, 4))

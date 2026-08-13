"""Crop-stage climate features for Canadian Prairies and Ontario.

Heat thresholds follow Morrison & Stewart (2002) for canola (29.5 °C) and
Schlenker-style EDD for maize (29 °C). Snowmelt is proxied by Nov–Mar
precipitation plus April–May root-zone wetness from NASA POWER.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _between(daily: pd.DataFrame, start: pd.Timestamp,
             end: pd.Timestamp) -> pd.DataFrame:
    return daily[(daily.date >= start) & (daily.date <= end)]


def _vpd_max(frame: pd.DataFrame) -> pd.Series:
    es = 0.6108 * np.exp(17.27 * frame.tmax / (frame.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * frame.tdew / (frame.tdew + 237.3))
    return (es - ea).clip(lower=0)


def _mean(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].mean()) if not frame.empty else float("nan")


def _sum(frame: pd.DataFrame, column: str) -> float:
    return float(frame[column].sum()) if not frame.empty else float("nan")


def _gdd(frame: pd.DataFrame, base: float) -> float:
    if frame.empty:
        return float("nan")
    return float(((frame.tmax + frame.tmin) / 2.0 - base).clip(lower=0).sum())


def _canola_core(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    y = harvest_year
    winter = _between(daily, pd.Timestamp(y - 1, 11, 1), pd.Timestamp(y, 3, 31))
    preseason = _between(daily, pd.Timestamp(y, 4, 1), pd.Timestamp(y, 5, 31))
    growing = _between(daily, pd.Timestamp(y, 5, 1), pd.Timestamp(y, 8, 31))
    flowering = _between(daily, pd.Timestamp(y, 6, 15), pd.Timestamp(y, 7, 31))
    september = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 9, 30))
    hsu = (flowering.tmax - 29.5).clip(lower=0)
    heat_dry_stress = hsu * (1.0 - flowering.gwetroot.clip(0, 1))
    return {
        "rain_winter": _sum(winter, "precip"),
        "rain_growing": _sum(growing, "precip"),
        "rain_flowering": _sum(flowering, "precip"),
        "sm_preseason": _mean(preseason, "gwetroot"),
        "sm_flowering": _mean(flowering, "gwetroot"),
        "hsu_flower": float(hsu.sum()),
        "heat_days_29p5": float(flowering.tmax.gt(29.5).sum()),
        "heat_dry_stress": float(heat_dry_stress.sum()),
        "vpd_flowering": float(_vpd_max(flowering).mean()),
        "frost_sep": float(september.tmin.lt(0.0).sum()),
        "gdd0_growing": _gdd(growing, 0.0),
    }


def canola_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Parkland / generic prairie canola."""
    return _canola_core(daily, harvest_year)


def canola_palliser_features(daily: pd.DataFrame,
                             harvest_year: int) -> dict[str, float]:
    """Semi-arid Palliser / southern AB — same core; feature_sets weight heat."""
    return _canola_core(daily, harvest_year)


def canola_peace_features(daily: pd.DataFrame,
                          harvest_year: int) -> dict[str, float]:
    """Peace River short-season canola — frost/GDD emphasized in feature_sets."""
    return _canola_core(daily, harvest_year)


def spring_wheat_features(daily: pd.DataFrame,
                          harvest_year: int) -> dict[str, float]:
    """Prairie spring wheat harvested in ``harvest_year``."""
    y = harvest_year
    winter = _between(daily, pd.Timestamp(y - 1, 11, 1), pd.Timestamp(y, 3, 31))
    preseason = _between(daily, pd.Timestamp(y, 4, 1), pd.Timestamp(y, 5, 31))
    growing = _between(daily, pd.Timestamp(y, 5, 1), pd.Timestamp(y, 8, 31))
    heading = _between(daily, pd.Timestamp(y, 7, 1), pd.Timestamp(y, 7, 31))
    september = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 9, 30))

    heat_excess = (heading.tmax - 30.0).clip(lower=0)
    return {
        "rain_winter": _sum(winter, "precip"),
        "rain_growing": _sum(growing, "precip"),
        "sm_preseason": _mean(preseason, "gwetroot"),
        "sm_heading": _mean(heading, "gwetroot"),
        "gdd0_growing": _gdd(growing, 0.0),
        "heat_excess_jul": float(heat_excess.sum()),
        "heat_days_30": float(heading.tmax.gt(30.0).sum()),
        "vpd_heading": float(_vpd_max(heading).mean()),
        "frost_sep": float(september.tmin.lt(0.0).sum()),
    }


def soy_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Manitoba soybeans — excess May moisture is the lead risk."""
    return soy_excess_features(daily, harvest_year)


def soy_excess_features(daily: pd.DataFrame,
                        harvest_year: int) -> dict[str, float]:
    """
    Red River excess-moisture pack.

    Mkhabela: early-season high SM linked to low canola/soy years;
    MASC Excess Moisture Insurance — unseedable by late June.
    ``excess_may`` = May days with precip > 15 mm (waterlogging proxy).
    """
    y = harvest_year
    winter = _between(daily, pd.Timestamp(y - 1, 11, 1), pd.Timestamp(y, 3, 31))
    may = _between(daily, pd.Timestamp(y, 5, 1), pd.Timestamp(y, 5, 31))
    growing = _between(daily, pd.Timestamp(y, 5, 15), pd.Timestamp(y, 9, 15))
    flowering = _between(daily, pd.Timestamp(y, 7, 1), pd.Timestamp(y, 7, 31))
    september = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 9, 30))
    heat_excess = (flowering.tmax - 30.0).clip(lower=0)
    return {
        "rain_winter": _sum(winter, "precip"),
        "rain_may": _sum(may, "precip"),
        "rain_growing": _sum(growing, "precip"),
        "sm_may": _mean(may, "gwetroot"),
        "sm_flowering": _mean(flowering, "gwetroot"),
        "excess_may": float(may.precip.gt(15.0).sum()),
        "heat_excess_jul": float(heat_excess.sum()),
        "vpd_flowering": float(_vpd_max(flowering).mean()),
        "frost_sep": float(september.tmin.lt(0.0).sum()),
        "gdd10_growing": _gdd(growing, 10.0),
    }


def corn_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Ontario grain corn — short-season GDD + July EDD + early frost."""
    y = harvest_year
    growing = _between(daily, pd.Timestamp(y, 5, 1), pd.Timestamp(y, 9, 30))
    july = _between(daily, pd.Timestamp(y, 7, 1), pd.Timestamp(y, 7, 31))
    september = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 9, 30))

    edd = (july.tmax - 29.0).clip(lower=0)
    return {
        "rain_growing": _sum(growing, "precip"),
        "rain_jul": _sum(july, "precip"),
        "sm_jul": _mean(july, "gwetroot"),
        "gdd10_growing": _gdd(growing, 10.0),
        "edd_jul": float(edd.sum()),
        "vpd_jul": float(_vpd_max(july).mean()),
        "frost_sep": float(september.tmin.lt(0.0).sum()),
        "heat_days_32": float(july.tmax.gt(32.0).sum()),
    }

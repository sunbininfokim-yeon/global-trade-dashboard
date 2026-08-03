"""Crop-stage features for Australian wheat and cotton."""

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


def wheat_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Full-season features for winter wheat harvested in ``harvest_year``."""
    y = harvest_year
    preseason = _between(daily, pd.Timestamp(y, 1, 1), pd.Timestamp(y, 4, 30))
    growing = _between(daily, pd.Timestamp(y, 4, 1), pd.Timestamp(y, 10, 31))
    early = _between(daily, pd.Timestamp(y, 5, 1), pd.Timestamp(y, 7, 31))
    winter = _between(daily, pd.Timestamp(y, 6, 1), pd.Timestamp(y, 8, 31))
    spring = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 11, 30))
    anthesis = _between(daily, pd.Timestamp(y, 9, 1), pd.Timestamp(y, 10, 31))

    spring_vpd = _vpd_max(spring)
    heat_excess = (spring.tmax - 30.0).clip(lower=0)
    heat_x_drought = (spring.tmax.gt(30.0) & spring.gwetroot.lt(0.30))

    return {
        "rain_growing": _sum(growing, "precip"),
        "rain_early": _sum(early, "precip"),
        "rain_spring": _sum(spring, "precip"),
        "sm_preseason": _mean(preseason, "gwetroot"),
        "sm_winter": _mean(winter, "gwetroot"),
        "sm_spring": _mean(spring, "gwetroot"),
        "sm_stress_days": float(spring.gwetroot.lt(0.30).sum()),
        "heat_excess_spring": float(heat_excess.sum()),
        "heat_x_drought": float(heat_x_drought.sum()),
        # ABARES farmpredict uses a 2 C screen for damaging cold exposure.
        # POWER's 2 m Tmin is not a canopy frost measurement, so this remains
        # an exposure proxy and is named/ documented as such.
        "frost_days": float(anthesis.tmin.lt(2.0).sum()),
        "vpd_spring": float(spring_vpd.mean()),
        # French-Schultz rainfall-only lower-bound proxy.  Stored soil water is
        # retained separately above; calling this a complete potential yield
        # would imply PAWC information the phase-1 feed does not yet contain.
        "french_schultz_rain_limit": max(0.0, _sum(growing, "precip") - 110.0),
    }


def cotton_features(daily: pd.DataFrame, harvest_year: int) -> dict[str, float]:
    """Full-season features for cotton harvested in ``harvest_year``."""
    y = harvest_year
    preseason = _between(daily, pd.Timestamp(y - 1, 9, 1),
                         pd.Timestamp(y - 1, 10, 31))
    flowering = _between(daily, pd.Timestamp(y - 1, 12, 1),
                         pd.Timestamp(y, 2, 28))
    harvest = _between(daily, pd.Timestamp(y, 4, 1), pd.Timestamp(y, 5, 31))

    heat_excess = (flowering.tmax - 35.0).clip(lower=0)
    heat_x_drought = (flowering.tmax.gt(35.0)
                      & flowering.gwetroot.lt(0.25))
    # A fixed GWETROOT threshold is not portable between MERRA-2 grid cells.
    # Keep the requested day count as a diagnostic, but use this continuous
    # interaction in the model so a dry-hot season does not collapse to a
    # constant zero simply because the reanalysis wetness scale is shifted.
    heat_dry_stress = heat_excess * (1.0 - flowering.gwetroot.clip(0, 1))
    return {
        "rain_preseason": _sum(preseason, "precip"),
        "rain_flowering": _sum(flowering, "precip"),
        "sm_preseason": _mean(preseason, "gwetroot"),
        "sm_flowering": _mean(flowering, "gwetroot"),
        "sm_stress_days": float(flowering.gwetroot.lt(0.25).sum()),
        "heat_excess_flowering": float(heat_excess.sum()),
        "heat_x_drought": float(heat_x_drought.sum()),
        "heat_dry_stress": float(heat_dry_stress.sum()),
        "vpd_flowering": float(_vpd_max(flowering).mean()),
        "harvest_rain": _sum(harvest, "precip"),
    }

"""
Climate features for Ukraine winter wheat / sunflower.

Reuses the same biophysical helpers as russia.climate (POWER windows, EDD,
winterkill, sunflower flowering). UA-specific stage tweaks live here so the
two packages can diverge without forking the math twice.
"""

from __future__ import annotations

# Re-export shared physics (brazil via russia).
from russia.climate import (  # noqa: F401
    fao56_et0,
    _svp,
    spi,
    fit_spi,
    apply_spi,
    window_totals,
    frost_days,
    heat_days,
    heat_excess,
    vpd_peak,
    mean_gwetroot,
    winterkill_days,
    winterkill_edd,
    winterkill_bare_frost,
    snow_proxy_mm,
    winter_wheat_features as _ru_winter_wheat,
    sunflower_features as _ru_sunflower,
)


def winter_wheat_features(daily, harvest_year,
                          grainfill_months=None,
                          heat_thr=28.0,
                          winterkill_tmin=-15.0):
    """
    UA winter wheat. Default grain-fill May–Jun (South earlier; West may
    stretch into July via regions.build overrides).
    """
    if grainfill_months is None:
        grainfill_months = [(5, 0), (6, 0)]
    return _ru_winter_wheat(
        daily, harvest_year,
        grainfill_months=grainfill_months,
        heat_thr=heat_thr,
        winterkill_tmin=winterkill_tmin,
    )


def sunflower_features(daily, harvest_year,
                       flower_months=None,
                       heat_thr=30.0):
    """UA sunflower flowering heat–drought (Jun–Aug default)."""
    if flower_months is None:
        flower_months = [(6, 0), (7, 0), (8, 0)]
    return _ru_sunflower(
        daily, harvest_year,
        flower_months=flower_months,
        heat_thr=heat_thr,
    )

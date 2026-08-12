"""
Derived climate features for Russian winter wheat.

Reuses brazil/china helpers for windows, EDD, SPI, ET0. Adds:
  - autumn soil recharge (Sep–Nov of year-1)
  - winterkill: bare-frost days + degree-days of hard freeze (POWER);
    optional ERA5-Land snow insulation when snow_depth is joined
  - April root-zone moisture (GWETROOT)
  - heading/grain-fill heat EDD and VPD (May–June South, May–July CBE)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from brazil.climate import (  # noqa: F401 - re-exported for regions.py
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
    _window,
)


WINTER = [(12, -1), (1, 0), (2, 0)]
AUTUMN = [(9, -1), (10, -1), (11, -1)]


def winterkill_days(daily, months, harvest_year, threshold=-15.0):
    """Count of days with Tmin at or below threshold over the dormancy window."""
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmin <= threshold).sum())


def winterkill_edd(daily, months, harvest_year, threshold=-15.0):
    """
    Σ max(0, threshold − Tmin) on hard-freeze days.

    Aase-type bare-frost severity without snow depth: more cold past the crown
    survival threshold is scored more heavily than a day-count alone.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    cold = (threshold - w.tmin).clip(lower=0)
    return float(cold.sum())


def snow_proxy_mm(daily, months, harvest_year, tmax_max=2.0):
    """
    Precipitation falling while Tmax is low enough to accumulate as snow.

    POWER has no snow depth. This is a crude insulation *candidate*, not actual
    pack height; ERA5-Land snow_depth replaces it when available.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float(w[w.tmax <= tmax_max].precip.sum())


def winterkill_bare_frost(daily, months, harvest_year,
                          tmin_thr=-15.0, snow_thr_m=0.05):
    """
    Σ |Tmin+15| on days with Tmin < −15 °C and insufficient snow cover.

    When `snow_depth` (m) is present (ERA5-Land join), uses the deep-dive rule.
    Without snow: counts bare frost as all hard-freeze days (worst case —
    conservative over-count of winterkill exposure).
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    hard = w.tmin < tmin_thr
    if "snow_depth" in w.columns and w.snow_depth.notna().any():
        bare = hard & (w.snow_depth.fillna(0) < snow_thr_m)
    else:
        bare = hard
    if not bare.any():
        return 0.0
    return float((tmin_thr - w.loc[bare, "tmin"]).clip(lower=0).sum())


def mean_gwetroot(daily, months, harvest_year):
    """Mean root-zone wetness (0–1) over a month window."""
    w = _window(daily, months, harvest_year)
    if w.empty or "gwetroot" not in w.columns:
        return None
    s = w.gwetroot.dropna()
    if s.empty:
        return None
    return float(s.mean())


def sm_stress_days(daily, months, harvest_year, thr=0.25):
    """Days with GWETROOT below threshold in the window."""
    w = _window(daily, months, harvest_year)
    if w.empty or "gwetroot" not in w.columns:
        return None
    return float((w.gwetroot < thr).sum())


def radiation_total(daily, months, harvest_year):
    w = _window(daily, months, harvest_year)
    if w.empty or "rs" not in w.columns:
        return None
    return float(w.rs.sum())


def gdd_total(daily, harvest_year, start_month, start_day, tbase=0.0,
              horizon=120):
    """Accumulate simple GDD from a fixed calendar plant date for spring greenup."""
    start = pd.Timestamp(year=harvest_year, month=start_month, day=start_day)
    end = start + pd.Timedelta(days=horizon)
    w = daily[(daily.date >= start) & (daily.date <= end)].sort_values("date")
    if w.empty:
        return None
    tmean = w.tmean if "tmean" in w.columns else (w.tmax + w.tmin) / 2.0
    return float((tmean - tbase).clip(lower=0).sum())


def winter_wheat_features(daily, harvest_year, grainfill_months,
                          heat_thr=28.0, winterkill_tmin=-15.0):
    """
    Full Phase-1 feature set for one point and harvest year Y.

    Phenology (Southern belt roughly; CBE is ~2–3 weeks later but same months
    work as stage windows for a statistical model):
      sown Y-1 Sep–Oct · dormancy Dec–Feb · spring recover Mar–Apr ·
      heading/fill May–Jun (South) or May–Jul (CBE) · harvest Jun–Jul.
    """
    y = harvest_year
    winter = WINTER
    autumn = AUTUMN
    spring_sm = [(4, 0)]
    precip_spring = [(4, 0), (5, 0), (6, 0)]

    feats = {
        # Autumn recharge → overwintering stand establishment
        "precip_autumn": window_totals(daily, autumn, y),
        "sm_autumn": mean_gwetroot(daily, autumn, y),
        # Winterkill / bare frost (POWER; snow when joined)
        "winterkill_days": winterkill_days(
            daily, winter, y, winterkill_tmin),
        "winterkill_edd": winterkill_edd(
            daily, winter, y, winterkill_tmin),
        "winterkill_bare_frost": winterkill_bare_frost(
            daily, winter, y, winterkill_tmin),
        "snow_proxy_mm": snow_proxy_mm(daily, winter, y),
        # Spring moisture after snowmelt
        "sm_april": mean_gwetroot(daily, spring_sm, y),
        "sm_stress_spring": sm_stress_days(daily, precip_spring, y, 0.25),
        "precip_spring": window_totals(daily, precip_spring, y),
        # Grain-fill heat and atmospheric demand
        "edd_grainfill": heat_excess(daily, grainfill_months, y, heat_thr),
        "heat_days_grainfill": heat_days(
            daily, grainfill_months, y, heat_thr),
        "vpd_grainfill": vpd_peak(daily, grainfill_months, y),
        "precip_grainfill": window_totals(daily, grainfill_months, y),
        # Green-up thermal time (1 Mar base 0 °C)
        "gdd_spring": gdd_total(daily, y, 3, 1, tbase=0.0, horizon=100),
        "radiation_spring": radiation_total(
            daily, [(3, 0), (4, 0), (5, 0)], y),
    }
    return feats


def sunflower_features(daily, harvest_year, flower_months=None,
                       heat_thr=30.0):
    """
    Summer oilseed features for Russian sunflower (South / CBE / Volga).

    Literature anchors (statistical, not WOFOST):
      - North Caucasus Peredovik series: April precip (+), May–Aug heat/precip
        stress; HTK above 20 °C (SPbU Biology 2023).
      - Hydrometcenter CFO sunflower models: agro-met factors 1–3 months before
        harvest (method.meteorf.ru Trudy 373).
      - WOFOST RU regional hybrids for sunflower (MSU Soil Sci.) — process
        benchmark; we keep ridge+trend like other packages.

    Calendar (approx): sow Apr–May · flower Jun–Aug · harvest Sep–Oct.
    """
    y = harvest_year
    flower_months = flower_months or [(6, 0), (7, 0), (8, 0)]
    april = [(4, 0)]
    may_aug = [(5, 0), (6, 0), (7, 0), (8, 0)]
    season = [(4, 0), (5, 0), (6, 0), (7, 0), (8, 0)]

    feats = {
        # Early moisture (paper: April precip supports establishment)
        "precip_april": window_totals(daily, april, y),
        "sm_april": mean_gwetroot(daily, april, y),
        # Flowering / seed-fill heat–drought complex
        "edd_flower": heat_excess(daily, flower_months, y, heat_thr),
        "heat_days_flower": heat_days(daily, flower_months, y, heat_thr),
        "vpd_flower": vpd_peak(daily, flower_months, y),
        "sm_flower": mean_gwetroot(daily, flower_months, y),
        "sm_stress_flower": sm_stress_days(daily, flower_months, y, 0.25),
        "precip_flower": window_totals(daily, flower_months, y),
        # Broader season moisture & radiation (oil content / biomass)
        "precip_may_aug": window_totals(daily, may_aug, y),
        "sm_season": mean_gwetroot(daily, season, y),
        "radiation_season": radiation_total(daily, season, y),
        "gdd_season": gdd_total(daily, y, 4, 15, tbase=6.0, horizon=150),
    }
    return feats


def mean_tmax(daily, months, harvest_year):
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float(w.tmax.mean())


def gtk_selyaninov(daily, months, harvest_year, t_thr=10.0):
    """
    Selyaninov hydrothermal coefficient proxy:
      precip_mm / (0.1 * Σ Tmean on days with Tmean > t_thr).
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    tmean = w.tmean if "tmean" in w.columns else (w.tmax + w.tmin) / 2.0
    warm = tmean > t_thr
    if not warm.any():
        return None
    denom = 0.1 * float(tmean[warm].sum())
    if denom <= 0:
        return None
    return float(w.precip.sum()) / denom


def spring_barley_features(daily, harvest_year, heat_thr=28.0):
    """
    Spring-barley weather features (South / CBE / Volga).

    Literature anchors (statistical, not WOFOST):
      - Non-chernozem / Ob / Ryazan: May–Jul precip & GTK; June heat
      - Altai GAU ML: Sep–Mar prior precip; monthly T/P
      - MSU WOFOST RU barley hybrids — process benchmark only

    Calendar (approx): sow Apr–May · critical moisture mid-May→Jul ·
    harvest Jul–Aug (South earlier).
    """
    y = harvest_year
    may = [(5, 0)]
    jun = [(6, 0)]
    jul = [(7, 0)]
    may_jul = [(5, 0), (6, 0), (7, 0)]
    jun_jul = [(6, 0), (7, 0)]
    # Autumn–winter recharge before spring sowing (Altai ML prior)
    sep_mar = [(9, -1), (10, -1), (11, -1), (12, -1), (1, 0), (2, 0), (3, 0)]

    feats = {
        "precip_may_jul": window_totals(daily, may_jul, y),
        "precip_may": window_totals(daily, may, y),
        "precip_jun": window_totals(daily, jun, y),
        "precip_jul": window_totals(daily, jul, y),
        "sm_may_jul": mean_gwetroot(daily, may_jul, y),
        "sm_stress_may_jul": sm_stress_days(daily, may_jul, y, 0.25),
        "gtk_may_jul": gtk_selyaninov(daily, may_jul, y),
        "tmax_jun": mean_tmax(daily, jun, y),
        "edd_jun_jul": heat_excess(daily, jun_jul, y, heat_thr),
        "heat_days_jun_jul": heat_days(daily, jun_jul, y, heat_thr),
        "vpd_may_jul": vpd_peak(daily, may_jul, y),
        "gdd_season": gdd_total(daily, y, 4, 15, tbase=5.0, horizon=120),
        "precip_sep_mar": window_totals(daily, sep_mar, y),
        "radiation_may_jul": radiation_total(daily, may_jul, y),
    }
    return feats

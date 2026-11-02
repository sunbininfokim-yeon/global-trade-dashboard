"""
The derived-variable formulas from Regions/인도/*/*_상세분석_및_수식.md.

Every function implements one formula from one guide, names the guide, and
takes a daily frame with columns

    date, tmax, tmin, tmean, precip, et0, rh_mean, vpd_max

This module is deliberately self-contained. The reference equations at the top
-- FAO-56 Penman-Monteith ET0 and the Gamma-fitted SPI -- also appear in
brazil/climate.py, and importing them from there would have avoided the
duplication. They are copied instead, for one reason: the two models must be
able to move independently. A change made to the Brazilian package for a
Brazilian reason must not silently alter what the Indian models compute. These
are published, stable equations (FAO-56 Irrigation and Drainage Paper 56;
McKee et al. 1993), not code under development, so the cost of two copies is
low and the cost of a hidden coupling is not.

No Brazilian data, coefficient or fitted parameter enters here or anywhere
else in this package. Yields come from ICRISAT's Indian district tables,
weather from NASA POWER at Indian coordinates, and every coefficient is fitted
on Indian seasons alone.

One substitution is made and flagged rather than buried: potential
evapotranspiration is FAO-56 Penman-Monteith computed here from NASA POWER
radiation, wind, dewpoint and temperature. The cotton guide writes
"Potential_Evapotranspiration" without naming an estimator; Penman-Monteith is
the FAO reference method and is what the number means throughout this package.
"""

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Reference evapotranspiration -- FAO-56 Penman-Monteith.
#
# Needed by 서부_마하라슈트라/면화 §2A, whose Moisture_Deficit is
# sum(PET - Rainfall) over the boll-formation window.
# ---------------------------------------------------------------------------

SOLAR_CONSTANT = 0.0820        # MJ m-2 min-1
STEFAN_BOLTZMANN = 4.903e-9    # MJ K-4 m-2 day-1
ALBEDO = 0.23                  # FAO-56 reference grass surface


def _svp(t):
    """Saturation vapour pressure at temperature t (kPa)."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(doy, lat_deg):
    """
    Ra (MJ m-2 day-1) from latitude and day of year, FAO-56 eq. 21.

    Latitude is signed, and solar declination comes from the day of year, so
    this is correct in either hemisphere. The Indian points run from about
    19 N (Nanded) to 31 N (Ludhiana).
    """
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.0)
    decl = 0.409 * np.sin(2 * np.pi * doy / 365.0 - 1.39)

    x = np.clip(-np.tan(phi) * np.tan(decl), -1.0, 1.0)
    ws = np.arccos(x)

    return (24 * 60 / np.pi) * SOLAR_CONSTANT * dr * (
        ws * np.sin(phi) * np.sin(decl)
        + np.cos(phi) * np.cos(decl) * np.sin(ws))


def fao56_et0(df, lat, elevation):
    """
    ET0 = [0.408 D (Rn - G) + g (900/(T+273)) u2 (es - ea)]
          / [D + g (1 + 0.34 u2)]

    Expects columns tmax, tmin, tmean, tdew, wind, rs (shortwave down,
    MJ m-2 day-1) and a date column. G is taken as zero, standard at daily
    step. Returns a Series of ET0 in mm/day.
    """
    tmax, tmin = df.tmax, df.tmin
    tmean = df.tmean if "tmean" in df else (tmax + tmin) / 2.0

    press = 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26
    gamma = 0.665e-3 * press

    es = (_svp(tmax) + _svp(tmin)) / 2.0
    ea = _svp(df.tdew)
    delta = 4098 * _svp(tmean) / (tmean + 237.3) ** 2

    rs = df.rs
    ra = extraterrestrial_radiation(df.date.dt.dayofyear.values, lat)
    rso = (0.75 + 2e-5 * elevation) * ra

    rns = (1 - ALBEDO) * rs
    cloud = np.clip(rs / np.where(rso > 0, rso, np.nan), 0.25, 1.0)
    rnl = (STEFAN_BOLTZMANN
           * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2.0)
           * (0.34 - 0.14 * np.sqrt(ea.clip(lower=0)))
           * (1.35 * cloud - 0.35))
    rn = rns - rnl

    u2 = df.wind.clip(lower=0.1)   # FAO-56 is undefined at zero wind

    num = 0.408 * delta * rn + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * u2)

    return (num / den).clip(lower=0)


# ---------------------------------------------------------------------------
# SPI -- Standardized Precipitation Index.
#
# Carried for the two Kharif crops as a normalised measure of how extreme the
# monsoon was against its own climatology, which is the quantity the soybean
# guide's "몬순의 힘" refers to.
# ---------------------------------------------------------------------------


def fit_spi(history):
    """
    Fit the SPI distribution to a history of accumulation totals.

    Returns the Gamma shape and scale plus the zero fraction q, so a later
    season can be scored against this climatology without refitting it.
    """
    x = pd.Series(history, dtype=float).dropna()
    if len(x) < 10:
        return None

    nonzero = x[x > 0]
    q = float((x <= 0).sum()) / len(x)

    # floc=0 pins the Gamma at the origin: rainfall cannot be negative, and a
    # free location parameter drifts negative on short records and distorts
    # exactly the dry tail that matters.
    shape, _loc, scale = stats.gamma.fit(nonzero, floc=0)
    return {"shape": float(shape), "scale": float(scale), "q": q}


def apply_spi(params, values):
    """
    Score totals against a fitted climatology.

    H(x) = q + (1-q)G(x), then the inverse standard normal, clipped away from
    0 and 1 so a record season maps to a large finite z rather than infinity.
    """
    if params is None:
        return np.nan * np.asarray(values, dtype=float)
    g = stats.gamma.cdf(values, params["shape"], loc=0, scale=params["scale"])
    h = np.clip(params["q"] + (1 - params["q"]) * g, 1e-6, 1 - 1e-6)
    return stats.norm.ppf(h)


def spi(totals):
    """
    Gamma-fitted SPI for one accumulation window, one value per year, fitted
    and scored on the same series.

    Forecasting a new season uses fit_spi on the training years and apply_spi
    on the new value instead, so the season being predicted does not help
    define the distribution it is scored against.
    """
    x = pd.Series(totals, dtype=float).dropna()
    params = fit_spi(x)
    if params is None:
        return pd.Series(np.nan, index=pd.Series(totals).index)
    return pd.Series(apply_spi(params, x.values), index=x.index)


# ---------------------------------------------------------------------------
# Window helpers.
#
# Months are (month, year_offset_from_harvest_year). Kharif crops never use a
# negative offset -- they are sown and harvested inside one calendar year.
# Rabi wheat reaches back to the previous November.
# ---------------------------------------------------------------------------


def _window(daily, months, harvest_year):
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y) & (daily.date.dt.month == month))
    return daily[mask]


def _span(daily, start, end):
    """Rows falling inside a closed date interval."""
    return daily[(daily.date >= start) & (daily.date <= end)]


def window_totals(daily, months, harvest_year):
    """Rainfall total over a set of (month, year_offset) windows."""
    w = _window(daily, months, harvest_year)
    return float(w.precip.sum()) if not w.empty else np.nan


def heat_days(daily, months, harvest_year, threshold=35.0):
    """Days above a temperature threshold."""
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmax > threshold).sum())


def waterlogging_penalty(daily, months, harvest_year, threshold=300.0):
    """
    max(0, monthly rain - threshold), summed over the months given.

    Used for the soybean guide's 수확기 침수: past roughly 300 mm in a month
    the crop cannot be harvested and standing beans rot in the field. Excess
    over a monthly threshold rather than a period total, because a month at
    500 mm and a month at 100 mm is a very different season from two months
    at 300 mm.
    """
    total = 0.0
    seen = False
    for month, offset in months:
        y = harvest_year + offset
        w = daily[(daily.date.dt.year == y) & (daily.date.dt.month == month)]
        if w.empty:
            continue
        total += max(0.0, float(w.precip.sum()) - threshold)
        seen = True
    return total if seen else None


# ---------------------------------------------------------------------------
# Rabi wheat -- 북서부_펀자브/밀 §2.
#
# The guide is explicit that rainfall weight should be cut hard here: the
# Indus-Gangetic canal network means this crop is irrigated, and what destroys
# a Punjab wheat harvest is March heat during grain filling, not drought. Both
# variables below are temperature-only by design.
# ---------------------------------------------------------------------------


def thsdd(daily, harvest_year, threshold=30.0, start=(2, 20), end=(3, 31)):
    """
    Terminal Heat Stress Degree Days (§2A):

        THSDD = sum over grain filling of max(0, Tmax - 30 C)

    Grain filling is taken as 20 February to 31 March, the guide's
    "2월 말부터 3월 말까지". A calendar window rather than a thermal-time one,
    because the guide states it as dates and sowing here is tightly bunched by
    the canal rotation.

    Degrees of overshoot, not a day count: the 2022 collapse the guide's
    reference paper analyses was driven by how far above 30 C March ran, not
    by how many days crossed it.
    """
    lo = pd.Timestamp(year=harvest_year, month=start[0], day=start[1])
    hi = pd.Timestamp(year=harvest_year, month=end[0], day=end[1])
    w = _span(daily, lo, hi)
    if w.empty:
        return None
    return float((w.tmax - threshold).clip(lower=0).sum())


def warm_night_days(daily, harvest_year, threshold=18.0,
                    start=(2, 1), end=(3, 31)):
    """
    Nights that never drop below 18 C during grain filling (§2B).

    Wheat respires through the night; when Tmin stays high the plant burns the
    day's photosynthate instead of laying it down as starch. Counted over a
    slightly wider window than THSDD -- warm nights matter from the start of
    February, before daytime heat becomes damaging.
    """
    lo = pd.Timestamp(year=harvest_year, month=start[0], day=start[1])
    hi = pd.Timestamp(year=harvest_year, month=end[0], day=end[1])
    w = _span(daily, lo, hi)
    if w.empty:
        return None
    return float((w.tmin > threshold).sum())


# ---------------------------------------------------------------------------
# Kharif soybean -- 중부_마디아프라데시/대두 §2.
#
# "월간 강수량 데이터를 버리고 반드시 일별(Daily) 강수량 데이터를 사용" -- discard
# monthly rainfall, count consecutive rainless days. Both functions below exist
# because a monthly total genuinely cannot express either of them.
# ---------------------------------------------------------------------------


def monsoon_onset_doy(daily, harvest_year, month=6, trigger_mm=50.0,
                      search_days=90):
    """
    Monsoon onset as the day June's running rainfall total first reaches
    50 mm (§2A).

    Accumulation starts on 1 June; the guide names the IMD convention and
    50 mm as the threshold. Returns a day-of-year in the harvest year -- a
    Kharif crop is sown and harvested inside one calendar year, so there is no
    year-boundary bookkeeping.

    Returns None when the window is not covered or the total never arrives.
    A failed monsoon is a real outcome and must not be confused with an onset
    of zero, which would read as the earliest possible arrival.
    """
    start = pd.Timestamp(year=harvest_year, month=month, day=1)
    end = start + pd.Timedelta(days=search_days)

    w = _span(daily, start, end).sort_values("date")
    if w.empty:
        return None

    cum = w.precip.fillna(0).cumsum()
    hit = w.date[cum >= trigger_mm]
    if hit.empty:
        return None

    jan1 = pd.Timestamp(year=harvest_year, month=1, day=1)
    return float((pd.Timestamp(hit.iloc[0]) - jan1).days + 1)


def days_late(onset, threshold=166):
    """
    max(0, onset_DOY - 166) -- days the monsoon arrived after 15 June.

    A hinge, not a raw date: the guide describes no penalty for a timely
    monsoon and a worsening one after it, so encoding the kink lets a linear
    model reproduce a threshold response. 15 June is the normal onset over
    Madhya Pradesh.
    """
    if onset is None:
        return None
    return max(0.0, float(onset - threshold))


def dry_spells(daily, start, end, dry_mm=1.0):
    """
    Maximal runs of rainless days inside a window.

    A day counts as dry below 1 mm rather than at exactly zero: trace rainfall
    that evaporates the same morning does nothing for a flowering soybean, and
    POWER's corrected precipitation reports small non-zero values on days that
    were dry on the ground.

    Returns a list of (length, mean_vpd) per run.
    """
    w = _span(daily, start, end).sort_values("date")
    if w.empty:
        return []

    rain = w.precip.fillna(0).values
    vpd = w.vpd_max.values

    runs, run_len, run_vpd = [], 0, []
    for i, p in enumerate(rain):
        if p < dry_mm:
            run_len += 1
            if not np.isnan(vpd[i]):
                run_vpd.append(vpd[i])
        else:
            if run_len:
                runs.append((run_len,
                             float(np.mean(run_vpd)) if run_vpd else np.nan))
            run_len, run_vpd = 0, []
    if run_len:
        runs.append((run_len, float(np.mean(run_vpd)) if run_vpd else np.nan))

    return runs


def flowering_drought_stress(daily, harvest_year, month=8, min_days=7):
    """
    Flowering_Drought_Stress = sum over August of
        (consecutive dry days > 7) * VPD                             (§2B)

    Read as: every dry spell longer than a week during flowering contributes
    its own length weighted by how hard the air was pulling water out of the
    crop while it ran. A ten-day break under saturated monsoon air is not the
    same event as a ten-day break under 4 kPa of deficit, which is why the
    guide multiplies rather than counts.

    Spells of seven days or fewer contribute nothing: the guide puts pod
    formation at risk and sets the threshold at a week.
    """
    start = pd.Timestamp(year=harvest_year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(0)

    if _span(daily, start, end).empty:
        return None

    total = 0.0
    for length, mean_vpd in dry_spells(daily, start, end):
        if length > min_days and not np.isnan(mean_vpd):
            total += length * mean_vpd
    return total


def longest_dry_spell(daily, months, harvest_year):
    """
    Longest rainless run across a set of (month, offset) windows.

    Carried alongside the weighted stress index so the training run can show
    whether the VPD weighting earns its place or whether raw spell length was
    doing the work.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    runs = dry_spells(daily, w.date.min(), w.date.max())
    return float(max((r[0] for r in runs), default=0))


# ---------------------------------------------------------------------------
# Kharif cotton -- 서부_마하라슈트라/면화 §2.
# ---------------------------------------------------------------------------


def moisture_deficit(daily, months, harvest_year):
    """
    Moisture_Deficit = sum over Aug-Sep of (PET - Rainfall)          (§2A)

    The boll-formation water ledger. Summed as a period total rather than
    clipped per day, which is the plain reading of the guide: a wet week
    genuinely does refill the black cotton soil that a dry week drew down.
    Negative values mean the period ran in surplus, which is the wet arm of
    the guide's inverted U and has to stay expressible.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or w.et0.isna().all():
        return None
    return float(w.et0.sum() - w.precip.sum())


def pest_risk_days(daily, months, harvest_year,
                   t_low=25.0, t_high=30.0, rh_threshold=80.0):
    """
    Pest_Risk_Days = count of days with 25 C <= T <= 30 C AND RH > 80%  (§2B)

    Pink bollworm favourability. Both conditions must hold on the *same day*,
    which is the whole point of the index: a hot dry month and a cool wet
    month can each supply half the condition all season and mean nothing.

    Temperature is the daily mean, since the guide gives a band -- a band
    applied to Tmax would flag a day that touched 30 C at noon and sat at
    18 C the rest of the time.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    tmean = w.tmean if "tmean" in w else (w.tmax + w.tmin) / 2.0
    hit = (tmean >= t_low) & (tmean <= t_high) & (w.rh_mean > rh_threshold)
    return float(hit.sum())


def boll_shedding_index(daily, months, harvest_year, threshold=32.0):
    """
    Heat during boll formation weighted by atmospheric dryness:
    sum of max(0, Tmax - 32) * VPD.

    Not written as a formula in this guide, which describes boll shedding
    qualitatively ("나무가 생존을 위해 꼬투리를 강제로 떨어뜨립니다"). Carried as
    a candidate feature so the training run can test it, and deliberately left
    out of the config's `core` set so it cannot be mistaken for one of the
    guide's own named variables.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    excess = (w.tmax - threshold).clip(lower=0)
    vpd = w.vpd_max.fillna(w.vpd_max.mean())
    return float((excess * vpd).sum())

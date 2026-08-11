"""
The derived-variable formulas from Regions/브라질/*/*_상세분석_및_수식.md.

Each function implements one formula from those guides and names the guide it
came from. They all take a daily frame with columns:

    date, tmax, tmin, precip, et0, rh_mean, vpd_max

and return either a scalar feature or a per-day series.

Two deliberate substitutions are made, both because the source the guide names
is not obtainable without a paid or credentialed feed. They are flagged here
rather than buried, because they change what the resulting feature means:

  - Potential evapotranspiration is FAO-56 Penman-Monteith computed here from
    NASA POWER radiation, wind, dewpoint and temperature -- not the
    Thornthwaite temperature-only estimate the coffee guide assumes.
    Penman-Monteith is the better estimator and is the equation the safrinha
    guide writes out in full, so both guides are served by one series.
  - CWSI (MATOPIBA soy) needs satellite canopy temperature. Without a
    thermal-infrared feed there is no Tc, so `vpd_heat_stress` stands in: it
    keeps the physical intent (stomatal closure under hot, dry air) using
    Tmax and VPD only. It is a proxy, not CWSI, and is named accordingly.
"""

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Reference evapotranspiration -- FAO-56 Penman-Monteith, written out in
# 마투그로수/옥수수 §2B and underlying every water-balance feature here.
# ---------------------------------------------------------------------------

SOLAR_CONSTANT = 0.0820        # MJ m-2 min-1
STEFAN_BOLTZMANN = 4.903e-9    # MJ K-4 m-2 day-1
ALBEDO = 0.23                  # FAO-56 reference grass surface


def _svp(t):
    """Saturation vapour pressure at temperature t (kPa)."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(doy, lat_deg):
    """Ra (MJ m-2 day-1) from latitude and day of year, FAO-56 eq. 21."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.0)
    decl = 0.409 * np.sin(2 * np.pi * doy / 365.0 - 1.39)

    # Sunset hour angle, clipped because |tan(phi)tan(decl)| can exceed 1
    # inside the polar circles. Irrelevant for Brazil, but a NaN here would
    # silently propagate through every downstream water balance.
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
    MJ m-2 day-1) and a date column. G is taken as zero, which is standard at
    daily step. Returns a Series of ET0 in mm/day.
    """
    tmax, tmin = df.tmax, df.tmin
    tmean = df.tmean if "tmean" in df else (tmax + tmin) / 2.0

    # Atmospheric pressure and psychrometric constant from elevation
    press = 101.3 * ((293 - 0.0065 * elevation) / 293) ** 5.26
    gamma = 0.665e-3 * press

    es = (_svp(tmax) + _svp(tmin)) / 2.0
    ea = _svp(df.tdew)
    delta = 4098 * _svp(tmean) / (tmean + 237.3) ** 2

    rs = df.rs
    ra = extraterrestrial_radiation(df.date.dt.dayofyear.values, lat)
    rso = (0.75 + 2e-5 * elevation) * ra

    rns = (1 - ALBEDO) * rs
    # Cloudiness term, bounded: Rs/Rso above 1 is a measurement artefact and
    # unbounded would drive net longwave negative.
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
# Rainy season onset and demise -- Liebmann et al. (2007) anomalous
# accumulation, as specified in 마투그로수/대두 §2B and 마투그로수/옥수수 §2A.
# ---------------------------------------------------------------------------


def anomalous_accumulation(daily, start, end, mean_rain=None):
    """
    A(d) = sum_{t=t0}^{d} (R(t) - Rbar) over [start, end].

    The curve falls through the dry season (R < Rbar every day) and rises
    through the wet season. Its absolute minimum is the onset of the rains,
    its absolute maximum the demise -- one pass gives both.

    `mean_rain` is Rbar, the site's long-run mean daily rainfall. Passing None
    computes it from the window itself, which is what makes the index
    self-calibrating across regions with very different rainfall totals.

    Returns (onset_date, end_date, curve) with curve a Series indexed by date.
    """
    w = daily[(daily.date >= start) & (daily.date <= end)].sort_values("date")
    if w.empty:
        return None, None, None

    rbar = float(w.precip.mean()) if mean_rain is None else mean_rain
    curve = (w.precip - rbar).cumsum()
    curve.index = w.date.values

    return curve.idxmin(), curve.idxmax(), curve


def onset_doy(daily, harvest_year, dry_midpoint=(7, 1), mean_rain=None):
    """
    Onset of the rainy season as a day-of-year in the *planting* calendar year.

    Accumulation starts at the middle of the dry season (1 July by default,
    DOY 182, the guide's t0) and runs a full year forward, so both the onset
    and the following demise fall inside one window.

    Returns (onset_doy, end_doy) or (None, None) when the window is not
    covered. DOY is measured in the planting year, so the 20 October threshold
    the guide uses is DOY 293.
    """
    m, d = dry_midpoint
    plant_year = harvest_year - 1
    start = pd.Timestamp(year=plant_year, month=m, day=d)
    end = start + pd.DateOffset(years=1) - pd.Timedelta(days=1)

    onset, demise, curve = anomalous_accumulation(daily, start, end, mean_rain)
    if onset is None:
        return None, None

    onset = pd.Timestamp(onset)
    demise = pd.Timestamp(demise)

    # Express both as a day count from 1 Jan of the planting year, so a demise
    # falling in the harvest year keeps counting past 365 instead of wrapping
    # back to 1 and looking like an absurdly early date.
    jan1 = pd.Timestamp(year=plant_year, month=1, day=1)
    return (onset - jan1).days + 1, (demise - jan1).days + 1


def onset_doy_agronomic(daily, harvest_year, trigger_mm=30.0, window=3,
                        dry_spell=10, look_ahead=15):
    """
    The agronomic onset rule from 마투그로수/대두 §2A: after 1 September, the
    first day whose 3-day rainfall exceeds 30 mm and which is not followed
    within 15 days by a dry spell of 10 or more days.

    Kept alongside the anomalous-accumulation version because the guide offers
    both and calls this one noisier; carrying both lets the training run show
    whether that is true here rather than assuming it.
    """
    plant_year = harvest_year - 1
    start = pd.Timestamp(year=plant_year, month=9, day=1)
    end = pd.Timestamp(year=harvest_year, month=1, day=31)

    w = daily[(daily.date >= start) & (daily.date <= end)].sort_values("date")
    w = w.reset_index(drop=True)
    if len(w) < window + look_ahead:
        return None

    roll = w.precip.rolling(window).sum()
    jan1 = pd.Timestamp(year=plant_year, month=1, day=1)

    for i in range(window - 1, len(w) - look_ahead):
        if not roll.iloc[i] > trigger_mm:
            continue
        # Longest run of dry days in the fortnight that follows.
        after = w.precip.iloc[i + 1:i + 1 + look_ahead].values
        longest, run = 0, 0
        for p in after:
            run = run + 1 if p < 1.0 else 0
            longest = max(longest, run)
        if longest < dry_spell:
            return (w.date.iloc[i] - jan1).days + 1

    return None


def days_late(onset, threshold=293):
    """
    max(0, ORS_DOY - 293) -- days the rains arrived after 20 October.

    A hinge, not a raw date: below the threshold the guide expects no penalty
    at all, and encoding that shape here lets a linear model reproduce the
    "exponentially worse after 20 October" behaviour the guide attributes to
    tree splits. (마투그로수/대두 §3B)
    """
    if onset is None:
        return None
    return max(0.0, float(onset - threshold))


# ---------------------------------------------------------------------------
# SPI -- Standardized Precipitation Index, 남부지방/대두 §2A.
# ---------------------------------------------------------------------------


def fit_spi(history):
    """
    Fit the SPI distribution to a history of accumulation totals.

    Returns the parameters needed to score any later season against this
    climatology: the Gamma shape and scale, plus the zero fraction q.
    """
    x = pd.Series(history, dtype=float).dropna()
    if len(x) < 10:
        return None

    nonzero = x[x > 0]
    q = float((x <= 0).sum()) / len(x)

    # floc=0 pins the Gamma at the origin: rainfall cannot be negative, and a
    # free location parameter routinely drifts negative on short records and
    # distorts the tails, which are exactly the drought years of interest.
    shape, _loc, scale = stats.gamma.fit(nonzero, floc=0)
    return {"shape": float(shape), "scale": float(scale), "q": q}


def apply_spi(params, values):
    """
    Score totals against a fitted climatology.

    H(x) = q + (1-q)G(x), then the inverse standard normal. Clipped away from
    0 and 1 so a record-setting season maps to a large finite z rather than an
    infinity that would poison the regression.
    """
    if params is None:
        return np.nan * np.asarray(values, dtype=float)
    g = stats.gamma.cdf(values, params["shape"], loc=0, scale=params["scale"])
    h = np.clip(params["q"] + (1 - params["q"]) * g, 1e-6, 1 - 1e-6)
    return stats.norm.ppf(h)


def spi(totals):
    """
    Gamma-fitted SPI for a series of equal-length accumulation totals, one per
    year, fitted and scored on the same series.

    Fitting across years (rather than across a single year's days) is what
    makes the result "how extreme is this season against its own climatology",
    which is the quantity the guide's thresholds -1.5 / +1.5 refer to.

    Forecasting a new season uses fit_spi on the training years and apply_spi
    on the new value instead, so the season being predicted does not help
    define the distribution it is scored against.
    """
    x = pd.Series(totals, dtype=float).dropna()
    params = fit_spi(x)
    if params is None:
        return pd.Series(np.nan, index=pd.Series(totals).index)
    return pd.Series(apply_spi(params, x.values), index=x.index)


def window_totals(daily, months, harvest_year):
    """Rainfall total over a set of (month, year_offset) windows."""
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y) & (daily.date.dt.month == month))
    w = daily[mask]
    return float(w.precip.sum()) if not w.empty else np.nan


# ---------------------------------------------------------------------------
# Crop water deficit -- FAO-56, 마투그로수/옥수수 §2C and 남부지방/옥수수 §2.
# ---------------------------------------------------------------------------

# FAO-56 crop coefficients by fraction of the season elapsed. The guides give
# the three anchors (initial 0.3, silking/mid 1.2, late 0.5); the values
# between them are the standard linear development ramp.
KC_MAIZE = [(0.00, 0.30), (0.20, 0.30), (0.45, 1.20), (0.70, 1.20), (1.00, 0.50)]


def kc_curve(fraction, anchors=KC_MAIZE):
    """Crop coefficient at a given fraction of the season, linearly ramped."""
    xs = [a[0] for a in anchors]
    ys = [a[1] for a in anchors]
    return float(np.interp(fraction, xs, ys))


def crop_water_deficit(daily, planting, season_days, anchors=KC_MAIZE):
    """
    CWD_t = min(0, CWD_{t-1} + (Rain_t - Kc * ET0_t))

    The running ledger of rainfall against crop demand, capped at zero because
    surplus above field capacity runs off rather than banking for later. The
    result is a Series of CWD indexed by date, in mm, always <= 0.
    """
    w = daily[(daily.date >= planting)
              & (daily.date < planting + pd.Timedelta(days=season_days))]
    w = w.sort_values("date")
    if w.empty:
        return None

    out, bal = [], 0.0
    for i, (_, row) in enumerate(w.iterrows()):
        kc = kc_curve(i / max(season_days - 1, 1), anchors)
        et = row.et0 if pd.notna(row.et0) else 0.0
        rain = row.precip if pd.notna(row.precip) else 0.0
        bal = min(0.0, bal + rain - kc * et)
        out.append(bal)

    return pd.Series(out, index=w.date.values)


def silking_stress(daily, planting, start_day=60, end_day=75,
                   season_days=130, anchors=KC_MAIZE):
    """
    Accumulated water deficit over the silking window, days 60-75 after
    planting. The guides' single most punitive corn feature: below -50 mm the
    ear does not fill and yield collapses regardless of the rest of the season.

    Returned as the mean CWD across the window, in mm (negative = deficit).
    """
    cwd = crop_water_deficit(daily, planting, season_days, anchors)
    if cwd is None or cwd.empty:
        return None

    idx = pd.to_datetime(pd.Series(cwd.index))
    lo = planting + pd.Timedelta(days=start_day)
    hi = planting + pd.Timedelta(days=end_day)
    w = cwd[((idx >= lo) & (idx <= hi)).values]

    return float(w.mean()) if len(w) else None


# ---------------------------------------------------------------------------
# Degree-day phenology -- MATOPIBA/면화 §2A.
# ---------------------------------------------------------------------------


def accumulated_degree_days(daily, planting, tbase=15.6, horizon=220):
    """
    ADD_d = sum ((Tmax + Tmin)/2 - Tbase), negative days contributing zero.

    Returns a Series of cumulative ADD indexed by date, used to locate growth
    stages by thermal time rather than by calendar date.
    """
    w = daily[(daily.date >= planting)
              & (daily.date < planting + pd.Timedelta(days=horizon))]
    w = w.sort_values("date")
    if w.empty:
        return None

    tmean = (w.tmax + w.tmin) / 2.0
    daily_add = (tmean - tbase).clip(lower=0)
    out = daily_add.cumsum()
    out.index = w.date.values
    return out


def stage_window(add, lo, hi):
    """
    The date range over which accumulated degree days sit between two
    thresholds -- e.g. 800-1200 ADD is cotton's flowering-to-boll window.
    """
    if add is None or add.empty:
        return None, None
    inside = add[(add >= lo) & (add <= hi)]
    if inside.empty:
        return None, None
    return pd.Timestamp(inside.index[0]), pd.Timestamp(inside.index[-1])


def cotton_heat_stress(daily, start, end, threshold=32.0):
    """
    Stress = sum over the flowering/boll window of max(0, Tmax - 32) * VPD.

    Heat and dry air multiply rather than add: 35 C in saturated air sheds far
    fewer bolls than 35 C in desert air, which is why the guide specifies the
    product. (MATOPIBA/면화 §2B)
    """
    if start is None or end is None:
        return None
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty:
        return None
    excess = (w.tmax - threshold).clip(lower=0)
    vpd = w.vpd_max.fillna(w.vpd_max.mean())
    return float((excess * vpd).sum())


# ---------------------------------------------------------------------------
# Water deficit with stage sensitivity -- 상파울루/커피 §2.
# ---------------------------------------------------------------------------


def monthly_water_deficit(daily, awc=100.0):
    """
    Thornthwaite & Mather bucket: DEF_m = max(0, ETp_m - AET_m).

    A single soil store of `awc` mm is filled by rain and drawn down by
    demand; whatever demand the store cannot meet is the month's deficit. ETp
    is Penman-Monteith ET0 (see module docstring).

    Returns a DataFrame with year, month, def_mm.
    """
    d = daily.dropna(subset=["precip", "et0"]).sort_values("date")
    keys = [d.date.dt.year.rename("year"), d.date.dt.month.rename("month")]
    m = d.groupby(keys).agg(
        precip=("precip", "sum"), etp=("et0", "sum")).reset_index()

    store, rows = awc, []
    for _, r in m.iterrows():
        surplus = r.precip - r.etp
        if surplus >= 0:
            store = min(awc, store + surplus)
            deficit = 0.0
        else:
            draw = min(store, -surplus)
            store -= draw
            deficit = -surplus - draw       # demand the soil could not cover
        rows.append({"year": int(r.year), "month": int(r.month),
                     "def_mm": float(deficit)})

    return pd.DataFrame(rows)


def weighted_deficit(defs, windows):
    """
    Sum of monthly deficits scaled by FAO yield-response factors Ky.

    `windows` is a list of (year, month, ky). Coffee's flowering deficit
    carries Ky 1.2 while the same millimetre shortfall at harvest carries 0.2,
    which is the whole point of weighting rather than summing raw deficits.
    """
    total = 0.0
    found = False
    for year, month, ky in windows:
        row = defs[(defs.year == year) & (defs.month == month)]
        if row.empty:
            continue
        total += float(row.def_mm.iloc[0]) * ky
        found = True
    return total if found else None


# ---------------------------------------------------------------------------
# Threshold penalties shared across guides.
# ---------------------------------------------------------------------------


def _window(daily, months, harvest_year):
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y) & (daily.date.dt.month == month))
    return daily[mask]


def frost_days(daily, months, harvest_year, threshold=0.0):
    """Days with Tmin at or below a threshold -- 0 C for corn, 1 C for coffee."""
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmin <= threshold).sum())


def heat_days(daily, months, harvest_year, threshold=35.0):
    """Days above a physiological heat threshold (35 C halts N fixation)."""
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmax > threshold).sum())


def heat_excess(daily, months, harvest_year, threshold=35.0):
    """
    Sum of max(0, Tmax - 35) -- the MATOPIBA guide's heat-penalty node.

    Degrees of overshoot, not just a count of days, so that a week at 40 C is
    distinguished from a week at 35.5 C.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmax - threshold).clip(lower=0).sum())


# ---------------------------------------------------------------------------
# Root-zone soil moisture (NASA POWER GWETROOT, 0-1) -- MATOPIBA soil-moisture
# work order. Sandy Cerrado soils decouple "rain fell" from "roots have
# water": 100mm can drain through sand in a day, or 30mm can sit in a clay
# patch for a week. Rainfall alone cannot see that difference; GWETROOT can.
# ---------------------------------------------------------------------------


def soil_moisture_mean(daily, months, harvest_year):
    """Mean root-zone wetness over a month/offset window."""
    w = _window(daily, months, harvest_year)
    if w.empty or "soil" not in w or w.soil.isna().all():
        return None
    return float(w.soil.mean())


def soil_stress_days(daily, months, harvest_year, threshold):
    """Days with root-zone wetness below a threshold (wilting-point proxy)."""
    w = _window(daily, months, harvest_year)
    if w.empty or "soil" not in w:
        return None
    return float((w.soil < threshold).sum())


def heat_x_drought_days(daily, months, harvest_year, temp_threshold, soil_threshold):
    """
    Days that are simultaneously hot and dry at the root.

    The guide's central claim for MATOPIBA: a hot day with wet roots or a dry
    day that stays cool both leave the crop's water balance intact: it is the
    conjunction, not either alone, that collapses yield.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or "soil" not in w:
        return None
    return float(((w.soil < soil_threshold) & (w.tmax > temp_threshold)).sum())


def wet_days(daily, months, harvest_year, threshold):
    """Days with root-zone wetness above a threshold (waterlogging proxy)."""
    w = _window(daily, months, harvest_year)
    if w.empty or "soil" not in w:
        return None
    return float((w.soil > threshold).sum())


def soil_moisture_mean_window(daily, start, end):
    """Same as soil_moisture_mean, over an explicit date range (cotton's
    ADD-based flowering window rather than a fixed calendar month)."""
    if start is None or end is None:
        return None
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty or "soil" not in w or w.soil.isna().all():
        return None
    return float(w.soil.mean())


def soil_stress_days_window(daily, start, end, threshold):
    if start is None or end is None:
        return None
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty or "soil" not in w:
        return None
    return float((w.soil < threshold).sum())


def heat_x_drought_days_window(daily, start, end, temp_threshold, soil_threshold):
    if start is None or end is None:
        return None
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty or "soil" not in w:
        return None
    return float(((w.soil < soil_threshold) & (w.tmax > temp_threshold)).sum())
    return float((w.tmax - threshold).clip(lower=0).sum())


def vpd_heat_stress(daily, months, harvest_year, threshold=35.0):
    """
    Stand-in for CWSI where canopy temperature is unavailable (see module
    docstring): mean VPD on days whose Tmax exceeds the threshold, i.e. how
    hard the air was pulling water out of the crop on its worst days.

    Returns None when the window has no weather at all and 0.0 when it has
    weather but no hot days. Collapsing those two into one zero is how a
    season predating the weather record ends up looking like a cool season --
    and, because that fake zero is never missing, how it survives a
    completeness filter that then discards the genuine features.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    hot = w[w.tmax > threshold]
    if hot.empty:
        return 0.0
    return float(hot.vpd_max.mean())


def vpd_peak(daily, months, harvest_year):
    """Highest daily VPD in the window -- 남부지방/옥수수 feature 2."""
    w = _window(daily, months, harvest_year)
    if w.empty or w.vpd_max.isna().all():
        return None
    return float(w.vpd_max.max())


def waterlogging_penalty(daily, months, harvest_year, threshold=300.0):
    """
    max(0, monthly rain - 300 mm), the El Nino harvest penalty from
    남부지방/대두 §3B: past roughly 300 mm in a month the combines cannot
    enter the field and standing beans rot.
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


def harvest_rain(daily, months, harvest_year, threshold=0.0):
    """
    Rain during harvest above a threshold. Cotton uses threshold 0 -- the
    guide is explicit that any rain on open bolls discolours the lint -- while
    wheat uses 200 mm for pre-harvest sprouting.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return max(0.0, float(w.precip.sum()) - threshold)


def effective_water_capacity(daily, months, harvest_year, sand_fraction):
    """
    Rainfall * (1 - sand_fraction) -- MATOPIBA/대두 §3A.

    Discounts rain that fell on sandy soil which cannot hold it. With one
    sand fraction per region this is a constant rescaling of rainfall, so it
    only earns its place in a model spanning regions of differing texture;
    that is how the MATOPIBA config uses it.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float(w.precip.sum()) * (1.0 - sand_fraction)


# ---------------------------------------------------------------------------
# Fusarium head blight weather -- 남부지방/밀 §2A.
# ---------------------------------------------------------------------------


def fhb_features(daily, start, end):
    """
    The three FHB predictors the wheat guide asks for, over the anthesis
    window: days above 85% mean RH, count of two-day rain events, and days
    in the pathogen's 15-30 C reproduction band.

    Del Ponte's published logistic coefficients are not reproduced in the
    guide, so this returns the features rather than an epidemic probability;
    the yield regression weights them itself. That is a weaker claim than the
    guide's P(Epidemic) and is called out in the run report.
    """
    w = daily[(daily.date >= start) & (daily.date <= end)].sort_values("date")
    if w.empty:
        return {}

    rh = w.rh_mean.fillna(0)
    rain = w.precip.fillna(0).values
    tmean = ((w.tmax + w.tmin) / 2.0)

    consecutive = 0
    for i in range(len(rain) - 1):
        if rain[i] > 0.2 and rain[i + 1] > 0.2:
            consecutive += 1

    return {
        "fhb_rh_days": float((rh > 85).sum()),
        "fhb_rain_events": float(consecutive),
        "fhb_warm_days": float(((tmean >= 15) & (tmean <= 30)).sum()),
    }

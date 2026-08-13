"""
The derived-variable formulas from Regions/아르헨티나/*/*_상세분석_및_수식.md.

Everything the Brazilian guides also asked for -- FAO-56 ET0, degree-day
phenology, SPI, threshold counts -- is imported from `brazil.climate` rather
than rewritten, because it is the same equation and one implementation is
easier to trust than two. This module holds only what the Argentine guides ask
for that the Brazilian ones did not:

  - the Doorenbos & Kassam Ky yield-response equation (팜파스/대두 §2A), which
    needs a real ET_act/ET_c ratio and therefore a soil water balance rather
    than the CWD ledger the safrinha guide used;
  - the anthesis Frost Intensity Index (팜파스/밀 §2A);
  - a heat count over a planting-relative window (북부/대두 §2A), as opposed to
    the calendar-month windows the Brazilian guides count over;
  - heat and dryness multiplied together over the flowering window
    (차코/면화 §2A), which needs a daily soil-moisture index;
  - heatwave *duration* (팜파스/대두 §3A), which is a run length, not a count.

Two substitutions, both flagged where they are used:

  - **Soil_Moisture_Index** (차코/면화 §2A) is the relative store of a
    single-layer FAO-56 bucket, not a satellite product. The guide offers
    "토양 수분 지수(또는 위성 기반 수분 지수)", so a modelled index is inside
    what it asks for; it is still a model, not an observation.
  - **WDEF** (팜파스/옥수수 §2B) is DSSAT's internal water-stress factor. DSSAT
    is not runnable here, so the same quantity is taken from the bucket:
    ET_act/ET_c over the silking window, which is what WDEF is defined as
    ("식물 뿌리가 흡수한 실제 물의 양 / 식물이 요구하는 물의 양", 0-1).
    Same definition, cruder soil physics.
"""

import numpy as np
import pandas as pd

from brazil.climate import kc_curve  # noqa: F401  (re-exported for callers)

# FAO-56 crop coefficients as (fraction of season elapsed, Kc). The three
# anchors per crop are the standard initial / mid-season / late values; the
# points between them are the linear development ramp.
KC_SOYBEAN = [(0.00, 0.40), (0.20, 0.40), (0.45, 1.15), (0.75, 1.15), (1.00, 0.50)]
KC_WHEAT = [(0.00, 0.40), (0.20, 0.40), (0.45, 1.15), (0.70, 1.15), (1.00, 0.35)]
KC_COTTON = [(0.00, 0.35), (0.15, 0.35), (0.45, 1.18), (0.75, 1.18), (1.00, 0.60)]
KC_CANE = [(0.00, 0.40), (0.15, 0.40), (0.40, 1.25), (0.75, 1.25), (1.00, 0.75)]

# Plant-available water in the top metre, mm. The Pampas are deep silty loams
# (Argiudolls) and hold appreciably more than the sandy Chaco soils, which is
# most of why the same rainfall shortfall bites harder in the north.
AWC_PAMPAS = 160.0
AWC_CHACO = 110.0
AWC_TUCUMAN = 140.0


def water_balance(daily, planting, season_days, awc, anchors):
    """
    Single-layer FAO-56 water balance over one growing season.

    store_t = clip(store_{t-1} + rain_t - ETa_t, 0, awc)
    ETc_t   = Kc(t) * ET0_t
    ETa_t   = ETc_t * min(1, store_{t-1} / (p * awc))

    The stress coefficient Ks is the FAO-56 linear form: transpiration runs at
    potential while the readily-available fraction lasts and falls off linearly
    once the store is drawn below it. That is the step the CWD ledger in the
    Brazilian safrinha model skips -- it accumulates unmet demand but never
    reduces demand in response to a dry soil -- and it is exactly what makes
    the ET_act/ET_c ratio the Ky equation needs well defined.

    Returns a DataFrame indexed by date with columns etc, eta, store, smi
    (store as a fraction of awc), or None when the season is not covered.
    """
    w = daily[(daily.date >= planting)
              & (daily.date < planting + pd.Timedelta(days=season_days))]
    w = w.sort_values("date")
    if len(w) < season_days * 0.9:
        return None

    # Readily available fraction: the share of the store a crop can take up
    # without closing stomata. 0.5 is the FAO-56 default for row crops.
    raw = 0.5 * awc

    store = awc          # seasons open at field capacity after fallow recharge
    rows = []
    n = max(season_days - 1, 1)
    for i, (_, r) in enumerate(w.iterrows()):
        et0 = float(r.et0) if pd.notna(r.et0) else 0.0
        rain = float(r.precip) if pd.notna(r.precip) else 0.0

        etc = kc_curve(i / n, anchors) * et0
        ks = min(1.0, store / raw) if raw > 0 else 0.0
        eta = etc * ks

        store = min(awc, max(0.0, store + rain - eta))
        rows.append({"date": r.date, "etc": etc, "eta": eta,
                     "store": store, "smi": store / awc})

    out = pd.DataFrame(rows).set_index("date")
    return out


def deficit_ratio(wb, start, end):
    """
    1 - ET_act/ET_c over a window -- the water deficit ratio of
    Doorenbos & Kassam (1979), 팜파스/대두 §2A.

    0 means the crop transpired everything it wanted; 1 means it got nothing.
    """
    if wb is None:
        return None
    w = wb[(wb.index >= start) & (wb.index <= end)]
    if w.empty:
        return None
    etc = float(w.etc.sum())
    if etc <= 0:
        return None
    return 1.0 - float(w.eta.sum()) / etc


def ky_penalty(wb, stages):
    """
    Sum of Ky * (1 - ET_act/ET_c) across growth stages.

    (1 - Ya/Ym) = Ky (1 - ETact/ETc), so this is the predicted *fractional*
    yield loss the guide's equation produces. `stages` is a list of
    (start, end, Ky). The soy guide's whole point is that Ky is 0.2-0.4 in
    vegetative growth and 1.5 at flowering, so a millimetre missing in January
    costs several times what the same millimetre costs in November.
    """
    total, seen = 0.0, False
    for start, end, ky in stages:
        d = deficit_ratio(wb, start, end)
        if d is None:
            continue
        total += ky * d
        seen = True
    return total if seen else None


def wdef(wb, start, end):
    """
    ET_act/ET_c over a window: DSSAT's WDEF, 0-1, 1 being unstressed.

    Complement of `deficit_ratio`, kept under its own name because the corn
    guide names WDEF specifically and reads it in the "higher is better"
    direction.
    """
    d = deficit_ratio(wb, start, end)
    return None if d is None else 1.0 - d


def frost_intensity_index(daily, anthesis, before=5, after=10, threshold=0.0):
    """
    FII = sum over [anthesis - 5, anthesis + 10] of max(0, threshold - Tmin).

    팜파스/밀 §2A. Degrees of frost accumulated across the window, not a count
    of frost days: a night at -4 C sterilises far more florets than a night at
    -0.5 C, and the guide is explicit that averaging Tmin destroys the signal.

    `threshold` exists because the guide's 0 C cannot be applied to this
    weather feed as written. NASA POWER reports a 2 m air temperature on a
    half-degree grid; the frost that kills Argentine wheat is a radiative,
    canopy-level, sub-grid event that happens while the gridded 2 m minimum is
    still several degrees above zero. Measured over the fixed 10-25 October
    anthesis window across the whole POWER record, the two southern wheat
    stations register 1 and 3 sub-zero days in 42 years and the three northern
    ones register none -- against a real frost climatology in which damaging
    spring frosts are a recurring event.

    So `threshold=0` is the guide's equation and returns almost nothing, while
    a raised threshold is a proxy for canopy frost risk rather than frost
    itself. Both are computed and the training run decides. Neither is a
    substitute for station minima (INTA SIGA, SMN), which is what this variable
    actually needs.
    """
    lo = anthesis - pd.Timedelta(days=before)
    hi = anthesis + pd.Timedelta(days=after)
    w = daily[(daily.date >= lo) & (daily.date <= hi)]
    if w.empty:
        return None
    return float((threshold - w.tmin).clip(lower=0).sum())


def heat_days_window(daily, planting, day_from, day_to, threshold=35.0):
    """
    Count of Tmax > threshold between two day counts after planting.

    북부/대두 §2A puts the decisive window at days 50-100 after sowing, which is
    a phenological window and not a calendar one -- the Brazilian guides all
    counted over named months instead.
    """
    lo = planting + pd.Timedelta(days=day_from)
    hi = planting + pd.Timedelta(days=day_to)
    w = daily[(daily.date >= lo) & (daily.date <= hi)]
    if w.empty:
        return None
    return float((w.tmax > threshold).sum())


def heat_excess_window(daily, planting, day_from, day_to, threshold=35.0):
    """Sum of max(0, Tmax - threshold) over a planting-relative window."""
    lo = planting + pd.Timedelta(days=day_from)
    hi = planting + pd.Timedelta(days=day_to)
    w = daily[(daily.date >= lo) & (daily.date <= hi)]
    if w.empty:
        return None
    return float((w.tmax - threshold).clip(lower=0).sum())


def heatwave_duration(daily, months, harvest_year, threshold=35.0):
    """
    Longest run of consecutive days above the threshold -- 팜파스/대두 §3A's
    `Heat_Wave_Duration`.

    A run, not a total. Ten scattered hot days let the crop recover overnight;
    ten consecutive ones do not, and the guide asks for the second quantity.
    """
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y)
                       & (daily.date.dt.month == month))
    w = daily[mask].sort_values("date")
    if w.empty:
        return None

    longest, run = 0, 0
    for hot in (w.tmax > threshold).values:
        run = run + 1 if hot else 0
        longest = max(longest, run)
    return float(longest)


def combined_heat_water_stress(daily, wb, start, end, threshold=32.0):
    """
    Combined_Stress = sum over flowering..peak bloom of
                      max(0, Tmax - 32) * (1 - Soil_Moisture_Index)

    차코/면화 §2A. The multiplication is the whole claim: cotton compensates for
    drought alone by pausing and re-flushing, and compensates for heat alone by
    transpiring, so neither term is linear on its own. Only their product --
    hot air over a soil with nothing left to give -- sheds bolls.

    SMI comes from the bucket balance (see module docstring).
    """
    if start is None or end is None or wb is None:
        return None
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty:
        return None

    smi = wb.smi.reindex(pd.DatetimeIndex(w.date.values))
    if smi.isna().all():
        return None
    dryness = (1.0 - smi.fillna(smi.mean())).clip(lower=0.0, upper=1.0).values
    excess = (w.tmax - threshold).clip(lower=0).values

    return float(np.sum(excess * dryness))


def mean_smi(wb, start, end):
    """Mean soil-moisture index over a window, 0-1. Reported for context."""
    if wb is None or start is None or end is None:
        return None
    w = wb[(wb.index >= start) & (wb.index <= end)]
    return float(w.smi.mean()) if not w.empty else None


# ---------------------------------------------------------------------------
# Root-zone soil wetness -- 0803 작업지시서.
#
# The instruction sheet asks for SMAP sub-surface soil moisture. SMAP starts in
# 2015, which would cut a 42-season record to 11, so the sheet's own fallback is
# taken instead: NASA POWER's GWETROOT, a MERRA-2 land-surface root-zone
# wetness available from 1981 on the same endpoint the rest of this pipeline
# already calls. It is a model field, not an observation -- but so is the
# bucket balance above, and GWETROOT does not inherit this module's guesses
# about available water capacity or Kc curves, so it is an independent second
# opinion on the same quantity.
#
# It is NOT on SMAP's scale, and that matters more than it sounds. GWETROOT is
# a dimensionless wetness *fraction* of plant-available capacity, not a
# volumetric water content. Measured over the whole POWER record:
#
#   Pergamino  p05 0.57  median 0.64  p95 0.73   days < 0.3 in 45 years: 0
#   Saenz Pena p05 0.41  median 0.51  p95 0.69   days < 0.3 in 45 years: 0
#   Tres Arroyos p05 0.44 median 0.51 p95 0.62   days > 0.8 in 45 years: 0
#
# So the sheet's literal thresholds (< 0.3 dry, < 0.2 severe, > 0.8 saturated)
# never fire on this field and would produce three identically-zero features.
# The thresholds below are therefore applied in *percentile* space against each
# point's own day-of-year climatology, which preserves what the sheet means by
# "dry for this place at this time of year" while leaving a variable that
# actually varies.
# ---------------------------------------------------------------------------

# Day-of-year smoothing half-width for the climatology, in days. A single
# calendar day has only ~45 samples across the record; +/-7 days gives ~675 and
# still resolves the seasonal cycle.
CLIMATOLOGY_HALFWIDTH = 7


def soil_wetness_percentile(daily, column="gwetroot"):
    """
    Convert a soil-wetness series to its day-of-year climatological percentile.

    Returns a Series aligned to `daily`, values in [0, 1], where 0.2 means
    "drier than 80% of the historical record for this location on this date".

    Computed against the whole record handed in. At collect time that is the
    full 1981-2025 archive; at forecast time the live pull is shorter, so the
    live percentile is scored against a shorter climatology than training used.
    That is a real inconsistency and the reason `predict.recent_weather` fetches
    from 1981 rather than a two-year lead-in for soil-moisture features.
    """
    if column not in daily.columns:
        return None

    doy = daily.date.dt.dayofyear.values
    vals = daily[column].values

    out = np.full(len(vals), np.nan)
    for d in range(1, 367):
        # Circular window around the day of year
        delta = np.abs(doy - d)
        delta = np.minimum(delta, 365 - delta)
        ref = vals[delta <= CLIMATOLOGY_HALFWIDTH]
        ref = ref[~np.isnan(ref)]
        if len(ref) < 30:
            continue
        target = doy == d
        if not target.any():
            continue
        out[target] = np.searchsorted(np.sort(ref), vals[target]) / len(ref)

    return pd.Series(out, index=daily.index)


def _window_dates(daily, start, end):
    return daily[(daily.date >= start) & (daily.date <= end)]


def mean_soil_wetness(daily, start, end, column="gwetroot"):
    """Mean root-zone wetness over a window, on GWETROOT's own scale."""
    w = _window_dates(daily, start, end)
    if w.empty or column not in w.columns or w[column].isna().all():
        return None
    return float(w[column].mean())


def mean_soil_percentile(daily, start, end):
    """
    Mean day-of-year percentile of root-zone wetness over a window.

    This is the sheet's `summer_sm` / `spring_sm` / `flowering_sm_cotton`,
    expressed so that a value is comparable between the Pampas and the Chaco --
    which the raw field is not, since their medians differ by 0.13.
    """
    w = _window_dates(daily, start, end)
    if w.empty or "sm_pct" not in w.columns or w.sm_pct.isna().all():
        return None
    return float(w.sm_pct.mean())


def autumn_recharge(daily, harvest_year, months=(3, 4, 5)):
    """
    Mean root-zone wetness percentile over the pre-sowing autumn.

    The sheet's single strongest idea for Pampas wheat: the crop is sown in
    June into whatever water the autumn left in the profile, and almost no rain
    falls over winter, so the March-May soil state is a stock the whole season
    then draws down. Spennemann et al. (2015) is the licence for treating it as
    a *persistent* state rather than as lagged rainfall -- Pampas soil-moisture
    anomalies survive months, which is exactly why an autumn number can predict
    an October outcome.
    """
    w = daily[(daily.date.dt.year == harvest_year)
              & (daily.date.dt.month.isin(months))]
    if w.empty or "sm_pct" not in w.columns or w.sm_pct.isna().all():
        return None
    return float(w.sm_pct.mean())


def heat_x_drought(daily, months, harvest_year, tmax_thr=35.0, sm_pct_thr=0.2):
    """
    Count of days that are both hot and dry -- the sheet's `heat_x_drought`.

    (Tmax > 35 C) AND (root-zone wetness below its 20th day-of-year
    percentile). The sheet writes the second condition as `susm < 0.3`; see the
    module comment for why that constant cannot be used on this field.

    The intersection is the point. Heat with water underneath is survivable --
    the crop transpires and cools -- and drought without heat is slow damage.
    Both at once closes stomata during pod or grain set, and that is the
    combination Podestá et al. (1999) and Magrin et al. (2005) trace La Niña
    yield collapses to.
    """
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y)
                       & (daily.date.dt.month == month))
    w = daily[mask]
    if w.empty or "sm_pct" not in w.columns or w.sm_pct.isna().all():
        return None
    return float(((w.tmax > tmax_thr) & (w.sm_pct < sm_pct_thr)).sum())


def dry_spell(daily, start, end, sm_pct_thr=0.2):
    """
    Longest run of consecutive days with root-zone wetness below its 20th
    day-of-year percentile -- the sheet's `dry_spell_cotton`.

    A run rather than a count, for the reason the 차코/면화 guide gives:
    cotton compensates for interrupted drought by pausing and re-flushing, so
    twenty scattered dry days are not twenty consecutive ones.
    """
    w = _window_dates(daily, start, end).sort_values("date")
    if w.empty or "sm_pct" not in w.columns or w.sm_pct.isna().all():
        return None

    longest = run = 0
    for dry in (w.sm_pct < sm_pct_thr).values:
        run = run + 1 if dry else 0
        longest = max(longest, run)
    return float(longest)


def wet_days(daily, months, harvest_year, sm_pct_thr=0.9):
    """
    Days with root-zone wetness above its 90th day-of-year percentile during
    harvest -- the sheet's `harvest_wet_days`.

    An El Niño autumn drowns the Pampas soybean harvest: the beans rot standing
    and the combines cannot enter the field. Distinct from rainfall totals,
    because what stops a combine is a saturated profile that will not drain,
    not the millimetres that fell that week.
    """
    mask = False
    for month, offset in months:
        y = harvest_year + offset
        mask = mask | ((daily.date.dt.year == y)
                       & (daily.date.dt.month == month))
    w = daily[mask]
    if w.empty or "sm_pct" not in w.columns or w.sm_pct.isna().all():
        return None
    return float((w.sm_pct > sm_pct_thr).sum())


def climate_shock_index(oni, iod, oni_thr=-0.5, iod_thr=0.4, shock=1.5):
    """
    IF (ONI < -0.5 AND IOD > 0.4, 1.5, 1.0) -- 팜파스/옥수수 §2A.

    The guide's own switch, kept as the discrete form it writes rather than
    smoothed into an interaction term, so the run can show whether the
    threshold shape earns its place next to the raw indices (which are carried
    alongside it).
    """
    if oni is None or iod is None:
        return None
    return shock if (oni < oni_thr and iod > iod_thr) else 1.0

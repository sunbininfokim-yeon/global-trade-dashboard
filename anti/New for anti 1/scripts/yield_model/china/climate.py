"""
Derived variables the China guides ask for and the Brazil set does not have.

The generic machinery -- FAO-56 ET0, Gamma-fitted SPI, threshold counts,
monthly water balance -- is reused from brazil.climate rather than copied.
That module is not Brazil-specific in anything but its docstrings, and a
second 600-line copy would drift.

What is genuinely new here is the shape of the Chinese risks. Brazil's guides
count hot days and dry spells; China's count *compound* events that only
damage the crop when three conditions coincide, or that damage it in
proportion to how long they persist:

    干热风 (dry-hot wind)  Tmax >= 30 AND RH <= 30% AND wind >= 3 m/s, together
    출수기 고온            sum(Tmax - 35) weighted by consecutive run length
    조기 서리              Tmin < 0 weighted by how far the crop is from maturity
    寒露风 (cold-dew wind) Tmin < 22 during late-rice heading
    수발아                 rain inside a fixed window before harvest

None of these reduce to a monthly mean, which is why -- as in Brazil -- every
one is computed per point and only then production-weighted.
"""

import numpy as np
import pandas as pd

# These modules always run as `python3 -m china.x` from scripts/yield_model, so
# the sibling package is importable directly. argentina/predict.py reaches into
# brazil.climate the same way.
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
    waterlogging_penalty,
    harvest_rain,
    monthly_water_deficit,
    crop_water_deficit,
    silking_stress,
    accumulated_degree_days,
    _window,
)


# ---------------------------------------------------------------------------
# 干热风 -- 중부_허난/밀 §2A
# ---------------------------------------------------------------------------


def dry_hot_wind_days(daily, months, harvest_year,
                      tmax_min=30.0, rh_max=30.0, wind_min=3.0):
    """
    Days meeting all three dry-hot-wind conditions at once.

    The guide writes it as a conjunction and means it: 32 C alone is an
    ordinary May day on the North China Plain, and 25% humidity alone is
    ordinary too. It is the combination -- hot, dry and windy together -- that
    strips water out of a filling grain faster than the root can replace it
    and shrivels the kernel within days.

    Requires RH2M and WS2M in the daily frame, which is why the China
    collector keeps both and the Brazil one does not.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or "wind" not in w.columns:
        return None
    hit = ((w.tmax >= tmax_min) & (w.rh_mean <= rh_max) & (w.wind >= wind_min))
    return float(hit.sum())


def dry_hot_wind_severity(daily, months, harvest_year,
                          tmax_min=30.0, rh_max=30.0, wind_min=3.0):
    """
    Degrees of heat overshoot accumulated on dry-hot-wind days only.

    A count treats a 30.1 C event and a 38 C event alike. This weights each
    qualifying day by how far past the threshold it ran, which is the form the
    guide's Σ implies once the condition is met.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or "wind" not in w.columns:
        return None
    hit = ((w.tmax >= tmax_min) & (w.rh_mean <= rh_max) & (w.wind >= wind_min))
    if not hit.any():
        return 0.0
    return float((w[hit].tmax - tmax_min).sum())


# ---------------------------------------------------------------------------
# Heat with persistence -- 남부_장강/쌀 §2A
# ---------------------------------------------------------------------------


def heat_penalty_with_duration(daily, months, harvest_year, threshold=35.0):
    """
    Σ max(0, Tmax - 35) × Duration, the guide's rice heat penalty.

    The guide is explicit that three consecutive days above 35 C hurt more
    than three scattered ones ("3일 이상 지속되면 수확량 감소폭이 비선형적으로
    커지도록"), because sustained heat during anthesis sterilises pollen that
    a single hot afternoon only stresses. Each day's overshoot is therefore
    multiplied by the length of the hot run it belongs to.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    w = w.sort_values("date")

    over = (w.tmax - threshold).clip(lower=0).values
    hot = over > 0
    total, i = 0.0, 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j < len(hot) and hot[j]:
            j += 1
        run = j - i
        total += float(over[i:j].sum()) * run
        i = j
    return total


def max_heat_run(daily, months, harvest_year, threshold=35.0):
    """Longest unbroken run of days above the threshold, in days."""
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    hot = (w.sort_values("date").tmax > threshold).values

    best, run = 0, 0
    for flag in hot:
        run = run + 1 if flag else 0
        best = max(best, run)
    return float(best)


# ---------------------------------------------------------------------------
# Flooding -- 남부_장강/쌀 §2B
# ---------------------------------------------------------------------------


def date_window_rain(daily, harvest_year, start_md, end_md, threshold=0.0):
    """
    Rainfall between two calendar dates, above an optional threshold.

    Month windows are too coarse for pre-harvest sprouting. 허난 §2B puts the
    damaging window at "5월 하순~6월 초" -- the last week of May into the first
    of June -- and a June-only window misses it by days: the 2023 Henan 수발아
    disaster, the event the whole guide is built around, was rain falling
    25-31 May. Scored on a June window that season ranks 30th of 42; on the
    guide's actual window it is what it should be.

    start_md and end_md are (month, day) inside the harvest year.
    """
    start = pd.Timestamp(year=harvest_year, month=start_md[0], day=start_md[1])
    end = pd.Timestamp(year=harvest_year, month=end_md[0], day=end_md[1])
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if w.empty:
        return None
    return max(0.0, float(w.precip.sum()) - threshold)


def max_nday_rain(daily, months, harvest_year, n=7):
    """
    Heaviest n-day rainfall total in the window.

    The guide's flood index is a Sentinel-1 inundation mask, which needs a SAR
    archive this pipeline does not pull. The observable that drives inundation
    is a short, intense burst rather than a wet season: the 1998 and 2020
    Yangtze floods were both multi-day deluges on ground already saturated.
    A rolling n-day maximum captures that where a monthly total does not, and
    is named as the substitute it is.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    daily_sum = (w.sort_values("date")
                 .groupby("date", as_index=False).precip.sum())
    roll = daily_sum.precip.rolling(n, min_periods=n).sum()
    return float(roll.max()) if roll.notna().any() else None


# ---------------------------------------------------------------------------
# Early frost weighted by maturity -- 동북3성/대두_옥수수 §2B
# ---------------------------------------------------------------------------


def frost_penalty_by_maturity(daily, harvest_year, planting_month, planting_day,
                              tbase, gdd_to_maturity, frost_months,
                              threshold=0.0):
    """
    Σ (Tmin < 0) × (1 - maturity fraction), the guide's Frost_Penalty.

    The guide multiplies the frost count by "Crop_Maturity_Stage" because the
    same September frost is a catastrophe on a crop still filling and an
    irrelevance on one already dry. Maturity is tracked here by accumulated
    growing degree days from planting rather than by calendar date, so a cold
    summer -- which delays maturity and *raises* frost exposure -- is
    represented instead of averaged away. That coupling is the whole mechanism
    behind Northeast China's bad corn years.

    Returns the penalty in "immature frost days": 0 when every frost fell on a
    finished crop, rising toward the raw frost count as the crop is caught
    earlier.
    """
    planting = pd.Timestamp(year=harvest_year, month=planting_month,
                            day=planting_day)
    add = accumulated_degree_days(daily, planting, tbase=tbase, horizon=200)
    if add is None or add.empty:
        return None

    w = _window(daily, frost_months, harvest_year)
    if w.empty:
        return None

    add_by_date = pd.Series(add.values, index=pd.to_datetime(add.index))
    penalty = 0.0
    for _, row in w.sort_values("date").iterrows():
        if row.tmin > threshold:
            continue
        gdd = add_by_date.asof(row.date)
        if pd.isna(gdd):
            continue
        maturity = min(1.0, float(gdd) / gdd_to_maturity)
        penalty += (1.0 - maturity)
    return float(penalty)


def gdd_total(daily, harvest_year, planting_month, planting_day, tbase,
              horizon=200):
    """
    Season-total growing degree days from planting.

    Carried alongside the frost penalty because in the Northeast the two are
    the same story read from opposite ends: a short thermal season is what
    leaves the crop standing green when the frost arrives.
    """
    planting = pd.Timestamp(year=harvest_year, month=planting_month,
                            day=planting_day)
    add = accumulated_degree_days(daily, planting, tbase=tbase, horizon=horizon)
    if add is None or add.empty:
        return None
    return float(add.iloc[-1])


# ---------------------------------------------------------------------------
# 寒露风 and 倒春寒 -- 남부_화남 double cropping
# ---------------------------------------------------------------------------


def cold_days(daily, months, harvest_year, tmin_max):
    """
    Days whose Tmin falls below a threshold.

    Two South China risks share this shape and only differ in when and how
    cold. 倒春寒 (late spring cold) kills early-rice seedlings transplanted in
    March; 寒露风 (cold-dew wind) arrives around the October solar term and
    sterilises late rice that is heading. Both are the reason a farmer drops
    the second crop the following year, which is what the guide is really
    trying to measure.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmin < tmin_max).sum())


def typhoon_proxy(daily, months, harvest_year, rain_mm=80.0, wind_ms=6.0):
    """
    Days combining torrential rain with high mean wind.

    A landfalling typhoon is not in any of the feeds this pipeline pulls. Its
    signature at a point is, though: daily rainfall an order of magnitude
    above normal arriving with sustained wind. POWER's WS2M is a 2 m daily
    mean, so the threshold is far below a typhoon's peak gust by construction
    -- this counts days a typhoon passed near, not its intensity.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or "wind" not in w.columns:
        return None
    return float(((w.precip >= rain_mm) & (w.wind >= wind_ms)).sum())


# ---------------------------------------------------------------------------
# Greenhouse light and snow -- 산둥_화북/채소 §2B
# ---------------------------------------------------------------------------


def low_radiation_days(daily, months, harvest_year, threshold=8.0):
    """
    Days whose all-sky shortwave flux falls below a threshold, in MJ/m2/day.

    Protected vegetable production is largely insulated from rain and wind --
    that is the guide's point about why an ordinary climate model fails here.
    What still reaches the crop through the plastic is light, and a long grey
    spell in a Shandong winter stops growth in a greenhouse as surely as
    drought stops it outdoors.
    """
    w = _window(daily, months, harvest_year)
    if w.empty or "rs" not in w.columns:
        return None
    return float((w.rs < threshold).sum())


def radiation_total(daily, months, harvest_year):
    """Total shortwave radiation over the window, MJ/m2."""
    w = _window(daily, months, harvest_year)
    if w.empty or "rs" not in w.columns:
        return None
    return float(w.rs.sum())


def snow_load_proxy(daily, months, harvest_year, tmax_max=2.0):
    """
    Precipitation falling on days cold enough to accumulate as snow.

    The guide's concern is structural: heavy wet snow collapses greenhouse
    frames and takes the crop with the building. Snow depth is not in POWER,
    so this stands in with precipitation on near-freezing days and is named a
    proxy in the config.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float(w[w.tmax <= tmax_max].precip.sum())


# ---------------------------------------------------------------------------
# Winter wheat overwintering
# ---------------------------------------------------------------------------


def winterkill_days(daily, months, harvest_year, threshold=-10.0):
    """
    Days below a hard-freeze threshold during dormancy.

    Huang-Huai-Hai winter wheat is normally cold-hardy enough that this is
    zero, which is exactly why it is worth carrying: the years it is not zero
    are the years it matters, and a feature that is flat in 40 of 45 seasons
    costs the ridge almost nothing.
    """
    w = _window(daily, months, harvest_year)
    if w.empty:
        return None
    return float((w.tmin <= threshold).sum())

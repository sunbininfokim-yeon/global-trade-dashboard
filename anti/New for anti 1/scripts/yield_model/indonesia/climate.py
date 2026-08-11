"""Small, explicit climate feature helpers used by the Indonesia models."""

from datetime import date

import numpy as np
import pandas as pd


WEATHER_COLUMNS = [
    "tmax", "tmin", "tmean", "precip", "rh_mean", "tdew", "solar", "soil"
]


def select_months(daily, harvest_year, months):
    """Select [(month, year offset)] relative to ``harvest_year``."""
    mask = pd.Series(False, index=daily.index)
    for month, offset in months:
        mask |= ((daily.date.dt.year == harvest_year + offset)
                 & (daily.date.dt.month == month))
    return daily[mask]


def mean_value(daily, harvest_year, months, column):
    w = select_months(daily, harvest_year, months)
    return float(w[column].mean()) if not w.empty else np.nan


def sum_value(daily, harvest_year, months, column):
    w = select_months(daily, harvest_year, months)
    return float(w[column].sum()) if not w.empty else np.nan


def edd(daily, harvest_year, months, threshold):
    w = select_months(daily, harvest_year, months)
    return float((w.tmax - threshold).clip(lower=0).sum()) if not w.empty else np.nan


def max_dry_spell(daily, harvest_year, months, rain_threshold=1.0):
    w = select_months(daily, harvest_year, months).sort_values("date")
    longest = run = 0
    for value in w.precip.values:
        run = run + 1 if value < rain_threshold else 0
        longest = max(longest, run)
    return float(longest) if len(w) else np.nan


def wet_days(daily, harvest_year, months, rain_threshold=5.0):
    w = select_months(daily, harvest_year, months)
    return float((w.precip >= rain_threshold).sum()) if not w.empty else np.nan


def fungal_risk_days(daily, harvest_year, months,
                     rain_threshold=5.0, humidity_threshold=85.0):
    """A soft disease-pressure proxy, not an observed disease diagnosis."""
    w = select_months(daily, harvest_year, months)
    if w.empty:
        return np.nan
    return float(((w.precip >= rain_threshold)
                  & (w.rh_mean >= humidity_threshold)).sum())


def wet_season_delay(daily, harvest_year, trigger_mm=30.0):
    """
    Days after 1 November until the first 3-day 30 mm wet spell.

    The search begins on 1 October of the year before harvest and ends on
    31 January. An onset before 1 November has zero delay. This is deliberately
    a simple, reproducible agronomic onset proxy; it is not a claim that one
    national planting date exists in Indonesia.
    """
    start = pd.Timestamp(harvest_year - 1, 10, 1)
    end = pd.Timestamp(harvest_year, 1, 31)
    normal = pd.Timestamp(harvest_year - 1, 11, 1)
    w = daily[(daily.date >= start) & (daily.date <= end)].sort_values("date")
    if len(w) < 3:
        return np.nan
    totals = w.precip.rolling(3).sum()
    hits = w.loc[totals >= trigger_mm, "date"]
    if hits.empty:
        return float((end - normal).days)
    return float(max(0, (hits.iloc[0] - normal).days))


def add_vpd(daily):
    out = daily.copy()
    es = 0.6108 * np.exp(17.27 * out.tmax / (out.tmax + 237.3))
    ea = 0.6108 * np.exp(17.27 * out.tdew / (out.tdew + 237.3))
    out["vpd_max"] = (es - ea).clip(lower=0)
    return out


def trailing_anomalies(frame, columns, window=20, min_history=20):
    """Add leak-free z scores against only the preceding ``window`` seasons."""
    out = frame.sort_values("year").copy()
    for column in columns:
        prior = out[column].shift(1)
        mean = prior.rolling(window, min_periods=min_history).mean()
        std = prior.rolling(window, min_periods=min_history).std(ddof=1)
        out[column + "_anom"] = (out[column] - mean) / std.replace(0, np.nan)
    return out


def day_of_year_climatology(history, end_year, years=20):
    """Daily climatology from complete years preceding ``end_year``."""
    start_year = end_year - years
    h = history[(history.date.dt.year >= start_year)
                & (history.date.dt.year < end_year)].copy()
    h["month_day"] = h.date.dt.strftime("%m-%d")
    return h.groupby("month_day")[WEATHER_COLUMNS].mean()


def fill_calendar(history, target_year, forecast=None):
    """
    Assemble target_year-2 through target_year as climatology -> observation
    -> short-range forecast, in that precedence order.
    """
    start = pd.Timestamp(target_year - 2, 1, 1)
    end = pd.Timestamp(target_year, 12, 31)
    dates = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    climatology = day_of_year_climatology(history, target_year, 20)
    dates["month_day"] = dates.date.dt.strftime("%m-%d")
    dates = dates.join(climatology, on="month_day").drop(columns="month_day")
    dates["source"] = "climatology"

    observed = history[(history.date >= start) & (history.date <= end)]
    if not observed.empty:
        obs = observed.set_index("date")
        mask = dates.date.isin(obs.index)
        for column in WEATHER_COLUMNS:
            dates.loc[mask, column] = dates.loc[mask, "date"].map(obs[column])
        dates.loc[mask, "source"] = "observed"

    if forecast is not None and not forecast.empty:
        fc = forecast.set_index("date")
        mask = dates.date.isin(fc.index) & ~dates.source.eq("observed")
        for column in ["tmax", "tmin", "tmean", "precip", "solar"]:
            if column in fc:
                dates.loc[mask, column] = dates.loc[mask, "date"].map(fc[column])
        dates.loc[mask, "source"] = "forecast"

    # Feb 29 may not exist in the 20-year slice after filtering. Interpolation
    # is safer than treating a missing day as zero rainfall or zero wetness.
    dates[WEATHER_COLUMNS] = dates[WEATHER_COLUMNS].interpolate(limit_direction="both")
    return add_vpd(dates)


def critical_progress(daily, harvest_year, months):
    w = select_months(daily, harvest_year, months)
    if w.empty:
        return {"observed": 0, "forecast": 0, "climatology": 0}, 0.0
    counts = w.source.value_counts().to_dict() if "source" in w else {"observed": len(w)}
    result = {k: int(counts.get(k, 0)) for k in ["observed", "forecast", "climatology"]}
    share = result["observed"] / len(w)
    return result, float(share)


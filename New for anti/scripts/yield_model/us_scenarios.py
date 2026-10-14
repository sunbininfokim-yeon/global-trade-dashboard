"""
Shared pieces of the US in-season scenario engine.

The in-season forecast follows the approach of UNL's Yield Forecasting Center
(Hybrid-Maize run on historical weather): the part of the season that has
already happened is taken as observed, the next ~16 days come from a weather
forecast, and every remaining day is filled from each past year's weather in
turn. Running the model once per past year gives a distribution of outcomes
instead of one number, and that distribution narrows by itself as real
weather replaces the borrowed years.

train_us.py uses these helpers to backtest the engine at fixed dates in the
season; predict_us.py uses them to turn the live scenarios into a forecast.
"""

import math

import numpy as np

# Dates at which the engine is backtested, as (label, months already known).
# Pre-season moisture is treated as known from 1 June; its June share is
# small next to the September-May recharge it mostly measures.
CUTOFFS = [
    ("06-01", ["preseason"]),
    ("06-30", ["preseason", "june"]),
    ("07-31", ["preseason", "june", "july"]),
    ("08-31", ["preseason", "june", "july", "august"]),
]

# Below this backtested skill the number is a reference (trend plus the
# range of past summers), not a forecast. Same bar the dashboard already
# uses for its low-confidence badge.
FORECAST_SKILL = 0.20

MONTHS = ("june", "july", "august")


def feature_month(name):
    """Which part of the season a month-separable feature belongs to."""
    head = name.split("_", 1)[0]
    if head == "preseason" or head in MONTHS:
        return head
    raise ValueError(f"{name} is not month-separable")


def _norm_cdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def mixture_quantiles(centers, sigma, qs):
    """Quantiles of an equal-weight mixture of N(center, sigma).

    Each weather scenario gives one model prediction; the model's own error
    is laid around each of them. Taking quantiles of the mixture keeps any
    skew in the scenarios (a run of hot Augusts drags the low tail further
    than the high one) instead of forcing a symmetric band.
    """
    c = np.asarray(centers, dtype=float)
    if sigma <= 0:
        return [float(np.quantile(c, q)) for q in qs]
    lo, hi = c.min() - 5 * sigma, c.max() + 5 * sigma
    grid = np.linspace(lo, hi, 4001)
    cdf = _norm_cdf((grid[:, None] - c[None, :]) / sigma).mean(axis=1)
    return [float(np.interp(q, cdf, grid)) for q in qs]


def cutoff_doy(label):
    """Day of year for an MM-DD cutoff label (non-leap calendar)."""
    m, d = (int(x) for x in label.split("-"))
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return sum(days[:m - 1]) + d


def skill_at(inseason, doy):
    """Backtested skill for a season observed through day-of-year doy.

    Linear between backtest dates, flat before the first and after the last.
    """
    pts = sorted((cutoff_doy(k), v["skill_vs_trend"])
                 for k, v in inseason["cutoffs"].items())
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return float(np.interp(doy, xs, ys))

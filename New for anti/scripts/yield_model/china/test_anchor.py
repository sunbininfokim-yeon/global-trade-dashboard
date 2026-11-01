"""Offline tests for china/anchor.py."""

import numpy as np
import pandas as pd

from china import anchor as A
from china.regions import BY_KEY


def _series(flatten_from=None):
    years = np.arange(1984, 2026)
    level = 3000 * np.exp(0.02 * (years - 1984))
    if flatten_from:
        stop = 3000 * np.exp(0.02 * (flatten_from - 1984))
        level = np.where(years > flatten_from, stop, level)
    return pd.DataFrame({"year": years, "target": level})


def _model(history, degree=1):
    coef = np.polyfit(history.year, np.log(history.target), degree)
    return {"trend": {"log_poly_coef": coef.tolist(), "degree": degree, "window": None}}


def test_offset_is_mean_recent_residual():
    h = _series()
    m = _model(h)
    assert abs(A.offset(m["trend"]["log_poly_coef"], h)) < 1e-9
    h2 = h.copy()
    h2.loc[h2.index[-3:], "target"] *= 0.97
    assert np.isclose(A.offset(m["trend"]["log_poly_coef"], h2), np.log(0.97))


def test_switches_on_for_a_flattening_series_only():
    cfg = BY_KEY["yangtze_rice"]
    flat = _series(flatten_from=2015)
    on = A.trend_anchor(cfg, _model(flat), flat)
    assert on and on["shift_pct"] < 0          # trend overshoots, shift is down
    rng = np.random.default_rng(1)
    noisy = _series()
    noisy["target"] *= np.exp(rng.normal(0, 0.03, len(noisy)))
    assert A.trend_anchor(cfg, _model(noisy), noisy) is None


def test_backtest_uses_only_earlier_seasons():
    h = _series(flatten_from=2015)
    full = A.backtest(_model(h), h)
    cut = h[h.year <= 2020]
    part = A.backtest(_model(cut), cut, recent=5)
    # the fold for 2020 must not change when later seasons are added
    assert full["n"] - part["n"] == 5

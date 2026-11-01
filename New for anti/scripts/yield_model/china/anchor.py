"""
Re-anchor the China trend to the last few published seasons.

Every China number is a trend extrapolation (no weather model beats the trend,
see README). The fitted log trend, though, runs 2-4% above the USDA series in
each of the last three seasons for most configs: Chinese yields flattened
after ~2018 and a polynomial fitted over 1984- keeps climbing. The published
point inherits that overshoot.

The fix is the standard one for a smoothed series: shift the trend by the mean
log residual of the last K seasons, so it extrapolates from where the series
actually is. K = 3, one value for every config.

The shift goes live for a config only if it also wins out of sample: refit the
trend on earlier seasons only, anchor it the same way, forecast the next
season, and compare with the plain trend over all folds and over the last
RECENT folds. Both must improve, or the plain trend stays.
"""

import numpy as np
import pandas as pd

from . import train as T

K = 3


def offset(coef, history, k=K):
    """Mean log residual of the last k labelled seasons around the trend."""
    h = history.dropna(subset=["target"]).sort_values("year").tail(k)
    if len(h) < k:
        return 0.0
    trend = np.poly1d(coef)
    return float(np.mean(np.log(h.target.values.astype(float)) - trend(h.year.values)))


def backtest(model, history, min_train=T.MIN_TRAIN, k=K, recent=T.RECENT_FOLDS):
    """Forward-chained log errors of the plain and the anchored trend."""
    h = history.dropna(subset=["target"]).sort_values("year")
    if model.get("regime_start"):
        h = h[h.year >= model["regime_start"]]
    years = h.year.values.astype(float)
    values = h.target.values.astype(float)
    degree, window = model["trend"]["degree"], model["trend"]["window"]
    plain, anchored = [], []
    for i, y in enumerate(years):
        prior = years < y
        if prior.sum() < min_train:
            continue
        trend = T.fit_trend(years[prior], values[prior], degree, window)
        e = np.log(values[i]) - trend(y)
        shift = float(np.mean(np.log(values[prior][-k:]) - trend(years[prior][-k:])))
        plain.append(e)
        anchored.append(e - shift)
    plain, anchored = np.array(plain), np.array(anchored)
    if len(plain) < recent:
        return None

    def rmse(a):
        return float(np.sqrt(np.mean(a ** 2)))

    out = {"k": k, "n": int(len(plain)),
           "rmse_plain_pct": rmse(plain) * 100, "rmse_anchored_pct": rmse(anchored) * 100,
           "recent_rmse_plain_pct": rmse(plain[-recent:]) * 100,
           "recent_rmse_anchored_pct": rmse(anchored[-recent:]) * 100}
    out["enabled"] = bool(out["rmse_anchored_pct"] < out["rmse_plain_pct"]
                          and out["recent_rmse_anchored_pct"] < out["recent_rmse_plain_pct"])
    return out


def trend_anchor(cfg, model, history):
    """The live shift for a config, with its backtest, or None when off."""
    test = backtest(model, history, cfg.min_train or T.MIN_TRAIN)
    if not test or not test["enabled"]:
        return None
    shift = offset(model["trend"]["log_poly_coef"], history)
    return {**{k: (round(v, 2) if isinstance(v, float) else v) for k, v in test.items()},
            "log_shift": shift, "shift_pct": round((np.exp(shift) - 1) * 100, 2)}


if __name__ == "__main__":
    import json
    import os
    from .regions import ALL
    for cfg in ALL:
        p = os.path.join(T.MODELS, f"{cfg.key}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            model = json.load(f)
        history = pd.read_csv(os.path.join(T.TRAINING, f"{cfg.key}.csv"))
        t = backtest(model, history, cfg.min_train or T.MIN_TRAIN)
        a = trend_anchor(cfg, model, history)
        print(f"{cfg.key:24} all {t['rmse_plain_pct']:.2f}->{t['rmse_anchored_pct']:.2f}%  "
              f"last{T.RECENT_FOLDS} {t['recent_rmse_plain_pct']:.2f}->{t['recent_rmse_anchored_pct']:.2f}%  "
              f"{'shift %+.1f%%' % a['shift_pct'] if a else 'off'}")

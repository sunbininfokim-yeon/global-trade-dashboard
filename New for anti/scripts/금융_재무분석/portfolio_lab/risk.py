"""Portfolio risk: vol, Sharpe, historical VaR/CVaR, risk contribution."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TRADING_DAYS = 252


def portfolio_returns(rets: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Constant-weight portfolio *log* returns from asset log returns.

    Mixing must happen in simple-return space:
    ``r_p = log1p(sum_i w_i * expm1(r_i))``.
    ``sum_i w_i * r_i`` on logs is wrong (and badly wrong with shorts / fat tails).
    """
    w = weights.reindex(rets.columns).fillna(0.0)
    port_simple = np.expm1(rets).mul(w, axis=1).sum(axis=1)
    return pd.Series(
        np.log1p(port_simple.clip(lower=-0.999999999)),
        index=rets.index,
        dtype="float64",
    )


def ann_vol(r: pd.Series, periods: int = TRADING_DAYS) -> float:
    return float(r.std(ddof=1) * np.sqrt(periods))


def ann_return(r: pd.Series, periods: int = TRADING_DAYS) -> float:
    # Compounded CAGR from log returns: (Π(1+r_s))^(periods/n)-1 = expm1(sum(log)*periods/n).
    # Do not use mean(log)*periods — that is not the UI “수익률” / Sharpe numerator story.
    clean = r.dropna()
    n = len(clean)
    if n == 0:
        return 0.0
    return float(np.expm1(float(clean.sum()) * (periods / n)))


def sharpe(r: pd.Series, rf_ann: float, periods: int = TRADING_DAYS) -> float:
    vol = ann_vol(r, periods)
    if vol <= 1e-12:
        return 0.0
    # Same compounding basis as ann_return, then subtract annual rf.
    return (ann_return(r, periods) - rf_ann) / vol


def hist_var_cvar(r: pd.Series, alpha: float = 0.95) -> tuple[float, float]:
    """Historical VaR/CVaR on *simple* (or already-simple) returns; positive = loss."""
    if r.empty:
        return 0.0, 0.0
    q = float(np.quantile(r.values, 1.0 - alpha))
    var = -q
    tail = r[r <= q]
    cvar = -float(tail.mean()) if len(tail) else var
    return max(var, 0.0), max(cvar, 0.0)


def parametric_var(vol_ann: float, alpha: float = 0.95, horizon_days: int = 1) -> float:
    from math import sqrt

    # approximate z for 95% / 99%
    z = {0.95: 1.6448536269514722, 0.99: 2.3263478740408408}.get(alpha, 1.6448536269514722)
    daily = vol_ann / sqrt(TRADING_DAYS)
    return float(z * daily * sqrt(horizon_days))


def risk_contribution(weights: pd.Series, cov: pd.DataFrame) -> pd.Series:
    w = weights.reindex(cov.index).fillna(0.0).values
    sigma = cov.values
    port_var = float(w @ sigma @ w)
    if port_var <= 0:
        return pd.Series(0.0, index=cov.index)
    mrc = sigma @ w
    rc = w * mrc
    return pd.Series(rc / port_var, index=cov.index)  # fraction of variance


def horizon_simple_returns(price_rets: pd.Series, windows: dict[str, int]) -> dict[str, float | None]:
    """Compound log returns over trailing windows (trading days)."""
    out: dict[str, float | None] = {}
    for name, n in windows.items():
        if len(price_rets) < n:
            out[name] = None
        else:
            out[name] = float(np.expm1(price_rets.iloc[-n:].sum()))
    return out


def portfolio_risk_bundle(
    rets: pd.DataFrame,
    weights: pd.Series,
    cov_short: pd.DataFrame,
    cov_long: pd.DataFrame,
    *,
    rf_ann: float = 0.03,
    total_value: float | None = None,
) -> dict[str, Any]:
    pr = portfolio_returns(rets, weights)
    # short window ~ 1y for hist VaR; long use full sample weekly
    short = pr.iloc[-252:] if len(pr) >= 60 else pr
    weekly = pr.resample("W-FRI").sum().dropna()
    long = weekly.iloc[-260:] if len(weekly) >= 40 else weekly

    # Hist VaR on simple daily/weekly portfolio returns (loss in value space).
    short_simple = pd.Series(np.expm1(short), index=short.index, dtype="float64")
    long_simple = pd.Series(np.expm1(long), index=long.index, dtype="float64")

    var1, cvar1 = hist_var_cvar(short_simple, 0.95)
    var10 = parametric_var(ann_vol(short), 0.95, 10)
    # scale hist 1d to 10d roughly for display alongside
    var10_hist = var1 * np.sqrt(10)

    var_m, cvar_m = hist_var_cvar(long_simple, 0.95)

    vol_s = ann_vol(short)
    vol_l = ann_vol(long, periods=52) if len(long) > 3 else ann_vol(pr)

    rc = risk_contribution(weights, cov_short)

    def money(x: float) -> float | None:
        if total_value is None:
            return None
        return float(total_value * x)

    return {
        "performance": {
            "ann_return_short": ann_return(short),
            "ann_return_long": ann_return(long, periods=52) if len(long) > 3 else ann_return(pr),
            "ann_volatility_short": vol_s,
            "ann_volatility_long": vol_l,
            "sharpe_short": sharpe(short, rf_ann),
            "sharpe_long": sharpe(long, rf_ann, periods=52) if len(long) > 3 else sharpe(pr, rf_ann),
            "horizon_returns": horizon_simple_returns(
                pr,
                {"1M": 21, "3M": 63, "1Y": 252},
            ),
            "risk_free_rate_ann": rf_ann,
        },
        "risk": {
            "short": {
                "method": "historical_1d + parametric_10d",
                "lookback": f"{len(short)}d",
                "var_1d_95": var1,
                "cvar_1d_95": cvar1,
                "var_10d_95": var10,
                "var_10d_95_hist_scaled": float(var10_hist),
                "var_1d_95_krw": money(var1),
                "var_10d_95_krw": money(var10),
            },
            "long": {
                "method": "historical_weekly",
                "lookback": f"{len(long)}w",
                "var_1m_95": var_m,
                "cvar_1m_95": cvar_m,
                "var_1m_95_krw": money(var_m),
            },
        },
        "risk_contribution": rc.sort_values(ascending=False).to_dict(),
    }

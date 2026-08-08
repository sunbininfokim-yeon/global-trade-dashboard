"""Portfolio risk / diversification engine (Sharpe, HHI, correlation)."""

from __future__ import annotations

import math
from typing import Any


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float], *, sample: bool = True) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    denom = len(xs) - 1 if sample else len(xs)
    var = sum((x - m) ** 2 for x in xs) / denom
    return math.sqrt(var)


def align_returns(series: dict[str, list[float]]) -> dict[str, list[float]]:
    """Truncate all series to the common length (tail-aligned)."""
    if not series:
        return {}
    n = min(len(v) for v in series.values())
    return {k: v[-n:] for k, v in series.items()}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    pos = {k: max(float(v), 0.0) for k, v in weights.items()}
    s = sum(pos.values())
    if s <= 0:
        raise ValueError("weights must sum to > 0")
    return {k: v / s for k, v in pos.items()}


def herfindahl(weights: dict[str, float]) -> dict[str, float]:
    w = normalize_weights(weights)
    hhi = sum(v * v for v in w.values())
    effective_n = (1.0 / hhi) if hhi > 0 else 0.0
    return {
        "hhi": round(hhi, 6),
        "effective_n": round(effective_n, 4),
        "n_names": len(w),
        "max_weight": round(max(w.values()), 6),
    }


def covariance_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    keys = list(returns.keys())
    aligned = align_returns(returns)
    out: dict[str, dict[str, float]] = {a: {} for a in keys}
    for i, a in enumerate(keys):
        for b in keys[i:]:
            xa, xb = aligned[a], aligned[b]
            ma, mb = _mean(xa), _mean(xb)
            n = len(xa)
            if n < 2:
                cov = 0.0
            else:
                cov = sum((xa[t] - ma) * (xb[t] - mb) for t in range(n)) / (n - 1)
            out[a][b] = cov
            out[b][a] = cov
    return out


def correlation_matrix(returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    cov = covariance_matrix(returns)
    keys = list(returns.keys())
    aligned = align_returns(returns)
    sig = {k: _std(aligned[k]) for k in keys}
    out: dict[str, dict[str, float]] = {a: {} for a in keys}
    for a in keys:
        for b in keys:
            denom = sig[a] * sig[b]
            out[a][b] = 0.0 if denom == 0 else round(cov[a][b] / denom, 6)
    return out


def portfolio_returns(weights: dict[str, float], returns: dict[str, list[float]]) -> list[float]:
    w = normalize_weights(weights)
    aligned = align_returns({k: returns[k] for k in w if k in returns})
    missing = [k for k in w if k not in aligned]
    if missing:
        raise ValueError(f"missing return series: {missing}")
    n = len(next(iter(aligned.values())))
    out = []
    for t in range(n):
        out.append(sum(w[k] * aligned[k][t] for k in w))
    return out


def sharpe_ratio(
    port_rets: list[float],
    *,
    risk_free_per_period: float = 0.0,
    periods_per_year: float = 252.0,
) -> dict[str, float]:
    excess = [r - risk_free_per_period for r in port_rets]
    mu = _mean(excess)
    sig = _std(excess)
    if sig == 0:
        sharpe = 0.0
    else:
        sharpe = (mu / sig) * math.sqrt(periods_per_year)
    return {
        "sharpe_annualized": round(sharpe, 4),
        "mean_excess_per_period": round(mu, 8),
        "vol_per_period": round(sig, 8),
        "vol_annualized": round(sig * math.sqrt(periods_per_year), 6),
        "n_periods": len(port_rets),
    }


def average_correlation(corr: dict[str, dict[str, float]]) -> float | None:
    keys = list(corr.keys())
    if len(keys) < 2:
        return None
    vals = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            vals.append(corr[a][b])
    return None if not vals else round(_mean(vals), 6)


def diversification_score(
    *,
    effective_n: float,
    n_names: int,
    avg_corr: float | None,
) -> dict[str, Any]:
    """0–100 heuristic: more effective names + lower avg corr → higher score."""
    if n_names <= 0:
        return {"score": 0, "band": "none", "note_ko": "보유 종목 없음"}
    name_component = min(effective_n / max(n_names, 1), 1.0) * 60.0
    if avg_corr is None:
        corr_component = 20.0
    else:
        # corr 1 → 0 points, corr 0 → 40 points
        corr_component = max(0.0, min(40.0, (1.0 - avg_corr) * 40.0))
    score = round(name_component + corr_component, 1)
    if score >= 70:
        band = "well_diversified"
        note = "비중이 고르고 상관도 상대적으로 낮습니다."
    elif score >= 40:
        band = "moderate"
        note = "분산은 있으나 편중 또는 동조화 여지가 있습니다."
    else:
        band = "concentrated"
        note = "소수 종목·높은 상관으로 분산 효과가 제한적입니다."
    return {"score": score, "band": band, "note_ko": note}


def analyze_portfolio(
    holdings: list[dict[str, Any]],
    returns: dict[str, list[float]],
    *,
    risk_free_annual: float = 0.03,
    periods_per_year: float = 252.0,
    industry_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    holdings: [{ticker, weight, industry_kit?}]
    returns: {ticker: [periodic simple returns]}
    """
    weights = {h["ticker"]: float(h["weight"]) for h in holdings}
    w = normalize_weights(weights)
    hhi = herfindahl(w)
    aligned = align_returns({k: returns[k] for k in w if k in returns})
    corr = correlation_matrix(aligned)
    avg_corr = average_correlation(corr)
    port = portfolio_returns(w, aligned)
    rf_period = risk_free_annual / periods_per_year
    sharpe = sharpe_ratio(port, risk_free_per_period=rf_period, periods_per_year=periods_per_year)
    div = diversification_score(
        effective_n=hhi["effective_n"],
        n_names=hhi["n_names"],
        avg_corr=avg_corr,
    )

    # industry concentration if provided on holdings
    ind_w: dict[str, float] = {}
    for h in holdings:
        kit = h.get("industry_kit") or "unknown"
        ind_w[kit] = ind_w.get(kit, 0.0) + w[h["ticker"]]
    if industry_weights:
        ind_w = normalize_weights(industry_weights)
    ind_hhi = herfindahl(ind_w) if ind_w else None

    return {
        "schema_version": "portfolio-risk-v1",
        "weights": {k: round(v, 6) for k, v in w.items()},
        "concentration": hhi,
        "industry_concentration": ind_hhi,
        "industry_weights": {k: round(v, 6) for k, v in ind_w.items()} if ind_w else {},
        "avg_pairwise_correlation": avg_corr,
        "correlation": corr,
        "sharpe": sharpe,
        "diversification": div,
        "risk_free_annual": risk_free_annual,
        "disclaimer_ko": "과거 수익률 기반 통계이며 미래 수익·투자 권유가 아닙니다.",
    }

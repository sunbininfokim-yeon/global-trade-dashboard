"""Leverage ETF rebalancing and concentration formulas (brief §4)."""

from __future__ import annotations

from typing import Any, Iterable


def rebalance_notional(aum: float, leverage: float, r: float) -> float:
    """TR for one product: AUM × (L² − L) × R.

    Sign of return follows R; magnitude uses |R| only if caller passes signed R
    and wants signed flow. Convention: positive TR means buy pressure when R>0
    for L>1; for L=-2, (L²-L)=6 so unit AUM impact is larger.
    """
    l = float(leverage)
    return float(aum) * (l * l - l) * float(r)


def total_rebalance(
    products: Iterable[dict[str, Any]],
    *,
    r: float,
    aum_key: str = "aum",
    L_key: str = "L",
) -> dict[str, float]:
    """Sum TR across products. Long and inverse are each computed then summed
    (do not net AUMs first).
    """
    long_tr = 0.0
    inv_tr = 0.0
    for p in products:
        aum = float(p[aum_key])
        L = float(p[L_key])
        tr = rebalance_notional(aum, L, r)
        if L < 0:
            inv_tr += tr
        else:
            long_tr += tr
    total = long_tr + inv_tr
    return {
        "tr_long": long_tr,
        "tr_inverse": inv_tr,
        "tr_total": total,
        "tr_abs_sum": abs(long_tr) + abs(inv_tr),
    }


def impact_ratio(tr: float, adv_spot: float) -> float | None:
    """IR (%) = TR / ADV_spot × 100."""
    if adv_spot is None or adv_spot <= 0:
        return None
    return abs(float(tr)) / float(adv_spot) * 100.0


def ir_band(ir_pct: float | None, *, low: float = 3.0, high: float = 10.0) -> str | None:
    if ir_pct is None:
        return None
    if ir_pct < low:
        return "low"
    if ir_pct < high:
        return "watch"
    return "high"


def leverage_exposure_pct(
    products: Iterable[dict[str, Any]],
    free_float_mcap: float,
    *,
    aum_key: str = "aum",
    L_key: str = "L",
    beta_key: str = "beta",
) -> float | None:
    """Σ (AUM × |L| × β) / free_float_mcap × 100."""
    if free_float_mcap is None or free_float_mcap <= 0:
        return None
    num = 0.0
    for p in products:
        beta = float(p.get(beta_key, 1.0))
        num += float(p[aum_key]) * abs(float(p[L_key])) * beta
    return num / float(free_float_mcap) * 100.0


def letf_turnover_ratio(letf_trading_value: float, underlying_adv: float) -> float | None:
    """LETF turnover / cash equity ADV (paper: 'exploded' for AI champions)."""
    if underlying_adv is None or underlying_adv <= 0:
        return None
    return float(letf_trading_value) / float(underlying_adv)


def concentration(mcaps: dict[str, float], universe_mcap: float, top_n: int) -> float | None:
    if universe_mcap is None or universe_mcap <= 0:
        return None
    ranked = sorted((float(v) for v in mcaps.values()), reverse=True)
    return sum(ranked[:top_n]) / float(universe_mcap) * 100.0


def conc_named(mcaps: dict[str, float], tickers: list[str], universe_mcap: float) -> float | None:
    if universe_mcap is None or universe_mcap <= 0:
        return None
    s = sum(float(mcaps[t]) for t in tickers if t in mcaps)
    return s / float(universe_mcap) * 100.0


def delta_pct(model: float | None, anchor: float | None) -> float | None:
    if model is None or anchor is None or anchor == 0:
        return None
    return (float(model) - float(anchor)) / abs(float(anchor)) * 100.0

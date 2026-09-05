"""Offline oracle for T25. Prints JSON only; never fetches or writes price data.

Default: deterministic numerical fixtures. --cache PATH: replay the existing
sample/golden using an existing cache (absence is an error, never a skip).
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "New for anti" / "scripts" / "금융_재무분석"
sys.path.insert(0, str(ENGINE))

def deny_network(*args, **kwargs):
    raise RuntimeError("network is disabled in the reference test")

socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network

from portfolio_lab.covariance import sample_cov, ewma_cov, ledoit_wolf_cov, corr_from_cov
from portfolio_lab.allocate import hierarchical_risk_parity, _hierarchical_clusters, _corr_distance
from portfolio_lab.risk import portfolio_risk_bundle, portfolio_returns

def reference(name, rets, weights, nav=1000000, rf=0.03):
    short = ewma_cov(rets.iloc[-252:])
    long = ledoit_wolf_cov(rets)
    bundle = portfolio_risk_bundle(rets, weights, short, long, rf_ann=rf, total_value=nav)
    order, merges, _ = _hierarchical_clusters(_corr_distance(corr_from_cov(long).values))
    return {
        "name": name,
        "input": {"dates": [str(d.date()) for d in rets.index], "logReturns": rets.values.tolist(),
                  "weights": weights.tolist(), "netAssetValue": nav, "riskFreeRateAnn": rf},
        "expected": {"sample_covariance": sample_cov(rets).values.tolist(),
                     "covariance_short": short.values.tolist(), "covariance_long": long.values.tolist(),
                     "shrinkage": long.attrs.get("shrinkage"), "mean_corr": long.attrs.get("mean_corr"),
                     "hrp_weights": hierarchical_risk_parity(long).tolist(),
                     "order": order, "merges": merges,
                     "portfolio_log_returns": portfolio_returns(rets, weights).tolist(),
                     "risk_contribution": [bundle["risk_contribution"][k] for k in rets.columns],
                     "performance": bundle["performance"], "risk": bundle["risk"]},
    }

def synthetic():
    cases = []
    for name, n, t in [("diversified", 4, 320), ("short_credit", 3, 80),
                       ("one_asset", 1, 65), ("near_singular", 3, 55), ("two_observations", 2, 2)]:
        data = [[0.0003 + 0.01 * np.sin(i * 0.37 + j * 0.8) + 0.006 * np.cos(i * (j + 1) * 0.19)
                 for j in range(n)] for i in range(t)]
        if name == "near_singular":
            data = [[r[0], r[0] * 1.000000001, 0.0] for r in data]
        weights = [1 / n] * n if name != "short_credit" else [1.1, -0.25, 0.45]
        rets = pd.DataFrame(data, index=pd.bdate_range("2023-01-02", periods=t))
        cases.append(reference(name, rets, pd.Series(weights), rf=0.0 if name == "one_asset" else 0.03))
    return cases

def cached(cache):
    from portfolio_lab.normalize import normalize_portfolio
    from portfolio_lab.resolve import InstrumentRegistry, resolve_portfolio
    from portfolio_lab.returns import aligned_returns
    sample = json.loads((ENGINE / "samples/user_balanced_portfolio.json").read_text())
    norm = normalize_portfolio(sample)
    positions, unresolved = resolve_portfolio(norm.portfolio, InstrumentRegistry(ENGINE / "instruments/registry.json"),
                                             net_asset_value=norm.net_asset_value_krw)
    if unresolved:
        raise RuntimeError(f"unresolved sample: {unresolved}")
    rets, weights, meta = aligned_returns(positions, cache, base_currency=sample.get("base_currency", "KRW"), cache_only=True)
    if meta.get("errors"):
        raise RuntimeError(f"incomplete cache: {meta['errors']}")
    result = reference("existing_user_balanced_cache", rets, weights, nav=norm.net_asset_value_krw,
                       rf=sample.get("risk_free_rate_ann", 0.03))
    result["cache_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(cache.glob("*.csv"))}
    result["price_sources"] = meta.get("price_sources")
    # Audit old golden provenance without changing the production NAV basis.
    result["legacy_gross_reference"] = reference("legacy_gross_basis", rets, weights / weights.abs().sum(),
                                                  nav=norm.net_asset_value_krw, rf=sample.get("risk_free_rate_ann", 0.03))
    return [result]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    print(json.dumps(cached(args.cache) if args.cache else synthetic(), allow_nan=False))

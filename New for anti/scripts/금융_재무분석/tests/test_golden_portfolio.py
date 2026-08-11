"""Golden-test harness: fixed sample portfolio + price cache → key metrics."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_lab.normalize import normalize_portfolio
from portfolio_lab.prices import load_price_series
from portfolio_lab.report import build_report
from portfolio_lab.resolve import InstrumentRegistry, resolve_portfolio
from portfolio_lab.returns import aligned_returns
from portfolio_lab.structure import load_profile

SAMPLE = ROOT / "samples" / "user_balanced_portfolio.json"
CACHE = ROOT / "cache" / "prices"
GOLDEN = ROOT / "tests" / "golden" / "user_balanced_metrics.json"
REGISTRY = ROOT / "instruments" / "registry.json"
PROFILES = ROOT / "instruments" / "risk_profiles.json"

# abs(a-b) <= max(abs_tol, rel_tol * max(|a|,|b|)); ~1e-3 rel or 0.5pp
ABS_TOL = 0.005
REL_TOL = 1e-3


def _finite(x: float | None) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(float(x))


def _close(a: float, b: float, *, abs_tol: float = ABS_TOL, rel_tol: float = REL_TOL) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b), 1e-12))


class TestGoldenPortfolio(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SAMPLE.is_file():
            raise unittest.SkipTest(f"missing sample portfolio: {SAMPLE}")
        if not CACHE.is_dir() or not any(CACHE.glob("*.csv")):
            raise unittest.SkipTest(
                f"price cache missing or empty at {CACHE}; "
                "run pipeline once without --cache-only, then re-run tests"
            )
        portfolio = json.loads(SAMPLE.read_text(encoding="utf-8"))
        registry = InstrumentRegistry(REGISTRY)
        norm = normalize_portfolio(portfolio)
        portfolio = norm.portfolio
        positions, unresolved = resolve_portfolio(portfolio, registry)
        if not positions:
            raise unittest.SkipTest(f"no positions resolved: {unresolved}")
        try:
            rets, weights, meta = aligned_returns(
                positions,
                CACHE,
                base_currency=str(portfolio.get("base_currency") or "KRW"),
                years=float(portfolio.get("years") or 5.0),
                cache_only=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"cache-only load failed: {exc}") from exc

        rf = float(portfolio.get("risk_free_rate_ann") or 0.03)
        profile_id = str(portfolio.get("risk_profile") or "balanced")
        profile_id, profile = load_profile(PROFILES, profile_id)
        report = build_report(
            portfolio_id=str(portfolio.get("portfolio_id") or SAMPLE.stem),
            base_currency=str(portfolio.get("base_currency") or "KRW"),
            positions=positions,
            rets=rets,
            weights=weights,
            meta=meta,
            rf_ann=rf,
            unresolved=unresolved,
            risk_profile_id=profile_id,
            risk_profile=profile,
            normalize_meta=norm.to_meta(),
        )
        cls.portfolio = portfolio
        cls.positions = positions
        cls.rets = rets
        cls.weights = weights
        cls.meta = meta
        cls.report = report
        cls.perf = report["performance"]

    def test_weights_sum_abs_one(self) -> None:
        self.assertAlmostEqual(float(self.weights.abs().sum()), 1.0, places=6)

    def test_no_nan_in_returns_or_metrics(self) -> None:
        self.assertFalse(bool(self.rets.isna().any().any()))
        for key in ("ann_return_short", "sharpe_short", "ann_volatility_short"):
            self.assertTrue(_finite(self.perf.get(key)), msg=key)
        r1y = (self.perf.get("horizon_returns") or {}).get("1Y")
        self.assertTrue(_finite(r1y), msg="horizon_returns.1Y")

    def test_leverage_uses_simple_times_lf(self) -> None:
        """Spot-check: synthetic 2x path is log1p(lf * simple), not lf * log."""
        lev = (self.meta or {}).get("synthetic_leverage") or {}
        self.assertTrue(lev, "expected synthetic leverage instrument in sample")
        iid, lf = next(iter(lev.items()))
        lf = float(lf)
        self.assertIn(iid, self.rets.columns)
        # Rebuild unlevered log from underlying Yahoo cache (000660.KS for hynix proxy).
        inst = next(p["instrument"] for p in self.positions if p["instrument"]["id"] == iid)
        ysym = inst.get("yahoo")
        self.assertTrue(ysym)
        raw = load_price_series(ysym, CACHE, years=5.0, cache_only=True)
        # Align to portfolio calendar via rets index; base-ccy for KRW listing is local.
        px = raw.reindex(self.rets.index).ffill()
        base_log = np.log(px / px.shift(1)).dropna()
        overlap = base_log.index.intersection(self.rets.index)
        self.assertGreater(len(overlap), 50)
        simple = np.expm1(base_log.loc[overlap])
        expected = np.log1p((lf * simple).clip(lower=-0.999999))
        got = self.rets.loc[overlap, iid]
        # Allow tiny FX/calendar ffill noise; shape must match simple×lf, not log×lf.
        wrong_log_scale = (lf * base_log.loc[overlap]).astype("float64")
        err_ok = float(np.nanmean(np.abs(got - expected)))
        err_bad = float(np.nanmean(np.abs(got - wrong_log_scale)))
        self.assertLess(err_ok, 1e-9)
        self.assertGreater(err_bad, err_ok * 10)

    def test_portfolio_1y_and_sharpe_finite(self) -> None:
        r1y = self.perf["horizon_returns"]["1Y"]
        sharpe = self.perf["sharpe_short"]
        self.assertTrue(_finite(r1y))
        self.assertTrue(_finite(sharpe))
        # Short-window CAGR should match 1Y horizon when lookback is 252d.
        ann = self.perf["ann_return_short"]
        self.assertTrue(_close(float(ann), float(r1y), abs_tol=1e-9, rel_tol=0.0))

    def test_golden_metrics_if_present(self) -> None:
        if not GOLDEN.is_file():
            self.skipTest(f"golden file not present: {GOLDEN}")
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        mapping = {
            "horizon_1y": self.perf["horizon_returns"]["1Y"],
            "sharpe_short": self.perf["sharpe_short"],
            "ann_vol_short": self.perf["ann_volatility_short"],
            "ann_return_short": self.perf["ann_return_short"],
        }
        for key, got in mapping.items():
            if key not in golden:
                continue
            exp = float(golden[key])
            self.assertTrue(
                _finite(got),
                msg=f"{key} not finite",
            )
            self.assertTrue(
                _close(float(got), exp),
                msg=f"{key}: got={got} expected={exp} (tol abs={ABS_TOL} rel={REL_TOL})",
            )


if __name__ == "__main__":
    unittest.main()

"""Portfolio risk unit tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from portfolio_risk.engine import analyze_portfolio, herfindahl, sharpe_ratio


class TestPortfolio(unittest.TestCase):
    def test_hhi_equal_weights(self):
        h = herfindahl({"a": 1, "b": 1, "c": 1, "d": 1})
        self.assertAlmostEqual(h["hhi"], 0.25, places=5)
        self.assertAlmostEqual(h["effective_n"], 4.0, places=5)

    def test_hhi_concentrated(self):
        h = herfindahl({"a": 0.9, "b": 0.1})
        self.assertGreater(h["hhi"], 0.8)
        self.assertLess(h["effective_n"], 1.3)

    def test_analyze_with_fixture(self):
        fixture = ROOT / "tests" / "fixtures" / "returns_sample.json"
        if not fixture.exists():
            import runpy

            runpy.run_path(str(ROOT / "tests" / "make_returns_fixture.py"), run_name="__main__")
        returns = json.loads(fixture.read_text(encoding="utf-8"))
        holdings = [
            {"ticker": "005930.KS", "weight": 0.4, "industry_kit": "electronics"},
            {"ticker": "010140.KS", "weight": 0.2, "industry_kit": "shipbuilding"},
            {"ticker": "011200.KS", "weight": 0.25, "industry_kit": "shipping"},
            {"ticker": "000660.KS", "weight": 0.15, "industry_kit": "electronics"},
        ]
        out = analyze_portfolio(holdings, returns, risk_free_annual=0.03)
        self.assertIn("sharpe_annualized", out["sharpe"])
        self.assertEqual(out["concentration"]["n_names"], 4)
        self.assertIsNotNone(out["avg_pairwise_correlation"])
        self.assertIn(out["diversification"]["band"], {
            "well_diversified",
            "moderate",
            "concentrated",
        })

    def test_zero_vol_sharpe(self):
        s = sharpe_ratio([0.01, 0.01, 0.01], risk_free_per_period=0.01)
        self.assertEqual(s["sharpe_annualized"], 0.0)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for optional AUM residual cash + top-N truncation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_lab.normalize import (  # noqa: E402
    MAX_NAMES,
    PortfolioNormalizeError,
    build_size_guide,
    normalize_portfolio,
    size_bucket_for_aum,
)


class TestNormalizeAum(unittest.TestCase):
    def test_empty_total_uses_sum(self) -> None:
        raw = {
            "positions": [
                {"query": "A", "value": 400},
                {"query": "B", "value": 600},
            ]
        }
        res = normalize_portfolio(raw)
        self.assertTrue(res.total_was_inferred)
        self.assertEqual(res.aum_krw, 1000.0)
        self.assertEqual(res.residual_cash_added, 0.0)
        vals = {p["query"]: p["value"] for p in res.portfolio["positions"]}
        self.assertEqual(vals["A"], 400)
        self.assertEqual(vals["B"], 600)
        self.assertNotIn("원화", vals)

    def test_total_fills_residual_krw_cash(self) -> None:
        raw = {
            "total_value": 1000,
            "positions": [
                {"query": "엔비디아", "value": 700},
            ],
        }
        res = normalize_portfolio(raw)
        self.assertFalse(res.total_was_inferred)
        self.assertEqual(res.aum_krw, 1000.0)
        self.assertEqual(res.residual_cash_added, 300.0)
        vals = {p["query"]: p["value"] for p in res.portfolio["positions"]}
        self.assertEqual(vals["엔비디아"], 700)
        self.assertEqual(vals["원화"], 300)

    def test_residual_merges_existing_cash(self) -> None:
        raw = {
            "aum_krw": 1000,
            "positions": [
                {"query": "원화", "value": 100},
                {"query": "주식", "value": 600},
            ],
        }
        res = normalize_portfolio(raw)
        self.assertEqual(res.residual_cash_added, 300.0)
        vals = {p["query"]: p["value"] for p in res.portfolio["positions"]}
        self.assertEqual(vals["원화"], 400)
        self.assertEqual(len(res.portfolio["positions"]), 2)

    def test_overflow_raises(self) -> None:
        raw = {
            "total_value": 1000,
            "positions": [
                {"query": "A", "value": 700},
                {"query": "B", "value": 500},
            ],
        }
        with self.assertRaises(PortfolioNormalizeError) as ctx:
            normalize_portfolio(raw)
        self.assertIn("exceeds", str(ctx.exception).lower())


class TestTruncate(unittest.TestCase):
    def test_25_positions_keep_20(self) -> None:
        positions = [{"query": f"n{i}", "value": float(i + 1)} for i in range(25)]
        # values 1..25 → top 20 are 6..25 (largest abs)
        res = normalize_portfolio({"positions": positions}, max_names=MAX_NAMES)
        kept = res.portfolio["positions"]
        self.assertEqual(len(kept), 20)
        self.assertEqual(len(res.truncated_positions), 5)
        kept_vals = sorted(float(p["value"]) for p in kept)
        self.assertEqual(kept_vals, [float(i) for i in range(6, 26)])
        drop_vals = sorted(float(t["value"]) for t in res.truncated_positions)
        self.assertEqual(drop_vals, [1.0, 2.0, 3.0, 4.0, 5.0])
        share_sum = sum(t["weight_share"] for t in res.truncated_positions)
        # 1+2+3+4+5 = 15, gross = 25*26/2 = 325
        self.assertAlmostEqual(share_sum, 15.0 / 325.0, places=9)
        self.assertIsNotNone(res.positions_truncated_ko)
        self.assertIsNotNone(res.positions_truncated_en)

    def test_large_cash_survives_if_top_abs(self) -> None:
        positions = [{"query": f"n{i}", "value": 10.0} for i in range(20)]
        positions.append({"query": "원화", "value": 1000.0})
        res = normalize_portfolio({"positions": positions}, max_names=20)
        queries = {p["query"] for p in res.portfolio["positions"]}
        self.assertIn("원화", queries)
        self.assertEqual(len(res.truncated_positions), 1)


class TestSizeGuide(unittest.TestCase):
    def test_bands(self) -> None:
        self.assertEqual(size_bucket_for_aum(1e6)["bucket"], "micro")
        self.assertEqual(size_bucket_for_aum(1e7)["bucket"], "small")
        self.assertEqual(size_bucket_for_aum(5e7)["bucket"], "standard")
        self.assertEqual(size_bucket_for_aum(2e8)["bucket"], "large")
        self.assertEqual(size_bucket_for_aum(6e8)["bucket"], "overload")

    def test_vs_actual(self) -> None:
        g = build_size_guide(5e7, n_names=10)  # standard 8–20
        assert g is not None
        self.assertEqual(g["vs_actual"]["status"], "ok")
        g2 = build_size_guide(5e7, n_names=3)
        assert g2 is not None
        self.assertEqual(g2["vs_actual"]["status"], "too_few")
        g3 = build_size_guide(1e7, n_names=18)  # small max 15
        assert g3 is not None
        self.assertEqual(g3["vs_actual"]["status"], "too_many")


if __name__ == "__main__":
    unittest.main()

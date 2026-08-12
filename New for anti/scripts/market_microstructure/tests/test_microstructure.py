#!/usr/bin/env python3
"""Unit tests for microstructure formulas + snapshot tables."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from market_microstructure.ai_casino_brief import (
    build_ai_casino_brief,
    markdown_ai_casino_brief,
)
from market_microstructure.engine import build_snapshot, markdown_tables
from market_microstructure.formulas import (
    impact_ratio,
    leverage_exposure_pct,
    rebalance_notional,
    total_rebalance,
)
from market_microstructure.krx_client import KRXAuthError, get_krx_api_key


class TestKrxAuth(unittest.TestCase):
    def test_missing_krx_api_raises(self):
        import os

        old = {k: os.environ.pop(k, None) for k in ("KRX_API", "KRX_OPENAPI_KEY")}
        try:
            with self.assertRaises(KRXAuthError):
                get_krx_api_key()
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_reads_krx_api_name(self):
        import os

        old = {k: os.environ.get(k) for k in ("KRX_API", "KRX_OPENAPI_KEY")}
        os.environ.pop("KRX_OPENAPI_KEY", None)
        os.environ["KRX_API"] = "dummy-not-a-real-key"
        try:
            self.assertEqual(get_krx_api_key(), "dummy-not-a-real-key")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestFormulas(unittest.TestCase):
    def test_tr_example_from_brief(self):
        # AUM 1조, L=2, R=-0.05 → TR = 1조 × 2 × 1 × (-0.05) = -500억? 
        # Brief: TR ≈ 1조 × 2 × 1 × 0.05 = 1,000억 (magnitude, sell direction)
        # Formula AUM × (L²-L) × R = 1e12 × (4-2) × (-0.05) = -1e11 = -1,000억
        tr = rebalance_notional(1_000_000_000_000, 2, -0.05)
        self.assertAlmostEqual(tr, -100_000_000_000)

    def test_inverse_impact_larger(self):
        # L=-2 → (L²-L)=6
        tr = rebalance_notional(1_000_000_000_000, -2, -0.05)
        self.assertAlmostEqual(tr, 1e12 * 6 * -0.05)

    def test_ir_bands(self):
        ir = impact_ratio(1_200_000_000_000, 12_000_000_000_000)
        self.assertAlmostEqual(ir, 10.0)

    def test_do_not_net_aum_before_tr(self):
        products = [
            {"aum": 1e12, "L": 2},
            {"aum": 0.2e12, "L": -2},
        ]
        out = total_rebalance(products, r=-0.05)
        # long: 1e12 * 2 * -0.05 = -1e11
        # inv: 0.2e12 * 6 * -0.05 = -6e10
        self.assertAlmostEqual(out["tr_long"], -1e11)
        self.assertAlmostEqual(out["tr_inverse"], -6e10)
        self.assertAlmostEqual(out["tr_abs_sum"], 1.6e11)


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        path = ROOT / "tests/fixtures/demo_day.json"
        self.day = json.loads(path.read_text(encoding="utf-8"))
        self.snap = build_snapshot(self.day)

    def test_schema(self):
        self.assertEqual(self.snap["schema_version"], "market-microstructure-v1")
        self.assertFalse(self.snap["broker_leverage_disclosure"]["available"])
        self.assertIn("concentration", self.snap)
        self.assertEqual(len(self.snap["stocks"]), 2)

    def test_distortion_squeeze_canonical_contract_is_additive(self):
        block = self.snap["distortion_squeeze"]
        self.assertEqual(block["schema_version"], "distortion-squeeze-v1")
        self.assertEqual(block["observed_as_of"], self.snap["as_of"])
        self.assertIn("concentration", block)
        self.assertIn("deposit_credit", block["market"])
        self.assertEqual(len(block["stocks"]), 2)
        self.assertIn("data_limits", block)

    def test_concentration_top2(self):
        # (400+250)/1250 = 52%
        self.assertAlmostEqual(self.snap["concentration"]["conc_top2_samsung_hynix_pct"], 52.0, places=1)

    def test_letf_turnover_hynix(self):
        h = next(s for s in self.snap["stocks"] if s["ticker"] == "000660")
        # 9.8e12 / 12e12
        self.assertAlmostEqual(h["letf_turnover_ratio"], 9.8 / 12.0, places=3)

    def test_paper_aum_calibration_near_26bn(self):
        row = next(r for r in self.snap["paper_calibration"] if r["field"] == "levered_etf_aum_usd")
        self.assertAlmostEqual(row["model_value"], 26e9, delta=1e6)
        self.assertAlmostEqual(row["delta_pct"] or 0.0, 0.0, delta=0.1)

    def test_paper_exposure_2_1_pct(self):
        row = next(
            r
            for r in self.snap["paper_calibration"]
            if r["field"] == "leverage_exposure_pct_aum_over_ff"
        )
        self.assertAlmostEqual(row["model_value"], 2.1, places=2)

    def test_markdown_has_tables(self):
        md = markdown_tables(self.snap)
        self.assertIn("LETF turnover / ADV", md)
        self.assertIn("Foreign vs retail", md)
        self.assertIn("Paper calibration", md)
        self.assertIn("Flow tangle", md)

    def test_flow_tangle_on_demo(self):
        h = next(s for s in self.snap["stocks"] if s["ticker"] == "000660")
        self.assertIn("flow_tangle", h)
        self.assertEqual(h["flow_tangle"]["wag_the_dog_band"], "high")
        self.assertGreater(h["flow_tangle"]["long_aum_share"], 0.5)

    def test_global_stack_from_external(self):
        day = json.loads((ROOT / "tests/fixtures/demo_day.json").read_text(encoding="utf-8"))
        day["external_venues"] = {
            "hk": {
                "notional_exposure_usd_sum": 1_000_000_000,
                "products": [
                    {
                        "ticker": "7709.HK",
                        "name": "CSOP Hynix 2x",
                        "underlying": "000660",
                        "L": 2,
                        "aum_usd": 500_000_000,
                        "trading_value_usd": 100_000_000,
                        "kr_spot_impact": "indirect_swap",
                    }
                ],
            },
            "crypto": {
                "open_interest_notional_usd_sum": 400_000_000,
                "quote_volume_24h_usd_sum": 1_500_000_000,
                "products": [
                    {
                        "ticker": "SKHYNIXUSDT",
                        "underlying": "000660",
                        "open_interest_notional_usd": 400_000_000,
                        "quote_volume_24h_usd": 1_500_000_000,
                        "last_funding_rate": 0.0,
                        "kr_spot_impact": "indirect_synthetic",
                    }
                ],
            },
            "by_underlying_usd": {
                "000660": {"hk_usd": 1_000_000_000, "crypto_usd": 400_000_000},
                "005930": {"hk_usd": 0.0, "crypto_usd": 0.0},
            },
            "disclaimer_ko": "test",
        }
        snap = build_snapshot(day)
        g = snap["global_leverage_stack"]
        self.assertEqual(g["hk_swap_letf_notional_usd"], 1_000_000_000)
        self.assertEqual(g["crypto_perp_oi_notional_usd"], 400_000_000)
        self.assertIn("Global leverage stack", markdown_tables(snap))
        h = next(s for s in snap["stocks"] if s["ticker"] == "000660")
        self.assertAlmostEqual(h["external_vs_spot"]["hk_notional_usd"], 1_000_000_000)

    def test_ai_casino_brief_ranks_hk_largest(self):
        day = json.loads((ROOT / "tests/fixtures/demo_day.json").read_text(encoding="utf-8"))
        day["external_venues"] = {
            "hk": {
                "notional_exposure_usd_sum": 2_000_000_000,
                "products": [
                    {
                        "ticker": "7709.HK",
                        "name": "CSOP Hynix 2x",
                        "underlying": "000660",
                        "L": 2,
                        "structure": "swap",
                        "direction": "long",
                        "aum_usd": 5_000_000_000,
                        "notional_exposure_usd": 10_000_000_000,
                        "trading_value_usd": 100_000_000,
                        "kr_spot_impact": "indirect_swap",
                    }
                ],
            },
            "crypto": {"open_interest_notional_usd_sum": 0, "products": []},
            "by_underlying_usd": {"000660": {"hk_usd": 2e9, "crypto_usd": 0}},
        }
        snap = build_snapshot(day)
        brief = build_ai_casino_brief(snap, day=day)
        self.assertEqual(brief["schema_version"], "ai-casino-brief-v1")
        self.assertEqual(brief["largest_etf"]["ticker"], "7709.HK")
        self.assertIn("Free float", markdown_ai_casino_brief(brief))
        self.assertIsNotNone(brief["free_float_leverage"]["kr_all_levered_etf_aum_over_kospi_ff_pct"])

    def test_letf_name_classify(self):
        from fetch_kr_public_extras import classify_letf_direction, classify_letf_name

        self.assertEqual(classify_letf_name("KODEX SK하이닉스단일종목레버리지"), "single_stock")
        self.assertEqual(classify_letf_name("KODEX 반도체레버리지"), "sector")
        self.assertEqual(classify_letf_name("TIGER 미국나스닥100레버리지(합성)"), "overseas")
        self.assertEqual(classify_letf_name("KODEX 레버리지"), "index")
        self.assertEqual(classify_letf_name("KODEX 곱버스"), "index")
        self.assertEqual(classify_letf_direction("KODEX 곱버스"), "gobus_inverse_2x")
        self.assertEqual(
            classify_letf_direction("KODEX 200선물인버스2X"), "gobus_inverse_2x"
        )
        self.assertEqual(classify_letf_direction("SOL SK하이닉스선물단일종목인버스2X"), "inverse_2x")
        self.assertEqual(classify_letf_direction("KODEX 레버리지"), "long")
        self.assertEqual(classify_letf_direction("KODEX 인버스"), "inverse")

    def test_public_extras_in_snapshot_from_fixture(self):
        day = json.loads((ROOT / "tests/fixtures/demo_day.json").read_text(encoding="utf-8"))
        extras_path = ROOT / "tests/fixtures/public_extras.json"
        if extras_path.exists():
            day["public_extras"] = json.loads(extras_path.read_text(encoding="utf-8"))
            day["flows_kospi_market"] = {
                "scope": "kospi_cash",
                "foreign_net_krw": -1e11,
                "retail_net_krw": 1e11,
                "institution_net_krw": 0,
                "quality": "observed",
                "source": "fixture",
            }
        snap = build_snapshot(day)
        md = markdown_tables(snap)
        if extras_path.exists():
            self.assertIn("Deposit & credit", md)
            self.assertIn("Levered ETF TV by category", md)
            self.assertIn("Short interest", md)


if __name__ == "__main__":
    unittest.main()

"""Offline regression tests for NAV/gross/credit accounting and exchange identification."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from portfolio_lab.normalize import PortfolioNormalizeError, normalize_portfolio  # noqa: E402
from portfolio_lab.resolve import InstrumentRegistry, resolve_portfolio  # noqa: E402
from portfolio_lab.risk import portfolio_returns  # noqa: E402
from portfolio_lab.structure import check_profile  # noqa: E402


REGISTRY = ROOT / "instruments" / "registry.json"


class TestAccounting(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = InstrumentRegistry(REGISTRY)

    def test_credit_funded_long_keeps_130_percent_nav_weight(self) -> None:
        raw = {
            "net_asset_value": 100.0,
            "credit_used_krw": 30.0,
            "positions": [{"query": "삼성전자", "value": 130.0}],
        }
        norm = normalize_portfolio(raw)
        self.assertEqual(norm.net_asset_value_krw, 100.0)
        self.assertEqual(norm.gross_exposure_krw, 130.0)
        self.assertEqual(norm.credit_used_krw, 30.0)

        positions, unresolved = resolve_portfolio(
            norm.portfolio,
            self.registry,
            net_asset_value=norm.net_asset_value_krw,
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(len(positions), 1)
        self.assertAlmostEqual(float(positions[0]["weight"]), 1.30)

        iid = positions[0]["instrument"]["id"]
        rets = pd.DataFrame({iid: [math.log1p(0.01)]})
        got = portfolio_returns(rets, pd.Series({iid: 1.30}))
        self.assertAlmostEqual(float(got.iloc[0]), math.log1p(0.013), places=12)

    def test_short_book_requires_explicit_cash_and_uses_nav_weights(self) -> None:
        raw = {
            "net_asset_value": 100.0,
            "positions": [
                {"query": "삼성전자", "value": 100.0},
                {"query": "엔비디아", "value": 30.0, "side": "short"},
                {"query": "원화", "value": 30.0},
            ],
        }
        norm = normalize_portfolio(raw)
        self.assertEqual(norm.gross_exposure_krw, 160.0)
        self.assertEqual(norm.signed_positions_value_krw, 100.0)
        positions, unresolved = resolve_portfolio(
            norm.portfolio,
            self.registry,
            net_asset_value=norm.net_asset_value_krw,
        )
        self.assertEqual(unresolved, [])
        weights = {p["instrument"]["id"]: float(p["weight"]) for p in positions}
        self.assertAlmostEqual(weights["eq:kr:005930"], 1.0)
        self.assertAlmostEqual(weights["eq:us:NVDA"], -0.3)
        self.assertAlmostEqual(weights["cash:krw"], 0.3)

    def test_short_book_with_unbalanced_ledger_fails_loudly(self) -> None:
        raw = {
            "net_asset_value": 100.0,
            "positions": [
                {"query": "삼성전자", "value": 100.0},
                {"query": "엔비디아", "value": 30.0, "side": "short"},
            ],
        }
        with self.assertRaises(PortfolioNormalizeError) as ctx:
            normalize_portfolio(raw)
        self.assertIn("ledger does not balance", str(ctx.exception))

    def test_foreign_cash_does_not_satisfy_base_cash_profile_band(self) -> None:
        positions = [
            {
                "instrument": {"id": "cash:krw", "name_ko": "원화 현금", "asset_class": "cash", "currency": "KRW"},
                "weight": 0.10,
            },
            {
                "instrument": {
                    "id": "cash:usd",
                    "name_ko": "달러 현금",
                    "asset_class": "cash",
                    "currency": "USD",
                    "fx_as_asset": True,
                },
                "weight": 0.20,
            },
        ]
        weights = pd.Series({"cash:krw": 0.10, "cash:usd": 0.20})
        profile = {
            "cash_min": 0.20,
            "cash_max": 0.50,
            "equity_like_max": 1.0,
            "single_name_max": 1.0,
            "leveraged_max": 1.0,
            "var_10d_budget": 1.0,
        }
        out = check_profile(
            positions,
            weights,
            {"short": {"var_10d_95": 0.0}},
            profile,
            base_currency="KRW",
        )
        self.assertAlmostEqual(out["cash_weight"], 0.10)
        self.assertAlmostEqual(out["foreign_cash_weight"], 0.20)
        self.assertFalse(out["ok"])

    def test_7709_is_actual_hkd_listing_not_hynix_spot_proxy(self) -> None:
        inst = self.registry.resolve_one("7709.HK")
        assert inst is not None
        self.assertEqual(inst.id, "etf:hk:7709")
        self.assertEqual(inst.yahoo, "7709.HK")
        self.assertEqual(inst.currency, "HKD")
        self.assertTrue(inst.leveraged)
        self.assertFalse(inst.synthetic_leverage)
        self.assertFalse(inst.proxy)

    def test_gross_exposure_is_a_warning_not_a_trade_block(self) -> None:
        positions = [
            {
                "instrument": {"id": "eq", "name_ko": "주식", "asset_class": "equity", "currency": "KRW"},
                "weight": 1.30,
            }
        ]
        profile = {
            "cash_min": 0.0,
            "cash_max": 1.0,
            "equity_like_max": 2.0,
            "single_name_max": 2.0,
            "leveraged_max": 1.0,
            "gross_exposure_max": 1.20,
            "var_10d_budget": 1.0,
        }
        out = check_profile(
            positions,
            pd.Series({"eq": 1.30}),
            {"short": {"var_10d_95": 0.0}},
            profile,
        )
        self.assertAlmostEqual(out["gross_exposure_of_nav"], 1.30)
        self.assertFalse(out["ok"])
        self.assertTrue(any("총노출" in message for message in out["breaches_ko"]))


if __name__ == "__main__":
    unittest.main()

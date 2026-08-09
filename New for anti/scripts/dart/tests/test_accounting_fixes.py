"""Accounting definition fixes (Gemini review): FCF, net debt, inventory turnover."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.ma_metrics import compute_ma_metrics
from dart_kfa.metrics import compute_metrics, load_metrics_spec
from dart_kfa.market import market_multiples


class TestFcfSign(unittest.TestCase):
    def test_sec_positive_capex(self):
        m = compute_metrics({"CFO": 111_482e6, "CAPEX": 12_715e6})
        self.assertAlmostEqual(m["fcf"]["value"], 98_767e6, delta=1.0)

    def test_dart_negative_capex(self):
        m = compute_metrics({"CFO": 40e12, "CAPEX": -45e12})
        self.assertAlmostEqual(m["fcf"]["value"], -5e12, delta=1.0)


class TestInventoryTurnover(unittest.TestCase):
    def test_uses_cogs(self):
        m = compute_metrics({"COGS": 220_960e6, "INVENTORIES": 5_718e6, "REVENUE": 416_161e6})
        self.assertAlmostEqual(m["inventory_turnover"]["value"], 220_960 / 5_718, places=2)

    def test_null_without_cogs(self):
        m = compute_metrics({"INVENTORIES": 100.0, "REVENUE": 1000.0})
        self.assertIsNone(m["inventory_turnover"]["value"])
        self.assertIn("COGS", m["inventory_turnover"]["reason"])


class TestNetDebt(unittest.TestCase):
    def test_apple_like_net_cash(self):
        amounts = {
            "CASH": 35_934e6,
            "MARKETABLE_SECURITIES_CURRENT": 18_763e6,
            "MARKETABLE_SECURITIES_NONCURRENT": 77_723e6,
            "LONG_TERM_DEBT_CURRENT": 12_350e6,
            "LONG_TERM_DEBT_NONCURRENT": 78_328e6,
            "COMMERCIAL_PAPER": 7_979e6,
            "OPERATING_INCOME": 133_050e6,
            "DEPRECIATION": 11_698e6,
            "CFO": 111_482e6,
            "CAPEX": 12_715e6,
            "REVENUE": 416_161e6,
        }
        base = compute_metrics(amounts, load_metrics_spec())
        ma = compute_ma_metrics(amounts, base)
        self.assertAlmostEqual(ma["gross_interest_bearing_debt"]["value"], 98_657e6, delta=1)
        self.assertAlmostEqual(ma["cash_and_marketable_securities"]["value"], 132_420e6, delta=1)
        self.assertLess(ma["net_debt"]["value"], 0)  # net cash
        self.assertAlmostEqual(ma["net_debt"]["value"], 98_657e6 - 132_420e6, delta=1)
        self.assertAlmostEqual(ma["fcf"]["value"], 98_767e6, delta=1)


class TestMarketMultiples(unittest.TestCase):
    def test_per(self):
        mm = market_multiples(
            price=200.0,
            shares_out=15e9,
            net_income=112e9,
            equity=74e9,
            ebitda=145e9,
            net_debt=-30e9,
        )
        self.assertAlmostEqual(mm["market_cap"], 3e12, delta=1)
        self.assertAlmostEqual(mm["per"], 3e12 / 112e9, places=2)
        self.assertLess(mm["ev"], mm["market_cap"])  # net cash


if __name__ == "__main__":
    unittest.main()

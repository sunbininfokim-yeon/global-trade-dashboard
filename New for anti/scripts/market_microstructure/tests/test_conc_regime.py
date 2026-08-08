#!/usr/bin/env python3
"""Offline tests for Conc observed point + regime proxy labels."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.conc_history import observed_point_from_listing  # noqa: E402
from market_microstructure.regime_proxy_backtest import (  # noqa: E402
    _channel_for_regimes,
    _proxy_regimes,
)


class TestConcObserved(unittest.TestCase):
    def test_from_fake_listing(self):
        listing = pd.DataFrame(
            {
                "Code": ["005930", "000660", "000270", "005380", "105560"]
                + [f"9{i:04d}" for i in range(10)],
                "Marcap": [400e12, 250e12, 50e12, 40e12, 30e12] + [10e12] * 10,
                "Stocks": [1] * 15,
                "Close": [1] * 15,
            }
        )
        pt = observed_point_from_listing(listing)
        self.assertEqual(pt["quality"], "observed")
        # 650 / (650+50+40+30+100) = 650/870
        self.assertAlmostEqual(pt["conc_top2_samsung_hynix_pct"], 650 / 870 * 100, places=2)


class TestRegimeProxy(unittest.TestCase):
    def test_down_day(self):
        regs = _proxy_regimes(-0.03, 0.02)
        self.assertIn("downside_put_bid", regs)
        self.assertEqual(_channel_for_regimes(regs), "downside")

    def test_vol_up(self):
        regs = _proxy_regimes(0.0, 0.08)
        self.assertIn("vol_long_straddle", regs)
        self.assertEqual(_channel_for_regimes(regs), "vol_up")


if __name__ == "__main__":
    unittest.main()

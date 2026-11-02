#!/usr/bin/env python3
"""Offline tests for Conc observed point + regime proxy labels."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.conc_history import append_observed, clean_history, observed_point_from_listing  # noqa: E402
from market_microstructure.regime_proxy_backtest import (  # noqa: E402
    _channel_for_regimes,
    _proxy_regimes,
)


class TestConcObserved(unittest.TestCase):
    def test_from_fake_listing(self):
        listing = pd.DataFrame(
            {
                "Code": ["005930", "000660", "000270", "005380", "105560"]
                + [f"9{i:04d}" for i in range(100)],
                "Marcap": [400e12, 250e12, 50e12, 40e12, 30e12] + [1e12] * 100,
                "Stocks": [1] * 105,
                "Close": [1] * 105,
            }
        )
        pt = observed_point_from_listing(
            listing, as_of="2026-10-30", latest_price_date="2026-10-30"
        )
        self.assertIsNotNone(pt)
        self.assertEqual(pt["quality"], "observed")
        # 650 / (650+50+40+30+100) = 650/870
        self.assertAlmostEqual(pt["conc_top2_samsung_hynix_pct"], 650 / 870 * 100, places=2)

    def test_rejects_weekend_or_stale_listing(self):
        listing = pd.DataFrame(
            {"Code": ["005930", "000660"] + [f"9{i:04d}" for i in range(100)],
             "Marcap": [1e12] * 102}
        )
        self.assertIsNone(
            observed_point_from_listing(listing, as_of="2026-10-31", latest_price_date="2026-10-30")
        )
        self.assertIsNone(
            observed_point_from_listing(listing, as_of="2026-10-30", latest_price_date="2026-10-29")
        )

    def test_clean_history_drops_hollow_holiday_but_keeps_equal_trading_days(self):
        def point(day, *, n=200, top2=50.0, top5=60.0, top10=70.0, mcap=1e15):
            return {"date": day, "conc_top2_samsung_hynix_pct": top2,
                    "conc_top5_pct": top5, "conc_top10_pct": top10,
                    "universe_mcap_krw": mcap, "n_names": n,
                    "quality": "observed", "source": "test"}

        cleaned = clean_history({"points": [
            point("2026-10-08"), point("2026-10-09"),  # Hangul Day
            point("2026-10-12"), point("2026-10-13"),  # equal real sessions
            point("2026-10-14", n=0, top2=0, top5=0, top10=0, mcap=0),
        ]})
        self.assertEqual([p["date"] for p in cleaned["points"]],
                         ["2026-10-08", "2026-10-12", "2026-10-13"])
        self.assertEqual(cleaned["as_of"], "2026-10-13")
        self.assertEqual(cleaned["stats"]["conc_top2_min"], 50.0)

        prior = cleaned["points"][-1]
        invalid = {**prior, "n_names": 0}
        self.assertEqual(append_observed(cleaned, invalid)["points"], cleaned["points"])
        with patch("market_microstructure.conc_history.observed_point_from_listing", return_value=None):
            self.assertEqual(append_observed(cleaned)["points"], cleaned["points"])

    def test_empty_and_nonfinite_listing_are_not_observed(self):
        for listing in (pd.DataFrame(), pd.DataFrame({"Code": ["005930", "000660"],
                                                    "Marcap": [float("inf"), 1]})):
            self.assertIsNone(observed_point_from_listing(
                listing, as_of="2026-10-30", latest_price_date="2026-10-30"))


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

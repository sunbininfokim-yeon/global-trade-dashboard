#!/usr/bin/env python3
"""Tests for investor × price-level binning (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.investor_price_levels import (  # noqa: E402
    aggregate_by_close_bins,
    aggregate_by_range_bins,
    trend_to_frame,
    _top_zone,
)


class TestInvestorPriceLevels(unittest.TestCase):
    def test_trend_to_frame_parses_signed(self):
        rows = [
            {
                "bizdate": "20260807",
                "closePrice": "1,422,000",
                "individualPureBuyQuant": "+198,922",
                "foreignerPureBuyQuant": "-56,357",
                "organPureBuyQuant": "+32,908",
                "accumulatedTradingVolume": "4,796,937",
            },
            {
                "bizdate": "20260806",
                "closePrice": "1,495,000",
                "individualPureBuyQuant": "+1,337,421",
                "foreignerPureBuyQuant": "-1,101,883",
                "organPureBuyQuant": "-275,040",
                "accumulatedTradingVolume": "5,498,295",
            },
        ]
        df = trend_to_frame(rows)
        self.assertEqual(len(df), 2)
        self.assertEqual(df.loc[pd.Timestamp("2026-08-07"), "retail_net_shares"], 198922)
        self.assertEqual(df.loc[pd.Timestamp("2026-08-06"), "foreign_net_shares"], -1101883)

    def test_close_bins_and_highlight(self):
        idx = pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
        joined = pd.DataFrame(
            {
                "close": [100.0, 110.0, 120.0, 130.0],
                "low": [95.0, 105.0, 115.0, 125.0],
                "high": [105.0, 115.0, 125.0, 135.0],
                "retail_net_shares": [1000, 2000, -500, 100],
                "foreign_net_shares": [-800, -900, 1500, 2000],
                "institution_net_shares": [-200, -1100, -1000, -2100],
            },
            index=idx,
        )
        bins = aggregate_by_close_bins(joined, n_bins=3)
        self.assertEqual(len(bins), 3)
        self.assertEqual(sum(b["n_days"] for b in bins), 4)
        buy_retail = _top_zone(bins, "retail", side="buy")
        buy_foreign = _top_zone(bins, "foreign", side="buy")
        self.assertIsNotNone(buy_retail)
        self.assertIsNotNone(buy_foreign)
        assert buy_retail is not None and buy_foreign is not None
        self.assertGreater(buy_retail["net_shares"], 0)
        self.assertGreater(buy_foreign["net_shares"], 0)

    def test_range_bins_conserves_approx(self):
        idx = pd.to_datetime(["2026-08-01", "2026-08-02"])
        joined = pd.DataFrame(
            {
                "close": [100.0, 120.0],
                "low": [90.0, 110.0],
                "high": [110.0, 130.0],
                "retail_net_shares": [1000, -1000],
                "foreign_net_shares": [0, 0],
                "institution_net_shares": [0, 0],
            },
            index=idx,
        )
        bins = aggregate_by_range_bins(joined, n_bins=4)
        total = sum(b["retail_net_shares"] for b in bins)
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()

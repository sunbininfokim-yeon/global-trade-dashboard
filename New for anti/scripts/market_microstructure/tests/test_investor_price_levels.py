#!/usr/bin/env python3
"""Tests for investor × price-level binning (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.investor_price_levels import (  # noqa: E402
    aggregate_by_close_bins,
    aggregate_by_range_bins,
    default_kospi_universe,
    high_vol_kospi_universe,
    build_ticker_levels,
    trend_to_frame,
    _top_zone,
)


class TestInvestorPriceLevels(unittest.TestCase):
    def test_three_actor_residual_is_preserved_and_krw_is_marked_estimated(self):
        rows = [{"bizdate": day, "closePrice": close,
                 "individualPureBuyQuant": "-100", "foreignerPureBuyQuant": "20",
                 "organPureBuyQuant": "10", "accumulatedTradingVolume": "500"}
                for day, close in [("20260921", "100"), ("20260922", "110")]]
        prices = pd.DataFrame({"open": [100, 110], "high": [101, 111],
                               "low": [99, 109], "close": [100, 110], "volume": [500, 500]},
                              index=pd.to_datetime(["2026-09-21", "2026-09-22"]))
        with patch("market_microstructure.investor_price_levels.fetch_naver_investor_trend", return_value=rows), \
             patch("market_microstructure.investor_price_levels.fetch_ohlc_panel", return_value=prices):
            block = build_ticker_levels("005930", n_bins=2)
        self.assertEqual(block["net_shares_quality"], "observed")
        self.assertEqual(block["net_krw_quality"], "estimated")
        self.assertEqual(block["net_krw_method"], "net_shares_times_close")
        self.assertEqual(block["actor_scope"], ["retail", "foreign", "institution"])
        day = block["days"][0]
        self.assertEqual(sum(day[a + "_net_shares"] for a in block["actor_scope"]), -70)
        self.assertEqual(sum(day[a + "_net_krw"] for a in block["actor_scope"]), -7000)
        self.assertNotIn("other_corp_net_shares", day)

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

    def test_default_kospi_universe_shape(self):
        listing = pd.DataFrame({
            "Code": ["000001", "000002", "000003", "000004", "000005", "000006"],
            "Name": ["보통주1", "보통주2", "보통주3", "보통주4", "보통주5", "우선주우"],
            "Marcap": [10, 30, 20, 40, 50, 100],
        })
        fdr = SimpleNamespace(StockListing=Mock(return_value=listing))
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            uni = default_kospi_universe(top_n=5)
        self.assertEqual(len(uni), 5)
        self.assertEqual(uni[0][0], "000005")
        for code, name in uni:
            self.assertEqual(len(code), 6)
            self.assertFalse(str(name).endswith("우"))

    def test_high_vol_universe_returns_meta(self):
        listing = pd.DataFrame({
            "Code": [f"{i:06d}" for i in range(1, 16)],
            "Name": [f"보통주{i}" for i in range(1, 16)],
            "Marcap": list(range(15, 0, -1)),
        })
        prices = pd.DataFrame({"Close": [100 + i % 4 for i in range(40)]})
        fdr = SimpleNamespace(
            StockListing=Mock(return_value=listing), DataReader=Mock(return_value=prices),
        )
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            hv = high_vol_kospi_universe(top_n=3, pool=15, lookback_days=30)
        self.assertIn("pairs", hv)
        self.assertEqual(hv.get("pool"), 15)
        self.assertLessEqual(len(hv["pairs"]), 3)
        self.assertEqual(hv["quality"], "observed")
        self.assertEqual(hv["scored_n"], 15)
        self.assertTrue(hv["ranks"])


if __name__ == "__main__":
    unittest.main()

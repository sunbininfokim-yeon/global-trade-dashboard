#!/usr/bin/env python3
"""Tests for cross-source US spot assembly (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fetch_us_public import fetch_us_names  # noqa: E402


class TestFetchUsPublic(unittest.TestCase):
    @patch("fetch_us_public.fetch_cboe_options")
    @patch("fetch_us_public.fetch_yahoo_spot_options")
    @patch("fetch_us_public.fetch_cboe_equity_quote")
    @patch("fetch_us_public.fetch_finra_short")
    @patch("fetch_us_public.fetch_vol_indices")
    def test_premarket_gap_uses_the_displayed_cboe_previous_close(
        self,
        vol,
        finra,
        cboe_spot,
        yahoo,
        cboe_options,
    ):
        vol.return_value = {"quality": "observed", "indices": {}}
        finra.return_value = {"quality": "observed"}
        cboe_spot.return_value = {
            "price": 99.0,
            "prev_close": 100.0,
            "day_return": -0.01,
            "quality": "observed",
        }
        yahoo.return_value = {
            "spot": {
                "premarket_price": 101.0,
                # This was calculated with Yahoo's own different denominator
                # and must not survive the Cboe/Yahoo merge.
                "premarket_gap": -0.2,
            },
            "options": {"quality": "missing"},
        }
        cboe_options.return_value = {"quality": "observed"}

        spot = fetch_us_names(["TEST"])["names"][0]["spot"]
        self.assertEqual(spot["prev_close"], 100.0)
        self.assertEqual(spot["premarket_price"], 101.0)
        self.assertEqual(spot["premarket_gap"], 0.01)
        self.assertEqual(spot["premarket_gap_quality"], "partial")


if __name__ == "__main__":
    unittest.main()

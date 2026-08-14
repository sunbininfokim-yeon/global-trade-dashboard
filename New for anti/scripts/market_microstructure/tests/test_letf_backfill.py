#!/usr/bin/env python3
"""Small deterministic checks for the observed-only LETF backfill driver."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backfill_single_stock_letf_history import records_for_day, trading_day_candidates  # noqa: E402


class TestSingleStockLetfBackfill(unittest.TestCase):
    def test_weekends_are_not_candidates(self):
        rows = trading_day_candidates(date(2026, 8, 7), date(2026, 8, 10))
        self.assertEqual(rows, [date(2026, 8, 7), date(2026, 8, 10)])

    def test_reversed_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            trading_day_candidates(date(2026, 8, 11), date(2026, 8, 10))

    def test_backfill_uses_krx_only_day_and_keeps_model_estimate_separate(self):
        fixture = json.loads((ROOT / "tests/fixtures/live_day.json").read_text(encoding="utf-8"))
        with patch("backfill_single_stock_letf_history.build_day_from_krx", return_value=fixture) as fetch:
            rows = records_for_day(date(2026, 8, 13))
        self.assertEqual({row["ticker"] for row in rows}, {"000660", "005930"})
        self.assertTrue(all(row["quality"] == "observed" for row in rows))
        self.assertTrue(all(row["implied_rebalance_quality"] == "estimated" for row in rows))
        self.assertTrue(all(row["implied_rebalance_ir_pct"] is not None for row in rows))
        fetch.assert_called_once_with(bas_dd="20260813", include_naver_flows=False)


if __name__ == "__main__":
    unittest.main()

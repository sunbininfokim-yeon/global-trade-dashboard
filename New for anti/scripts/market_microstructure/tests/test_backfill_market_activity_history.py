#!/usr/bin/env python3
"""Pure tests for KRX market-history backfill transforms (no network)."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backfill_market_activity_history import (  # noqa: E402
    direction_record_from_krx_rows,
    trading_day_candidates,
)


class TestBackfillMarketActivityHistory(unittest.TestCase):
    def test_direction_record_keeps_both_denominators(self):
        stock_rows = [{"ACC_TRDVAL": "1,000"}, {"ACC_TRDVAL": "2,000"}]
        etf_rows = [
            {"ISU_NM": "KODEX 레버리지", "ACC_TRDVAL": "100"},
            {"ISU_NM": "KODEX 인버스", "ACC_TRDVAL": "50"},
            {"ISU_NM": "단일종목 하이닉스 인버스2X", "ACC_TRDVAL": "20"},
            {"ISU_NM": "KODEX 200선물인버스2X", "ACC_TRDVAL": "30"},
        ]
        out = direction_record_from_krx_rows(
            date(2026, 8, 19), stock_rows, etf_rows
        )
        self.assertEqual(out["kospi_cash_tv_krw"], 3000.0)
        self.assertAlmostEqual(
            out["levered_inverse_etf_tv_over_kospi_cash_tv_pct"],
            200.0 / 3000.0 * 100.0,
            places=6,
        )
        self.assertEqual(out["by_direction"]["long"]["trading_value_krw"], 100.0)
        self.assertEqual(out["by_direction"]["long"]["share_of_lev_tv_pct"], 50.0)
        self.assertAlmostEqual(
            out["by_direction"]["long"]["share_of_kospi_tv_pct"],
            100.0 / 3000.0 * 100.0,
            places=6,
        )
        self.assertEqual(out["by_direction"]["inverse_2x"]["trading_value_krw"], 20.0)
        self.assertEqual(
            out["by_direction"]["gobus_inverse_2x"]["trading_value_krw"], 30.0
        )

    def test_candidates_skip_weekend(self):
        self.assertEqual(
            trading_day_candidates(date(2026, 8, 14), date(2026, 8, 17)),
            [date(2026, 8, 14), date(2026, 8, 17)],
        )


if __name__ == "__main__":
    unittest.main()

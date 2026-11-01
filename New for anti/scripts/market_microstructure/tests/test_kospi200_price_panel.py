#!/usr/bin/env python3
"""The price panel keeps workbook rows and refuses an unresolved return overwrite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_kospi200_price_panel import (  # noqa: E402
    audit_stored_returns,
    reconcile_index_gaps,
)


class PricePanelTests(unittest.TestCase):
    def test_gap_fill_keeps_workbook_row_and_leaves_trading_value_missing(self) -> None:
        workbook = {
            "rows": [
                {
                    "date": "2020-02-28",
                    "open": 270.0,
                    "high": 275.0,
                    "low": 260.0,
                    "close": 265.0,
                    "volume_screen": 100.0,
                    "source_span": "2020-02-01_2020-02-28",
                }
            ]
        }
        naver = {
            "2020-02-28": {"open": 270.0, "high": 275.0, "low": 260.0, "close": 265.0, "volume": 100.0},
            "2020-03-19": {"open": 220.0, "high": 230.0, "low": 200.0, "close": 210.0, "volume": 300.0},
        }
        report = reconcile_index_gaps(workbook, naver, collected_at="2026-11-01T08:00:00+00:00")
        self.assertEqual(report["rows_added"], 1)
        self.assertEqual(workbook["rows"][0]["close"], 265.0)
        added = workbook["rows"][1]
        self.assertEqual(added["date"], "2020-03-19")
        self.assertIsNone(added["trading_value_krw"])
        self.assertEqual(added["trading_value_quality"], "missing")
        self.assertEqual(added["source"], "Naver fchart KPI200")
        self.assertEqual(added["provider_published_at"], "unknown")
        self.assertEqual(added["collected_at"], "2026-11-01T08:00:00+00:00")

    def test_overlap_mismatch_does_not_pick_a_source(self) -> None:
        workbook = {
            "rows": [
                {
                    "date": "2020-02-28",
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume_screen": 1.0,
                }
            ]
        }
        naver = {"2020-02-28": {"open": 1.0, "high": 1.0, "low": 1.0, "close": 9.0, "volume": 1.0}}
        with self.assertRaises(ValueError):
            reconcile_index_gaps(workbook, naver, collected_at="2026-11-01T08:00:00+00:00")
        self.assertEqual(workbook["rows"][0]["close"], 1.0)

    def test_sign_flip_stays_unusable_and_history_is_not_rewritten(self) -> None:
        history = {"date": "2026-10-23", "ticker": "005930", "underlying_day_return": 0.0047}
        price = {"tickers": {"005930": {"days": [
            {"date": "2026-10-22", "close": 214500.0},
            {"date": "2026-10-23", "close": 213500.0},
        ]}}}
        naver = {
            "005930": {
                "2026-10-22": {
                    "closePrice": "214,500",
                    "compareToPreviousClosePrice": "0",
                    "fluctuationsRatio": "0.00",
                    "compareToPreviousPrice": {"name": "UNCHANGED"},
                },
                "2026-10-23": {
                    "closePrice": "213,500",
                    "compareToPreviousClosePrice": "-1,000",
                    "fluctuationsRatio": "-0.47",
                    "compareToPreviousPrice": {"name": "FALLING"},
                },
            }
        }
        report = audit_stored_returns(price, [history], naver)
        self.assertFalse(report["usable_as_close_to_close_signal"])
        self.assertFalse(report["overwrite"])
        self.assertEqual(history["underlying_day_return"], 0.0047)
        flip = report["by_ticker"]["005930"]["sign_flips_versus_price_file"][0]
        self.assertEqual(flip["naver_direction"], "FALLING")
        self.assertLess(flip["price_file_close_to_close"], 0)
        self.assertGreater(flip["letf_history_underlying_day_return"], 0)


if __name__ == "__main__":
    unittest.main()

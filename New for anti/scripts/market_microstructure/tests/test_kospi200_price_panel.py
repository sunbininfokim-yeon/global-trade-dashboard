#!/usr/bin/env python3
"""The price panel keeps workbook rows and refuses an unresolved return overwrite."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_kospi200_price_panel import (  # noqa: E402
    CONCLUSION_KO,
    apply_etf_definition,
    audit_stored_returns,
    reconcile_index_gaps,
    return_quality,
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
        again = reconcile_index_gaps(workbook, naver, collected_at="2026-11-02T08:00:00+00:00")
        self.assertEqual(again["rows_added"], 0)
        self.assertEqual(len(workbook["rows"]), 2)
        self.assertEqual(workbook["gap_fill"]["collected_at"], "2026-11-01T08:00:00+00:00")

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

    def test_unchecked_etf_stays_unknown_and_a_second_pass_is_stable(self) -> None:
        doc = {"candidates": [
            {"ticker": "069500", "rows": [{"close": 1}]},
            {"ticker": "105190", "rows": [{"close": 2}]},
        ]}
        apply_etf_definition(doc, collected_at="2026-11-01T08:30:00+00:00")
        first = json.dumps(doc, sort_keys=True)
        apply_etf_definition(doc, collected_at="2026-11-01T08:30:00+00:00")
        self.assertEqual(json.dumps(doc, sort_keys=True), first)
        self.assertEqual(doc["candidates"][0]["price_adjustment"], "backward_cash_distribution")
        self.assertEqual(doc["candidates"][1]["price_adjustment"], "unknown")
        self.assertEqual(doc["candidates"][1]["dividend_treatment"], "unknown")
        self.assertEqual(doc["candidates"][0]["rows"][0]["close"], 1)
        self.assertIn("U_t / (U_{t-1} - D)", doc["adjustment_evidence"]["formula"])
        self.assertIn("두 번", doc["adjustment_evidence"]["double_count_ko"])
        self.assertEqual(doc["candidates"][0]["adjustment_checked"]["ex_dates_fitting_formula"], 12)
        tiger = {"ticker": "102110"}
        apply_etf_definition({"candidates": [tiger]}, collected_at="2026-11-01T08:30:00+00:00")
        self.assertEqual(tiger["adjustment_checked"]["ex_dates_fitting_formula"], 11)
        self.assertEqual(tiger["adjustment_checked"]["not_fit"], ["2026-10-29"])

    def test_return_quality_follows_the_snapshot_pairs(self) -> None:
        reproduced = {("005930", "2026-08-13")}
        self.assertEqual(return_quality("005930", "2026-08-13", reproduced), "observed_krx")
        self.assertEqual(
            return_quality("005930", "2026-05-27", reproduced),
            "naver_candle_match_krx_close_unchecked",
        )
        self.assertEqual(return_quality("005930", "2026-08-10", reproduced), "krx_close_unchecked")

    def test_conclusion_does_not_call_the_krx_based_return_wrong(self) -> None:
        self.assertIn("정의 차이", CONCLUSION_KO)
        self.assertNotIn("신호에 쓰지 않는다", CONCLUSION_KO)


if __name__ == "__main__":
    unittest.main()

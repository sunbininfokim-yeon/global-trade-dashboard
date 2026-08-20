#!/usr/bin/env python3
"""Contract tests for the JSONL files rendered by the derivatives UI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.derivatives_history import (  # noqa: E402
    HistoryValidationError,
    activity_record_from_board,
    append_jsonl,
    direction_record_from_micro,
    stock_records_from_micro,
    validate_activity_record,
    validate_direction_record,
    validate_stock_record,
)
from fetch_kr_derivatives import derivative_day_candidates  # noqa: E402
from backfill_single_stock_letf_history import trading_day_candidates  # noqa: E402


def _board() -> dict:
    return {
        "kr": {
            "as_of": "2026-08-12",
            "kospi200_futures": {
                "quality": "observed",
                "source": "KRX OpenAPI drv/fut_bydd_trd",
                "volume": 100.0,
                "trading_value_krw": 200.0,
            },
            "kospi200_options": {
                "quality": "observed",
                "source": "KRX OpenAPI drv/opt_bydd_trd",
                "call_volume": 20.0,
                "put_volume": 10.0,
                "call_trading_value_krw": 30.0,
                "put_trading_value_krw": 15.0,
                "put_call_volume": 0.5,
                "put_call_trading_value": 0.5,
            },
        }
    }


def _micro() -> dict:
    directions = {
        key: {
            "trading_value_krw": 100.0,
            "share_of_lev_tv_pct": 25.0,
            "share_of_kospi_tv_pct": 1.0,
        }
        for key in ("long", "inverse", "inverse_2x", "gobus_inverse_2x")
    }
    return {
        "as_of": "2026-08-12",
        "market_letf_derivatives_ratios": {
            "quality": "observed",
            "source": "KRX/FDR",
            "levered_inverse_etf_tv_over_kospi_cash_tv_pct": 4.0,
            "by_direction": directions,
        },
        "letf_category_share": {"kospi_cash_tv_krw": 10_000.0},
        "stocks": [
            {
                "ticker": "000660",
                "source": "KRX/FDR",
                "quality": "observed",
                "adv_spot_krw": 1_000.0,
                "letf_trading_value_krw": 100.0,
                "letf_turnover_ratio": 0.1,
                "letf_aum_sum_krw": 500.0,
                "letf_aum_long_krw": 400.0,
                "letf_aum_inverse_krw": 100.0,
                "day_return": -0.05,
                "products": [
                    {
                        "ticker": "A",
                        "name": "A LETF",
                        "L": 2.0,
                        "direction": "long",
                        "aum": 500.0,
                        "aum_source": "INVSTASST_NETASST_TOTAMT",
                        "aum_quality": "observed",
                        "trading_value": 100.0,
                    }
                ],
            },
            {
                "ticker": "005930",
                "source": "KRX/FDR",
                "quality": "observed",
                "spot_trading_value_krw": 2_000.0,
                "letf_trading_value_krw": 50.0,
                "letf_turnover_ratio": 0.025,
                "letf_aum_sum_krw": 300.0,
                "letf_aum_long_krw": 300.0,
                "letf_aum_inverse_krw": 0.0,
                "products": [
                    {"ticker": "B", "name": "B LETF", "aum": None, "trading_value": None}
                ],
            },
        ],
    }


class TestDerivativesHistory(unittest.TestCase):
    def test_snapshot_records_keep_actual_dates_and_fields(self):
        activity = activity_record_from_board(_board())
        direction = direction_record_from_micro(_micro())
        stocks = stock_records_from_micro(_micro())

        self.assertEqual(activity["date"], "2026-08-12")
        self.assertEqual(activity["kospi200_options"]["put_call_volume"], 0.5)
        self.assertEqual(direction["by_direction"]["long"]["share_of_lev_tv_pct"], 25.0)
        self.assertEqual(stocks[0]["spot_trading_value_krw"], 1_000.0)
        self.assertEqual(stocks[0]["underlying_day_return"], -0.05)
        self.assertEqual(stocks[0]["implied_rebalance_krw"], -50.0)
        self.assertEqual(stocks[0]["implied_ir_pct"], 5.0)
        self.assertEqual(stocks[0]["implied_rebalance_quality"], "estimated")
        self.assertEqual(stocks[1]["quality"], "partial")
        self.assertIn("aum_krw", stocks[1]["products"][0])
        self.assertIsNone(stocks[1]["implied_rebalance_krw"])
        self.assertIsNone(stocks[1]["implied_ir_pct"])

    def test_missing_derivatives_source_creates_no_activity_placeholder(self):
        board = _board()
        board["kr"]["kospi200_options"]["quality"] = "missing"
        self.assertIsNone(activity_record_from_board(board))

    def test_append_replaces_only_same_observation_key(self):
        record = activity_record_from_board(_board())
        newer = json.loads(json.dumps(record))
        newer["kospi200_futures"]["volume"] = 999.0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "activity.jsonl"
            append_jsonl(path, [record], validator=validate_activity_record, key_fields=("date",))
            append_jsonl(path, [newer], validator=validate_activity_record, key_fields=("date",))
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kospi200_futures"]["volume"], 999.0)

    def test_invalid_common_field_is_rejected_before_write(self):
        record = activity_record_from_board(_board())
        record.pop("source")
        with self.assertRaises(HistoryValidationError):
            validate_activity_record(record)

    def test_direction_and_stock_validators_accept_contract_records(self):
        validate_direction_record(direction_record_from_micro(_micro()))
        for record in stock_records_from_micro(_micro()):
            validate_stock_record(record)

    def test_derivatives_candidate_days_skip_weekend_without_rewriting_manual_day(self):
        days = derivative_day_candidates(now=datetime(2026, 8, 17, 17, 35), max_lookback=3)
        self.assertEqual(days, ["20260816", "20260815", "20260814"])
        self.assertEqual(derivative_day_candidates("2026-08-13"), ["20260813"])

    def test_single_stock_backfill_only_generates_weekday_candidates(self):
        from datetime import date

        self.assertEqual(
            trading_day_candidates(date(2026, 8, 14), date(2026, 8, 17)),
            [date(2026, 8, 14), date(2026, 8, 17)],
        )


if __name__ == "__main__":
    unittest.main()

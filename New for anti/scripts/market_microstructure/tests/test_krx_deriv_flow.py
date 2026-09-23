#!/usr/bin/env python3
"""Contract tests for build_krx_deriv_flow (KRX 15007 investor-flow history)."""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_krx_deriv_flow import build  # noqa: E402


def flow_row(day: str, product: str, *, foreign=(100, 60), collected="2026-09-01T00:00:00Z",
             quality="observed", net_override=None) -> dict:
    mn = 1_000_000
    buy, sell = foreign
    row = {"date": day, "product": product, "quality": quality, "collected_at": collected}
    for inv, (b, s) in {"foreign": (buy, sell), "institution": (sell, buy),
                        "retail": (10, 10), "other_corp": (5, 5)}.items():
        row[f"{inv}_buy_krw"] = b * mn
        row[f"{inv}_sell_krw"] = s * mn
        row[f"{inv}_net_krw"] = (b - s) * mn
    if net_override is not None:
        row["foreign_net_krw"] = net_override * mn
    row["market_total_buy_krw"] = (buy + sell + 15) * mn
    return row


def write_hive(base: Path, rows: list[dict]) -> None:
    part = base / "year=2026" / "month=09" / "part.jsonl.gz"
    part.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(part, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


class TestKrxDerivFlow(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.norm = self.root / "data" / "normalized"

    def tearDown(self):
        self.td.cleanup()

    def test_columns_in_source_unit_and_latest_collection_wins(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-01", "futures", foreign=(100, 60), collected="2026-09-01T00:00:00Z"),
            # Re-collected: the later row replaces the earlier one.
            flow_row("2026-09-01", "futures", foreign=(120, 60), collected="2026-09-02T00:00:00Z"),
            flow_row("2026-09-01", "options_call", foreign=(7, 9)),
            flow_row("2026-09-01", "options_put", foreign=(3, 1)),
            flow_row("2026-09-02", "futures", foreign=(50, 80)),
        ])
        payload, stats = build(self.root)
        self.assertEqual(payload["dates"], ["2026-09-01", "2026-09-02"])
        fut = payload["flow"]["futures"]
        self.assertEqual(fut["foreign_net"], [60, -30])
        self.assertEqual(fut["institution_net"], [-60, 30])
        self.assertEqual(fut["foreign_buy"], [120, 50])
        # A product KRX did not publish that day is null, never 0.
        self.assertEqual(payload["flow"]["options_call"]["foreign_net"], [-2, None])
        self.assertEqual(stats["missing_product_days"], 2)
        self.assertEqual(payload["as_of"], "2026-09-02")

    def test_inconsistent_net_is_dropped_not_trusted(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-01", "futures", foreign=(100, 60), net_override=999),
        ])
        payload, stats = build(self.root)
        fut = payload["flow"]["futures"]
        self.assertIsNone(fut["foreign_net"][0])
        self.assertIsNone(fut["foreign_buy"][0])
        self.assertEqual(fut["institution_net"][0], -40)
        self.assertEqual(stats["inconsistent_cells"], 1)

    def test_partial_rows_are_listed(self):
        row = flow_row("2026-09-01", "options_call", quality="partial_observed")
        for k in list(row):
            if k.endswith("_krw"):
                row[k] = None
        write_hive(self.norm / "krx_15007_k200_investor", [row])
        payload, _ = build(self.root)
        self.assertEqual(payload["partial_days"]["options_call"], ["2026-09-01"])
        self.assertEqual(payload["flow"]["options_call"]["foreign_net"], [None])

    def test_futures_front_regular_session_only_and_zero_is_blank(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-01", "futures"), flow_row("2026-09-02", "futures"),
        ])
        write_hive(self.norm / "kospi200_futures_oi", [
            {"date": "2026-09-01", "session": "night", "close": 1.0, "open_interest_contracts": 1,
             "expiry_or_contract_month": "202609"},
            {"date": "2026-09-01", "session": "regular", "close": 1100.5, "open_interest_contracts": 130000,
             "volume_contracts": 70000, "expiry_or_contract_month": "202609"},
            {"date": "2026-09-02", "session": "regular", "close": 1101.0, "open_interest_contracts": 0,
             "volume_contracts": 0, "expiry_or_contract_month": "202612"},
        ])
        payload, _ = build(self.root)
        front = payload["futures_front"]
        self.assertEqual(front["close"], [1100.5, 1101.0])
        self.assertEqual(front["open_interest"], [130000, None])
        self.assertEqual(front["contract"], ["202609", "202612"])

    def test_missing_hive_raises(self):
        with self.assertRaises(FileNotFoundError):
            build(self.root)


if __name__ == "__main__":
    unittest.main()

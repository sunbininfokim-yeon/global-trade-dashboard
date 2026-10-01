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

from build_krx_deriv_flow import build, merge_with_previous  # noqa: E402


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

    def test_option_chain_totals_walls_and_expiry_iv(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-09", "futures"), flow_row("2026-09-10", "futures"), flow_row("2026-09-11", "futures"),
        ])
        write_hive(self.norm / "kospi200_futures_oi", [
            {"date": d, "session": "regular", "close": 1100.0, "open_interest_contracts": 1, "expiry_or_contract_month": "202612"}
            for d in ("2026-09-09", "2026-09-10", "2026-09-11")
        ])
        chain = []
        for d, exp in (("2026-09-09", "202609"), ("2026-09-10", "202609"), ("2026-09-11", "202610")):
            for t, strike, oi, iv in (("call", 1100.0, 50, 30.0), ("call", 1150.0, 90, 28.0),
                                      ("put", 1100.0, 40, 32.0), ("put", 1000.0, 70, 40.0),
                                      ("put", 950.0, 0, 200.0)):
                chain.append({"date": d, "session": "regular", "option_type": t, "strike": strike,
                              "open_interest_contracts": oi, "implied_volatility": iv,
                              "expiry_or_contract_month": exp})
            chain.append({"date": d, "session": "night", "option_type": "call", "strike": 1100.0,
                          "open_interest_contracts": 999999, "expiry_or_contract_month": exp})
        write_hive(self.norm / "kospi200_option_oi", chain)
        payload, _ = build(self.root)
        o = payload["option_oi"]
        self.assertEqual(o["call_oi"], [140, 140, 140])  # night session ignored
        self.assertEqual(o["put_oi"], [110, 110, 110])  # zero OI is a blank, not a strike
        self.assertEqual(o["call_wall"], [1150.0] * 3)
        self.assertEqual(o["put_wall"], [1000.0] * 3)
        self.assertEqual(o["atm_strike"], [1100.0] * 3)
        # 09-10 is September's expiry (2nd Thursday, and the front rolls next day).
        self.assertEqual(o["atm_iv"], [31.0, None, 31.0])
        self.assertEqual(o["profile"]["date"], "2026-09-11")

    def test_program_block_has_its_own_axis(self):
        write_hive(self.norm / "krx_15007_k200_investor", [flow_row("2026-09-08", "futures")])
        mn = 1_000_000
        write_hive(self.norm / "kospi_program", [
            {"date": "2026-09-07", "program_type": t, "buy_krw": 10 * mn, "sell_krw": 4 * mn, "net_krw": 6 * mn}
            for t in ("arbitrage", "non_arbitrage", "total")
        ] + [{"date": "2026-09-04", "program_type": "total", "buy_krw": 1 * mn, "sell_krw": 4 * mn, "net_krw": 9 * mn}])
        payload, stats = build(self.root)
        p = payload["program"]
        self.assertEqual(p["dates"], ["2026-09-04", "2026-09-07"])
        self.assertEqual(p["total_net"], [None, 6])  # 1 - 4 != 9: dropped
        self.assertEqual(p["arbitrage_net"], [None, 6])
        self.assertEqual(stats["program_inconsistent"], 1)
        self.assertEqual(payload["last_dates"]["program"], "2026-09-07")
        self.assertEqual(payload["last_dates"]["flow"], "2026-09-08")

    def test_merge_keeps_history_the_source_no_longer_has(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-01", "futures", foreign=(100, 60)),
            flow_row("2026-09-02", "futures", foreign=(50, 80)),
        ])
        old, _ = build(self.root)
        # The source now holds only the last day, re-collected with a new value,
        # plus one new day.
        for part in (self.norm / "krx_15007_k200_investor").rglob("*.gz"):
            part.unlink()
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-02", "futures", foreign=(55, 80)),
            flow_row("2026-09-03", "futures", foreign=(70, 70)),
        ])
        new, _ = build(self.root)
        merged = merge_with_previous(old, new)
        self.assertEqual(merged["dates"], ["2026-09-01", "2026-09-02", "2026-09-03"])
        self.assertEqual(merged["flow"]["futures"]["foreign_net"], [40, -25, 0])
        self.assertEqual(merged["futures_front"]["close"], [None, None, None])
        self.assertEqual(merged["as_of"], "2026-09-03")
        self.assertEqual(merged["last_dates"]["flow"], "2026-09-03")
        # A stalled source (the same build again, nothing new) leaves the
        # published file unchanged, 09-01 included.
        stalled = merge_with_previous(merged, new)
        self.assertEqual(stalled["dates"], merged["dates"])
        self.assertEqual(stalled["flow"]["futures"]["foreign_net"], [40, -25, 0])

    def test_raw_csv_fills_days_the_hive_has_not_caught_up_to(self):
        write_hive(self.norm / "krx_15007_k200_investor", [
            flow_row("2026-09-21", p, foreign=(100, 60)) for p in ("futures", "options_call", "options_put")
        ])
        header = "﻿일자,기관 합계,기타법인,개인,외국인 합계,전체\n"
        for day, foreign_buy in (("2026-09-21", 999), ("2026-09-22", 40)):
            d = self.root / "data" / "raw" / "krx_15007" / day
            d.mkdir(parents=True)
            for p in ("futures", "options_call", "options_put"):
                (d / f"{p}_buy.csv").write_text(header + f"{day},10,1,5,{foreign_buy},{foreign_buy + 16}\n", encoding="utf-8")
                (d / f"{p}_sell.csv").write_text(header + f"{day},4,2,3,25,34\n", encoding="utf-8")
        # A blank cell is no observation, not zero.
        (d / "options_put_sell.csv").write_text(header + "2026-09-22,4,2,,25,34\n", encoding="utf-8")
        payload, stats = build(self.root)
        self.assertEqual(payload["dates"], ["2026-09-21", "2026-09-22"])
        self.assertEqual(stats["raw_csv_rows"], 2)
        fut = payload["flow"]["futures"]
        # The hive keeps 09-21; the raw export only adds 09-22.
        self.assertEqual(fut["foreign_net"], [40, 15])
        self.assertEqual(fut["institution_net"], [-40, 6])
        self.assertEqual(fut["retail_net"][1], 2)
        self.assertEqual(fut["other_corp_net"][1], -1)
        self.assertEqual(fut["market_total_buy"][1], 56)
        self.assertEqual(payload["flow"]["options_put"]["foreign_net"], [40, None])
        self.assertEqual(payload["last_dates"]["flow"], "2026-09-22")

    def test_missing_hive_raises(self):
        with self.assertRaises(FileNotFoundError):
            build(self.root)


if __name__ == "__main__":
    unittest.main()

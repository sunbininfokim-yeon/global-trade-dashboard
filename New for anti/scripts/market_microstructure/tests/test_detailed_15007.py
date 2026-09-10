#!/usr/bin/env python3
"""Contract tests for the authenticated KRX 15007 call/put flow adapter."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fetch_kr_derivatives import build_detailed_15007  # noqa: E402


def write_export(path: Path, rows: list[tuple[str, int, int]]) -> None:
    path.write_text(
        "[15007] 투자자별 거래실적\n"
        "일자,기관 합계,기타법인,개인,외국인 합계,전체\n"
        + "".join(f"{day},0,0,0,{foreign},{total}\n" for day, foreign, total in rows),
        encoding="utf-8",
    )


class TestDetailed15007(unittest.TestCase):
    def test_builds_call_put_gross_flows_in_krw(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            call_buy, call_sell = root / "call_buy.csv", root / "call_sell.csv"
            put_buy, put_sell = root / "put_buy.csv", root / "put_sell.csv"
            write_export(call_buy, [("2026/08/28", 69111, 94530)])
            write_export(call_sell, [("2026/08/28", 63028, 94530)])
            write_export(put_buy, [("2026/08/28", 55285, 97570)])
            write_export(put_sell, [("2026/08/28", 79129, 97570)])
            out = build_detailed_15007(
                option_call_buy=call_buy, option_call_sell=call_sell,
                option_put_buy=put_buy, option_put_sell=put_sell,
            )

        call = out["products"]["options_call"]
        put = out["products"]["options_put"]
        self.assertEqual(call["quality"], "observed")
        self.assertEqual(call["foreign"], {
            "buy_krw": 69_111_000_000,
            "sell_krw": 63_028_000_000,
            "net_krw": 6_083_000_000,
        })
        self.assertEqual(put["foreign"]["net_krw"], -23_844_000_000)
        self.assertEqual(call["market_total"]["net_krw"], 0)
        self.assertEqual(call["series"][0]["conversion_to_krw"], 1_000_000)

    def test_partial_download_does_not_create_zero_or_observed_row(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            call_buy = root / "call_buy.csv"
            write_export(call_buy, [("2026/08/28", 69111, 94530)])
            out = build_detailed_15007(option_call_buy=call_buy)
        call = out["products"]["options_call"]
        self.assertEqual(call["quality"], "partial_observed")
        self.assertEqual(call["foreign"]["net_krw"], None)
        self.assertEqual(call["series"], [])

    def test_same_date_replaces_only_that_observation(self):
        prior = build_detailed_15007()
        prior["products"]["options_call"] = {
            "as_of": "2026-08-27", "source": "old", "quality": "observed",
            "foreign": {"buy_krw": 2, "sell_krw": 1, "net_krw": 1},
            "market_total": {"buy_krw": 2, "sell_krw": 2, "net_krw": 0},
            "series": [{
                "date": "2026-08-27", "source": "old", "quality": "observed",
                "foreign": {"buy_krw": 2, "sell_krw": 1, "net_krw": 1},
                "market_total": {"buy_krw": 2, "sell_krw": 2, "net_krw": 0},
            }],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            buy, sell = root / "buy.csv", root / "sell.csv"
            write_export(buy, [("2026/08/27", 4, 8)])
            write_export(sell, [("2026/08/27", 3, 8)])
            out = build_detailed_15007(option_call_buy=buy, option_call_sell=sell, previous=prior)
        rows = out["products"]["options_call"]["series"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["foreign"]["net_krw"], 1_000_000)


if __name__ == "__main__":
    unittest.main()

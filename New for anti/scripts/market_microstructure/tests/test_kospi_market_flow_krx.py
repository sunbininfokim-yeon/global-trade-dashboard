#!/usr/bin/env python3
"""KOSPI stock-market investor flow: stock-scoped KRX 12008, Naver, carry-forward."""

from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch_kr_public_extras  # noqa: E402
import pandas as pd  # noqa: E402

import market_microstructure.investor_price_levels as ipl  # noqa: E402
from market_microstructure.investor_price_levels import (  # noqa: E402
    build_kospi_index_levels,
    fetch_kospi_market_investor_history,
    load_krx_12008_kospi_flows,
)

EOK = 100_000_000


def row(day: str, retail: float, foreign: float, inst: float, *, collected="2026-09-21T00:00:00Z", broken=None,
        scope="stock") -> dict:
    out = {"date": day, "collected_at": collected, "dataset": "krx_12008_kospi_stock_investor"}
    if scope is not None:
        out["security_scope"] = scope
    for actor, net in (("retail", retail), ("foreign", foreign), ("institution", inst)):
        buy = 50_000 * EOK
        out[f"{actor}_buy_krw"] = buy
        out[f"{actor}_sell_krw"] = buy - net * EOK
        out[f"{actor}_net_krw"] = net * EOK
    if broken:
        out[f"{broken}_net_krw"] += 999 * EOK
    return out


def write_hive(root: Path, rows: list[dict], dataset: str = "krx_12008_kospi_stock_investor") -> None:
    part = root / "data" / "normalized" / dataset / "year=2026" / "month=09" / "part.jsonl.gz"
    part.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(part, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


class TestKospiMarketFlowKrx(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_loads_eok_latest_collection_wins_and_drops_broken_actor(self):
        write_hive(self.root, [
            row("2026-09-17", 100, -200, 90, collected="2026-09-18T00:00:00Z"),
            row("2026-09-17", 1, -2, 1, collected="2026-09-21T00:00:00Z"),
            row("2026-09-18", 50, -60, 10, broken="institution"),
        ])
        df = load_krx_12008_kospi_flows(self.root)
        self.assertEqual([d.strftime("%Y-%m-%d") for d in df.index], ["2026-09-17", "2026-09-18"])
        self.assertEqual(df.loc["2026-09-17", "retail_net_eok"], 1)
        self.assertEqual(df.loc["2026-09-17", "foreign_net_eok"], -2)
        self.assertTrue(df["institution_net_eok"].isna().iloc[1])
        self.assertEqual(df.loc["2026-09-18", "retail_net_eok"], 50)

    def test_etf_inclusive_hive_and_unscoped_rows_are_ignored(self):
        # The original 12008 hive counts ETF/ETN trades: a different quantity.
        write_hive(self.root, [row("2026-09-17", 9, -9, 0)], dataset="krx_12008_kospi_investor")
        write_hive(self.root, [row("2026-09-18", 1, -1, 0, scope=None), row("2026-09-19", 1, -1, 0, scope="all")])
        self.assertTrue(load_krx_12008_kospi_flows(self.root).empty)

    def test_carries_forward_published_stock_days_when_today_is_empty(self):
        prev = {"quality": "observed", "flow_source": "naver", "days": [
            {"date": "2026-09-15", "close": 6600.0, "retail_net_eok": 10.0, "foreign_net_eok": -20.0, "institution_net_eok": 5.0},
            {"date": "2026-09-16", "close": 6700.0, "retail_net_eok": 30.0, "foreign_net_eok": -40.0, "institution_net_eok": 6.0},
        ]}
        with mock.patch.object(ipl, "_fetch_naver_kospi_market_investor_history", return_value=pd.DataFrame()):
            out = build_kospi_index_levels(max_days=180, previous=prev)
        self.assertEqual(out["quality"], "observed")
        self.assertEqual(out["n_days"], 2)
        self.assertEqual(out["flow_date_end"], "2026-09-16")
        self.assertEqual(out["carried_forward_days"], 2)
        self.assertEqual(out["days"][-1]["retail_net_eok"], 30.0)

    def test_previous_block_from_another_scope_is_not_carried(self):
        prev = {"quality": "observed", "flow_source": "krx_12008", "days": [
            {"date": "2026-09-16", "close": 6700.0, "retail_net_eok": 30.0, "foreign_net_eok": -40.0, "institution_net_eok": 6.0}]}
        with mock.patch.object(ipl, "_fetch_naver_kospi_market_investor_history", return_value=pd.DataFrame()):
            out = build_kospi_index_levels(max_days=180, previous=prev)
        self.assertEqual(out["quality"], "missing")

    def test_history_prefers_krx_and_never_calls_naver(self):
        write_hive(self.root, [row(f"2026-09-{d:02d}", d, -d, 0) for d in (14, 15, 16, 17)])
        with mock.patch("market_microstructure.investor_price_levels._fetch_naver_kospi_market_investor_history") as naver:
            df = fetch_kospi_market_investor_history(max_days=3, krx_root=self.root)
        naver.assert_not_called()
        self.assertEqual(df.attrs["source_key"], "krx_12008_stock")
        self.assertEqual(len(df), 3)
        self.assertEqual(df.index.max().strftime("%Y-%m-%d"), "2026-09-17")

    def test_public_extras_falls_back_to_krx_when_naver_is_empty(self):
        write_hive(self.root, [row("2026-09-16", 10, -20, 5), row("2026-09-17", 30, -40, 6)])
        empty = {"history": [], "latest": None, "quality": "missing", "source": "naver"}
        with mock.patch.object(fetch_kr_public_extras, "_fetch_naver_kospi_investor_flows", return_value=empty), \
                mock.patch.dict(os.environ, {"KRX_MONTH_PASTE_DIR": str(self.root)}):
            out = fetch_kr_public_extras.fetch_naver_kospi_investor_flows()
        self.assertEqual(out["quality"], "observed")
        self.assertIn("KRX 12008", out["source"])
        self.assertEqual(out["scope"], "kospi_cash")
        self.assertEqual(out["latest"]["date_raw"], "26.09.17")
        self.assertEqual(out["latest"]["retail_net_eok"], 30)
        self.assertEqual(out["latest"]["foreign_net_krw"], -40 * EOK)

    def test_public_extras_does_not_use_the_etf_inclusive_hive(self):
        write_hive(self.root, [row("2026-09-17", 30, -40, 6)], dataset="krx_12008_kospi_investor")
        empty = {"history": [], "latest": None, "quality": "missing", "source": "naver"}
        with mock.patch.object(fetch_kr_public_extras, "_fetch_naver_kospi_investor_flows", return_value=empty), \
                mock.patch.dict(os.environ, {"KRX_MONTH_PASTE_DIR": str(self.root)}):
            out = fetch_kr_public_extras.fetch_naver_kospi_investor_flows()
        self.assertEqual(out["quality"], "missing")  # caller then keeps the previous observation

    def test_public_extras_keeps_naver_when_it_works(self):
        live = {"history": [{"date_raw": "26.09.23"}], "latest": {"date_raw": "26.09.23"}, "quality": "observed"}
        with mock.patch.object(fetch_kr_public_extras, "_fetch_naver_kospi_investor_flows", return_value=live):
            self.assertIs(fetch_kr_public_extras.fetch_naver_kospi_investor_flows(), live)


if __name__ == "__main__":
    unittest.main()

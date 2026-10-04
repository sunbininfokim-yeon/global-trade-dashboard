"""A failed listing/screen must never publish a two-stock success snapshot."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_investor_price_levels as cli  # noqa: E402
from market_microstructure import investor_price_levels as levels  # noqa: E402


def listing(n=3):
    return pd.DataFrame({
        "Code": [f"{i:06d}" for i in range(1, n + 1)],
        "Name": [f"보통주{i}" for i in range(1, n + 1)],
        "Marcap": list(range(n, 0, -1)),
    })


def fake_fdr(stock_listing):
    return SimpleNamespace(
        StockListing=Mock(return_value=stock_listing),
        DataReader=Mock(return_value=pd.DataFrame({"Close": [100 + i % 4 for i in range(40)]})),
    )


class TestUniverseFailure(unittest.TestCase):
    def test_none_or_empty_listing_does_not_select_two_stocks(self):
        for empty in (None, pd.DataFrame()):
            with self.subTest(listing_type=type(empty).__name__), patch.dict(
                sys.modules, {"FinanceDataReader": fake_fdr(empty)}
            ):
                with self.assertRaisesRegex(levels.KospiUniverseError, "listing is empty"):
                    levels.default_kospi_universe(top_n=10)
                with self.assertRaisesRegex(levels.KospiUniverseError, "listing is empty"):
                    levels.high_vol_kospi_universe(top_n=10, pool=100)

    def test_source_exception_is_an_explicit_universe_failure(self):
        fdr = fake_fdr(None)
        fdr.StockListing.side_effect = RuntimeError("KRX temporarily blocked")
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            with self.assertRaisesRegex(levels.KospiUniverseError, "listing failed.*blocked"):
                levels.default_kospi_universe()

    def test_missing_listing_columns_are_rejected(self):
        with patch.dict(sys.modules, {"FinanceDataReader": fake_fdr(listing().drop(columns="Marcap"))}):
            with self.assertRaisesRegex(levels.KospiUniverseError, "missing columns: Marcap"):
                levels.default_kospi_universe(top_n=2)

    def test_short_listing_cannot_claim_requested_top_or_pool(self):
        with patch.dict(sys.modules, {"FinanceDataReader": fake_fdr(listing(2))}):
            with self.assertRaisesRegex(levels.KospiUniverseError, "need 10"):
                levels.default_kospi_universe(top_n=10)
            with self.assertRaisesRegex(levels.KospiUniverseError, "need 100"):
                levels.high_vol_kospi_universe(top_n=10, pool=100)

    def test_filtered_or_invalid_listing_does_not_invent_a_universe(self):
        invalids = [listing().assign(Name="우선주우"), listing().assign(Marcap="invalid"),
                    listing().assign(Code="000001")]
        for invalid in invalids:
            with self.subTest(rows=invalid.to_dict()), patch.dict(
                sys.modules, {"FinanceDataReader": fake_fdr(invalid)}
            ):
                with self.assertRaises(levels.KospiUniverseError):
                    levels.default_kospi_universe(top_n=3)

    def test_incomplete_price_screen_cannot_claim_high_vol_ranking(self):
        # Even enough scores to pick top-2 cannot establish the ranking of a
        # three-stock pool when the third stock's returns were not observed.
        for n_observed in (0, 2):
            fdr = fake_fdr(listing())
            prices = fdr.DataReader.return_value
            fdr.DataReader.side_effect = lambda code, start: prices if int(code) <= n_observed else None
            with self.subTest(n_observed=n_observed), patch.dict(sys.modules, {"FinanceDataReader": fdr}):
                with self.assertRaisesRegex(levels.KospiUniverseError, f"scored {n_observed}/3"):
                    levels.high_vol_kospi_universe(top_n=2, pool=3)

    def test_successful_both_rankings_use_one_listing(self):
        fdr = fake_fdr(listing())
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}), patch.object(
            levels, "build_ticker_levels", return_value={"quality": "observed"}
        ), patch.object(levels, "build_kospi_index_levels", return_value={"quality": "observed"}):
            report = levels.build_investor_price_levels_report(kospi_top_n=2, high_vol_pool=3)
        fdr.StockListing.assert_called_once_with("KOSPI")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["universe_meta"]["marcap_top"]["n"], 2)
        self.assertEqual(report["universe_meta"]["high_vol_in_marcap_top"]["scored_n"], 3)
        self.assertEqual(report["universe_meta"]["high_vol_in_marcap_top"]["quality"], "observed")

    def test_custom_tickers_do_not_require_a_listing(self):
        fdr = fake_fdr(None)
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}), patch.object(
            levels, "build_ticker_levels", return_value={"quality": "observed"}
        ), patch.object(levels, "build_kospi_index_levels", return_value={"quality": "observed"}):
            report = levels.build_investor_price_levels_report([("005930", "삼성전자")])
        fdr.StockListing.assert_not_called()
        self.assertEqual(report["universe_mode"], "custom")
        self.assertEqual(report["universe_n"], 1)

    def test_cli_failed_universe_preserves_json_and_markdown_and_exits_nonzero(self):
        for mode in ("marcap", "high_vol", "both"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                script_root = Path(tmp) / "scripts" / "market_microstructure"
                script_root.mkdir(parents=True)
                out = Path(tmp) / "public" / "data" / "investor_price_levels_v1.json"
                out.parent.mkdir(parents=True)
                previous = json.dumps({"as_of": "2026-09-30", "kospi_index_levels": {"quality": "observed"}})
                out.write_text(previous, encoding="utf-8")
                md = script_root / "INVESTOR_PRICE_LEVELS.md"
                md.write_text("previous report", encoding="utf-8")
                stderr, stdout = io.StringIO(), io.StringIO()
                with patch.object(cli, "ROOT", script_root), patch.object(
                    sys, "argv", ["build_investor_price_levels.py", "--live", "--universe", mode]
                ), patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch.dict(
                    sys.modules, {"FinanceDataReader": fake_fdr(None)}
                ), patch.object(
                    levels, "build_ticker_levels"
                ) as fetch_ticker, patch.object(levels, "build_kospi_index_levels") as fetch_index, \
                    redirect_stderr(stderr), redirect_stdout(stdout):
                    code = cli.main()
                self.assertEqual(code, 1)
                self.assertEqual(out.read_text(encoding="utf-8"), previous)
                self.assertEqual(md.read_text(encoding="utf-8"), "previous report")
                self.assertIn("snapshot kept unchanged", stderr.getvalue())
                self.assertIn("::error title=KOSPI universe unavailable::", stderr.getvalue())
                self.assertNotIn("Wrote", stdout.getvalue())
                fetch_ticker.assert_not_called()
                fetch_index.assert_not_called()


if __name__ == "__main__":
    unittest.main()

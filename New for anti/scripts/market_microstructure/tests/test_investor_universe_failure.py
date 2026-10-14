"""A failed listing/screen must never publish a two-stock success snapshot."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from collections import Counter
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
    def setUp(self):
        # Production waits one second before each sequential retry.
        self.sleep_patch = patch("time.sleep")
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

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

    def test_short_valid_history_and_zero_volume_do_not_block_or_retry(self):
        fdr = fake_fdr(listing(4))
        prices = fdr.DataReader.return_value
        def read(code, start):
            if code == "000003":
                return prices.head(8)
            if code == "000004":
                return prices.assign(Volume=0)
            return prices
        fdr.DataReader.side_effect = read
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            result = levels.high_vol_kospi_universe(top_n=2, pool=4)
        self.assertEqual(result["scored_n"], 2)
        self.assertEqual(result["excluded_n"], 2)
        self.assertEqual(result["retried_n"], 0)
        self.assertEqual({r["reason"] for r in result["excluded"]},
                         {"insufficient_history", "no_trading_volume"})
        self.assertEqual(fdr.DataReader.call_count, 4)
        self.sleep.assert_not_called()
        fdr.StockListing.assert_called_once_with("KOSPI")

    def test_failed_tickers_only_retry_once_on_main_thread_after_initial_pool(self):
        fdr = fake_fdr(listing(4))
        prices = fdr.DataReader.return_value
        calls = []
        lock = threading.Lock()
        def read(code, start):
            with lock:
                calls.append((code, threading.current_thread().name))
                attempt = sum(c == code for c, _ in calls)
            if code in {"000002", "000003"} and attempt == 1:
                if code == "000002":
                    raise TimeoutError("temporary failure")
                return pd.DataFrame()
            if code == "000004":
                return prices.head(5)
            return prices
        fdr.DataReader.side_effect = read
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            result = levels.high_vol_kospi_universe(top_n=2, pool=4)
        self.assertEqual(Counter(c for c, _ in calls),
                         {"000001": 1, "000002": 2, "000003": 2, "000004": 1})
        self.assertEqual(set(c for c, _ in calls[:4]), {"000001", "000002", "000003", "000004"})
        self.assertEqual(calls[4:], [("000002", "MainThread"), ("000003", "MainThread")])
        self.assertEqual(result["scored_n"], 3)
        self.assertEqual(result["excluded_n"], 1)
        self.assertEqual(result["retried_n"], 2)
        self.assertTrue(all(r["final_status"] == "scored" for r in result["retries"]))
        self.assertEqual(self.sleep.call_count, 2)
        fdr.StockListing.assert_called_once_with("KOSPI")

    def test_invalid_or_missing_prices_are_not_a_normal_exclusion(self):
        bad_frames = [None, pd.DataFrame(), pd.DataFrame({"Open": [1]}),
                      pd.DataFrame({"Close": [100] * 20 + [float("nan")]}),
                      pd.DataFrame({"Close": [100] * 20 + [0]}),
                      pd.DataFrame({"Close": [100] * 20, "Volume": [float("nan")] * 20})]
        for bad in bad_frames:
            with self.subTest(columns=getattr(bad, "columns", None)):
                fdr = fake_fdr(listing(2))
                prices = fdr.DataReader.return_value
                fdr.DataReader.side_effect = lambda code, start: bad if code == "000002" else prices
                with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
                    with self.assertRaisesRegex(levels.KospiUniverseError, "after one sequential retry"):
                        levels.high_vol_kospi_universe(top_n=1, pool=2)
                self.assertEqual(Counter(c.args[0] for c in fdr.DataReader.call_args_list),
                                 {"000001": 1, "000002": 2})

    def test_retry_can_return_a_verified_short_history_exclusion(self):
        fdr = fake_fdr(listing(2))
        prices = fdr.DataReader.return_value
        seen = Counter()
        def read(code, start):
            seen[code] += 1
            if code == "000002":
                return None if seen[code] == 1 else prices.head(5)
            return prices
        fdr.DataReader.side_effect = read
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            result = levels.high_vol_kospi_universe(top_n=1, pool=2)
        self.assertEqual(result["excluded_n"], 1)
        self.assertEqual(result["retries"][0]["final_status"], "excluded")

    def test_not_enough_eligible_scores_still_blocks(self):
        fdr = fake_fdr(listing(3))
        prices = fdr.DataReader.return_value
        fdr.DataReader.side_effect = lambda code, start: prices if code == "000001" else prices.head(5)
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            with self.assertRaisesRegex(levels.KospiUniverseError, "1 eligible scores; need 2"):
                levels.high_vol_kospi_universe(top_n=2, pool=3)
        self.assertEqual(fdr.DataReader.call_count, 3)

    def test_flat_prices_with_trading_volume_are_eligible(self):
        fdr = fake_fdr(listing(2))
        fdr.DataReader.return_value = pd.DataFrame({"Close": [100] * 40, "Volume": [1] * 40})
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            result = levels.high_vol_kospi_universe(top_n=1, pool=2)
        self.assertEqual(result["scored_n"], 2)
        self.assertEqual(result["ranks"][0]["realized_vol_ann"], 0)
        self.assertEqual(result["pairs"][0][0], "000001")

    def test_zero_close_zero_volume_full_window_can_be_excluded_without_retry(self):
        fdr = fake_fdr(listing(2))
        prices = fdr.DataReader.return_value
        fdr.DataReader.side_effect = lambda code, start: prices if code == "000001" else prices.assign(Close=0, Volume=0)
        with patch.dict(sys.modules, {"FinanceDataReader": fdr}):
            result = levels.high_vol_kospi_universe(top_n=1, pool=2)
        self.assertEqual(result["excluded"][0]["reason"], "no_trading_volume")
        self.assertEqual(fdr.DataReader.call_count, 2)
        self.sleep.assert_not_called()

    def test_cli_unresolved_screen_preserves_published_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_root = Path(tmp) / "scripts" / "market_microstructure"
            script_root.mkdir(parents=True)
            out = Path(tmp) / "public" / "data" / "investor_price_levels_v1.json"
            out.parent.mkdir(parents=True)
            previous = '{"as_of": "2026-09-30"}'
            out.write_text(previous)
            md = script_root / "INVESTOR_PRICE_LEVELS.md"
            md.write_text("previous report")
            fdr = fake_fdr(listing(3))
            prices = fdr.DataReader.return_value
            fdr.DataReader.side_effect = lambda code, start: None if code == "000003" else prices
            with patch.object(cli, "ROOT", script_root), patch.object(
                sys, "argv", ["build_investor_price_levels.py", "--live", "--top", "2", "--pool", "3"]
            ), patch.dict(sys.modules, {"FinanceDataReader": fdr}), \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 1)
            self.assertEqual(out.read_text(), previous)
            self.assertEqual(md.read_text(), "previous report")
            self.assertEqual(fdr.DataReader.call_count, 4)


if __name__ == "__main__":
    unittest.main()

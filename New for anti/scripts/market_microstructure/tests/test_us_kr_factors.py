import gzip
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ["numpy", "pandas", "scipy", "sklearn", "exchange_calendars"]):
    raise unittest.SkipTest("install requirements-us-kr-preopen.txt")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_us_kr_preopen as runner
import us_kr_factors as factors
import train_us_kr_factors as training

TARGET = "2026-11-09"
NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def flow(ticker, day):
    return {"ticker": ticker, "date": day, "source_screen": "12009", "quality": "observed",
            "collected_at": day + "T12:00:00+00:00", "market_total_buy_krw": 100,
            "foreign_net_krw": 11, "other_foreign_net_krw": -1}


class FactorTests(unittest.TestCase):
    def setUp(self):
        self.model = runner.read(factors.DEFAULT_MODEL)
        self.us = {"symbols": {s: [{"date": "2026-11-05", "close": 100},
                                   {"date": "2026-11-06", "close": 101}] for s in factors.SYMBOLS}}

    def test_missing_12009_stays_unavailable_and_other_groups_compute(self):
        with patch.object(factors, "option_features", return_value={"2026-11-06": [.1]*4}):
            result = factors.factor_payload(self.model, {}, self.us, target=TARGET, now=NOW)
        self.assertEqual(set(result), set(factors.CONFIG))
        self.assertEqual(result["options"]["status"], "available")
        self.assertEqual(result["us_price"]["status"], "available")
        foreign = result["foreign_stock_flow"]
        self.assertEqual(foreign["status"], "unavailable")
        self.assertEqual([r["ticker"] for r in foreign["cards"]], ["005930", "000660"])
        self.assertIsNone(foreign["cards"][0]["scores"]["opening_up"]["probability"])
        self.assertIn(foreign["validation"]["skill"], {"none", "weak", "yes"})

    def test_complete_stock_window_is_required_per_ticker(self):
        rows = [flow("005930", f"2026-11-0{d}") for d in range(2, 7)]
        rows.extend(flow("000660", f"2026-11-0{d}") for d in range(2, 6))
        with patch.object(factors, "read_flow", return_value=rows):
            result = factors.factor_payload(self.model, {}, self.us, target=TARGET, now=NOW)
        foreign = result["foreign_stock_flow"]
        self.assertEqual(foreign["status"], "partial")
        self.assertEqual([r["status"] for r in foreign["cards"]], ["available", "unavailable"])
        score = foreign["cards"][0]["scores"]["closing_up"]
        self.assertAlmostEqual(score["up_probability"] + score["down_probability"], 1)

    def test_monthly_12009_reads_from_sparse_checkout_git_object(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            part = repo / factors.FLOW_PATH / "year=2026/month=11/part.jsonl.gz"
            part.parent.mkdir(parents=True)
            row = flow("005930", "2026-11-06")
            part.write_bytes(gzip.compress(json.dumps(row).encode()))
            subprocess.run(["git", "init", "-q", temp], check=True)
            subprocess.run(["git", "-C", temp, "add", "."], check=True)
            subprocess.run(["git", "-C", temp, "-c", "user.name=Test", "-c", "user.email=test@example.org",
                            "commit", "-qm", "fixture"], check=True)
            part.unlink()
            self.assertEqual(factors.read_flow(repo/"data/raw/krx_15007", None, ["2026-11-06"]), [row])

    def test_factor_cutoff_after_source_loading(self):
        late = datetime(2026, 11, 8, 23, 31, tzinfo=timezone.utc)
        result = factors.factor_payload(self.model, {}, self.us, target=TARGET, now=NOW, clock=lambda: late)
        self.assertTrue(all(group["status"] == "unavailable" for group in result.values()))

    def test_public_factors_are_additive_without_mutating_archived_forecast(self):
        forecast = {"target_date": TARGET, "status": "unavailable", "generated_at": NOW.isoformat(),
                    "reasons": [], "KR_source_date": "2026-11-06", "required_US_session": "2026-11-06",
                    "forecast_cutoff_KST": "2026-11-09T08:30:00+09:00", "model_id": "a",
                    "trained_through": "2026-10-22"}
        old = runner.display_payload(forecast)
        display = runner.display_payload(forecast, factors={"options": {}})
        self.assertEqual(display.pop("factors"), {"options": {}})
        self.assertEqual(display, old)
        self.assertNotIn("factors", forecast)
        previous = {"status": "research_preopen_forecast", "target_date": TARGET,
                    "cards": [{"ticker": "KOSPI"}], "factors": {"stale": {}}}
        refreshed = runner.display_payload(forecast, previous, {"options": {}})
        self.assertEqual(refreshed["cards"], previous["cards"])
        self.assertEqual(refreshed["factors"], {"options": {}})


    def test_validation_includes_the_last_month_of_each_quarter(self):
        rows = [
            {"date": "2021-03-30", "target_date": "2021-03-31", "x": [0.1], "y": 1},
            {"date": "2021-06-29", "target_date": "2021-06-30", "x": [0.1], "y": 0},
        ]
        with patch.object(training, "split", return_value=(rows, rows)), \
             patch.object(training, "fitted", return_value={}), \
             patch.object(training, "calibrated", return_value=.5):
            scored = training.evaluate(rows, "2021-06-30")
        self.assertEqual([r["target_date"] for r in scored], ["2021-03-31", "2021-06-30"])

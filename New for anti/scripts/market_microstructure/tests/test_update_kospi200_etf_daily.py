import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from update_kospi200_etf_daily import completed, plan_ticker, run  # noqa: E402

KST = timezone(timedelta(hours=9))


def bar(close, volume=100.0):
    return {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": volume}


def candidate():
    return {
        "ticker": "069500",
        "price_adjustment": "backward_cash_distribution",
        "rows": [{"date": "2026-10-29", **bar(10.0)}, {"date": "2026-10-30", **bar(11.0)}],
    }


AFTER = datetime(2026, 11, 2, 21, 0, tzinfo=KST)


class CompletedTest(unittest.TestCase):
    def test_session_rule(self):
        self.assertTrue(completed("2026-10-30", datetime(2026, 11, 2, 9, 0, tzinfo=KST)))
        self.assertFalse(completed("2026-11-02", datetime(2026, 11, 2, 15, 40, tzinfo=KST)))
        self.assertTrue(completed("2026-11-02", datetime(2026, 11, 2, 18, 30, tzinfo=KST)))
        # 2026-11-02 09:00 UTC is 18:00 KST on the same date: still before the cut.
        self.assertFalse(completed("2026-11-02", datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)))


class PlanTest(unittest.TestCase):
    def test_appends_completed_day(self):
        adj = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
        raw = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
        report = plan_ticker(candidate(), adj, raw, AFTER)
        self.assertEqual(report["status"], "ok")
        self.assertEqual([r["date"] for r in report["appended"]], ["2026-11-02"])
        row = report["appended"][0]
        self.assertEqual(row["provider_published_at"], "unknown")
        self.assertEqual(row["volume_quality"], "provisional_same_day")

    def test_unfinished_session_is_skipped(self):
        adj = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
        report = plan_ticker(candidate(), adj, dict(adj), datetime(2026, 11, 2, 14, 0, tzinfo=KST))
        self.assertEqual(report["appended"], [])
        self.assertEqual(report["skipped"][0]["date"], "2026-11-02")

    def test_rebased_history_stops(self):
        adj = {"2026-10-30": bar(9.0), "2026-11-02": bar(12.0)}
        report = plan_ticker(candidate(), adj, dict(adj), AFTER)
        self.assertEqual(report["status"], "provider_rebased")
        self.assertEqual(report["appended"], [])

    def test_day_missing_from_unadjusted_table_is_skipped(self):
        adj = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
        report = plan_ticker(candidate(), adj, {"2026-10-30": bar(11.0)}, AFTER)
        self.assertEqual(report["appended"], [])

    def test_distribution_day_is_skipped(self):
        adj = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
        raw = {"2026-10-30": bar(11.0), "2026-11-02": bar(14.0)}
        report = plan_ticker(candidate(), adj, raw, AFTER)
        self.assertEqual(report["appended"], [])
        self.assertIn("distribution", report["skipped"][0]["reason"])

    def test_stored_volume_difference_is_reported_not_rewritten(self):
        adj = {"2026-10-30": bar(11.0, volume=150.0)}
        cand = candidate()
        report = plan_ticker(cand, adj, dict(adj), AFTER)
        self.assertEqual(report["stored_volume_differs"][0]["date"], "2026-10-30")
        self.assertEqual(cand["rows"][-1]["volume"], 100.0)


class RunTest(unittest.TestCase):
    def test_no_new_day_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "etf.json"
            doc = {"candidates": [candidate()]}
            path.write_text(json.dumps(doc), encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            src = {"2026-10-30": bar(11.0)}
            summary = run(["069500"], path=path, now=AFTER,
                          adjusted_fn=lambda t, s: src, unadjusted_fn=lambda t: src)
            self.assertEqual(summary["reports"][0]["appended"], [])
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_append_updates_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "etf.json"
            path.write_text(json.dumps({"candidates": [candidate()]}), encoding="utf-8")
            src = {"2026-10-30": bar(11.0), "2026-11-02": bar(12.0)}
            run(["069500"], path=path, now=AFTER, adjusted_fn=lambda t, s: src, unadjusted_fn=lambda t: src)
            cand = json.loads(path.read_text(encoding="utf-8"))["candidates"][0]
            self.assertEqual((cand["n"], cand["date_end"]), (3, "2026-11-02"))
            self.assertEqual(cand["rows"][1]["volume"], 100.0)


if __name__ == "__main__":
    unittest.main()

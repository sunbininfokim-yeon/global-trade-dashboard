"""Prospective call-flow edge tracker: frozen rule, write-once rows, honest scoring."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import track_call_intraday_edge as t  # noqa: E402


def weekdays(start, n):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def is_session(day):
    return date.fromisoformat(day).weekday() < 5


def board(values):
    return {"kr": {"investor_nets": {"detailed_15007": {"products": {"options_call": {"series": [
        {"date": d, "quality": "observed", "foreign": {"net_krw": v * 100}, "market_total": {"buy_krw": 100}}
        for d, v in values.items()]}}}}}}


DAYS = weekdays("2026-08-03", 70)   # last day 2026-11-06 (Fri)
BASE = {d: (i % 7 - 3) * 0.001 for i, d in enumerate(DAYS)}


class Tracker(unittest.TestCase):
    def test_records_next_session_position_from_frozen_rule(self):
        vals = dict(BASE, **{"2026-11-06": 0.05})
        led = t.update({}, board(vals), {}, is_session, "2026-11-08T00:00:00+00:00")
        row = led["rows"]["2026-11-09"]
        self.assertEqual((row["signal_date"], row["position"]), ("2026-11-06", 1))
        self.assertEqual(led["rule_sha256"], t.RULE_SHA)

    def test_no_rows_before_first_target(self):
        led = t.update({}, board(BASE), {}, is_session, "x")
        self.assertTrue(all(k >= t.RULE["first_target"] for k in led["rows"]))

    def test_recorded_position_never_changes_and_revision_is_logged(self):
        vals = dict(BASE, **{"2026-11-06": 0.05})
        led = t.update({}, board(vals), {}, is_session, "2026-11-08T00:00:00+00:00")
        led = t.update(copy.deepcopy(led), board(dict(vals, **{"2026-11-06": -0.05})), {}, is_session, "later")
        self.assertEqual(led["rows"]["2026-11-09"]["position"], 1)
        self.assertEqual(led["revisions"][0]["kept"], "recorded")

    def test_scores_open_to_close_once(self):
        vals = dict(BASE, **{"2026-11-06": 0.05})
        bars = {"KOSPI": {"2026-11-09": {"open": 100.0, "close": 101.0}},
                "005930": {"2026-11-09": {"open": 100.0, "close": 99.0}}}
        led = t.update({}, board(vals), bars, is_session, "2026-11-09T07:00:00+00:00")
        r = led["rows"]["2026-11-09"]
        self.assertAlmostEqual(r["primary"]["pnl_bp"], 100.0)
        self.assertAlmostEqual(r["secondary"]["pnl_bp"], -100.0)
        bars["KOSPI"]["2026-11-09"]["close"] = 50.0
        led = t.update(copy.deepcopy(led), board(vals), bars, is_session, "later")
        self.assertAlmostEqual(led["rows"]["2026-11-09"]["primary"]["pnl_bp"], 100.0)
        self.assertEqual(led["summary"]["primary"]["n"], 1)

    def test_changed_rule_is_refused(self):
        with self.assertRaises(SystemExit):
            t.update({"rule_sha256": "other"}, board(BASE), {}, is_session, "x")

    def test_needs_40_prior_observations(self):
        short = dict(list(BASE.items())[-30:])
        self.assertEqual(t.update({}, board(short), {}, is_session, "x")["rows"], {})

    def test_reference_excludes_the_signal_day(self):
        vals = {d: 0.0 for d in DAYS}
        vals["2026-11-06"] = 1.0
        row = t.update({}, board(vals), {}, is_session, "x")["rows"]["2026-11-09"]
        self.assertEqual(row["reference_median"], 0.0)


if __name__ == "__main__":
    unittest.main()

"""v2 shadow: feature alignment, write-once records, plan gate and paired scoring."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import us_kr_v2_shadow as v  # noqa: E402

MODEL = Path(__file__).resolve().parents[1] / "models" / "shadow" / "us_kr_v2_20261116.json"


def us_frames(day, prev):
    us = {s: {prev: (100.0, 100.0), day: (100.0, 101.0)} for s in v.US + ["EWY"]}
    us["^VIX"] = {prev: (20.0, 20.0), day: (20.0, 19.0)}
    us["EWY"][day] = (50.0, 51.0)
    return us


def krw(points):
    return pd.Series({pd.Timestamp(t, tz="Asia/Seoul").tz_convert("UTC"): p for t, p in points}).sort_index()


class Features(unittest.TestCase):
    def test_values_and_monday_fx(self):
        # Monday 11/16 target: source Fri 11/13, US Fri 11/13 vs Thu 11/12.
        kr = {"2026-11-12": (100.0, 100.0), "2026-11-13": (101.0, 102.0)}
        fx = krw([("2026-11-13 14:00", 1400.0), ("2026-11-14 06:00", 1414.0)])  # last bar before weekend
        x, why = v.features(kr, us_frames("2026-11-13", "2026-11-12"), fx,
                            "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-13", "2026-11-12")
        self.assertIsNone(why)
        self.assertAlmostEqual(x["return1"], 0.02)
        self.assertAlmostEqual(x["gap1"], 0.01)
        self.assertAlmostEqual(x["EWY_intraday"], 0.02)
        self.assertAlmostEqual(x["KRW_overnight"], 0.01)
        self.assertAlmostEqual(x["^VIX"], -0.05)

    def test_missing_us_bar_is_unavailable(self):
        kr = {"2026-11-12": (100.0, 100.0), "2026-11-13": (101.0, 102.0)}
        us = us_frames("2026-11-13", "2026-11-12"); del us["MU"]["2026-11-13"]
        fx = krw([("2026-11-13 14:00", 1400.0), ("2026-11-14 06:00", 1414.0)])
        x, why = v.features(kr, us, fx, "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-13", "2026-11-12")
        self.assertIsNone(x); self.assertIn("missing bar", why)

    def test_fx_must_move_past_source_session(self):
        kr = {"2026-11-12": (100.0, 100.0), "2026-11-13": (101.0, 102.0)}
        fx = krw([("2026-11-13 14:00", 1400.0)])
        x, why = v.features(kr, us_frames("2026-11-13", "2026-11-12"), fx,
                            "2026-11-16", "2026-11-13", "2026-11-12", "2026-11-13", "2026-11-12")
        self.assertIsNone(x); self.assertIn("KRW", why)


class Records(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(MODEL.read_text())

    def test_frozen_model_validates(self):
        v.validate_model(self.model)
        self.assertEqual(self.model["features"], v.FEATURES)
        tampered = dict(self.model, C=1.0)
        with self.assertRaises(ValueError):
            v.validate_model(tampered)

    def test_write_once(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a" / "first.json"
            self.assertTrue(v.write_once(p, {"x": 1}))
            self.assertFalse(v.write_once(p, {"x": 2}))
            self.assertEqual(json.loads(p.read_text()), {"x": 1})

    def test_plan_waits_then_runs_then_stops(self):
        with tempfile.TemporaryDirectory() as d:
            at = lambda s: datetime.fromisoformat(s).astimezone(timezone.utc)
            early = v.plan(self.model, d, at("2026-11-18T05:30:00+09:00"))
            self.assertEqual((early["target"], early["run"]), ("2026-11-18", False))
            self.assertIn("US close", early["reason"])
            self.assertTrue(v.plan(self.model, d, at("2026-11-18T06:30:00+09:00"))["run"])
            late = v.plan(self.model, d, at("2026-11-18T08:31:00+09:00"))
            self.assertIn("cutoff", late["reason"])
            self.assertIn("training", v.plan(self.model, d, at("2026-11-16T06:30:00+09:00"))["reason"])

    def test_score_pairs_with_v1(self):
        with tempfile.TemporaryDirectory() as d:
            mid = self.model["model_id"]
            a2, a1 = Path(d) / "v2", Path(d) / "v1"
            v.write_once(v.first_path(a2, "2026-11-18", mid), {
                "target_date": "2026-11-18", "alignment": {"source": "2026-11-17"},
                "results": {"KOSPI": {"probabilities": {"opening_up": 0.7, "closing_up": 0.4}}}})
            v.write_once(a1 / "2026-11-18" / "115ddb42c8c8449b" / "first.json", {
                "status": "research_preopen_forecast",
                "results": {"KOSPI": {"scores": {"opening_up": {"probability": 0.9},
                                                 "closing_up": {"probability": 0.6}}}}})
            kr = {"KOSPI": {"2026-11-17": (100.0, 100.0), "2026-11-18": (101.0, 99.0)}}
            out = v.score(self.model, a2, a1, kr)
            o, c = out["summary"]["KOSPI:opening_up"], out["summary"]["KOSPI:closing_up"]
            self.assertEqual((o["n"], o["n_paired"]), (1, 1))
            self.assertAlmostEqual(o["paired_v2_brier"], 0.09)
            self.assertAlmostEqual(o["paired_v1_brier"], 0.01)
            self.assertAlmostEqual(c["paired_v2_brier"], 0.16)
            self.assertEqual(c["paired_v1_hit"], 0.0)


if __name__ == "__main__":
    unittest.main()

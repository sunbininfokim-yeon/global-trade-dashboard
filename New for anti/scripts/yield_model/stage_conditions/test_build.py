import unittest
from datetime import date

import numpy as np
import pandas as pd

from . import build as B

SOY = [
    {"kind": "sow", "name_ko": "파종", "start": "06-15", "end": "07-20"},
    {"kind": "veg", "name_ko": "영양생장", "start": "06-25", "end": "08-10"},
    {"kind": "repro", "name_ko": "개화", "start": "08-01", "end": "09-05"},
    {"kind": "fill", "name_ko": "비대", "start": "08-25", "end": "09-30"},
    {"kind": "harvest", "name_ko": "수확", "start": "09-25", "end": "11-10"},
]


def daily(drought=None, end="2026-10-18"):
    dates = pd.date_range("1983-01-01", end)
    rng = np.random.default_rng(1)
    frame = pd.DataFrame({
        "date": dates,
        "precip": rng.choice([0.0, 8.0], len(dates), p=[0.5, 0.5]),
        "tmax": 30 + rng.normal(0, 1.5, len(dates)),
        "tmin": 20.0,
        "soil": 0.6 + rng.normal(0, 0.02, len(dates)),
    })
    if drought:
        lo, hi = drought
        mask = frame.date.between(lo, hi)
        frame.loc[mask, "precip"] = 0.0
        frame.loc[mask, "soil"] = 0.3
        frame.loc[mask, "tmax"] = 38.0
    return frame


class StageConditionTests(unittest.TestCase):
    def test_wheat_season_crosses_year(self):
        stages = [{"kind": "sow", "start": "09-01", "end": "10-31"},
                  {"kind": "dormant", "start": "12-01", "end": "02-28"},
                  {"kind": "harvest", "start": "06-01", "end": "07-20"}]
        placed = B.place(stages, 2025)
        self.assertEqual(placed[1], (date(2025, 12, 1), date(2026, 2, 28)))
        self.assertEqual(B.harvest_year(stages, placed), 2026)
        self.assertEqual(B.current_anchor(stages, date(2026, 8, 1)), 2025)

    def test_normal_season_is_neutral_and_future_is_upcoming(self):
        crop = {"crop": "soy", "label_ko": "대두", "stages": SOY}
        entry = B.crop_entry("x", crop, daily(), date(2026, 8, 15), None)
        states = [s["status"] for s in entry["stages"]]
        self.assertEqual(states[-2:], ["upcoming", "upcoming"])
        self.assertNotEqual(entry["overall"]["verdict"], "unfavorable")

    def test_flowering_drought_is_unfavourable(self):
        crop = {"crop": "soy", "label_ko": "대두", "stages": SOY}
        entry = B.crop_entry("x", crop, daily(("2026-08-01", "2026-09-30")),
                             date(2026, 10, 18), None)
        repro = entry["stages"][2]
        self.assertEqual(repro["status"], "unfavorable")
        self.assertEqual(entry["overall"]["verdict"], "unfavorable")

    def test_running_stage_compares_same_days(self):
        frame = daily()
        _, rows = B.stage_table(frame, SOY, 2026, 35.0, date(2026, 8, 10))
        repro = rows[2]
        self.assertEqual(repro["state"], "in_progress")
        self.assertLess(repro["observed_share"], 0.5)
        self.assertLess(abs(repro["current"]["precip"] - np.mean([p["precip"] for p in repro["past"]])),
                        3 * np.std([p["precip"] for p in repro["past"]]))

    def test_cane_crush_labelled_by_its_main_year(self):
        stages = [{"kind": "sow", "start": "10-15", "end": "02-28"},
                  {"kind": "veg", "start": "05-01", "end": "10-31"},
                  {"kind": "harvest", "start": "12-01", "end": "04-30"}]
        placed = B.place(stages, 2024)
        self.assertEqual(placed[1][0], date(2025, 5, 1))
        self.assertEqual(B.harvest_year(stages, placed), 2026)


class VerdictCheckTests(unittest.TestCase):
    def hist(self, unf, neu, fav, n=(6, 14, 7)):
        return {"n": sum(n), "classes": {
            "unfavorable": {"n": n[0], "mean_residual_pct": unf},
            "neutral": {"n": n[1], "mean_residual_pct": neu},
            "favorable": {"n": n[2], "mean_residual_pct": fav}}}

    def test_matched_and_unmatched(self):
        # Ukraine wheat 2000-2026: favourable years +14.8%, unfavourable -0.6%.
        h = self.hist(-0.6, -1.3, 14.8)
        self.assertEqual(B.verdict_check(h, "favorable"), "matched")
        self.assertEqual(B.verdict_check(h, "unfavorable"), "unmatched")
        self.assertIsNone(B.verdict_check(h, "neutral"))
        self.assertIsNone(B.verdict_check(None, "unfavorable"))

    def test_call_made_in_most_seasons_says_nothing(self):
        # Uganda coffee: unfavourable in 23 of 31 seasons.
        h = self.hist(-0.2, -0.6, 31.2, n=(23, 6, 2))
        self.assertEqual(B.verdict_check(h, "unfavorable"), "unmatched")
        self.assertEqual(B.verdict_check(h, "favorable"), "unmatched")  # 2 seasons is too few


if __name__ == "__main__":
    unittest.main()

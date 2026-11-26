from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import us_realestate as ure  # noqa: E402


class Transforms(unittest.TestCase):
    def test_spread_uses_same_or_previous_day(self):
        mort = [("2026-11-19", 7.20), ("2026-11-26", 7.21)]
        dgs10 = [("2026-11-18", 4.80), ("2026-11-19", 4.90), ("2026-11-25", 4.91)]   # no 11-26 print yet
        out = ure.spread_on_dates(mort, dgs10)
        self.assertEqual([d for d, _ in out], ["2026-11-19", "2026-11-26"])
        self.assertAlmostEqual(out[0][1], 230.0)
        self.assertAlmostEqual(out[1][1], 230.0)

    def test_spread_skips_dates_before_the_other_series(self):
        self.assertEqual(ure.spread_on_dates([("2000-01-01", 8.0)], [("2001-01-01", 6.0)]), [])

    def test_ratio_index_averages_to_100(self):
        a = [("1987-01-01", 100.0), ("1987-02-01", 200.0), ("1987-03-01", 300.0)]
        b = [("1987-01-01", 100.0), ("1987-02-01", 100.0), ("1987-03-01", 100.0)]
        out = ure.ratio_index(a, b)
        self.assertAlmostEqual(sum(v for _, v in out) / 3, 100.0)
        self.assertAlmostEqual(out[2][1], 150.0)

    def test_extra_note_names_both_peaks(self):
        pts = [("2006-05-01", 132.9), ("2012-01-01", 80.0), ("2022-05-01", 135.1), ("2026-09-01", 120.2)]
        n = ure.extra_note("price_to_rent", pts)
        self.assertIn("135.1(2022-05)", n)
        self.assertIn("132.9(2006-05)", n)
        self.assertIn("지금 120.2", n)
        self.assertEqual(ure.extra_note("mortgage_30y", pts), "")

    def test_extra_note_delinquency_and_spread(self):
        d = [("1991-01-01", 12.0), ("2010-01-01", 8.7), ("2026-04-01", 1.5)]
        n = ure.extra_note("delinq_cre", d)
        self.assertIn("최고 12.00%(1991Q1)", n)
        self.assertIn("금융위기 이후 최고 8.70%(2010Q1)", n)
        sp = [(f"2000-01-{i:02d}", float(v)) for i, v in enumerate(range(100, 300, 10), 1)]
        self.assertIn("중앙값 200bp", ure.extra_note("mortgage_spread", sp))

    def test_every_spec_has_a_transform_and_a_format(self):
        fake = lambda sid: [("2020-01-01", 1.0), ("2021-01-01", 2.0)]
        for sid, spec in ure.SPECS.items():
            ure.series_for(sid, fake)
            self.assertIn(spec.fmt, ups._FORMATS)


class Apply(unittest.TestCase):
    def pack(self):
        return {"ui": {"category_tabs": [{"id": "liquidity", "order": 1}, {"id": "inflation", "order": 6}]},
                "countries": [{"iso3": "USA", "active_categories": ["liquidity"], "categories": {"liquidity": []}, "indicators": []}]}

    def patch(self, sid):
        spec = ure.SPECS[sid]
        return ups.build_patch(spec, [("2026-07-01", 1.5), ("2026-10-01", 1.6)], retrieved_at="2026-11-26T00:00:00Z")

    def test_creates_tab_and_cards_once(self):
        p = self.pack()
        patches = {sid: self.patch(sid) for sid in ("mortgage_30y", "bank_cre_loans")}
        changed = ure.apply(p, patches)
        self.assertIn("(tab)", changed)
        usa = p["countries"][0]
        self.assertEqual([t["id"] for t in p["ui"]["category_tabs"]], ["liquidity", "inflation", "realestate"])
        self.assertEqual(usa["active_categories"][-1], "realestate")
        self.assertEqual([c["id"] for c in usa["categories"]["realestate"]], ["mortgage_30y", "bank_cre_loans"])
        self.assertTrue(next(i for i in usa["indicators"] if i["id"] == "bank_cre_loans")["yoy_line"])
        snap = json.dumps(p, sort_keys=True)
        self.assertEqual(ure.apply(p, {sid: self.patch(sid) for sid in patches}), [])
        self.assertEqual(json.dumps(p, sort_keys=True), snap)

    def test_missing_series_makes_no_empty_card(self):
        p = self.pack()
        ure.apply(p, {"mortgage_30y": self.patch("mortgage_30y")})
        ids = [i["id"] for i in p["countries"][0]["indicators"]]
        self.assertEqual(ids, ["mortgage_30y"])


if __name__ == "__main__":
    unittest.main()

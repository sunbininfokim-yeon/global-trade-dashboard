"""Switzerland (SNB data portal + FRED): che_public_series."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import che_public_series as chs  # noqa: E402

HEAD = '﻿"CubeId";"x"\n"PublishingDate";"2026-09-28 10:00"\n\n'


class Cube(unittest.TestCase):
    def test_rows_are_filtered_by_key_and_gaps_skipped(self):
        text = HEAD + '"Date";"D0";"D1";"Value"\n"2026-07";"B";"GM3";"1232174"\n"2026-07";"VV";"GM3";"3.4"\n"2026-08";"VV";"GM3";""\n'
        self.assertEqual(chs.parse_cube(text.lstrip("﻿"), "VV", "GM3"), [("2026-07-01", 3.4)])
        with self.assertRaises(ValueError):
            chs.parse_cube(text, "VV", "GM2")

    def test_periods(self):
        self.assertEqual(chs.period_key("2026-Q2"), "2026-04-01")
        self.assertEqual(chs.period_key("2026-08"), "2026-08-01")
        self.assertEqual(chs.period_key("2026-09-25"), "2026-09-25")
        self.assertIsNone(chs.period_key("2025"))

    def test_error_body_is_not_a_cube(self):
        with self.assertRaises(ValueError):
            chs.parse_cube('{"code":"404","message":"Table x not found"}', "LZ")


class Transforms(unittest.TestCase):
    def test_daily_to_month_last_and_mean(self):
        daily = [("2026-08-28", 0.4), ("2026-08-31", 0.5), ("2026-09-28", 0.7)]
        self.assertEqual(chs.month_last(daily), [("2026-08-01", 0.5), ("2026-09-01", 0.7)])
        self.assertAlmostEqual(chs.month_mean(daily)[0][1], 0.45)

    def test_spread_only_where_both_months_exist(self):
        (d, bp), = chs.spread_bp([("2026-08-01", 0.47), ("2026-09-01", 0.6)], [("2026-08-01", 3.18)])
        self.assertEqual(d, "2026-08-01")
        self.assertAlmostEqual(bp, -271.0)


class Wiring(unittest.TestCase):
    def fake(self):
        cubes = {
            "snbgwdzid": HEAD + '"Date";"D0";"Value"\n"2026-08-29";"LZ";"0"\n"2026-09-25";"LZ";"0"\n"2026-09-25";"SARON";"-0.05"\n',
            "snbfxtr": HEAD + '"Date";"D0";"Value"\n"2025-Q4";"T0";"-6"\n"2026-Q1";"T0";"3940"\n',
        }
        return chs.Sources(cube=lambda c: cubes[c], yield_10y=lambda: [], fred=lambda s: [])

    def test_policy_rate_pins_the_running_month_to_its_last_day(self):
        pts, last = chs.series_for("snb_policy_rate", self.fake())
        patch = chs.build_patch("snb_policy_rate", pts, last, retrieved_at="t")
        self.assertEqual(patch["asof"], "2026-09-25")
        self.assertEqual(patch["history"]["5y"]["dates"][-1], "2026-09-25")

    def test_fx_transactions_in_chf_billions_with_sign(self):
        pts, _ = chs.series_for("fx_intervention", self.fake())
        patch = chs.build_patch("fx_intervention", pts, None, retrieved_at="t")
        self.assertEqual(patch["display"], "CHF 3.9B")
        self.assertEqual(patch["reference_period"], "2026Q1")
        self.assertEqual(chs.ups._FORMATS["bn1chf"](-0.006), "-CHF 0.0B")

    def test_unit_change_reaches_the_chip(self):
        c = {"indicators": [{"id": "fx_intervention", "unit": "bn_usd", "data_status": "demo"}],
             "categories": {"fx": [{"id": "fx_intervention", "unit": "bn_usd"}]}, "headlines": [], "data_status_summary": {}}
        pts, _ = chs.series_for("fx_intervention", self.fake())
        chs.apply_all(c, {"fx_intervention": chs.build_patch("fx_intervention", pts, None, retrieved_at="t")}, retrieved_at="t")
        self.assertEqual(c["categories"]["fx"][0]["unit"], "bn_chf")
        self.assertEqual(c["indicators"][0]["data_status"], "live")


if __name__ == "__main__":
    unittest.main()

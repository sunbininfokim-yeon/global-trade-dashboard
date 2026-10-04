"""Australia (ABS Data API + FRED + Pink Sheet): aus_public_series."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import aus_public_series as aus  # noqa: E402

HDR = "DATAFLOW,MEASURE,SEX,AGE,TSEST,REGION,FREQ,TIME_PERIOD,OBS_VALUE,UNIT_MEASURE,UNIT_MULT\n"


class AbsCsv(unittest.TestCase):
    def test_months_and_quarters_sorted_and_blank_skipped(self):
        text = HDR + "ABS:LF,M13,3,1599,20,AUS,M,2026-08,4.64,PCT,0\nABS:LF,M13,3,1599,20,AUS,M,2026-07,4.48,PCT,0\nABS:LF,M13,3,1599,20,AUS,M,2026-06,,PCT,0\n"
        self.assertEqual(aus.parse_abs_csv(text), [("2026-07-01", 4.48), ("2026-08-01", 4.64)])
        self.assertEqual(aus.period_key("2026-Q2"), "2026-04-01")

    def test_no_records_raises(self):
        with self.assertRaises(ValueError):
            aus.parse_abs_csv("NoRecordsFound")


def src(abs_series=None, fred=None, pink=None):
    return aus.Sources(abs_=lambda n: abs_series[n], fred=lambda s: fred[s], pink=lambda: pink)


class Series(unittest.TestCase):
    def test_employment_change_is_the_monthly_difference_in_thousands(self):
        s = src({"employment_change": [("2026-07-01", 14797.0), ("2026-08-01", 14836.6)]})
        (d, v), = aus.series_for("employment_change", s)
        self.assertEqual(d, "2026-08-01")
        self.assertAlmostEqual(v, 39.6)
        self.assertEqual(aus.build_patch("employment_change", [(d, v)], retrieved_at="t")["display"], "+40K")

    def test_current_account_in_aud_billions_with_sign(self):
        s = src({"current_account": [("2026-04-01", -27220.0)]})
        patch = aus.build_patch("current_account", aus.series_for("current_account", s), retrieved_at="t")
        self.assertEqual((patch["display"], patch["reference_period"]), ("-A$27.2B", "2026Q2"))

    def test_spread_only_months_both_have(self):
        s = src(fred={"IRLTLT01USM156N": [("2026-07-01", 4.6), ("2026-08-01", 4.68)], "IRLTLT01AUM156N": [("2026-08-01", 5.015)]})
        (d, bp), = aus.series_for("us_au_10y_spread", s)
        self.assertAlmostEqual(bp, -33.5)

    def test_coal_card_is_renamed_to_what_it_shows(self):
        c = {"indicators": [{"id": "coking_coal", "unit": "usd_t", "data_status": "demo"}],
             "categories": {"growth": [{"id": "coking_coal", "unit": "usd_t"}]}, "headlines": [], "data_status_summary": {}}
        pts = aus.series_for("au_coal", src(pink={"Coal, Australian": [("2026-08-01", 135.2)], "Iron ore, cfr spot": []}))
        aus.apply_all(c, {"au_coal": aus.build_patch("au_coal", pts, retrieved_at="t")}, retrieved_at="t")
        self.assertEqual([i["id"] for i in c["indicators"]], ["au_coal"])
        self.assertEqual(c["categories"]["growth"][0]["id"], "au_coal")
        self.assertEqual(c["indicators"][0]["label_ko"], "호주 연료탄")


if __name__ == "__main__":
    unittest.main()

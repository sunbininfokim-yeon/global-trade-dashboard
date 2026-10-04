"""Observed public series for the USA indicators (macro_monitor.us_public_series, h41_fima)."""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import h41_fima  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

CSV = "observation_date,M2SL\n2025-06-01,100.0\n2025-07-01,.\n2025-08-01,110.0\n"


class Fetching(unittest.TestCase):
    def test_missing_values_are_skipped(self):
        self.assertEqual(ups.parse_fred_csv(CSV), [("2025-06-01", 100.0), ("2025-08-01", 110.0)])

    def test_empty_or_malformed_csv_is_an_error(self):
        with self.assertRaises(ValueError):
            ups.parse_fred_csv("observation_date,X\n")
        with self.assertRaises(ValueError):
            ups.parse_fred_csv("<html>blocked</html>")


class Transforms(unittest.TestCase):
    def test_pct_change_against_the_lagged_observation(self):
        pts = [(f"2025-{m:02d}-01", 100.0 + m) for m in range(1, 13)] + [("2026-01-01", 120.0)]
        got = ups.pct_change(pts, 12)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "2026-01-01")
        self.assertAlmostEqual(got[0][1], (120 / 101 - 1) * 100)

    def test_qoq_is_lag_one(self):
        got = ups.pct_change([("2026-01-01", 200.0), ("2026-04-01", 202.0)], 1)
        self.assertAlmostEqual(got[0][1], 1.0)

    def test_diff(self):
        self.assertEqual(ups.diff([("a", 100.0), ("b", 160.0), ("c", 150.0)]), [("b", 60.0), ("c", -10.0)])

    def test_vs_base_starts_at_the_base_and_needs_it(self):
        pts = [("2019-11-01", 90.0), ("2019-12-01", 100.0), ("2020-01-01", 110.0)]
        self.assertEqual(ups.vs_base(pts, "2019-12-01"), [("2019-12-01", 0.0), ("2020-01-01", 10.000000000000009)])
        with self.assertRaises(ValueError):
            ups.vs_base(pts, "2019-10-01")

    def test_scale(self):
        self.assertEqual(ups.scale([("a", 6235.0)], 0.001), [("a", 6.235)])

    def test_period_labels(self):
        self.assertEqual(ups.month_end("2026-02-01"), "2026-02-28")
        self.assertEqual(ups.quarter_end("2026-04-01"), "2026-06-30")
        self.assertEqual(ups.quarter_label("2026-07-01"), "2026Q3")


def _monthly(n, start=(2010, 1)):
    y, m = start
    out = []
    for i in range(n):
        out.append((f"{y:04d}-{m:02d}-01", float(i)))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class Patch(unittest.TestCase):
    def test_monthly_history_windows_and_dates(self):
        spec = ups.SPECS["nfp"]
        p = ups.build_patch(spec, _monthly(200), retrieved_at="T")
        self.assertEqual((len(p["history"]["5y"]["dates"]), len(p["history"]["10y"]["dates"])), (60, 120))
        self.assertTrue(p["history"]["5y"]["dates"][-1].endswith(("-28", "-29", "-30", "-31")))     # month end
        self.assertEqual(p["history"]["5y"]["values"][-1], 199.0)

    def test_display_reference_and_cleared_changes(self):
        p = ups.build_patch(ups.SPECS["nfp"], [("2026-07-01", 21.0), ("2026-08-01", 162.0)], retrieved_at="T")
        self.assertEqual((p["display"], p["reference_period"], p["asof"]), ("162K", "2026-08", "2026-08-31"))
        self.assertIsNone(p["change_1m_pct"])
        self.assertEqual((p["quality"], p["data_status"], p["source"]), ("live", "live", "fred:PAYEMS"))

    def test_quarterly_and_weekly(self):
        q = ups.build_patch(ups.SPECS["gdp_qoq"], [("2026-01-01", 0.6), ("2026-04-01", 0.37)], retrieved_at="T")
        self.assertEqual((q["display"], q["reference_period"], q["asof"]), ("0.4%", "2026Q2", "2026-06-30"))
        w = ups.build_patch(ups.SPECS["discount_window"], [("2026-09-16", 6.879), ("2026-09-23", 6.235)], retrieved_at="T")
        self.assertEqual((w["display"], w["asof"]), ("$6.24B", "2026-09-23"))

    def test_label_override_only_where_the_definition_changed(self):
        self.assertEqual(ups.build_patch(ups.SPECS["trimmed_mean_cpi"], [("2026-08-01", 2.57)], retrieved_at="T")["label_ko"],
                         "Cleveland Fed 절사평균 CPI YoY")
        self.assertNotIn("label_ko", ups.build_patch(ups.SPECS["nfp"], [("2026-08-01", 1.0)], retrieved_at="T"))

    def test_a_nowcast_is_as_of_the_day_it_was_read_not_the_quarter_end(self):
        p = ups.build_patch(ups.SPECS["gdpnow"], [("2026-07-01", 5.0796)], retrieved_at="2026-09-25T06:00:00Z")
        self.assertEqual((p["asof"], p["observed_at"], p["reference_period"]), ("2026-09-25", "2026-09-25", "2026Q3"))

    def test_no_observations_is_an_error(self):
        with self.assertRaises(ValueError):
            ups.build_patch(ups.SPECS["nfp"], [], retrieved_at="T")


class SeriesFor(unittest.TestCase):
    def setUp(self):
        self.data = {
            "M2SL": [("2019-12-01", 100.0)] + [(f"2025-{m:02d}-01", 150.0) for m in range(1, 13)] + [("2026-01-01", 156.0)],
            "PAYEMS": [("2026-06-01", 158892.0), ("2026-07-01", 158913.0), ("2026-08-01", 159075.0)],
            "GDPC1": [("2025-04-01", 100.0), ("2025-07-01", 101.0), ("2025-10-01", 102.0), ("2026-01-01", 103.0), ("2026-04-01", 104.0)],
            "WLCFLPCL": [("2026-09-23", 6235.0)],
            "IR": [(f"2025-{m:02d}-01", 150.0) for m in range(1, 13)] + [("2026-01-01", 153.0)],
        }
        self.fred = lambda sid: self.data[sid]

    def test_m2_yoy_and_vs_2019(self):
        self.assertAlmostEqual(ups.series_for("m2_yoy", self.fred)[-1][1], 4.0)
        self.assertAlmostEqual(ups.series_for("m2_vs_2019", self.fred)[-1][1], 56.0)

    def test_nfp_is_the_monthly_change(self):
        self.assertEqual(ups.series_for("nfp", self.fred)[-1], ("2026-08-01", 162.0))

    def test_gdp_yoy_uses_four_quarters_back(self):
        self.assertAlmostEqual(ups.series_for("gdp_yoy", self.fred)[-1][1], 4.0)
        self.assertAlmostEqual(ups.series_for("gdp_qoq", self.fred)[-1][1], (104 / 103 - 1) * 100)

    def test_millions_become_billions_except_where_the_amounts_are_tiny(self):
        self.assertEqual(ups.series_for("discount_window", self.fred)[-1][1], 6.235)
        # FIMA repo is a few $M in a normal week; in $B it would read "$0.00B" every week
        self.assertEqual(ups.series_for("fima_repo", self.fred, [("2026-09-23", 255.0)])[-1][1], 255.0)
        p = ups.build_patch(ups.SPECS["fima_repo"], [("2026-09-23", 255.0)], retrieved_at="T")
        self.assertEqual((p["display"], p["unit"]), ("$255M", "mn_usd"))

    def test_fima_without_history_is_an_error(self):
        with self.assertRaises(ValueError):
            ups.series_for("fima_repo", self.fred, None)

    def test_import_price_yoy(self):
        self.assertAlmostEqual(ups.series_for("import_price_yoy", self.fred)[-1][1], 2.0)


def _usa():
    def ind(i, **kw):
        return {"id": i, "label_ko": i, "quality": "demo", "data_status": "demo", "source": "fixture_synth",
                "value": 1.0, "display": "1", "history": {"5y": {"dates": ["x"], "values": [1.0]}}, **kw}
    return {
        "indicators": [ind("nfp"), ind("gdp_yoy"), ind("gdp_qoq"), ind("gdp", source="derived"), ind("qra_coupon_bn"),
                       ind("qra_bill_bn"), ind("gdpnow")],
        "categories": {"growth": [{"id": "nfp", "display": "175K"}, {"id": "gdp", "display": "2.4% | 0.5%"}, {"id": "gdpnow", "display": "2.0%"}],
                       "liquidity": [{"id": "qra_coupon_bn"}]},
        "headlines": [{"id": "gdpnow", "display": "2.0%", "data_status": "demo"}],
    }


class Apply(unittest.TestCase):
    def patches(self):
        return {
            "nfp": ups.build_patch(ups.SPECS["nfp"], [("2026-07-01", 100.0), ("2026-08-01", 162.0)], retrieved_at="T1"),
            "gdp_yoy": ups.build_patch(ups.SPECS["gdp_yoy"], [("2026-04-01", 2.7)], retrieved_at="T1"),
            "gdp_qoq": ups.build_patch(ups.SPECS["gdp_qoq"], [("2026-04-01", 0.37)], retrieved_at="T1"),
            "gdpnow": ups.build_patch(ups.SPECS["gdpnow"], [("2026-07-01", 5.0796)], retrieved_at="T1"),
        }

    def test_indicators_chips_headlines_and_composite(self):
        usa = _usa()
        r = ups.apply_all(usa, self.patches(), retrieved_at="T1")
        by = {i["id"]: i for i in usa["indicators"]}
        self.assertEqual(by["nfp"]["quality"], "live")
        self.assertEqual(usa["categories"]["growth"][0]["display"], "162K")
        self.assertEqual(usa["headlines"][0]["display"], "5.1%")
        self.assertEqual(usa["headlines"][0]["data_status"], "live")
        self.assertEqual(by["gdp"]["display"], "2.7% | 0.4%")
        self.assertEqual(by["gdp"]["modes"]["qoq"]["id"], "gdp_qoq")
        self.assertEqual(usa["categories"]["growth"][1]["display"], "2.7% | 0.4%")
        self.assertIn("gdp", r["changed"])

    def test_legacy_synthetic_duplicates_are_removed_everywhere(self):
        usa = _usa()
        r = ups.apply_all(usa, self.patches(), retrieved_at="T1")
        self.assertEqual(sorted(r["removed"]), ["qra_bill_bn", "qra_coupon_bn"])
        self.assertNotIn("qra_coupon_bn", [i["id"] for i in usa["indicators"]])
        self.assertEqual(usa["categories"]["liquidity"], [])

    def test_a_second_identical_run_changes_nothing_and_keeps_retrieved_at(self):
        usa = _usa()
        ups.apply_all(usa, self.patches(), retrieved_at="T1")
        snapshot = copy.deepcopy(usa)
        again = self.patches()
        for p in again.values():
            p["retrieved_at"] = "T2"
        r = ups.apply_all(usa, again, retrieved_at="T2")
        self.assertEqual((r["changed"], r["removed"], r["summary_changed"]), ([], [], False))
        self.assertEqual(usa, snapshot)

    def test_a_series_not_fetched_leaves_its_card(self):
        usa = _usa()
        patches = self.patches()
        del patches["nfp"]
        ups.apply_all(usa, patches, retrieved_at="T1")
        by = {i["id"]: i for i in usa["indicators"]}
        self.assertEqual((by["nfp"]["quality"], by["nfp"]["source"]), ("demo", "fixture_synth"))

    def test_composite_waits_for_both_real_series(self):
        usa = _usa()
        patches = self.patches()
        del patches["gdp_qoq"]
        ups.apply_all(usa, patches, retrieved_at="T1")
        by = {i["id"]: i for i in usa["indicators"]}
        self.assertEqual(by["gdp"]["source"], "derived")


HTML_NOW = """<html><body><table>
<tr><th>Reserve Bank credit ...</th><th>Averages of daily figures</th><th>Wednesday Sep 23, 2026</th></tr>
<tr><td>Reserve Bank credit</td><td>6,701,637</td><td>+ 4,030</td><td>+ 141,150</td><td>6,700,760</td></tr>
<tr><td>Repurchase agreements 6</td><td>2</td><td>- 50</td><td>- 2</td><td>1</td></tr>
<tr><td>Foreign official</td><td>0</td><td>- 1</td><td>0</td><td>0</td></tr>
<tr><td>Others</td><td>2</td><td>- 49</td><td>- 2</td><td>1</td></tr>
</table></body></html>"""
HTML_2020 = HTML_NOW.replace("Wednesday Sep 23, 2026", "Wednesday Mar 25, 2020").replace(
    "<td>Foreign official</td><td>0</td><td>- 1</td><td>0</td><td>0</td>", "<td>Foreign official</td><td>1,000</td><td>+ 5</td><td>+ 9</td><td>60,000</td>")


class AutoLoans(unittest.TestCase):
    def test_millions_become_trillions_and_the_card_carries_a_growth_line(self):
        pts = ups.series_for("auto_loans", lambda sid: [("2026-03-01", 1559740.62), ("2026-06-01", 1574750.49)])
        self.assertAlmostEqual(pts[-1][1], 1.57475049)
        patch = ups.build_patch(ups.SPECS["auto_loans"], pts, retrieved_at="t")
        self.assertEqual((patch["display"], patch["reference_period"], patch["asof"]), ("$1.57T", "2026Q2", "2026-06-30"))
        self.assertTrue(patch["yoy_line"])

    def test_a_card_missing_from_the_pack_is_added_once_with_its_chip(self):
        usa = {"indicators": [], "categories": {"growth": [{"id": "nfp"}]}, "headlines": []}
        patch = ups.build_patch(ups.SPECS["auto_loans"], [("2026-06-01", 1.57)], retrieved_at="t")
        ups.apply_all(usa, {"auto_loans": patch}, retrieved_at="t")
        ups.apply_all(usa, {"auto_loans": patch}, retrieved_at="t")
        self.assertEqual([i["id"] for i in usa["indicators"]], ["auto_loans"])
        self.assertEqual([c["id"] for c in usa["categories"]["growth"]], ["nfp", "auto_loans"])
        self.assertEqual(usa["categories"]["growth"][1]["display"], "$1.57T")

    def test_no_patch_no_card(self):
        usa = {"indicators": [], "categories": {"growth": []}, "headlines": []}
        ups.apply_all(usa, {}, retrieved_at="t")
        self.assertEqual(usa["indicators"], [])


class RemoveIndicator(unittest.TestCase):
    def country(self):
        return {"indicators": [{"id": "export_yoy_vn", "label_ko": "수출 YoY"}, {"id": "gdp_yoy"}],
                "categories": {"growth": [{"id": "export_yoy_vn"}, {"id": "gdp_yoy"}], "liquidity": [{"id": "m2_yoy"}]},
                "headlines": [{"id": "export_yoy_vn"}]}

    def test_drops_the_indicator_its_chip_and_its_headline(self):
        c = self.country()
        self.assertTrue(ups.remove_indicator(c, "export_yoy_vn"))
        self.assertEqual([i["id"] for i in c["indicators"]], ["gdp_yoy"])
        self.assertEqual([ch["id"] for ch in c["categories"]["growth"]], ["gdp_yoy"])
        self.assertEqual([ch["id"] for ch in c["categories"]["liquidity"]], ["m2_yoy"])   # untouched category
        self.assertEqual(c["headlines"], [])

    def test_an_id_already_gone_is_a_no_op(self):
        c = self.country()
        ups.remove_indicator(c, "export_yoy_vn")
        self.assertFalse(ups.remove_indicator(c, "export_yoy_vn"))


class H41(unittest.TestCase):
    def test_wednesday_level_of_the_foreign_official_row(self):
        self.assertEqual(h41_fima.parse_release(HTML_NOW), {"wednesday": "2026-09-23", "foreign_official_mn": 0.0})

    def test_thousands_separator(self):
        self.assertEqual(h41_fima.parse_release(HTML_2020), {"wednesday": "2020-03-25", "foreign_official_mn": 60000.0})

    def test_other_foreign_official_rows_are_not_taken(self):
        # a 'Foreign official' line before the repo block (deposits, reverse repos) must not be read
        html = HTML_NOW.replace("<tr><td>Repurchase agreements 6",
                                "<tr><td>Foreign official</td><td>9</td><td>9</td><td>9</td><td>999</td></tr><tr><td>Repurchase agreements 6")
        self.assertEqual(h41_fima.parse_release(html)["foreign_official_mn"], 0.0)

    def test_missing_row_or_table_is_an_error(self):
        with self.assertRaises(ValueError):
            h41_fima.parse_release(HTML_NOW.replace("Foreign official", "Somebody else"))
        with self.assertRaises(ValueError):
            h41_fima.parse_release("<html><body>nothing</body></html>")

    def test_thursdays(self):
        days = h41_fima.thursdays(date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual(days, ["2026-09-03", "2026-09-10", "2026-09-17", "2026-09-24"])


if __name__ == "__main__":
    unittest.main()

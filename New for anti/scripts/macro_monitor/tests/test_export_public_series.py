"""Export amounts for Singapore (SingStat NODX), Israel (FRED goods exports) and Hong Kong (C&SD total
exports): macro_monitor.export_public_series."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import export_public_series as eps  # noqa: E402


def doc(*cols, row="4.2", unit="Thousand Dollars"):
    return {"Data": {"row": [{"seriesNo": row, "rowText": "Non-Oil", "uoM": unit,
                              "columns": [{"key": k, "value": v} for k, v in cols]}]}}


class SingStat(unittest.TestCase):
    def test_months_are_dated_and_sorted(self):
        out = eps.parse_singstat(doc(("2026 Aug", "19413566"), ("2026 Jul", "19,378,953"), ("1976 Jan", "379371")), "4.2")
        self.assertEqual(out, [("1976-01-01", 379371.0), ("2026-07-01", 19378953.0), ("2026-08-01", 19413566.0)])

    def test_a_value_that_is_not_a_number_is_skipped_not_zero(self):
        out = eps.parse_singstat(doc(("2026 Jul", "19378953"), ("2026 Aug", "na"), ("2026 Q3", "1")), "4.2")
        self.assertEqual(out, [("2026-07-01", 19378953.0)])

    def test_a_row_that_is_not_there_raises(self):
        with self.assertRaises(ValueError):
            eps.parse_singstat(doc(("2026 Aug", "1"), row="4.1"), "4.2")
        with self.assertRaises(ValueError):
            eps.parse_singstat(doc(("garbage", "1")), "4.2")


class HKGCsv(unittest.TestCase):
    def test_monthly_rows_are_dated_the_annual_row_is_skipped(self):
        csv = "CCYY,MM,obs_value,sd_value\n1952,,2899.0000000000,\n2026,7,672518.0000000000,\n2026,8,667851.0000000000,\n"
        self.assertEqual(eps.parse_hkg_csv(csv), [("2026-07-01", 672518.0), ("2026-08-01", 667851.0)])

    def test_a_malformed_row_is_skipped_not_a_crash(self):
        csv = "CCYY,MM,obs_value,sd_value\n2026,8,667851.0,\n2026,not-a-month,1.0,\ngarbage\n"
        self.assertEqual(eps.parse_hkg_csv(csv), [("2026-08-01", 667851.0)])

    def test_no_monthly_rows_raises(self):
        with self.assertRaises(ValueError):
            eps.parse_hkg_csv("CCYY,MM,obs_value,sd_value\n1952,,2899.0,\n")


class Series(unittest.TestCase):
    def test_hong_kong_hkd_million_becomes_billions(self):
        hk = next(e for e in eps.EXPORTS if e.iso3 == "HKG")
        out = eps.series_for(hk, hkg_csv=lambda: [("2026-07-01", 672518.0), ("2026-08-01", 667851.0)])
        self.assertEqual(out, [("2026-07-01", 672.518), ("2026-08-01", 667.851)])

    def test_singapore_thousand_dollars_become_billions(self):
        sg = next(e for e in eps.EXPORTS if e.iso3 == "SGP")
        out = eps.series_for(sg, singstat=lambda t, r: ([("2026-08-01", 19413566.0)], "Thousand Dollars"))
        self.assertEqual(out, [("2026-08-01", 19.413566)])

    def test_singapore_other_unit_is_refused_rather_than_rescaled(self):
        sg = next(e for e in eps.EXPORTS if e.iso3 == "SGP")
        with self.assertRaises(ValueError):
            eps.series_for(sg, singstat=lambda t, r: ([("2026-08-01", 19.4)], "Million Dollars"))

    def test_israel_dollars_become_billions(self):
        il = next(e for e in eps.EXPORTS if e.iso3 == "ISR")
        out = eps.series_for(il, fred=lambda sid: [("2026-06-01", 6120015000.0)] if sid == "XTEXVA01ILM667S" else [])
        self.assertEqual(out, [("2026-06-01", 6.120015)])


class Apply(unittest.TestCase):
    def country(self):
        return {"indicators": [{"id": "high_tech_export_yoy", "label_ko": "하이테크 수출 YoY", "unit": "%", "data_status": "demo",
                                "analog_ko": "한국 반도체 수출과 같은 growth 드라이버 슬롯."},
                               {"id": "gdp", "unit": "%", "data_status": "demo"}],
                "categories": {"growth": [{"id": "high_tech_export_yoy", "unit": "%", "analog_ko": "x"}]},
                "headlines": [], "data_status_summary": {"demo": 2}}

    def points(self):
        return [(f"{2020 + m // 12}-{m % 12 + 1:02d}-01", 5.0 + m * 0.01) for m in range(72)]

    def test_rate_card_becomes_an_amount_with_a_growth_line(self):
        il = next(e for e in eps.EXPORTS if e.iso3 == "ISR")
        c = self.country()
        patch = eps.build_patch(il, self.points(), retrieved_at="t")
        self.assertTrue(eps.apply(c, il, patch))
        by = {i["id"]: i for i in c["indicators"]}
        self.assertNotIn("high_tech_export_yoy", by)
        ind = by["export_il"]
        self.assertTrue(ind["yoy_line"])
        self.assertEqual((ind["unit"], ind["data_status"]), ("bn_usd", "live"))
        self.assertTrue(ind["display"].startswith("$") and ind["display"].endswith("B"))
        self.assertNotIn("analog_ko", ind)                          # "same slot as Korea's semiconductors" is gone
        chip = c["categories"]["growth"][0]
        self.assertEqual((chip["id"], chip["unit"], chip["display"]), ("export_il", "bn_usd", ind["display"]))
        self.assertNotIn("analog_ko", chip)
        self.assertEqual(c["data_status_summary"], {"live": 1, "demo": 1})

    def test_second_run_changes_nothing(self):
        il = next(e for e in eps.EXPORTS if e.iso3 == "ISR")
        c = self.country()
        eps.apply(c, il, eps.build_patch(il, self.points(), retrieved_at="t"))
        self.assertFalse(eps.apply(c, il, eps.build_patch(il, self.points(), retrieved_at="later")))
        self.assertEqual({i["id"]: i for i in c["indicators"]}["export_il"]["retrieved_at"], "t")

    def test_singapore_display_carries_its_currency(self):
        sg = next(e for e in eps.EXPORTS if e.iso3 == "SGP")
        self.assertEqual(eps.build_patch(sg, [("2026-08-01", 19.4136)], retrieved_at="t")["display"], "S$19.4B")

    def test_hong_kong_trade_yoy_becomes_an_exports_amount(self):
        hk = next(e for e in eps.EXPORTS if e.iso3 == "HKG")
        c = {"indicators": [{"id": "trade_yoy", "label_ko": "수출입 YoY", "unit": "%", "data_status": "demo"}],
             "categories": {"growth": [{"id": "trade_yoy", "unit": "%"}]}, "headlines": [], "data_status_summary": {"demo": 1}}
        patch = eps.build_patch(hk, self.points(), retrieved_at="t")
        self.assertTrue(eps.apply(c, hk, patch))
        by = {i["id"]: i for i in c["indicators"]}
        self.assertNotIn("trade_yoy", by)
        ind = by["export_hk"]
        self.assertTrue(ind["display"].startswith("HK$") and ind["display"].endswith("B"))
        self.assertEqual((ind["unit"], ind["data_status"]), ("bn_hkd", "live"))


class Ids(unittest.TestCase):
    def test_every_amount_card_is_drawn_as_bars(self):
        """macro.js draws MM_FLOW_IDS as bars; an amount left out would fall back to a line."""
        js = (Path(__file__).resolve().parents[2].parent / "macro.js").read_text(encoding="utf-8")
        flow = js[js.index("const MM_FLOW_IDS"):js.index("]);", js.index("const MM_FLOW_IDS"))]
        for e in eps.EXPORTS:
            self.assertIn(f"'{e.new_id}'", flow)
        for i in ("export_krw", "semi_export_krw"):
            self.assertIn(f"'{i}'", flow)


if __name__ == "__main__":
    unittest.main()

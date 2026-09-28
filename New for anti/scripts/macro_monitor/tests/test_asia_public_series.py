"""Hong Kong (C&SD CSVs), Singapore (SingStat) and Taiwan (CBC API): hk/sg/tw_public_series."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import hk_public_series as hks  # noqa: E402
from macro_monitor import sg_public_series as sgs  # noqa: E402
from macro_monitor import tw_public_series as tws  # noqa: E402


class CenStatD(unittest.TestCase):
    def test_suppressed_figures_and_annual_rows_are_skipped(self):
        csv = "CCYY,Q,obs_value,sd_value\n1961,,0.0000000000,9\n1961,1,0.0000000000,9\n2026,1,5.9000000000,104\n2026,2,4.3000000000,\n"
        self.assertEqual(hks.parse_censtatd(csv), [("2026-01-01", 5.9), ("2026-04-01", 4.3)])

    def test_month_column_may_come_first_and_classifications_filter(self):
        csv = "MM,CCYY,obs_value,sd_value\n,2004,0.0,9\n7,2026,4.5,102\n"
        self.assertEqual(hks.parse_censtatd(csv), [("2026-07-01", 4.5)])
        bop = "BOP_COMPONENT,CCYY,Q,obs_value,sd_value\nCRA,2026,2,96000.0,109\nFA,2026,2,-5000.0,\n"
        self.assertEqual(hks.parse_censtatd(bop, where={"BOP_COMPONENT": "CRA"}), [("2026-04-01", 96000.0)])

    def test_legend_decides_which_codes_suppress(self):
        legend = {"9": {"obs_value_suppressed": "1"}, "104": {"obs_value_suppressed": "0"}}
        self.assertEqual(hks.suppressed_codes(legend), frozenset({"9"}))
        self.assertIn("9", hks.suppressed_codes(None))            # snapshot when the legend is unreadable
        self.assertNotIn("104", hks.SUPPRESSED_FALLBACK)          # "revised" is a real figure

    def test_not_a_censtatd_csv_raises(self):
        with self.assertRaises(ValueError):
            hks.parse_censtatd("<html>blocked</html>")

    def test_current_account_is_in_billions(self):
        csv = "BOP_COMPONENT,CCYY,Q,obs_value,sd_value\nCRA,2026,2,96000.0,\n"
        self.assertEqual(hks.series_for("current_account", lambda name: csv, hks.SUPPRESSED_FALLBACK), [("2026-04-01", 96.0)])


def sg_doc(row_no, *cols, unit="Index"):
    return {"Data": {"row": [{"seriesNo": row_no, "rowText": "x", "uoM": unit,
                              "columns": [{"key": k, "value": v} for k, v in cols]}]}}


class SingStat(unittest.TestCase):
    def test_months_and_quarters_are_dated_annual_columns_skipped(self):
        self.assertEqual(sgs.period_key("2026 Aug"), "2026-08-01")
        self.assertEqual(sgs.period_key("2026 2Q"), "2026-04-01")
        self.assertIsNone(sgs.period_key("2026"))
        pts, unit = sgs.parse_row(sg_doc("1", ("2026 2Q", "155,942.7"), ("2026 1Q", "150000")), "1")
        self.assertEqual(pts, [("2026-01-01", 150000.0), ("2026-04-01", 155942.7)])

    def test_m2_yoy_is_never_computed_across_the_2021_change_of_definition(self):
        old = [(f"{y}-{m:02d}-01", 100.0 + i) for i, (y, m) in enumerate((y, m) for y in (2020, 2021) for m in range(1, 13)) if (y, m) <= (2021, 6)]
        new = [(f"{y}-{m:02d}-01", 90.0 + i) for i, (y, m) in enumerate((y, m) for y in (2021, 2022, 2023) for m in range(1, 13)) if (y, m) >= (2021, 7)]
        tables = {("M920281", "2"): (old, "Million Dollars"), ("M701111", "1.1"): (new, "Million Dollars")}
        out = dict(sgs.series_for("m2_yoy", lambda t, r: tables[(t, r)]))
        self.assertIn("2021-06-01", out)                          # old basis against old basis
        self.assertFalse(any("2021-07-01" <= d < "2022-07-01" for d in out))
        self.assertIn("2022-07-01", out)                          # new basis against new basis

    def test_current_account_unit_is_checked(self):
        with self.assertRaises(ValueError):
            sgs.series_for("current_account", lambda t, r: ([("2026-04-01", 1.0)], "Per Cent"))


def cbc_doc(rows, *tables):
    return {"meta": {}, "data": {"structure": {f"Table{i + 1}": [{"data": x} for x in t] for i, t in enumerate(tables)},
                                 "dataSets": rows}}


class Cbc(unittest.TestCase):
    def test_columns_are_the_product_of_the_tables_in_order(self):
        doc = cbc_doc([["2026M07", "702248", "7.42", "701550", "6.58"]], ["M2"], ["日平均", "期底"], ["金額", "年增率"])
        self.assertEqual(tws.columns(doc), ["M2|日平均|金額", "M2|日平均|年增率", "M2|期底|金額", "M2|期底|年增率"])
        self.assertEqual(tws.column(doc, "M2|日平均|年增率"), [("2026-07-01", 7.42)])

    def test_empty_cells_and_annual_rows_are_skipped(self):
        doc = cbc_doc([["2025", "1.9"], ["2026M06", "-"], ["2026M07", "1.90"], ["2026Q2", "2.0"]], ["x"])
        self.assertEqual(tws.column(doc, "x"), [("2026-04-01", 2.0), ("2026-07-01", 1.9)])
        with self.assertRaises(ValueError):
            tws.column(doc, "y")

    def test_export_card_is_an_amount_with_a_growth_line(self):
        doc = cbc_doc([["2025Q2", "150000.0"], ["2026Q2", "205698.0"]], ["商品-收入"])
        pts = tws.series_for("export_tw", lambda code: doc)
        self.assertEqual(pts, [("2025-04-01", 150.0), ("2026-04-01", 205.698)])
        patch = tws.build_patch("export_tw", pts, retrieved_at="t")
        self.assertTrue(patch["yoy_line"])
        self.assertEqual(patch["display"], "$205.7B")

    def test_rename_turns_the_rate_card_into_the_amount_card(self):
        c = {"indicators": [{"id": "export_yoy_tw", "unit": "%", "data_status": "demo"}],
             "categories": {"growth": [{"id": "export_yoy_tw", "unit": "%"}]}, "headlines": [], "data_status_summary": {}}
        patch = tws.build_patch("export_tw", [("2026-04-01", 205.698)], retrieved_at="t")
        tws.apply_all(c, {"export_tw": patch}, retrieved_at="t")
        self.assertEqual([i["id"] for i in c["indicators"]], ["export_tw"])
        self.assertEqual(c["categories"]["growth"][0]["unit"], "bn_usd")


if __name__ == "__main__":
    unittest.main()

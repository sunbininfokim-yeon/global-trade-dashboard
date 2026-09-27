"""Korean official-statistics series (macro_monitor.kr_public_series, macro_monitor.kosis)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date  # noqa: E402

from macro_monitor import ecos  # noqa: E402
from macro_monitor import kosis  # noqa: E402
from macro_monitor import kr_public_series as krs  # noqa: E402


def rows(c1, c1_nm, itm, itm_nm, prd_de, dt, unit="%"):
    return {"C1": c1, "C1_NM": c1_nm, "ITM_ID": itm, "ITM_NM": itm_nm, "PRD_DE": prd_de, "DT": dt, "UNIT_NM": unit}


class Client(unittest.TestCase):
    def test_series_is_picked_by_name_and_ordered(self):
        r = [rows("0", "총지수", "T3", "전년동월비", "202607", "2.1"), rows("0", "총지수", "T3", "전년동월비", "202606", "2.0"),
             rows("A", "상품", "T3", "전년동월비", "202607", "1.5"), rows("0", "총지수", "T1", "지수", "202607", "118.2")]
        self.assertEqual(kosis.series(r, prd_se="M", c1_nm="총지수", itm_nm="전년동월비"), [("2026-06-01", 2.0), ("2026-07-01", 2.1)])

    def test_names_ignore_spacing(self):
        r = [rows("QB", "농산물 및 석유류제외지수", "T3", "전년동월비", "202607", "2.4")]
        self.assertEqual(kosis.series(r, prd_se="M", c1_nm="농산물및석유류제외지수", itm_nm="전년동월비")[0][1], 2.4)

    def test_no_match_and_ambiguity_raise(self):
        r = [rows("0", "총지수", "T3", "전년동월비", "202607", "2.1")]
        with self.assertRaises(kosis.KosisError):
            kosis.series(r, prd_se="M", c1_nm="서비스", itm_nm="전년동월비")
        both = r + [rows("00", "총지수", "T3", "전년동월비", "202607", "2.2")]          # same name under two codes
        with self.assertRaises(kosis.KosisError):
            kosis.series(both, prd_se="M", c1_nm="총지수", itm_nm="전년동월비")

    def test_missing_values_are_skipped_not_zero(self):
        r = [rows("0", "총지수", "T3", "전년동월비", "202606", "-"), rows("0", "총지수", "T3", "전년동월비", "202607", "2,100.5")]
        self.assertEqual(kosis.series(r, prd_se="M", c1_nm="총지수", itm_nm="전년동월비"), [("2026-07-01", 2100.5)])

    def test_period_spelling(self):
        self.assertEqual(kosis.period_to_date("202607", "M"), "2026-07-01")
        self.assertEqual(kosis.period_to_date("202402", "Q"), "2024-06-01")

    def test_key_is_required_and_never_in_messages(self):
        import os
        old = os.environ.pop("KOSIS_API_KEY", None)
        try:
            with self.assertRaises(kosis.KosisError):
                kosis.api_key()
            os.environ["KOSIS_API_KEY"] = "secret-value-123"
            self.assertNotIn("secret-value-123", kosis._scrub("GET https://x/?apiKey=secret-value-123"))
        finally:
            os.environ.pop("KOSIS_API_KEY", None)
            if old is not None:
                os.environ["KOSIS_API_KEY"] = old


class ExportsInWon(unittest.TestCase):
    def test_unit_multipliers(self):
        self.assertEqual(krs.usd_multiplier("천달러"), 1e3)
        self.assertEqual(krs.usd_multiplier("백만 달러"), 1e6)
        with self.assertRaises(ValueError):
            krs.usd_multiplier("USD")

    def test_dollars_times_the_months_average_rate_in_trillions(self):
        usd = [("2026-06-01", 62_000_000.0), ("2026-07-01", 65_000_000.0)]           # thousand dollars
        fx = [("2026-06-01", 1500.0), ("2026-07-01", 1400.0)]
        out = krs.export_krw_tn("천달러", usd, fx)
        self.assertEqual([d for d, _ in out], ["2026-06-01", "2026-07-01"])
        self.assertAlmostEqual(out[0][1], 93.0)                                        # 62.0bn USD x 1500
        self.assertAlmostEqual(out[1][1], 91.0)

    def test_a_month_without_a_rate_is_left_out(self):
        usd = [("2026-07-01", 65_000_000.0), ("2026-08-01", 66_000_000.0)]
        self.assertEqual([d for d, _ in krs.export_krw_tn("천달러", usd, [("2026-07-01", 1400.0)])], ["2026-07-01"])


class Rename(unittest.TestCase):
    def test_indicator_chip_and_headline_follow_the_new_id(self):
        c = {"indicators": [{"id": "export_yoy_kr", "label_ko": "수출 YoY", "unit": "%"}, {"id": "ccsi"}],
             "categories": {"growth": [{"id": "export_yoy_kr"}, {"id": "ccsi"}]}, "headlines": [{"id": "export_yoy_kr"}]}
        changed = krs.rename_indicator(c, "export_yoy_kr", "export_krw", {"label_ko": "수출(원화 환산)", "unit": "tn_krw", "retrieved_at": "t"})
        self.assertTrue(changed)
        self.assertEqual([i["id"] for i in c["indicators"]], ["export_krw", "ccsi"])
        self.assertEqual(c["categories"]["growth"][0]["id"], "export_krw")
        self.assertEqual(c["headlines"][0]["id"], "export_krw")
        self.assertFalse(krs.rename_indicator(c, "export_yoy_kr", "export_krw", {"label_ko": "수출(원화 환산)", "unit": "tn_krw", "retrieved_at": "later"}))   # idempotent


ECOS_DOC = {"StatisticSearch": {"list_total_count": 3, "row": [
    {"TIME": "202606", "DATA_VALUE": "119.99", "UNIT_NAME": "2020=100"},
    {"TIME": "202607", "DATA_VALUE": "119.77", "UNIT_NAME": "2020=100"},
    {"TIME": "202608", "DATA_VALUE": "-", "UNIT_NAME": "2020=100"}]}}


class EcosClient(unittest.TestCase):
    def test_periods_by_cycle(self):
        self.assertEqual(ecos.period_to_date("20260923", "D"), "2026-09-23")
        self.assertEqual(ecos.period_to_date("202608", "M"), "2026-08-01")
        self.assertEqual(ecos.period_to_date("2026Q2", "Q"), "2026-04-01")
        with self.assertRaises(ValueError):
            ecos.period_to_date("2026", "M")

    def test_rows_become_points_and_a_dash_is_skipped(self):
        pts, unit = ecos.parse_rows(ECOS_DOC, "M")
        self.assertEqual((pts, unit), ([("2026-06-01", 119.99), ("2026-07-01", 119.77)], "2020=100"))

    def test_an_error_answer_raises_with_its_message(self):
        with self.assertRaises(ecos.EcosError) as cm:
            ecos.parse_rows({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}, "M")
        self.assertIn("INFO-200", str(cm.exception))

    def test_windows_and_the_key(self):
        import os

        self.assertEqual(ecos.window("Q", date(2026, 9, 27), 11), ("2015Q1", "2026Q3"))
        self.assertEqual(ecos.window("D", date(2026, 9, 27), 11), ("20150101", "20260927"))
        old = os.environ.pop("ECOS_API_KEY", None)
        try:
            with self.assertRaises(ecos.MissingKey):
                ecos.api_key()
            os.environ["ECOS_API_KEY"] = "abc-key-123"
            self.assertNotIn("abc-key-123", ecos._scrub("GET /api/abc-key-123/json"))
        finally:
            os.environ.pop("ECOS_API_KEY", None)
            if old is not None:
                os.environ["ECOS_API_KEY"] = old


def stub(**series):
    """A Sources whose ECOS reader answers from a dict {"stat/cycle/item[/item]": (points, unit)} and whose
    KOSIS reader answers from {"kosis/<tbl>": (points, unit)}."""
    def read(stat, cycle, items, mode="raw"):
        return series[f"{stat}/{cycle}/{'/'.join(items)}"]

    def kread(org, tbl, c1, c1_nm):
        return series[f"kosis/{tbl}"]
    return krs.Sources(ecos_read=read, kosis_read=kread, fred=lambda sid: series[sid])


class KoreaSeries(unittest.TestCase):
    def test_flows_and_balances_are_converted_to_the_unit_the_card_says(self):
        s = stub(**{"301Y013/M/000000": ([("2026-07-01", 42078.0)], "백만달러"), "732Y001/M/99": ([("2026-08-01", 442281314.0)], "천달러"),
                    "151Y001/Q/1000000": ([("2026-04-01", 2019785.3)], "십억원"), "103Y002/M/BCAA1": ([("2026-07-01", 635700.0)], "십억원")})
        self.assertAlmostEqual(krs.series_for("current_account", s)[-1][1], 42.078)          # million USD -> billion
        self.assertAlmostEqual(krs.series_for("fx_reserves", s)[-1][1], 442.281314)          # thousand USD -> billion
        self.assertAlmostEqual(krs.series_for("household_credit", s)[-1][1], 2019.7853)      # billion won -> trillion
        self.assertAlmostEqual(krs.series_for("bok_total_assets", s)[-1][1], 635.7)

    def test_yoy_from_an_index_and_a_quarterly_growth_rate(self):
        idx = [(f"2025-{m:02d}-01", 100.0) for m in range(1, 13)] + [("2026-01-01", 103.0)]
        gdp = [(f"2025-{m:02d}-01", 100.0 + i) for i, m in enumerate((1, 4, 7, 10))] + [("2026-01-01", 104.0)]
        s = stub(**{"901Y009/M/0": (idx, "2020=100"), "200Y106/Q/1400": (gdp, "십억원"), "200Y104/Q/1400": (gdp, "십억원")})
        self.assertAlmostEqual(krs.series_for("cpi_yoy", s)[-1][1], 3.0)
        self.assertAlmostEqual(krs.series_for("gdp_yoy", s)[-1][1], 4.0)                    # 104 vs 100 a year earlier
        self.assertAlmostEqual(krs.series_for("gdp_qoq", s)[-1][1], (104 / 103 - 1) * 100)

    def test_spreads_are_in_bp_and_the_rate_gap_is_dated_by_its_older_input(self):
        s = stub(**{"817Y002/D/010300000": ([("2026-09-23", 4.686)], "연%"), "817Y002/D/010200000": ([("2026-09-23", 4.006)], "연%"),
                    "722Y001/D/0101000": ([("2026-09-24", 3.0)], "연%"),
                    "DFEDTARU": [("2026-09-26", 4.0)]})
        self.assertAlmostEqual(krs.series_for("corp_spread_aa", s)[-1][1], 68.0)
        gap = krs.series_for("us_kr_rate_gap", s)
        self.assertEqual(gap, [("2026-09-24", 100.0)])                                     # 4.00 - 3.00 in bp, dated 09-24 not 09-26

    def test_monthly_sums_leave_out_the_running_month(self):
        pts = [("2026-08-03", 100.0), ("2026-08-31", -50.0), ("2026-09-01", 999.0), ("2026-09-23", 1.0)]
        self.assertEqual(krs.month_sums(pts, date(2026, 9, 27)), [("2026-08-01", 50.0)])

    def test_foreign_net_buying_adds_both_markets_in_trillion_won(self):
        s = stub(**{"802Y001/D/0030000": ([("2026-08-01", -100000.0)], "억원"), "802Y001/D/0113000": ([("2026-08-01", -20000.0)], "억원")})
        self.assertAlmostEqual(krs.series_for("foreign_equity_kr", s)[-1][1], -12.0)         # -120,000 100 million won = -12 trillion

    def test_exports_are_dollars_times_the_months_average_rate_and_need_that_rate(self):
        s = stub(**{"901Y118/M/T002": ([("2026-06-01", 101956159.0), ("2026-07-01", 98959099.0)], "천불"),
                    "EXKOUS": [("2026-06-01", 1529.4619), ("2026-07-01", 1486.0132)]})
        out = krs.series_for("export_krw", s)
        self.assertAlmostEqual(out[-1][1], 98959099 * 1e3 * 1486.0132 / 1e12)
        s2 = stub(**{"901Y118/M/T002": ([("2026-07-01", 98959099.0)], "천불"), "EXKOUS": [("2026-06-01", 1529.0)]})
        self.assertEqual(krs.series_for("export_krw", s2), [])                               # no July rate yet: nothing filled in

    def test_semiconductor_exports_are_a_won_amount_from_the_dollar_series(self):
        s = stub(**{"kosis/DT_092_115_2009_S023": ([("2026-07-01", 41015104140.0), ("2026-08-01", 46670721377.0)], "달러"),
                    "EXKOUS": [("2026-07-01", 1486.0132), ("2026-08-01", 1403.2186)]})
        out = krs.series_for("semi_export_krw", s)
        self.assertAlmostEqual(out[-1][1], 46670721377 * 1403.2186 / 1e12)                  # about 65.5 trillion won
        self.assertEqual(krs.usd_multiplier("달러"), 1.0)

    def test_the_running_month_is_dated_by_the_run_date(self):
        p = krs.build_patch("ccsi", [("2026-08-01", 104.5), ("2026-09-01", 106.6)], retrieved_at="t", today=date(2026, 9, 27))
        self.assertEqual((p["asof"], p["observed_at"], p["display"]), ("2026-09-27", "2026-09-27", "106.6"))
        self.assertEqual(p["history"]["5y"]["dates"][-1], "2026-09-27")
        done = krs.build_patch("bsi", [("2026-08-01", 77.0)], retrieved_at="t", today=date(2026, 9, 27))
        self.assertEqual(done["asof"], "2026-08-31")


class Cache(unittest.TestCase):
    def test_a_key_less_run_reads_the_cache_and_a_write_only_happens_on_change(self):
        import os
        import tempfile

        old = os.environ.pop("ECOS_API_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "c.json"
                cache = krs.load_cache(path)
                read = krs.ecos_reader(cache, {}, date(2026, 9, 27))
                with self.assertRaises(ecos.MissingKey):
                    read("901Y009", "M", ("0",))
                updates = {"901Y009/M/0/raw": {"points": [("2013-12-01", 1.0), ("2026-08-01", 120.05)], "unit": "2020=100"}}
                self.assertTrue(krs.save_cache(cache, updates, "t1", path))
                cache = krs.load_cache(path)
                self.assertEqual(krs.ecos_reader(cache, {}, date(2026, 9, 27))("901Y009", "M", ("0",)), ([("2026-08-01", 120.05)], "2020=100"))
                self.assertFalse(krs.save_cache(cache, updates, "t2", path))
                self.assertEqual(krs.load_cache(path)["retrieved_at"], "t1")
        finally:
            if old is not None:
                os.environ["ECOS_API_KEY"] = old


class KosisReader(unittest.TestCase):
    def test_a_key_less_run_reads_the_cached_kosis_series(self):
        import os

        old = os.environ.pop("KOSIS_API_KEY", None)
        try:
            cache = {"series": {"kosis/127/T/X": {"unit": "달러", "points": [["2026-08-01", 46670721377.0]]}}}
            read = krs.kosis_reader(cache, {}, date(2026, 9, 27))
            self.assertEqual(read("127", "T", "X", "반도체"), ([("2026-08-01", 46670721377.0)], "달러"))
            with self.assertRaises(kosis.MissingKey):
                read("127", "T", "OTHER", "반도체")                                        # nothing cached for it: the missing key surfaces
            self.assertTrue(issubclass(kosis.MissingKey, kosis.KosisError))
        finally:
            if old is not None:
                os.environ["KOSIS_API_KEY"] = old


class Apply(unittest.TestCase):
    def test_exports_card_becomes_an_amount_in_won_with_its_chip_and_the_gdp_chip_follows(self):
        def ind(i, status="demo", **kw):
            return {"id": i, "label_ko": i, "data_status": status, "quality": "demo", "unit": "%", **kw}
        kor = {"indicators": [ind("export_yoy_kr", label_ko="수출 YoY"), ind("gdp_yoy"), ind("gdp_qoq"), ind("gdp")],
               "categories": {"growth": [{"id": "export_yoy_kr"}, {"id": "gdp"}]}, "headlines": [], "data_status_summary": {"demo": 4}}
        gdp = [("2025-04-01", 100.0), ("2025-07-01", 100.5), ("2025-10-01", 101.0), ("2026-01-01", 101.5), ("2026-04-01", 102.0)]
        s = stub(**{"200Y106/Q/1400": (gdp, "십억원"), "200Y104/Q/1400": (gdp, "십억원"),
                    "901Y118/M/T002": ([("2026-07-01", 98959099.0)], "천불"), "EXKOUS": [("2026-07-01", 1486.0132)]})
        patches = {k: krs.build_patch(k, krs.series_for(k, s), retrieved_at="t", today=date(2026, 9, 27)) for k in ("gdp_yoy", "gdp_qoq", "export_krw")}
        r = krs.apply_all(kor, patches, retrieved_at="t")
        by = {i["id"]: i for i in kor["indicators"]}
        self.assertNotIn("export_yoy_kr", by)
        self.assertEqual(by["export_krw"]["display"], "147.1조원")
        self.assertEqual(kor["categories"]["growth"][0]["id"], "export_krw")
        self.assertEqual(kor["categories"]["growth"][0]["unit"], "tn_krw")           # the chip no longer says "%"
        self.assertTrue(by["export_krw"]["yoy_line"])                                # the drawer draws the growth line
        self.assertNotIn("yoy_line", by["gdp_yoy"])                                  # a rate is not given a second rate
        self.assertEqual(by["gdp"]["source"], "ecos:200Y106+200Y104")
        self.assertEqual(kor["data_status_summary"], {"live": 3, "demo": 1} if by["gdp"]["data_status"] == "demo" else {"live": 4})
        again = krs.apply_all(kor, patches, retrieved_at="later")
        self.assertEqual(again["changed"], [])


if __name__ == "__main__":
    unittest.main()

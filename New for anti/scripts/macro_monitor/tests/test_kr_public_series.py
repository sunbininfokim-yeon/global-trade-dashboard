"""Korean official-statistics series (macro_monitor.kr_public_series, macro_monitor.kosis)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


if __name__ == "__main__":
    unittest.main()

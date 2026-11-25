"""SEC companyfacts -> DART-shaped rows. Facts follow the companyfacts layout
(Walmart-style filer without a total-liabilities tag, 52/53-week years)."""
import unittest

from dart_kfa.sec_rows import annual_rows, fiscal_year_ends, kit_for_sic, report_periods, financial_kind_for_sic


def pt(val, end, start=None, form="10-K", fp="FY", filed="2026-03-01"):
    p = {"val": val, "end": end, "form": form, "fp": fp, "filed": filed}
    if start:
        p["start"] = start
    return p


YEARS = [("2021-02-01", "2022-01-30"), ("2022-01-31", "2023-01-29"), ("2023-01-30", "2024-01-28"),
         ("2024-01-29", "2025-01-26"), ("2025-01-27", "2026-01-25")]


def facts():
    rev = [pt(100 + 10 * i, e, s) for i, (s, e) in enumerate(YEARS)]
    rev.append(pt(999, "2025-04-27", "2025-01-27", form="10-Q", fp="Q1"))
    rev.append(pt(1, "2026-01-25", "2025-10-27", form="10-K"))           # a quarter inside the 10-K: not a year
    return {"cik": 1, "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": rev}},
        "NetIncomeLoss": {"units": {"USD": [pt(10 + i, e, s) for i, (s, e) in enumerate(YEARS)]}},
        "LiabilitiesAndStockholdersEquity": {"units": {"USD": [pt(500 + i, e) for i, (_, e) in enumerate(YEARS)]}},
        "StockholdersEquity": {"units": {"USD": [pt(200 + i, e) for i, (_, e) in enumerate(YEARS)]}},
        "LiabilitiesCurrent": {"units": {"USD": [pt(100, e) for _, e in YEARS]}},
        "EarningsPerShareBasic": {"units": {"USD/shares": [pt(1.5, e, s) for s, e in YEARS]}},
    }}}


class SecRows(unittest.TestCase):
    def test_fiscal_year_ends_take_one_year_durations(self):
        self.assertEqual(fiscal_year_ends(facts()), [e for _, e in YEARS])

    def test_rows_cover_five_years_with_derived_liabilities(self):
        f = facts()
        out = annual_rows(f, fiscal_year_ends(f))
        self.assertEqual(sorted(out), [2024, 2026])
        rows = {r["account_id"]: r for r in out[2026]}
        self.assertEqual((rows["ifrs-full_Revenue"]["thstrm_amount"], rows["ifrs-full_Revenue"]["bfefrmtrm_amount"]), ("140", "120"))
        self.assertEqual(rows["ifrs-full_Liabilities"]["thstrm_amount"], "300.0")      # 504 - 204 (equity fallback)
        self.assertTrue(rows["ifrs-full_Liabilities"]["account_nm"].startswith("derived:"))
        self.assertEqual(rows["ifrs-full_NoncurrentLiabilities"]["thstrm_amount"], "200.0")
        self.assertEqual(rows["ifrs-full_BasicEarningsLossPerShare"]["thstrm_amount"], "1.5")

    def test_report_periods_use_actual_start(self):
        rp = report_periods(facts(), "2026-01-25")
        self.assertEqual(rp["FY"], {"start": "2025-01-27", "end": "2026-01-25"})
        self.assertEqual(rp["Q1"]["end"], "2025-04-27")

    def test_sic_kits(self):
        self.assertEqual([kit_for_sic(x) for x in (3674, 3571, 7372, 6021, 3721, 5331, 2834, 3999, 9999, None)],
                         ["semiconductor", "it_hardware", "it_services", "financial", "aerospace_defense",
                          "retail_wholesale", "pharma_bio", "manufacturing", "general", "general"])
        self.assertEqual((financial_kind_for_sic(6021), financial_kind_for_sic(6311), financial_kind_for_sic(7372)),
                         ("basel", "kics", None))


if __name__ == "__main__":
    unittest.main()

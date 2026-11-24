from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import cn_official as cn  # noqa: E402

RELEASE = """<p>Table 2 Year-on-Year Growth Rate of GDP</p><p>Unit: %</p>
<table><tr><td>Year</td><td>Q1</td><td>Q2</td><td>Q3</td><td>Q4</td></tr>
<tr><td>2024</td><td>5.3</td><td>4.7</td><td>4.6</td><td>5.4</td></tr>
<tr><td>2025</td><td>5.4</td><td>5.2</td><td>4.8</td><td>4.5</td></tr>
<tr><td>2026</td><td>5.0</td><td>4.3</td><td>4.5</td><td></td></tr></table>
<p>Note: The year-on-year growth rate refers to ...</p>"""

LIST = '<li><a href="./202610/t20261021_1965671.html">17.Preliminary Accounting Results of GDP for the Third Quarter of 2026</a></li>'


class Nbs(unittest.TestCase):
    def test_table_two_by_quarter_and_open_quarters_skipped(self):
        pts = cn.parse_gdp_table(RELEASE)
        self.assertEqual(pts[0], ("2024-01-01", 5.3))
        self.assertEqual(pts[-1], ("2026-07-01", 4.5))
        self.assertEqual(len(pts), 11)

    def test_release_link_found_on_the_list(self):
        url = cn.find_gdp_release(lambda u: LIST if u.endswith("index.html") else "")
        self.assertEqual(url, "https://www.stats.gov.cn/english/PressRelease/202610/t20261021_1965671.html")

    def test_missing_table_raises(self):
        with self.assertRaises(ValueError):
            cn.parse_gdp_table("<p>nothing</p>")


SAFE_LIST = (
    '<a href="/en/2021/0203/2045.html" target="_blank">Official Reserve Assets (2026)</a>'
    '<a href="/en/2021/0203/1799.html" target="_blank">Data Template on International Reserves (2026)</a>'
    '<a href="/en/2021/0203/2386.html" target="_blank">Official Reserve Assets (2025)</a>'
    '<a href="/en/2021/0203/2385.html" target="_blank">Official Reserve Assets (2025)</a>'
    '<a href="/en/2021/0203/2280.html" target="_blank">Official Reserve Assets (2024)</a>')


def _xlsx(header, total):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["\xa0Official reserve assets"])
    ws.append(["Item", *header])
    ws.append(["1. Foreign currency reserves", "34000.00\xa0", "24600.00\xa0"])
    ws.append(["\xa0\xa0\xa0\xa0合计", *total])
    ws.append(["\xa0\xa0Total"])
    wb.create_sheet("Sheet2")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Safe(unittest.TestCase):
    def test_newest_two_years_found(self):
        got = cn.find_reserve_files(lambda u: SAFE_LIST if u.endswith("index.html") else "")
        self.assertEqual(got, [(2026, "https://www.safe.gov.cn/en/2021/0203/2045.html"),
                               (2025, "https://www.safe.gov.cn/en/2021/0203/2386.html")])

    def test_usd_total_under_each_month_october_as_text_or_number(self):
        # USD and SDR columns per month; the label sits over the USD one. 2026.1 as a number is October.
        data = _xlsx([2026.09, None, "2026.10", None, 2026.11, None],
                     ["37894.30\xa0", "27800.00\xa0", "37775.60\xa0", "27700.00\xa0", None, None])
        self.assertEqual(cn.parse_reserves_xlsx(data), [("2026-09-01", 3789.43), ("2026-10-01", 3777.56)])
        data = _xlsx([2017.09, None, 2017.1, None], ["32043.81", "22673.11", "32039.86", "22809.27"])
        self.assertEqual(cn.parse_reserves_xlsx(data), [("2017-09-01", 3204.38), ("2017-10-01", 3203.99)])

    def test_safe_months_replace_imf_and_older_months_stay(self):
        card = {"history": {"10y": {"dates": ["2025-11-30", "2025-12-31"], "values": [3723.79, 3748.75]}}}
        got = cn.merge_history(card, [("2025-12-01", 3744.31), ("2026-01-01", 3836.28)])
        self.assertEqual(got, [("2025-11-01", 3723.79), ("2025-12-01", 3744.31), ("2026-01-01", 3836.28)])

    def test_patch_reads_safe_and_last_month(self):
        p = cn.build_reserves_patch([("2026-09-01", 3789.43), ("2026-10-01", 3777.56)],
                                    ["https://www.safe.gov.cn/en/2021/0203/2045.html"], retrieved_at="2026-11-24T00:00:00Z")
        self.assertEqual((p["display"], p["reference_period"], p["source"]), ("$3,778B", "2026-10", "safe:official_reserve_assets"))


    def test_cache_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.json"
            self.assertIsNone(cn.load_reserves_cache(f))
            cn.save_reserves_cache(f, [("2026-10-01", 3777.56)], ["u"], "2026-11-24T00:00:00Z")
            self.assertEqual(cn.load_reserves_cache(f), ([("2026-10-01", 3777.56)], ["u"], "2026-11-24T00:00:00Z"))


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

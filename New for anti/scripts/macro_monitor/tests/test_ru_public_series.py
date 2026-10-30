"""Russia: Bank of Russia and Moscow Exchange sources (macro_monitor.ru_public_series)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import ru_public_series as rus  # noqa: E402


class Parsers(unittest.TestCase):
    def test_official_rates_are_per_unit_with_comma_decimals(self):
        xml = ('<ValCurs><Record Date="01.08.2026" Id="R01235"><Nominal>1</Nominal><Value>79,4637</Value></Record>'
               '<Record Date="28.09.2026" Id="R01235"><Nominal>10</Nominal><Value>125,6</Value></Record></ValCurs>')
        out = rus.parse_dynamic(xml)
        self.assertEqual([d for d, _ in out], ["2026-08-01", "2026-09-28"])
        self.assertAlmostEqual(out[0][1], 79.4637)
        self.assertAlmostEqual(out[1][1], 12.56)                  # nominal 10
        with self.assertRaises(ValueError):
            rus.parse_dynamic("<ValCurs/>")

    def test_key_rate_records(self):
        xml = "<KR><DT>2026-09-28T00:00:00+03:00</DT><Rate>14.00</Rate></KR><KR><DT>2026-09-25T00:00:00+03:00</DT><Rate>14.00</Rate></KR>"
        self.assertEqual(rus.parse_keyrate(xml), [("2026-09-25", 14.0), ("2026-09-28", 14.0)])

    def test_reserves_on_the_first_are_the_previous_month_end(self):
        xml = "<mr><D0>2026-09-01T00:00:00+03:00</D0><p1>769022.00</p1><p2>435539.00</p2></mr>"
        self.assertEqual(rus.parse_mrrf(xml), [("2026-08-01", 769022.0)])
        self.assertEqual(rus.prev_month("2026-01-01"), "2025-12-01")

    def test_inflation_table_takes_the_inflation_column(self):
        html = ("<table><tr><th>Дата</th><th>Ключевая ставка</th><th>Инфляция</th><th>Цель</th></tr>"
                "<tr><td>08.2026</td><td>14,00</td><td>6,33</td><td>4,00</td></tr>"
                "<tr><td>09.2013</td><td>5,50</td><td>6,14</td><td> — </td></tr></table>")
        self.assertEqual(rus.parse_infl(html), [("2013-09-01", 6.14), ("2026-08-01", 6.33)])

    def test_zero_coupon_curve_ten_year_point_and_a_day_without_a_curve(self):
        html = ("<tr><td>Срок до погашения, лет</td><td>5.00</td><td>10.00</td></tr>"
                "<tr><td>Доходность, % годовых</td><td>16.18</td><td>16.65</td></tr>")
        self.assertEqual(rus.parse_zcyc(html), 16.65)
        self.assertIsNone(rus.parse_zcyc(html.replace("16.65", " — ")))

    def test_monthly_candles_take_the_newest_point_from_the_daily_history(self):
        monthly = {"candles": {"data": [["2026-08-01 00:00:00", "2026-08-31 23:59:59", 2178.87],
                                        ["2026-09-01 00:00:00", "2026-09-30 23:59:59", 2240.0]]}}
        daily = {"history": {"data": [["2026-09-25", 2273.87], ["2026-09-28", 2246.3]]}}
        pts, last = rus.parse_candles(monthly, daily)
        self.assertEqual(pts[-1], ("2026-09-01", 2246.3))
        self.assertEqual(last, "2026-09-28")                     # not the candle's 09-30


class OfzCache(unittest.TestCase):
    def test_only_missing_months_and_the_running_month_are_asked_for(self):
        cache = {"ofz_10y": {"2026-07-01": ["2026-07-31", 15.9]}}
        asked = []

        def zcyc(day):
            asked.append(day)
            return None if day.weekday() >= 5 else 16.0 + day.day / 100

        start = rus.HISTORY_FROM
        rus.HISTORY_FROM = date(2026, 7, 1)
        try:
            pts, last, changed = rus.ofz_monthly(cache, date(2026, 9, 28), fetch=zcyc, pause=0)
        finally:
            rus.HISTORY_FROM = start
        self.assertTrue(changed)
        self.assertNotIn(date(2026, 7, 31), asked)             # kept
        self.assertIn(date(2026, 8, 31), asked)                # missing
        self.assertEqual(cache["ofz_10y"]["2026-08-01"][0], "2026-08-31")
        self.assertEqual(last, "2026-09-28")
        self.assertEqual([d for d, _ in pts], ["2026-07-01", "2026-08-01", "2026-09-01"])


if __name__ == "__main__":
    unittest.main()

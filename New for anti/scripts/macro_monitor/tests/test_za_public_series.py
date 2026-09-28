"""South Africa: SARB web API + FRED + World Bank Pink Sheet (macro_monitor.za_public_series)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import za_public_series as zas  # noqa: E402


def sarb_doc(*rows):
    return [{"Period": f"{d}T00:00:00", "Value": v, "Timeseries": "X", "Description": "x"} for d, v in rows]


class Parsing(unittest.TestCase):
    def test_sarb_answer_is_newest_first_and_comes_out_ascending(self):
        out = zas.parse_sarb(sarb_doc(("2026-08-31", 4.4), ("2026-07-31", 4.3), ("2026-06-30", None)))
        self.assertEqual(out, [("2026-07-31", 4.3), ("2026-08-31", 4.4)])

    def test_sarb_answer_that_is_not_a_list_raises(self):
        with self.assertRaises(ValueError):
            zas.parse_sarb({"Message": "blocked"})
        with self.assertRaises(ValueError):
            zas.parse_sarb([])

    def test_pink_sheet_link_is_taken_from_the_page(self):
        html = '<a href="https://thedocs.worldbank.org/en/doc/abc-0050012026/related/CMO-Historical-Data-Monthly.xlsx">x</a>'
        self.assertTrue(zas.pink_sheet_url(html).endswith("CMO-Historical-Data-Monthly.xlsx"))
        with self.assertRaises(ValueError):
            zas.pink_sheet_url("<html>no link</html>")


class Joining(unittest.TestCase):
    def test_override_replaces_the_shared_months_extend_only_adds_later_ones(self):
        hist = [("2026-06-01", 1.0), ("2026-07-01", 2.0)]
        recent = [("2026-07-01", 2.5), ("2026-08-01", 3.0)]
        self.assertEqual(zas.join(hist, recent, "override"), [("2026-06-01", 1.0), ("2026-07-01", 2.5), ("2026-08-01", 3.0)])
        self.assertEqual(zas.join(hist, recent, "extend"), [("2026-06-01", 1.0), ("2026-07-01", 2.0), ("2026-08-01", 3.0)])

    def test_daily_observations_collapse_to_the_months_last_and_keep_the_day(self):
        pts, last = zas.to_monthly([("2026-08-28", 8.8), ("2026-09-24", 8.9), ("2026-09-25", 8.96)])
        self.assertEqual(pts, [("2026-08-01", 8.8), ("2026-09-01", 8.96)])
        self.assertEqual(last, "2026-09-25")

    def test_a_missing_month_is_a_gap_not_a_filled_value(self):
        out = zas.with_gaps([("2023-11-01", 5.0), ("2024-02-01", 6.0)])
        self.assertEqual(out, [("2023-11-01", 5.0), ("2023-12-01", None), ("2024-01-01", None), ("2024-02-01", 6.0)])
        q = zas.with_gaps([("2025-10-01", 1.0), ("2026-04-01", 2.0)], months=3)
        self.assertEqual([d for d, _ in q], ["2025-10-01", "2026-01-01", "2026-04-01"])

    def test_policy_rate_is_the_rate_in_force_at_each_month_end(self):
        changes = [("2025-11-21", 6.75), ("2026-05-29", 7.0), ("2026-09-25", 7.25)]
        out = dict(zas.step_monthly(changes, date(2026, 9, 29)))
        self.assertEqual(out["2025-11-01"], 6.75)
        self.assertEqual(out["2026-04-01"], 6.75)
        self.assertEqual(out["2026-05-01"], 7.0)            # decided on the 29th: in force at the month end
        self.assertEqual(out["2026-09-01"], 7.25)            # running month: in force today

    def test_chained_yoy_needs_four_consecutive_quarters(self):
        q = [("2025-01-01", 1.0), ("2025-04-01", 1.0), ("2025-07-01", 1.0), ("2025-10-01", 1.0), ("2026-04-01", 1.0)]
        out = dict(zas.chain_yoy(q))
        self.assertAlmostEqual(out["2025-10-01"], (1.01 ** 4 - 1) * 100)
        self.assertNotIn("2026-04-01", out)                  # 2026Q1 is missing


class SarbCache(unittest.TestCase):
    def test_answers_accumulate_and_the_cache_covers_an_unreachable_site(self):
        cache = {"series": {"MMRD002A": [["2026-08-01", 7.0]]}}
        updates = {}
        read = zas.sarb_reader(cache, updates, fetch=lambda code: [("2026-09-28", 7.25)], pause=0)
        self.assertEqual(read("MMRD002A"), [("2026-08-01", 7.0), ("2026-09-28", 7.25)])
        self.assertIn("MMRD002A", updates)

        def blocked(code):
            raise RuntimeError("403")
        read2 = zas.sarb_reader(cache, {}, fetch=blocked, pause=0)
        self.assertEqual(read2("MMRD002A"), [("2026-08-01", 7.0)])
        with self.assertRaises(zas.SarbUnavailable):
            read2("NEVERSEEN")


class Series(unittest.TestCase):
    def src(self, **fred):
        sarb = {
            "CPI1000F": [("2026-07-31", 4.3), ("2026-08-31", 4.4)],
            "MRDREPOR": [("2026-05-29", 7.0), ("2026-09-25", 7.25)],
            "MMRD002A": [("2026-09-28", 7.25)],
            "CMJD004A": [("2026-09-25", 8.96)],
        }
        return zas.Sources(sarb=lambda c: sarb[c], fred=lambda i: fred[i], pink=lambda: {}, today=date(2026, 9, 29))

    def test_cpi_history_from_fred_is_overridden_by_sarb(self):
        idx = [(f"2025-{m:02d}-01", 100 + m) for m in range(1, 13)] + [(f"2026-{m:02d}-01", 104 + m) for m in range(1, 8)]
        pts, last = zas.series_for("cpi_yoy", self.src(ZAFCPIALLMINMEI=idx))
        by = dict(pts)
        self.assertEqual(by["2026-07-01"], 4.3)
        self.assertEqual(by["2026-08-01"], 4.4)
        self.assertIsNone(last)

    def test_ten_year_takes_sarbs_day_only_after_the_oecd_months(self):
        pts, last = zas.series_for("sagb_10y", self.src(IRLTLT01ZAM156N=[("2026-07-01", 8.7), ("2026-08-01", 8.75)]))
        self.assertEqual(pts[-1], ("2026-09-01", 8.96))
        self.assertEqual(last, "2026-09-25")

    def test_policy_rate_ends_with_the_latest_daily_value_dated_by_its_day(self):
        pts, last = zas.series_for("sarb_repo", self.src(IRSTCB01ZAM156N=[("2023-12-01", 8.25)]))
        self.assertEqual(pts[-1], ("2026-09-01", 7.25))
        self.assertEqual(last, "2026-09-28")
        patch = zas.build_patch("sarb_repo", pts, last, retrieved_at="t")
        self.assertEqual(patch["asof"], "2026-09-28")
        self.assertEqual(patch["history"]["10y"]["dates"][-1], "2026-09-28")


if __name__ == "__main__":
    unittest.main()

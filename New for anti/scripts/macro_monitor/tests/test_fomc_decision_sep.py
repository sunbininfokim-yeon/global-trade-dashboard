"""Offline tests for decision parsing and the SEP Table 1 parser.

Fixtures are trimmed from the real 2026-09-16 (four projection years + longer
run) and 2026-06-17 (three + longer run) projection pages, fetched
2026-09-24, kept literal so they run without the Fed's site.
"""
from __future__ import annotations

import unittest

from macro_monitor.fomc_collect.decision import parse_decision
from macro_monitor.fomc_collect.sep import parse_sep_summary


def _table(header_years: list[str], rows: list[list[str]]) -> str:
    def tr(cells):
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    top = tr(["Variable", "Median 1", "Central Tendency 2", "Range 3"])
    return "<html><body><table>" + top + tr(header_years * 3) + "".join(tr(r) for r in rows) + "</table></body></html>"


class TestParseDecision(unittest.TestCase):
    def test_raise_derives_the_prior_range_from_the_stated_step(self):
        d = parse_decision(
            "The Committee decided to raise the target range for the federal funds rate "
            "by 1/4 percentage point to 3-3/4 to 4 percent, in support of the dual mandate."
        )
        self.assertEqual((d["action"], d["change_bp"]), ("raise", 25))
        self.assertEqual((d["range_low"], d["range_high"]), (3.75, 4.0))
        self.assertEqual((d["prior_range_low"], d["prior_range_high"]), (3.5, 3.75))

    def test_lower_with_non_breaking_hyphens(self):
        d = parse_decision(
            "the Committee decided to lower the target range for the federal funds rate "
            "by 1/4 percentage point to 4 to 4‑1/4 percent."
        )
        self.assertEqual((d["action"], d["change_bp"]), ("lower", -25))
        self.assertEqual((d["range_low"], d["range_high"]), (4.0, 4.25))
        self.assertEqual((d["prior_range_low"], d["prior_range_high"]), (4.25, 4.5))

    def test_maintain_has_no_step_and_same_prior_range(self):
        d = parse_decision(
            "The Committee decided to maintain the target range for the federal funds rate "
            "at 3-1/2 to 3-3/4 percent."
        )
        self.assertEqual((d["action"], d["change_bp"]), ("maintain", 0))
        self.assertEqual((d["prior_range_low"], d["prior_range_high"]), (3.5, 3.75))

    def test_half_point_move(self):
        d = parse_decision(
            "The Committee decided to lower the target range for the federal funds rate "
            "by 1/2 percentage point to 4-3/4 to 5 percent."
        )
        self.assertEqual(d["change_bp"], -50)

    def test_missing_decision_sentence_is_none_not_a_guess(self):
        self.assertIsNone(parse_decision("Economic activity is expanding at a solid pace."))


class TestParseSep(unittest.TestCase):
    def test_four_year_layout_with_blank_prior_cells_and_footnote(self):
        years = ["2026", "2027", "2028", "2029", "Longer run"]
        rows = [
            ["Change in real GDP", "2.3", "2.4", "2.2", "2.1", "2.0"] + ["2.2–2.4"] * 5 + ["2.1–2.6"] * 5,
            ["June projection", "2.2", "2.3", "2.2", "", "2.0"] + ["2.0–2.3"] * 5 + ["1.8–2.6"] * 5,
            ["Unemployment rate", "4.1", "4.1", "4.1", "4.1", "4.2"] + ["4.1–4.2"] * 5 + ["4.0–4.3"] * 5,
            ["PCE inflation", "3.7", "2.3", "2.1", "2.0", "2.0"] + ["3.5–3.7"] * 5 + ["2.9–3.8"] * 5,
            ["Core PCE inflation 4", "3.4", "2.5", "2.2", "2.0", ""] + ["3.3–3.4"] * 5 + ["2.8–3.5"] * 5,
            ["Federal funds rate", "4.1", "4.1", "3.9", "3.6", "3.2"] + ["4.1–4.4"] * 5 + ["3.6–4.6"] * 5,
            ["June projection", "3.8", "3.6", "3.4", "", "3.1"] + ["3.6–4.1"] * 5 + ["3.1–4.4"] * 5,
        ]
        out = parse_sep_summary(_table(years, rows), meeting_date="2026-09-16", source_url="x")
        self.assertEqual(out["years"], years)
        by_id = {v["id"]: v for v in out["variables"]}
        self.assertEqual(by_id["gdp"]["median"]["2026"], 2.3)
        self.assertEqual(by_id["gdp"]["prior_period"], "June")
        self.assertIsNone(by_id["gdp"]["prior_median"]["2029"])  # blank in the prior SEP, not zero
        self.assertIsNone(by_id["core_pce"]["median"]["Longer run"])
        self.assertEqual(by_id["core_pce"]["label"], "Core PCE inflation")  # footnote marker dropped
        self.assertEqual(by_id["fed_funds_rate"]["median"]["2026"], 4.1)
        self.assertEqual(by_id["fed_funds_rate"]["prior_median"]["2026"], 3.8)

    def test_three_year_layout(self):
        years = ["2026", "2027", "2028", "Longer run"]
        one = lambda label, med: [label, *med] + ["1.0–2.0"] * 4 + ["0.5–2.5"] * 4  # noqa: E731
        rows = [
            one("Change in real GDP", ["2.2", "2.3", "2.2", "2.0"]),
            one("Unemployment rate", ["4.3", "4.3", "4.2", "4.2"]),
            one("PCE inflation", ["3.6", "2.3", "2.0", "2.0"]),
            one("Core PCE inflation", ["3.3", "2.5", "2.1", ""]),
            one("Federal funds rate", ["3.8", "3.6", "3.4", "3.1"]),
            one("March projection", ["3.4", "3.1", "3.1", "3.1"]),
        ]
        out = parse_sep_summary(_table(years, rows), meeting_date="2026-06-17", source_url="x")
        self.assertEqual(out["years"], years)
        ffr = next(v for v in out["variables"] if v["id"] == "fed_funds_rate")
        self.assertEqual(ffr["prior_period"], "March")
        self.assertEqual(ffr["prior_median"]["Longer run"], 3.1)

    def test_a_table_missing_a_variable_raises_instead_of_storing_half_a_sep(self):
        years = ["2026", "2027", "2028", "Longer run"]
        rows = [["Change in real GDP", "2.2", "2.3", "2.2", "2.0"] + ["1–2"] * 4 + ["0–3"] * 4]
        with self.assertRaises(ValueError):
            parse_sep_summary(_table(years, rows), meeting_date="2026-06-17", source_url="x")


if __name__ == "__main__":
    unittest.main()

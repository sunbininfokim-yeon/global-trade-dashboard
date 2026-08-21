"""Offline regression tests for macro_monitor.fomc_collect.parse.

Fixtures are trimmed excerpts of real federalreserve.gov pages (fetched
2026-08-21), kept as literal strings here rather than network fixtures so
these run without a live call and catch a regex regression even if the
Fed's site is unreachable.
"""
from __future__ import annotations

import unittest

from macro_monitor.fomc_collect.parse import parse_beige_book_summary, parse_statement

_HTML = lambda body: f"<html><body><div>{body}</div></body></html>"  # noqa: E731


class TestParseStatement(unittest.TestCase):
    def test_format_a_unanimous(self):
        html = _HTML(
            "The Committee decided to maintain the target range. "
            "Voting for the monetary policy action were Jerome H. Powell, Chair; "
            "John C. Williams, Vice Chair; Michael S. Barr; and Christopher J. Waller. "
            "For media inquiries, please email media@frb.gov."
        )
        row = parse_statement(html, meeting_date="2025-01-29", source_url="x")
        self.assertTrue(row["parsed_ok"])
        self.assertEqual(row["vote_for"], 4)
        self.assertEqual(row["vote_against"], 0)
        self.assertEqual(row["dissenters"], [])
        self.assertIn("Jerome H. Powell, Chair", row["voters_for"])

    def test_format_a_single_dissenter(self):
        html = _HTML(
            "Voting for the monetary policy action were Jerome H. Powell, Chair; "
            "John C. Williams, Vice Chair; and Michael S. Barr. "
            "Voting against this action was Stephen I. Miran, who preferred to lower "
            "the target range for the federal funds rate by 1/4 percentage point at this meeting. "
            "For media inquiries, please email media@frb.gov."
        )
        row = parse_statement(html, meeting_date="2026-03-18", source_url="x")
        self.assertTrue(row["parsed_ok"])
        self.assertEqual(row["vote_for"], 3)
        self.assertEqual(row["vote_against"], 1)
        self.assertEqual(row["dissenters"], [{"name": "Stephen I. Miran", "dissent_direction": "easier"}])

    def test_format_a_two_dissent_groups_different_directions(self):
        # Real shape from 2025-12-10: one dissenter preferring a bigger cut,
        # two others preferring no change -- two groups, two directions.
        html = _HTML(
            "Voting for the monetary policy action were Jerome H. Powell, Chair; and Michael S. Barr. "
            "Voting against this action were Stephen I. Miran, who preferred to lower the target range "
            "for the federal funds rate by 1/2 percentage point at this meeting; and Austan D. Goolsbee "
            "and Jeffrey R. Schmid, who preferred no change to the target range for the federal funds rate "
            "at this meeting. "
            "For media inquiries, please email media@frb.gov."
        )
        row = parse_statement(html, meeting_date="2025-12-10", source_url="x")
        self.assertTrue(row["parsed_ok"])
        by_name = {d["name"]: d["dissent_direction"] for d in row["dissenters"]}
        self.assertEqual(by_name["Stephen I. Miran"], "easier")
        self.assertEqual(by_name["Austan D. Goolsbee"], "other_public_dissent")
        self.assertEqual(by_name["Jeffrey R. Schmid"], "other_public_dissent")

    def test_format_b_oxford_comma_dissenters(self):
        # Real shape from 2026-07-29: three names joined by an Oxford comma,
        # no semicolons -- the case that first exposed the semicolon-only split.
        html = _HTML(
            "The Federal Open Market Committee approved the following statement "
            "for release by a 9 – 3 vote: The Committee decided to maintain the target range. "
            "Voting against the monetary policy action were Beth M. Hammack, Neel Kashkari, "
            "and Lorie K. Logan, who preferred to raise the target range for the federal funds rate "
            "by 1/4 percentage point at this meeting. "
            "For media inquiries, please email media@frb.gov."
        )
        row = parse_statement(html, meeting_date="2026-07-29", source_url="x")
        self.assertTrue(row["parsed_ok"])
        self.assertEqual(row["vote_for"], 9)
        self.assertEqual(row["vote_against"], 3)
        names = {d["name"] for d in row["dissenters"]}
        self.assertEqual(names, {"Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan"})
        self.assertTrue(all(d["dissent_direction"] == "tighter" for d in row["dissenters"]))

    def test_qualified_dissent_raises_instead_of_misfiling(self):
        # Real shape from 2025-03-19: a dissent that isn't a rate-direction
        # preference at all ("who supported no change... but preferred to
        # continue..."). Must not be silently folded into tighter/easier.
        html = _HTML(
            "Voting for the monetary policy action were Jerome H. Powell, Chair. "
            "Voting against this action was Christopher J. Waller, who supported no change for the "
            "federal funds target range but preferred to continue the current pace of decline in "
            "securities holdings. "
            "For media inquiries, please email media@frb.gov."
        )
        with self.assertRaises(ValueError):
            parse_statement(html, meeting_date="2025-03-19", source_url="x")

    def test_compound_dissent_raises_instead_of_dropping_names(self):
        # Real shape from 2026-04-29: an ordinary dissent (Miran) followed by
        # a second, qualified-dissent clause (Hammack/Kashkari/Logan) that
        # doesn't match "who preferred to raise/lower/no change". Both must
        # be caught -- silently keeping just Miran would under-report who
        # dissented.
        html = _HTML(
            "Voting for the monetary policy action were Jerome H. Powell, Chair; and Michael S. Barr. "
            "Voting against this action was Stephen I. Miran, who preferred to lower the target range "
            "for the federal funds rate by 1/4 percentage point at this meeting; and Beth M. Hammack, "
            "Neel Kashkari, and Lorie K. Logan, who supported maintaining the target range for the "
            "federal funds rate but did not support inclusion of an easing bias in the statement. "
            "For media inquiries, please email media@frb.gov."
        )
        with self.assertRaises(ValueError):
            parse_statement(html, meeting_date="2026-04-29", source_url="x")


class TestParseBeigeBook(unittest.TestCase):
    def test_national_summary_sections_stop_before_district_repeats(self):
        html = _HTML(
            "National Summary Overall Economic Activity Activity increased modestly. "
            "Labor Markets Employment rose on balance. "
            "Prices Prices increased moderately. "
            "Highlights by Federal Reserve District Boston Prices rose. New York Prices fell."
        )
        row = parse_beige_book_summary(html, edition="2026-07", source_url="x")
        self.assertTrue(row["parsed_ok"])
        sections = {s["section"]: s["text"] for s in row["national_sections"]}
        self.assertEqual(set(sections), {"Overall Economic Activity", "Labor Markets", "Prices"})
        # The per-district "Prices" repeats must not have leaked into the
        # national Prices section's text or produced extra "Prices" rows.
        self.assertNotIn("Boston", sections["Prices"])


if __name__ == "__main__":
    unittest.main()

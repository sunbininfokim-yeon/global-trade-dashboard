"""Offline tests for the FOMC minutes parser and how the assembler uses it.

Fixtures are trimmed from real minutes pages (2025-10-29, 2026-04-29,
2026-06-17, 2026-07-29) and the Fed's calendar page, fetched 2026-09-25,
kept literal so they run without the Fed's site.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_us_macro_quality_from_collect import _current_vote_roster, _minutes_block  # noqa: E402
from macro_monitor.fomc_collect.minutes import parse_minutes, parse_release_dates  # noqa: E402


def _page(body: str) -> str:
    return f'<html><body><div id="article">{body}</div></body></html>'


_POLICY = (
    "<p><strong>Committee Policy Actions</strong><br /> In support of the Committee's dual-mandate goals, "
    "nine members agreed to maintain the target range. In June, the Committee had indicated in its statement "
    'that it "will deliver price stability." Almost all members agreed that it was appropriate to retain this '
    "language. Three members voted against the decision, preferring an increase of 25 basis points.</p>"
    "<blockquote><p>The Committee decided to maintain the target range. Several participants said this inside the "
    "quoted statement and must not be counted.</p></blockquote>"
)


class TestParseMinutes(unittest.TestCase):
    def test_heading_shares_a_paragraph_with_its_first_body_text(self):
        out = parse_minutes(_page(_POLICY), meeting_date="2026-07-29", source_url="x")
        self.assertTrue(out["policy_actions_text"][0].startswith("In support of the Committee"))
        self.assertNotIn("Committee Policy Actions", out["policy_actions_text"][0])

    def test_sentence_ending_inside_a_closing_quote_still_splits(self):
        out = parse_minutes(_page(_POLICY), meeting_date="2026-07-29", source_url="x")
        quantified = {s["quantifier"]: s["text"] for s in out["statements"]}
        self.assertIn("almost all", quantified)  # follows '...price stability."'
        self.assertTrue(quantified["almost all"].startswith("Almost all members agreed"))
        self.assertEqual(quantified["three"].split()[0], "Three")

    def test_blockquote_statement_text_is_not_counted(self):
        out = parse_minutes(_page(_POLICY), meeting_date="2026-07-29", source_url="x")
        self.assertFalse(any("quoted statement" in s["text"] for s in out["statements"]))

    def test_participants_views_quantifiers_are_kept_verbatim_and_grouped(self):
        body = (
            "<p><strong>Participants' Views on Current Conditions and the Economic Outlook</strong><br /> "
            "Participants acknowledged that inflation remained elevated. Several participants noted that price "
            "increases were broad based. Some participants remarked that services inflation was high. "
            "A few participants observed that tariffs mattered. A couple of participants pointed to energy.</p>"
        )
        out = parse_minutes(_page(body), meeting_date="2026-07-29", source_url="x")
        by_group = {}
        for s in out["statements"]:
            by_group.setdefault(s["group"], []).append(s["quantifier"])
        self.assertEqual(by_group["unqualified"], ["participants"])
        self.assertEqual(by_group["several"], ["several"])
        self.assertEqual(by_group["some"], ["some"])
        self.assertEqual(sorted(by_group["few"]), ["a couple of", "a few"])

    def test_semicolon_vote_list_with_titles(self):
        body = (
            "<p><strong>Committee Policy Actions</strong><br /> Members agreed.</p>"
            "<p><strong>Voting for this action:</strong> Jerome H. Powell, Chair; John C. Williams, Vice Chair; "
            "Michael S. Barr; and Christopher J. Waller.</p>"
            "<p><strong>Voting against this action:</strong> Stephen I. Miran, who preferred to lower the target range "
            "by 1/2 percentage point at this meeting, and Jeffrey R. Schmid, who preferred no change to the target "
            "range at this meeting.</p>"
        )
        out = parse_minutes(_page(body), meeting_date="2025-10-29", source_url="x")
        self.assertEqual(out["voting_for"], ["Jerome H. Powell", "John C. Williams", "Michael S. Barr", "Christopher J. Waller"])
        against = {a["name"]: a["reason"] for a in out["voting_against"]}
        self.assertEqual(set(against), {"Stephen I. Miran", "Jeffrey R. Schmid"})
        self.assertTrue(against["Stephen I. Miran"].startswith("preferred to lower"))
        self.assertTrue(against["Jeffrey R. Schmid"].startswith("preferred no change"))

    def test_two_dissent_groups_with_different_reasons(self):
        body = (
            "<p><strong>Committee Policy Actions</strong><br /> Members agreed.</p>"
            "<p><strong>Voting for this action:</strong> Kevin Warsh, John C. Williams, and Michael S. Barr.</p>"
            "<p><strong>Voting against this action:</strong> Stephen I. Miran, who preferred to lower the target "
            "range by 1/4 percentage point at this meeting and Beth M. Hammack, Neel Kashkari, and Lorie K. Logan, "
            "who supported maintaining the target range but did not support inclusion of an easing bias.</p>"
        )
        out = parse_minutes(_page(body), meeting_date="2026-04-29", source_url="x")
        against = {a["name"]: a["reason"] for a in out["voting_against"]}
        self.assertEqual(set(against), {"Stephen I. Miran", "Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan"})
        self.assertTrue(against["Stephen I. Miran"].startswith("preferred to lower"))
        self.assertTrue(against["Neel Kashkari"].startswith("supported maintaining"))

    def test_none_means_no_dissent_and_trailing_text_is_not_names(self):
        body = (
            "<p><strong>Committee Policy Actions</strong><br /> Members agreed.</p>"
            "<p><strong>Voting for this action :</strong> Kevin Warsh, Michael S. Barr, and Lisa D. Cook.</p>"
            "<p><strong>Voting against this action:</strong> None . Consistent with the Committee's decision, the "
            "Board voted unanimously to maintain the interest rate paid on reserve balances at 3.65 percent.</p>"
        )
        out = parse_minutes(_page(body), meeting_date="2026-06-17", source_url="x")
        self.assertEqual(out["voting_against"], [])
        self.assertEqual(len(out["voting_for"]), 3)

    def test_first_vote_wins_over_later_notation_votes(self):
        body = (
            "<p><strong>Committee Policy Actions</strong><br /> Members agreed.</p>"
            "<p><strong>Voting for this action:</strong> A One, B Two, and C Three.</p>"
            "<p><strong>Voting against this action:</strong> None.</p>"
            "<p><strong>Notation Vote</strong><br /> By notation vote completed on August 22 ...</p>"
            "<p><strong>Voting for this action:</strong> A One and B Two.</p>"
        )
        out = parse_minutes(_page(body), meeting_date="2025-07-30", source_url="x")
        self.assertEqual(len(out["voting_for"]), 3)

    def test_unreadable_page_raises_instead_of_storing_nothing(self):
        with self.assertRaises(ValueError):
            parse_minutes("<html><body><div id='article'><p>Nothing here.</p></div></body></html>",
                          meeting_date="2026-07-29", source_url="x")


class TestReleaseDates(unittest.TestCase):
    def test_reads_the_printed_release_date_not_a_computed_one(self):
        html = (
            "<html><body>2026 FOMC Meetings July 28-29 Statement: PDF | HTML Implementation Note Press Conference "
            "Minutes: PDF | HTML (Released August 19, 2026) September 15-16* Statement: PDF | HTML Projection "
            "Materials PDF | HTML October 27-28 "
            "2025 FOMC Meetings December 9-10* Statement: PDF | HTML Minutes: PDF | HTML (Released December 30, 2025) "
            "</body></html>"
        )
        out = parse_release_dates(html)
        self.assertEqual(out["2026-07-29"], "2026-08-19")
        self.assertEqual(out["2025-12-10"], "2025-12-30")  # 20 days, not the usual 21
        self.assertNotIn("2026-09-16", out)  # not out yet -> no date invented


class TestAssemblerUsesMinutes(unittest.TestCase):
    def _row(self):
        return {
            "meeting_date": "2026-07-29", "vote_for": 9, "vote_against": 3, "voters_for": [],
            "dissenters": [{"name": n, "dissent_direction": "tighter"}
                           for n in ("Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan")],
        }

    _ROSTER = [{"name": n, "role": ""} for n in
               ("A One", "B Two", "C Three", "D Four", "E Five", "F Six", "G Seven", "H Eight", "I Nine",
                "Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan")]

    def _minutes(self, **overrides):
        base = {
            "meeting_date": "2026-07-29",
            "voting_for": [f"Named {i}" for i in range(9)],
            "voting_against": [{"name": n, "reason": "x"} for n in ("Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan")],
        }
        base.update(overrides)
        return base

    def test_minutes_named_voters_replace_the_roster_inference(self):
        entries = _current_vote_roster(self._row(), self._ROSTER, self._minutes())
        fors = [e for e in entries if e["vote"] == "for"]
        self.assertEqual({e["source"] for e in fors}, {"minutes"})
        self.assertFalse(any(e["inferred"] for e in fors))
        self.assertEqual(fors[0]["name"], "Named 0")

    def test_minutes_that_disagree_with_the_tally_are_ignored(self):
        bad = self._minutes(voting_for=["Only One"])
        entries = _current_vote_roster(self._row(), self._ROSTER, bad)
        self.assertEqual({e["source"] for e in entries if e["vote"] == "for"}, {"roster_inferred"})

    def test_minutes_naming_different_dissenters_are_ignored(self):
        bad = self._minutes(voting_against=[{"name": "Somebody Else", "reason": None}] * 3)
        entries = _current_vote_roster(self._row(), self._ROSTER, bad)
        self.assertEqual({e["source"] for e in entries if e["vote"] == "for"}, {"roster_inferred"})

    def test_pending_minutes_are_an_expectation_with_its_basis_stated(self):
        calendar = {"meetings": [{"decision_date": "2026-07-29"}, {"decision_date": "2026-09-16"},
                                 {"decision_date": "2026-10-28"}]}
        block = _minutes_block({"minutes": [{"meeting_date": "2026-07-29", "released_on": "2026-08-19"}]},
                               calendar, today=date(2026, 9, 25))
        self.assertEqual(block["latest"]["meeting_date"], "2026-07-29")
        self.assertEqual(block["pending"]["meeting_date"], "2026-09-16")
        self.assertEqual(block["pending"]["expected_release"], "2026-10-07")
        self.assertEqual(block["pending"]["basis"], "decision_plus_21_days_expected")

    def test_an_older_gap_is_not_reported_as_the_pending_release(self):
        calendar = {"meetings": [{"decision_date": "2026-04-29"}, {"decision_date": "2026-07-29"}]}
        block = _minutes_block({"minutes": [{"meeting_date": "2026-07-29", "released_on": "2026-08-19"}]},
                               calendar, today=date(2026, 9, 25))
        self.assertIsNone(block["pending"])


if __name__ == "__main__":
    unittest.main()

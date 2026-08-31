"""Offline regression tests for operative-text extraction and word diffing.

Fixtures mirror the real page shape (fetched 2026-08-31): a "For release at
... Share" masthead, then the statement body, then a vote/procedural tail
that extract_operative_text must exclude.
"""
from __future__ import annotations

import unittest

from macro_monitor.fomc_collect.parse import extract_operative_text
from macro_monitor.fomc_collect.statement_diff import changed_word_count, diff_operative_text

_HTML = lambda body: f"<html><body><div>{body}</div></body></html>"  # noqa: E731


class TestExtractOperativeText(unittest.TestCase):
    def test_bounds_between_masthead_and_voting_for(self):
        html = _HTML(
            "Federal Reserve Board - FOMC statement Back to Home "
            "For release at 2:00 p.m. EDT Share "
            "Economic activity is expanding at a solid pace. "
            "Voting for the monetary policy action were Jerome H. Powell, Chair. "
            "For media inquiries, please email media@frb.gov."
        )
        operative = extract_operative_text(html)
        self.assertEqual(operative, "Economic activity is expanding at a solid pace.")

    def test_bounds_between_masthead_and_voting_against_format_b(self):
        html = _HTML(
            "For release at 2:00 p.m. EDT Share "
            "The Federal Open Market Committee approved the following statement for release by a 9 - 3 vote: "
            "The Committee decided to maintain the target range. "
            "Voting against the monetary policy action were Beth M. Hammack, who preferred to raise. "
            "For media inquiries, please email media@frb.gov."
        )
        operative = extract_operative_text(html)
        self.assertEqual(operative, "The Committee decided to maintain the target range.")
        self.assertNotIn("Voting against", operative)
        self.assertNotIn("9 - 3 vote", operative)

    def test_missing_masthead_returns_none_instead_of_guessing(self):
        html = _HTML("Economic activity is expanding at a solid pace.")
        self.assertIsNone(extract_operative_text(html))


class TestDiffOperativeText(unittest.TestCase):
    def test_single_word_replacement(self):
        segments = diff_operative_text(
            "Economic activity is expanding at a solid pace.",
            "Economic activity is expanding at a moderate pace.",
        )
        ops = [seg["op"] for seg in segments]
        self.assertIn("replace", ops)
        replace = next(seg for seg in segments if seg["op"] == "replace")
        self.assertEqual(replace["before"], "solid")
        self.assertEqual(replace["after"], "moderate")

    def test_identical_text_is_all_equal(self):
        text = "Inflation remains elevated relative to the Committee's 2 percent goal."
        segments = diff_operative_text(text, text)
        self.assertTrue(all(seg["op"] == "equal" for seg in segments))
        self.assertEqual(changed_word_count(segments), 0)

    def test_changed_word_count_ignores_whitespace(self):
        segments = diff_operative_text(
            "Job gains have kept pace with the workforce.",
            "Job gains have slowed relative to the workforce.",
        )
        self.assertGreater(changed_word_count(segments), 0)


if __name__ == "__main__":
    unittest.main()

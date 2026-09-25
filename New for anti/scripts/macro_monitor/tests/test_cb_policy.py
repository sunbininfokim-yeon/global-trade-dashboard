"""Assembling the KOR / JPN policy-board blocks (macro_monitor.cb_collect.assemble)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.cb_collect.assemble import assemble_boj, assemble_bok, voters_for  # noqa: E402

TODAY = date(2026, 9, 25)

ROSTER = [
    {"name": "신현송", "role": "의장(총재)", "term_start": "2026-04-21", "term_end": "2030-04-20"},
    {"name": "장용성", "role": "위원", "term_start": "2023-04-21", "term_end": "2027-04-20"},
    {"name": "황건일", "role": "위원", "term_start": "2024-02-13", "term_end": "2027-04-20"},
    {"name": "김종화", "role": "위원", "term_start": "2024-04-25", "term_end": "2028-04-20"},
    {"name": "이수형", "role": "위원", "term_start": "2024-04-25", "term_end": "2028-04-20"},
    {"name": "김진일", "role": "위원", "term_start": "2026-05-15", "term_end": "2030-05-12"},
    {"name": "권민수", "role": "부총재", "term_start": "2026-08-21", "term_end": "2029-08-20"},
]
ALL7 = [r["name"] for r in ROSTER]


def bok_meeting(day, prior, rate, *, vote=None, minutes=None, text="본문", sentences=None):
    return {
        "meeting_date": day, "source_url": f"u/{day}", "prior_rate_pct": prior, "rate_pct": rate,
        "action": "raise" if rate > prior else "lower" if rate < prior else "maintain",
        "change_bp": int(round((rate - prior) * 100)), "vote": vote, "paragraphs": [text],
        "outlook_sentences": sentences or [], "minutes": minutes,
    }


DISSENT = {"favor_count": 6, "unanimous": False, "text": "t",
           "against": [{"name": "황건일", "preferred_rate_pct": 2.75, "direction": "hold"}]}


class VotersFor(unittest.TestCase):
    def test_minutes_attendance_minus_dissenters(self):
        m = bok_meeting("2026-08-27", 2.75, 3.0, vote=DISSENT, minutes={"present": ALL7, "absent": [], "released_on": "2026-09-15"})
        names, src = voters_for(m, ROSTER)
        self.assertEqual(names, [n for n in ALL7 if n != "황건일"])
        self.assertEqual(src, "minutes_attendance")

    def test_newest_meeting_without_minutes_uses_the_roster_when_it_fits(self):
        names, src = voters_for(bok_meeting("2026-08-27", 2.75, 3.0, vote=DISSENT), ROSTER)
        self.assertEqual(src, "roster_inferred")
        self.assertEqual(len(names), 6)

    def test_roster_not_used_when_a_term_does_not_cover_the_date(self):
        # 권민수's term starts 2026-08-21: on 2026-07-16 only six current members sat, the tally cannot be reproduced.
        vote = {"favor_count": 7, "unanimous": True, "against": [], "text": "t"}
        self.assertEqual(voters_for(bok_meeting("2026-07-16", 2.5, 2.75, vote=vote), ROSTER), (None, None))

    def test_attendance_that_contradicts_the_tally_gives_no_names(self):
        m = bok_meeting("2026-08-27", 2.75, 3.0, vote=DISSENT, minutes={"present": ALL7[:5], "absent": []})
        self.assertEqual(voters_for(m, ROSTER), (None, None))

    def test_no_vote_sentence_no_names(self):
        self.assertEqual(voters_for(bok_meeting("2025-01-16", 3.0, 3.0), ROSTER), (None, None))


class Bok(unittest.TestCase):
    def doc(self):
        minutes = {"present": ALL7, "absent": [], "released_on": "2026-09-15", "page_url": "p"}
        return {"retrieved_at": "2026-09-25T00:00:00Z", "roster": ROSTER, "calendar": {"2026": ["2026-08-27", "2026-10-22", "2026-11-26"]},
                "meetings": [
                    bok_meeting("2026-05-28", 2.5, 2.5, vote={"favor_count": 5, "unanimous": False, "text": "t",
                                "against": [{"name": "장용성", "preferred_rate_pct": 2.75, "direction": "higher"},
                                            {"name": "유상대", "preferred_rate_pct": 2.75, "direction": "higher"}]},
                                minutes={"present": ["신현송", "장용성", "유상대", "김종화", "이수형", "김진일", "황건일"], "absent": [],
                                         "released_on": "2026-06-16"}),
                    bok_meeting("2026-07-16", 2.5, 2.75, minutes={"present": ALL7, "absent": [], "released_on": "2026-08-04"}),
                    bok_meeting("2026-08-27", 2.75, 3.0, vote=DISSENT, minutes=minutes, text="새 본문", sentences=["s1"]),
                ]}

    def test_decision_votes_and_history(self):
        b = assemble_bok(self.doc(), today=TODAY)
        self.assertEqual((b["decision"]["action"], b["decision"]["change_bp"], b["decision"]["majority"]), ("raise", 25, "6-1"))
        self.assertEqual([h["rate_pct"] for h in b["decision_history"]], [2.5, 2.75, 3.0])
        self.assertEqual(b["votes"]["for_source"], "minutes_attendance")
        self.assertEqual(b["votes"]["against"][0]["direction"], "hold")
        # only meetings with a vote sentence enter the vote history (the July one has none here)
        self.assertEqual([v["meeting_date"] for v in b["vote_history"]], ["2026-05-28", "2026-08-27"])
        self.assertEqual(b["vote_history"][0]["dissenters"], ["장용성", "유상대"])

    def test_diff_between_the_last_two_meetings(self):
        b = assemble_bok(self.doc(), today=TODAY)
        d = b["statement_diffs"][0]
        self.assertEqual((d["previous_meeting"], d["current_meeting"]), ("2026-07-16", "2026-08-27"))
        self.assertGreater(d["changed_word_count"], 0)

    def test_next_meeting_and_outlook(self):
        b = assemble_bok(self.doc(), today=TODAY)
        self.assertEqual(b["schedule"]["next_meeting_date"], "2026-10-22")
        self.assertTrue(b["outlook"]["forecast_round"])            # August is a forecast round
        self.assertEqual(b["outlook"]["sentences"], ["s1"])

    def test_missing_minutes_get_an_expected_date_from_the_recent_lag(self):
        doc = self.doc()
        doc["meetings"][-1]["minutes"] = None
        doc["meetings"][0]["minutes"]["released_on"] = "2026-06-16"     # 19 days
        doc["meetings"][1]["minutes"]["released_on"] = "2026-08-04"     # 19 days
        doc["meetings"].insert(0, bok_meeting("2026-04-10", 2.5, 2.5, minutes={"present": ALL7, "absent": [], "released_on": "2026-04-29"}))
        b = assemble_bok(doc, today=TODAY)
        pending = [r for r in b["releases"] if r["status"] == "expected"]
        self.assertEqual(pending[0]["date"], "2026-09-15")             # 2026-08-27 + 19 days
        self.assertIn("19", pending[0]["basis"])

    def test_no_data_is_none(self):
        self.assertIsNone(assemble_bok({"meetings": []}, today=TODAY))


def boj_meeting(day, rate, *, against=(), unanimous=False, narrative=None, bank_view=None, present=("Ueda Kazuo", "Himino Ryozo", "Takata Hajime")):
    n_for = len(present) - len(against)
    return {
        "meeting_date": day, "source_url": f"u/{day}", "title": "t", "guideline_rate_pct": rate, "unanimous": unanimous,
        "vote_for_count": len(present) if unanimous else n_for, "vote_against_count": 0 if unanimous else len(against),
        "voting_for": [n for n in present if n not in against], "voting_for_source": "statement",
        "voting_against": [{"name": n, "reason": f"{n} dissented", "proposal_rate_pct": rate + 0.25} for n in against],
        "assessment_dissents": [], "members_present": list(present), "members_absent": [],
        "releases": {"summary_of_opinions": "2026-10-01", "minutes": "2026-11-05"},
        "narrative": narrative, "bank_view": bank_view,
    }


class Boj(unittest.TestCase):
    def doc(self):
        bv = lambda text: {"source_url": "gor", "summary": text, "forecasts": {"prior_made_in": "April 2026", "years": []}}  # noqa: E731
        return {"retrieved_at": "x", "calendar": [
                    {"meeting_days": ["2026-09-17", "2026-09-18"], "decision_date": "2026-09-18", "outlook_release": None,
                     "opinions_release": "2026-10-01", "minutes_release": "2026-11-05"},
                    {"meeting_days": ["2026-10-29", "2026-10-30"], "decision_date": "2026-10-30", "outlook_release": "2026-10-30",
                     "opinions_release": "2026-11-10", "minutes_release": "2026-12-23"},
                    {"meeting_days": ["2026-07-30", "2026-07-31"], "decision_date": "2026-07-31", "outlook_release": "2026-07-31",
                     "opinions_release": "2026-08-10", "minutes_release": "2026-09-28"}],
                "meetings": [
                    boj_meeting("2026-04-28", 0.75, bank_view=bv("april view")),
                    boj_meeting("2026-06-16", 1.0, narrative="june body text"),
                    boj_meeting("2026-07-31", 1.0, against=("Takata Hajime",), bank_view=bv("july view")),
                    boj_meeting("2026-09-18", 1.25, against=("Takata Hajime",), narrative="sept body text"),
                ]}

    def test_decision_uses_the_previous_meeting_as_prior(self):
        b = assemble_boj(self.doc(), today=TODAY)
        d = b["decision"]
        self.assertEqual((d["prior_rate_pct"], d["rate_pct"], d["action"], d["change_bp"]), (1.0, 1.25, "raise", 25))
        self.assertEqual(d["majority"], "2-1")
        # the first meeting has no known prior, so it is not in the history
        self.assertEqual([h["meeting_date"] for h in b["decision_history"]], ["2026-06-16", "2026-07-31", "2026-09-18"])

    def test_dissenter_direction_from_the_proposed_rate(self):
        b = assemble_boj(self.doc(), today=TODAY)
        self.assertEqual(b["votes"]["against"][0]["direction"], "higher")

    def test_diffs_compare_like_with_like(self):
        b = assemble_boj(self.doc(), today=TODAY)
        by = {d["kind"]: d for d in b["statement_diffs"]}
        self.assertEqual((by["statement"]["previous_meeting"], by["statement"]["current_meeting"]), ("2026-06-16", "2026-09-18"))
        self.assertEqual((by["bank_view"]["previous_meeting"], by["bank_view"]["current_meeting"]), ("2026-04-28", "2026-07-31"))
        self.assertEqual([d["kind"] for d in b["statement_diffs"]], ["statement", "bank_view"])   # newest first

    def test_releases_carry_status_from_the_calendar(self):
        b = assemble_boj(self.doc(), today=TODAY)
        got = {(r["meeting_date"], r["kind"]): r["status"] for r in b["releases"]}
        self.assertEqual(got[("2026-07-31", "summary_of_opinions")], "released")
        self.assertEqual(got[("2026-07-31", "minutes")], "scheduled")        # 2026-09-28 is after "today"
        self.assertEqual(got[("2026-09-18", "minutes")], "scheduled")

    def test_next_meeting_from_the_calendar(self):
        s = assemble_boj(self.doc(), today=TODAY)["schedule"]
        self.assertEqual((s["next_meeting_date"], s["next_outlook_release"]), ("2026-10-30", "2026-10-30"))
        self.assertEqual(s["next_meeting_days"], ["2026-10-29", "2026-10-30"])

    def test_outlook_table_from_the_latest_report(self):
        self.assertEqual(assemble_boj(self.doc(), today=TODAY)["outlook"]["meeting_date"], "2026-07-31")


if __name__ == "__main__":
    unittest.main()

"""The weekly result table: deadlines, links, notices as catalogue candidates."""

from __future__ import annotations

import unittest
from datetime import date

from export_controls import report
from export_controls.catalogue import load as load_catalogue
from export_controls.universe import load as load_universe

TODAY = date(2026, 10, 2)

# Deadline cases as fixtures, not the live catalogue: rows there change every week.
DEADLINE_DOC = {"controls": [
    {"id": "ind-sugar", "country_ko": "인도", "level": "prohibited", "until": "2026-09-30", "url": "https://a"},
    {"id": "rus-fuel-products", "country_ko": "러시아", "level": "prohibited", "until": "2027-01-31",
     "review_valid_until": "2026-10-08", "url": "https://b"},
    {"id": "ind-wheat", "level": "lifted", "until": "2026-09-01", "url": "https://c"},
]}


def notice(iso, measure, en, items=(), day="2026-09-30", ko=None):
    return {
        "id": en[:12], "url": f"https://example.gov/{iso}", "commodities": [],
        "published_at": f"{day}T00:00:00+00:00",
        "title": {"original": en, "en": en, "ko": ko or en},
        "control": {"issuer": iso, "measure": measure, "items": list(items), "targets": []},
    }


class DeadlineTest(unittest.TestCase):
    def test_passed_and_near_deadlines(self):
        flags = {f["id"]: f for f in report.deadline_flags(DEADLINE_DOC, TODAY)}
        self.assertEqual(flags["ind-sugar"]["state"], "지남")      # until 2026-09-30
        self.assertEqual(flags["ind-sugar"]["days"], -2)
        self.assertEqual(flags["rus-fuel-products"]["field"], "review_valid_until")
        self.assertEqual(flags["rus-fuel-products"]["state"], "임박")
        self.assertNotIn("ind-wheat", flags)                     # lifted rows are not deadlines


class LinkTest(unittest.TestCase):
    def test_only_gone_pages_count_as_broken(self):
        codes = iter([200, 404, 403, None] * 20)
        links = report.link_checks(load_catalogue(), fetch=lambda url: next(codes))
        states = {x["state"] for x in links}
        self.assertEqual(states, {"ok", "깨짐", "자동 확인 불가"})


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.doc, self.universe = load_catalogue(), load_universe()

    def test_notices_match_existing_rows_or_draft_new_ones(self):
        notices = [
            notice("RUS", "export_ban", "Government extends temporary ban on export of certain fuels", ["fuel"]),
            notice("IND", "suspension", "DGFT Notification 35/2026-27: Amendment in the Export Policy of Wheat"),
            notice("IND", "export_restriction", "Amendment in the Export Policy of Onions", ["onions"]),
            notice("USA", "export_restriction", "Commerce revises license review policy for semiconductors"),
            notice("CHN", "sanctions", "Countermeasures against a defence firm"),            # not a candidate measure
            notice("IND", "export_ban", "Export of wheat prohibited", day="2026-09-01"),        # older than a week
        ]
        cands, skipped = report.candidates(self.doc, notices, self.universe, TODAY)
        by_iso = {(c["issuer"], tuple(c["commodities"])): c for c in cands}
        self.assertEqual(by_iso[("RUS", ("petroleum_products",))]["matches"], ["rus-fuel-products"])
        self.assertEqual(by_iso[("IND", ("wheat",))]["matches"], ["ind-wheat"])
        onion = by_iso[("IND", ("onions",))]
        self.assertEqual(onion["matches"], [])
        self.assertEqual(onion["draft"]["level"], "restricted")
        self.assertEqual(onion["draft"]["confidence"], "low")
        self.assertTrue(onion["draft"]["needs_reconfirm"])
        self.assertEqual(skipped, 1)   # the semiconductor notice names no commodity
        self.assertEqual(len(cands), 3)

    def test_rendered_table_has_every_section(self):
        entry = {"week": "2026-W40", "control_count": 20, "needs_reconfirm": ["a"],
                 "pairs": {"live": 28, "lifted": 1, "unchecked": 196}, "open_questions": ["q1"]}
        rep = report.build(DEADLINE_DOC, self.universe, today=TODAY, entry=entry,
                           notices=[notice("IND", "export_restriction", "Amendment in the Export Policy of Onions", ["onions"])],
                           links=[{"id": "x", "url": "https://a", "status": 404, "state": "깨짐"}])
        text = report.render(rep)
        for part in ("## 1. 기한", "`ind-sugar`", "## 2. 원문 링크", "| `x` | 깨짐 | 404 |",
                     "## 3.", "**신규 후보**", "\"id\": \"ind-onions\"", "## 4. 열린 질문", "- q1"):
            self.assertIn(part, text)
        self.assertEqual(report.summary_counts(rep)["new_candidates"], 1)


if __name__ == "__main__":
    unittest.main()

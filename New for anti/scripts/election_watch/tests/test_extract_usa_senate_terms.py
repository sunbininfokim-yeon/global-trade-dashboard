import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from election_watch.extract_usa_senate_terms import apply_senate_terms


class SenateTermsTests(unittest.TestCase):
    def test_darline_graham_is_not_rewritten_to_lindsey(self):
        congress = {
            "summary": {},
            "members": [
                {
                    "bioguideId": "G000608",
                    "name": "Graham, Darline",
                    "chamber": "senate",
                    "state": "South Carolina",
                }
            ],
        }
        terms = {
            "members": [
                {
                    "bioguide_id": "G000608",
                    "senate_class": 2,
                    "senate_class_roman": "II",
                    "term_end": "2027-01-03",
                    "next_election_year": 2026,
                    "up_in_2026": True,
                }
            ]
        }
        apply_senate_terms(congress, terms)
        row = congress["members"][0]
        self.assertEqual(row["name"], "Graham, Darline")
        self.assertEqual(row["senate_class"], 2)
        self.assertTrue(row["up_in_2026"])

    def test_committed_overlay_covers_all_100_senators(self):
        terms = json.loads((ROOT / "config" / "extracted" / "usa_senate_terms.json").read_text(encoding="utf-8"))
        members = terms["members"]
        self.assertEqual(len(members), 100)
        self.assertEqual(sum(1 for row in members if row.get("up_in_2026")), 35)
        specials = [row for row in members if row.get("election_kind_2026") == "special"]
        self.assertEqual({row["state"] for row in specials}, {"FL", "OH"})
        self.assertTrue(all(row["senate_class"] == 3 and row["next_election_year"] == 2026 for row in specials))
        congress = {"members": [{"bioguideId": row["bioguide_id"], "chamber": "senate"} for row in members]}
        apply_senate_terms(congress, terms)
        self.assertEqual(congress["summary"]["senate_up_in_2026"], 35)
        self.assertEqual(congress["summary"]["senate_regular_up_in_2026"], 33)
        self.assertEqual(congress["summary"]["senate_special_up_in_2026"], 2)
        graham = next(row for row in members if row["bioguide_id"] == "G000608")
        self.assertEqual(graham["name"], "Darline Graham")
        self.assertEqual(graham["senate_class"], 2)


if __name__ == "__main__":
    unittest.main()

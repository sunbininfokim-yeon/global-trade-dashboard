"""Election records for the country 선거 card (build_election_records.py)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build_election_records as ber  # noqa: E402


class ElectionRecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = ber.build("2026-11-01")

    def test_offices_are_ordered_executive_legislature_local(self):
        for iso3, doc in self.docs.items():
            keys = [ber.OFFICE_ORDER[o["key"]] for o in doc["offices"]]
            self.assertEqual(keys, sorted(keys), iso3)

    def test_runoff_is_one_record_with_two_rounds(self):
        bra = next(o for o in self.docs["BRA"]["offices"] if o["system_id"] == "bra-president")
        last = bra["records"][0]
        self.assertEqual([r["round"] for r in last["rounds"]], [1, 2])
        self.assertEqual(last["first_round_date"], "2026-10-04")
        self.assertNotIn("결선:", last["winner_ko"] or "")

    def test_parliamentary_executive_points_at_its_chamber(self):
        deu = next(o for o in self.docs["DEU"]["offices"] if o["key"] == "executive")
        self.assertEqual(deu["elected_how"], "by_legislature")
        self.assertEqual(deu["selected_by_system_id"], "deu-bundestag")

    def test_no_invented_dates(self):
        for doc in self.docs.values():
            for office in doc["offices"]:
                nxt = office.get("next")
                if nxt and nxt.get("date"):
                    self.assertRegex(nxt["date"], r"^\d{4}-\d{2}-\d{2}$")
                for rec in office["records"]:
                    self.assertRegex(rec["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_researched_input_is_validated_and_wins(self):
        good = {"schema": "election_records_input_v1", "country": "KOR", "as_of": "2026-11-07", "offices": [
            {"key": "executive", "system_id": "kor-president", "records": [
                {"election_id": "kor-2025-president", "date": "2025-06-03", "turnout_pct": 79.4,
                 "sources": ["https://info.nec.go.kr/"],
                 "candidates": [{"name": "A", "votes": 60}, {"name": "B", "votes": 40}]}]}]}
        self.assertEqual(ber.validate_input("KOR", good), [])
        doc = {"offices": [dict(o, records=list(o["records"])) for o in self.docs["KOR"]["offices"]], "issues": []}
        ber.apply_input(doc, good)
        rec = next(o for o in doc["offices"] if o["system_id"] == "kor-president")["records"][0]
        self.assertEqual(rec["origin"], "researched")
        self.assertEqual([c["vote_pct"] for c in rec["candidates"]], [60.0, 40.0])
        self.assertEqual(rec["vote_pct_basis"], "listed_candidates")
        bad = {**good, "offices": [{"key": "executive", "records": [{"election_id": "x", "date": "2025", "turnout_pct": 120}]}]}
        errors = ber.validate_input("KOR", bad)
        self.assertTrue(any("date" in e for e in errors) and any("sources" in e for e in errors) and any("turnout" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

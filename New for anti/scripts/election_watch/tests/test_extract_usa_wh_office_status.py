import unittest

from election_watch.extract_usa_wh_office_status import (
    apply_office_status,
    classify_unscoped_kind,
    parse_cea_chair,
    build_office_status,
)


CEA_HTML = """
<html><body>
<p>Under President Trump, Christopher Phelan serves as Chairman and Aaron Hedlund serves as Member.</p>
</body></html>
"""

CEQ_HTML = """
<html><body>
<p>The Council on Environmental Quality (CEQ), established by the National Environmental Policy Act (NEPA) in 1970, is within the Executive Office of the President (EOP).</p>
</body></html>
"""


class OfficeStatusTests(unittest.TestCase):
    def test_cea_chair_from_official_about(self):
        parsed = parse_cea_chair(CEA_HTML)
        self.assertEqual(parsed["name_en"], "Christopher Phelan")
        self.assertEqual(parsed["status"], "incumbent")

    def test_unscoped_kinds(self):
        klopp = classify_unscoped_kind(
            {
                "name_en": "Jacalynne B. Klopp",
                "office_en": "DEPUTY ASSISTANT TO THE PRESIDENT AND ADVISOR",
                "payroll_status": "EMPLOYEE",
                "wh_salary_usd": 175000,
            }
        )
        self.assertEqual(klopp["kind"], "political_deputy_unscoped")
        self.assertFalse(klopp["vacant"])
        lake = classify_unscoped_kind(
            {
                "name_en": "Peter M. Lake",
                "office_en": "SENIOR ADVISOR",
                "payroll_status": "DETAILEE",
                "wh_salary_usd": 197200,
            }
        )
        self.assertEqual(lake["kind"], "detailee_unscoped")
        tracy = classify_unscoped_kind(
            {
                "name_en": "Tracy L. Johnson",
                "office_en": "SENIOR ADVISOR",
                "payroll_status": "EMPLOYEE",
                "wh_salary_usd": 0,
            }
        )
        self.assertEqual(tracy["kind"], "unpaid_senior_unscoped")
        selip = classify_unscoped_kind(
            {
                "name_en": "Meghan I. Selip",
                "office_en": "SENIOR ADVISOR",
                "payroll_status": "EMPLOYEE",
                "wh_salary_usd": 110500,
            }
        )
        self.assertEqual(selip["kind"], "staff_senior_unscoped")

    def test_vacant_only_pclob_chair(self):
        status = build_office_status(as_of="2026-09-14", cea=parse_cea_chair(CEA_HTML), ceq_html=CEQ_HTML)
        by_id = {row["id"]: row for row in status["offices"]}
        self.assertTrue(by_id["pclob_chair"]["vacant"])
        self.assertFalse(by_id["ceq"]["vacant"])
        self.assertFalse(by_id["vp_chief_of_staff"]["vacant"])
        self.assertFalse(by_id["whmo"]["vacant"])
        self.assertEqual(by_id["cea"]["name_en"], "Christopher Phelan")
        self.assertEqual(by_id["ondcp"]["name_en"], "Sara Carter")
        self.assertIsNone(by_id["ceq"]["name_en"])

    def test_reported_fill_stays_out_of_official_name(self):
        status = build_office_status(as_of="2026-10-01", cea=parse_cea_chair(CEA_HTML), ceq_html=CEQ_HTML)
        by_id = {row["id"]: row for row in status["offices"]}
        for office_id, name in (("vp_chief_of_staff", "Nick Luna"), ("ceq", "Rachael McNitt")):
            row = by_id[office_id]
            self.assertIsNone(row["name_en"])
            self.assertEqual(row["source_grade"], "reported_reliable")
            self.assertEqual(row["seat_status"], "filled_reported")
            self.assertIn(name, row["ui_ko"])
            self.assertIn("보도 기준", row["ui_ko"])
            self.assertGreaterEqual(len(row["reported"]["sources"]), 2)
        self.assertIsNone(by_id["whmo"].get("reported"))

    def test_official_ceq_name_drops_reported_fill(self):
        html = "<p>Chairman: Jane Example</p>"
        status = build_office_status(as_of="2026-10-01", ceq_html=html)
        ceq = next(row for row in status["offices"] if row["id"] == "ceq")
        self.assertIsNone(ceq["reported"])
        self.assertEqual(ceq["seat_status"], "incumbent_unconfirmed")

    def test_apply_sets_core_vp_and_ceq_head(self):
        eop = {
            "core": [{"id": "vp_chief_of_staff", "name_en": None, "reported_successor_unconfirmed": {"name_en": "Nick Luna"}}],
            "eop_office_heads": [{"id": "ceq", "name_en": None}],
        }
        apply_office_status(eop, build_office_status(as_of="2026-10-01", ceq_html=CEQ_HTML))
        vp = eop["core"][0]
        self.assertEqual(vp["name_en"], "Nick Luna")
        self.assertEqual(vp["status"], "보도 기준")
        self.assertNotIn("reported_successor_unconfirmed", vp)
        ceq = eop["eop_office_heads"][0]
        self.assertEqual(ceq["name_en"], "Rachael McNitt")
        self.assertEqual(ceq["source_grade"], "reported_reliable")


if __name__ == "__main__":
    unittest.main()

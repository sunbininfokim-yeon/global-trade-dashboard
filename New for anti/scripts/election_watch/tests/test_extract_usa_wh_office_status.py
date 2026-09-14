import unittest

from election_watch.extract_usa_wh_office_status import (
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


if __name__ == "__main__":
    unittest.main()

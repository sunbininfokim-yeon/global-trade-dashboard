import unittest

from election_watch.extract_usa_eop import (
    parse_administration_html,
    parse_cabinet_html,
    parse_staff_pdf_text,
    payroll_name_to_display,
)

CABINET_HTML = """
<html><body>
<h2 class="wp-block-heading"><strong>Scott Bessent</strong></h2>
<h3 class="wp-block-heading"><strong>Secretary of the Treasury</strong></h3>
<h2><strong>Russ Vought</strong></h2>
<h3><strong>Director of the Office of Management and Budget</strong></h3>
<h2><strong>Keith E. Sonderling</strong></h2>
<h3><strong>Acting Secretary of Labor</strong></h3>
<h2>Initiatives</h2>
<h3>Subscribe to the WH Newsletter</h3>
</body></html>
"""

ADMIN_HTML = """
<html><body>
<h1>The Administration</h1>
<h2>President Donald J. Trump</h2>
<h2>Vice President JD Vance</h2>
<h2>The Cabinet</h2>
</body></html>
"""

STAFF_TEXT = """
EXECUTIVE OFFICE OF THE PRESIDENT
ANNUAL REPORT TO CONGRESS ON WHITE HOUSE OFFICE PERSONNEL
WHITE HOUSE OFFICE
As of Date: Wednesday, July 1, 2026
NAME STATUS SALARY PAY BASIS POSITION TITLE
AGEN, JARROD P. EMPLOYEE $195,200.00 Per Annum ASSISTANT TO THE PRESIDENT AND EXECUTIVE DIRECTOR OF THE NATIONAL ENERGY DOMINANCE COUNCIL
HASSETT, KEVIN A. EMPLOYEE $195,200.00 Per Annum ASSISTANT TO THE PRESIDENT FOR ECONOMIC POLICY AND DIRECTOR OF THE NATIONAL ECONOMIC COUNCIL
LEAVITT, KAROLINE C. EMPLOYEE $195,200.00 Per Annum ASSISTANT TO THE PRESIDENT AND PRESS SECRETARY
For Official Use Only Page 4 of 8
For Official Use Only
RUBIO, MARCO A. EMPLOYEE $0.00 Per Annum ASSISTANT TO THE PRESIDENT AND NATIONAL SECURITY ADVISOR
SCAVINO, JR., DANIEL J. EMPLOYEE $195,200.00 Per Annum ASSISTANT TO THE PRESIDENT AND DEPUTY CHIEF OF STAFF AND DIRECTOR OF THE OFFICE OF PRESIDENTIAL PERSONNEL
WILES, SUSAN S. EMPLOYEE $195,200.00 Per Annum ASSISTANT TO THE PRESIDENT AND CHIEF OF STAFF
ADKISSON, SAMUEL D. EMPLOYEE $121,500.00 Per Annum SPECIAL ASSISTANT TO THE PRESIDENT AND ASSOCIATE COUNSEL
"""


class ExtractUsaEopTests(unittest.TestCase):
    def test_cabinet_pairs_skip_newsletter(self):
        rows = parse_cabinet_html(CABINET_HTML)
        self.assertEqual(
            [r["portfolio_ko"] for r in rows],
            ["재무장관", "관리예산처장", "노동장관 (직무대행)"],
        )
        self.assertEqual(rows[2]["status"], "acting")
        self.assertEqual(rows[1]["name_en"], "Russ Vought")

    def test_admin_president_vp(self):
        parsed = parse_administration_html(ADMIN_HTML)
        self.assertEqual(parsed["president"], "Donald J. Trump")
        self.assertEqual(parsed["vice_president"], "JD Vance")

    def test_payroll_name(self):
        self.assertEqual(payroll_name_to_display("RUBIO, MARCO A."), "Marco A. Rubio")
        self.assertEqual(payroll_name_to_display("SCAVINO, JR., DANIEL J."), "Daniel J. Scavino, Jr.")
        self.assertEqual(payroll_name_to_display("CHEUNG, STEVEN"), "Steven Cheung")

    def test_staff_pdf_assistants(self):
        parsed = parse_staff_pdf_text(STAFF_TEXT)
        self.assertEqual(parsed["as_of"], "2026-07-01")
        self.assertEqual(parsed["assistants"]["nsa"]["name_en"], "Marco A. Rubio")
        self.assertEqual(parsed["assistants"]["nsa"]["salary_usd"], 0.0)
        self.assertEqual(parsed["assistants"]["nec_director"]["name_en"], "Kevin A. Hassett")
        self.assertEqual(parsed["assistants"]["wh_chief_of_staff"]["name_en"], "Susan S. Wiles")
        self.assertEqual(parsed["assistants"]["press_secretary"]["name_en"], "Karoline C. Leavitt")
        self.assertNotIn("wh_counsel", parsed["assistants"])
        self.assertTrue("ASSOCIATE COUNSEL" not in parsed["assistants"].get("nsa", {}).get("title", ""))


if __name__ == "__main__":
    unittest.main()

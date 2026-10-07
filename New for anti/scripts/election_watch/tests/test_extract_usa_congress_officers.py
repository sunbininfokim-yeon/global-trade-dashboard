import unittest

from election_watch.extract_usa_congress_officers import (
    flip_name,
    parse_clerk_xml,
    parse_crec_prayer,
    parse_house_chaplain_page,
    parse_house_history,
    parse_senate_chaplain_table,
    parse_senate_leadership,
    parse_senate_officers_staff,
    parse_senate_party_secretaries,
)

CAO_HTML = """
<table>
<tr><th>Congress and Years</th><th>Name</th><th>State</th><th>Title</th><th>Date</th></tr>
<tr><td>118th (2023–2025)</td><td>SZPINDOR, Catherine</td><td>VA</td><td>Chief Administrative Officer of the House</td><td>Elected Jan 07, 2023</td></tr>
<tr><td>119th (2025–2027)</td><td>SZPINDOR, Catherine&nbsp;17</td><td>VA</td><td>Chief Administrative Officer of the House</td><td>Elected Jan 03, 2025</td></tr>
<tr><td>119th (2025–2027)</td><td>BINSTED, Anne Dressendorfer</td><td>VA</td><td>Chief Administrative Officer of the House</td><td>Appointed Dec 31, 2025&nbsp;18</td></tr>
</table>
"""

CHAPLAIN_HTML = """
<table>
<tr><td>118th (2023–2025)</td><td>The Reverend Margaret Grun KIBBEN</td><td>Presbyterian</td><td>Jan 07, 2023</td></tr>
<tr><td>119th (2025–2027)</td><td>The Reverend Margaret Grun KIBBEN</td><td>Presbyterian</td><td>Jan 03, 2025&nbsp;15</td></tr>
</table>
"""

CHAPLAIN_PAGE = """
<div>Message from the Chaplain</div><div>The Reverend Patrick J. Conroy</div>
<footer><p>The Reverend Dr. Margaret Grun Kibben, Chaplain, U.S. House of Representatives</p></footer>
"""

SENATE_LEADERSHIP = """
 President Pro Tempore Grassley, Chuck (R-IA)
 Senate Majority Leader Thune, John (R-SD)
 Senate-Elected Officers & Officials
 Parliamentarian MacDonough, Elizabeth
 Secretary for the Majority Duncan, Robert M.
 Chaplain Black, Barry
"""

SENATE_STAFF = (
    "The current secretary of the Senate is Jackie Barber. "
    "The current sergeant at arms is Jennifer A. Hemingway. "
)

PARTY_SECRETARIES = """
- Democratic Party Secretaries
- | Name | Years of Service |
| --- | --- |
| Gary Myrick | 2011–present |
- Republican Party Secretaries
- | Name | Years of Service |
| --- | --- |
| Laura Dove | 2013–2020 |
| Robert Duncan | 2020–present |
"""

SENATE_CHAPLAIN = """
| Name | Denomination | Date of Appointment | Note |
| --- | --- | --- | --- |
| Lloyd John Ogilvie, D.D. | Presbyterian | Mar 11, 1995 | – |
| Barry C. Black, Ph.D., D. Min., D.D. | Seventh-day Adventist | July 7, 2003 | – |
"""


class CongressOfficerTests(unittest.TestCase):
    def test_flip_name(self):
        self.assertEqual(flip_name("MCFARLAND, William"), "William McFarland")
        self.assertEqual(flip_name("MCCUMBER, Kevin F."), "Kevin F. McCumber")
        self.assertEqual(flip_name("Margaret Grun KIBBEN"), "Margaret Grun Kibben")

    def test_house_cao_change_with_predecessor(self):
        row = parse_house_history(CAO_HTML)
        self.assertEqual(row["name_en"], "Anne Dressendorfer Binsted")
        self.assertEqual(row["since"], "2025-12-31")
        self.assertEqual(row["appointment"], "appointed")
        self.assertEqual(row["predecessor_en"], "Catherine Szpindor")
        self.assertNotIn("denomination", row)

    def test_house_chaplain_table_and_footer(self):
        row = parse_house_history(CHAPLAIN_HTML)
        self.assertEqual(row["name_en"], "Margaret Grun Kibben")
        self.assertEqual(row["denomination"], "Presbyterian")
        self.assertEqual(parse_house_chaplain_page(CHAPLAIN_PAGE), "Margaret Grun Kibben")

    def test_clerk_xml_verbatim(self):
        self.assertEqual(parse_clerk_xml("<clerk>KEVIN F. McCUMBER</clerk>"), "KEVIN F. McCUMBER")

    def test_senate_leadership(self):
        rows = parse_senate_leadership(SENATE_LEADERSHIP)
        self.assertEqual(rows["president_pro_tempore"]["name_en"], "Chuck Grassley")
        self.assertEqual(rows["president_pro_tempore"]["party_abbr"], "R")
        self.assertEqual(rows["parliamentarian"]["name_en"], "Elizabeth MacDonough")
        self.assertEqual(rows["chaplain"]["name_en"], "Barry Black")
        self.assertNotIn("minority_secretary", rows)

    def test_senate_staff_keeps_middle_initial(self):
        rows = parse_senate_officers_staff(SENATE_STAFF)
        self.assertEqual(rows["secretary"]["name_en"], "Jackie Barber")
        self.assertEqual(rows["sergeant_at_arms"]["name_en"], "Jennifer A. Hemingway")

    def test_party_secretaries(self):
        rows = parse_senate_party_secretaries(PARTY_SECRETARIES)
        self.assertEqual(rows["D"]["name_en"], "Gary Myrick")
        self.assertEqual(rows["R"]["name_en"], "Robert Duncan")
        self.assertEqual(rows["R"]["since_year"], "2020")

    def test_senate_chaplain_table(self):
        row = parse_senate_chaplain_table(SENATE_CHAPLAIN)
        self.assertEqual(row["name_en"], "Barry C. Black")
        self.assertEqual(row["since"], "2003-07-07")

    def test_crec_prayer_skips_guest(self):
        self.assertEqual(
            parse_crec_prayer("The Chaplain, Dr. Barry C. Black, offered the following prayer: Let us pray."),
            "Barry C. Black",
        )
        self.assertEqual(
            parse_crec_prayer("The Chaplain, the Reverend Margaret Grun Kibben, offered the following prayer"),
            "Margaret Grun Kibben",
        )
        self.assertIsNone(parse_crec_prayer("The guest Chaplain offered the following prayer"))


if __name__ == "__main__":
    unittest.main()

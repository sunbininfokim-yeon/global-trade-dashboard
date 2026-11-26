import unittest
from urllib.error import URLError
from xml.etree import ElementTree as ET

from refresh_usa_congress_agenda import HOUSE_FEED, SENATE_RECORDS, house_week, refresh, senate_records, source_content


ATOM = """<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><link href="https://docs.house.gov/floor/Default.aspx?date=2026-11-30"/></entry>
    <entry><link href="https://docs.house.gov/floor/Default.aspx?date=2026-11-16"/></entry>
    <entry><link href="https://example.org/floor/Default.aspx?date=2026-12-14"/></entry>
</feed>"""

WEEK = """<floorschedule week-date="2026-11-30" update-date="2026-11-25">
    <category><floor-items>
        <floor-item><legis-num>H.R. 80</legis-num><floor-text>Title <em>with</em> markup</floor-text></floor-item>
        <floor-item remove-date="2026-11-25"><floor-text>Withdrawn item</floor-text></floor-item>
    </floor-items></category>
</floorschedule>"""

RECORDS = """<rss><channel>
    <item><guid>CREC-2026-11-23</guid></item>
    <item><guid>CREC-2026-11-24</guid></item>
    <item><guid>CREC-2026-11-23</guid></item>
    <item><guid>unsafe-id</guid></item>
</channel></rss>"""


class CongressAgendaTest(unittest.TestCase):
    def test_house_uses_latest_official_week_and_excludes_withdrawn_item(self):
        def read(url):
            self.assertIn("20261130.xml", url)
            return ET.fromstring(WEEK)

        result = house_week(ET.fromstring(ATOM), read)
        self.assertEqual(result["date"], "2026-11-30")
        self.assertEqual(result["entries"], [{
            "title": "H.R. 80 · Title with markup",
            "date_note_ko": "심의 가능 안건",
            "url": "https://docs.house.gov/floor/Default.aspx?date=2026-11-30",
        }])

    def test_senate_digest_is_deduplicated_and_marked_as_public_record(self):
        result = senate_records(ET.fromstring(RECORDS))
        self.assertEqual([row["date"] for row in result["entries"]], ["2026-11-24", "2026-11-23"])
        self.assertTrue(all(row["date_note_ko"] == "공개 기록" for row in result["entries"]))

    def test_partial_source_failure_keeps_last_good_data_and_original_date(self):
        def read(url):
            if url == HOUSE_FEED:
                raise URLError("offline")
            self.assertEqual(url, SENATE_RECORDS)
            return ET.fromstring(RECORDS)

        old = {
            "id": "house_floor", "date": "2026-11-16", "checked_at": "2026-11-16T00:00:00Z",
            "status": "ok", "entries": [{"title": "Last good agenda"}],
        }
        output = refresh({"sources": [old]}, [], "2026-11-26T00:00:00Z", read)
        house, senate = output["sources"]
        for key in ("date", "checked_at", "entries"):
            self.assertEqual(house[key], old[key])
        self.assertEqual(house["status"], "stale")
        self.assertEqual(senate["status"], "ok")
        self.assertEqual(senate["date"], "2026-11-24")
        self.assertTrue(all("checked_at" not in row for row in source_content(output)))

    def test_house_rejects_xml_for_a_different_week(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            house_week(ET.fromstring(ATOM), lambda _: ET.fromstring(WEEK.replace("2026-11-30", "2026-11-16")))

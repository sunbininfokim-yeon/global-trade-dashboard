import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from election_watch.usa_committee_cards import (  # noqa: E402
    ALLOWED_URL_PREFIXES,
    NO_NAMED_DEPARTMENT_SYSTEM_CODES,
    URL_TEMPLATES,
    build_committee_cards,
    committee_homepage_url,
    member_office_url,
)


class CommitteeCardJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        committees = json.loads(
            (ROOT / "config" / "extracted" / "usa_committees.json").read_text(encoding="utf-8")
        )
        cls.cards = build_committee_cards(committees)

    def test_standing_counts_match_119th_rosters(self):
        self.assertEqual(self.cards["counts"]["house"], 20)
        self.assertEqual(self.cards["counts"]["senate"], 16)
        self.assertEqual(len(self.cards["standing"]), 36)

    def test_every_standing_committee_has_chair_and_ranking_member(self):
        for card in self.cards["standing"]:
            with self.subTest(card["committee_id"]):
                self.assertIsNotNone(card.get("chair"), card)
                self.assertIsNotNone(card.get("ranking_member"), card)
                self.assertEqual(card["chair"]["role_ko"], "위원장")
                self.assertEqual(card["ranking_member"]["role_ko"], "간사")
                self.assertTrue(card["chair"].get("bioguide"))
                self.assertTrue(card["ranking_member"].get("bioguide"))

    def test_urls_use_official_id_templates_only(self):
        for card in self.cards["standing"]:
            urls = [card.get("committee_url")]
            for person in (card.get("chair"), card.get("ranking_member")):
                urls.extend([person.get("member_office_url"), person.get("bioguide_url")])
            for url in urls:
                self.assertTrue(url)
                self.assertTrue(url.startswith(ALLOWED_URL_PREFIXES), url)
                self.assertNotIn("walberg.house.gov", url)
                self.assertNotIn("lastname.senate.gov", url)
                self.assertNotIn("agriculture.house.gov", url)
                self.assertNotIn("armed-services.senate.gov", url)

    def test_house_agriculture_joins_usda_and_clerk_urls(self):
        card = next(row for row in self.cards["house"] if row["system_code"] == "hsag00")
        self.assertEqual(card["committee_id"], "119-house-hsag00")
        self.assertEqual(card["clerk_code"], "AG00")
        self.assertEqual(card["chair"]["name"], "Glenn Thompson")
        self.assertEqual(card["ranking_member"]["name"], "Angie Craig")
        self.assertEqual(
            card["committee_url"], "https://clerk.house.gov/Committees/AG00"
        )
        self.assertEqual(
            card["chair"]["member_office_url"],
            "https://clerk.house.gov/members/T000467",
        )
        self.assertEqual(
            [row["agency_id"] for row in card["agencies"]],
            ["fr-agriculture-department"],
        )

    def test_senate_armed_services_joins_dod_without_invented_senate_host(self):
        card = next(row for row in self.cards["senate"] if row["system_code"] == "ssas00")
        self.assertEqual(card["committee_id"], "119-senate-ssas00")
        self.assertEqual(card["clerk_code"], None)
        self.assertEqual(card["chair"]["bioguide"], "W000437")
        self.assertEqual(card["ranking_member"]["bioguide"], "R000122")
        self.assertEqual(
            card["committee_url"], "https://www.congress.gov/committee/ssas00"
        )
        self.assertEqual(
            card["chair"]["member_office_url"],
            "https://bioguide.congress.gov/search/bio/W000437",
        )
        self.assertEqual(
            [row["agency_id"] for row in card["agencies"]],
            ["fr-defense-department"],
        )

    def test_no_inferred_department_when_rule_does_not_name_one(self):
        by_code = {row["system_code"]: row for row in self.cards["standing"]}
        for code in NO_NAMED_DEPARTMENT_SYSTEM_CODES:
            self.assertEqual(by_code[code]["agencies"], [], code)

    def test_url_builders_do_not_invent_personal_domains(self):
        self.assertEqual(
            member_office_url("house", "T000467"),
            "https://clerk.house.gov/members/T000467",
        )
        self.assertEqual(
            member_office_url("senate", "W000437"),
            "https://bioguide.congress.gov/search/bio/W000437",
        )
        self.assertEqual(
            committee_homepage_url("house", "AG00", "hsag00"),
            "https://clerk.house.gov/Committees/AG00",
        )
        self.assertEqual(
            URL_TEMPLATES["house_member_office"],
            "https://clerk.house.gov/members/{bioguide}",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_news.build import build_ticker
from commodity_news.importance import ImportanceModel
from commodity_news.lang import detect_lang
from commodity_news.rss import RawItem, parse_feed_xml
from commodity_news.score import NewsScorer, apply_regional_and_taiwan_balance


def _load(name: str):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


class ScoreTests(unittest.TestCase):
    def setUp(self):
        imp = ImportanceModel(_load("importance.json"))
        self.scorer = NewsScorer(
            _load("commodities.json"),
            _load("diplomacy.json"),
            _load("regions.json"),
            _load("elections.json"),
            politics_extra=_load("politics_extra.json"),
            importance_model=imp,
        )

    def _raw(self, title, summary="", region="west", source_id="x"):
        return RawItem(
            source_id=source_id,
            source_name=source_id,
            region=region,
            source_lang="en",
            title=title,
            summary=summary,
            url=f"https://example.test/{hash(title) & 0xffff}",
            published_at="2026-08-03T10:00:00+00:00",
        )

    def test_admits_commodity(self):
        item = self.scorer.score(
            self._raw("Brent crude prices fall as tanker freights ease", region="mena")
        )
        self.assertIsNotNone(item)
        self.assertIn("oil", item.commodities)

    def test_rejects_sports(self):
        item = self.scorer.score(
            self._raw("Celebrity football transfer shakes Premier League")
        )
        self.assertIsNone(item)

    def test_rejects_non_election_noise(self):
        item = self.scorer.score(
            self._raw(
                "Parliamentary brawl and scandal deepen crisis",
                "No election scheduled",
            )
        )
        self.assertIsNone(item)

    def test_admits_cabinet_reshuffle(self):
        item = self.scorer.score(
            self._raw(
                "Japan cabinet reshuffle names new foreign minister",
                "Prime minister overhauls ministerial posts including finance minister",
                region="japan",
            )
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.category, "cabinet_reshuffle")
        self.assertEqual(item.info_grade, "1")

    def test_rejects_horserace_poll_admits_governance(self):
        race = self.scorer.score(
            self._raw(
                "Candidate leads national poll in presidential preference poll",
                "RCP average shows trail in national poll horse race",
                region="west",
            )
        )
        self.assertIsNone(race)
        gov = self.scorer.score(
            self._raw(
                "Presidential job approval rating slips in latest survey",
                "Net approval and cabinet approval move lower",
                region="west",
            )
        )
        self.assertIsNotNone(gov)
        self.assertEqual(gov.election_type, "governance_poll")

    def test_major_country_grade3_beats_minor_grade2(self):
        """A × grade3 weight can exceed C × grade2 (cold priority)."""
        a3 = self.scorer.importance_model.apply(
            base=2.0, region="west", text="local municipal story USA", category="commodity",
            election_type="local", freshness=1.0,
        )
        c2 = self.scorer.importance_model.apply(
            base=2.0, region="africa", text="diplomacy sanction treaty obscure",
            category="diplomacy", election_type=None, freshness=1.0,
        )
        # Force grades via inputs: commodity+local → 3, diplomacy → 2; west→A, africa→C
        self.assertEqual(a3["country_tier"], "A")
        self.assertEqual(a3["info_grade"], "3")
        self.assertEqual(c2["country_tier"], "C")
        self.assertEqual(c2["info_grade"], "2")
        self.assertGreater(a3["importance"], c2["importance"])

    def test_admits_local_election(self):
        item = self.scorer.score(
            self._raw(
                "Local election campaign heats up in provincial mayor race",
                "Voters head to polls for municipal election",
            )
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.category, "election")
        self.assertEqual(item.election_type, "local")

    def test_admits_party_leadership(self):
        item = self.scorer.score(
            self._raw(
                "Ruling party leadership contest begins as chair race tightens",
                "Party leader election candidates debate",
            )
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.election_type, "party_leadership")

    def test_admits_by_election(self):
        item = self.scorer.score(
            self._raw("By-election called after MP resignation", "Voters face special election")
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.election_type, "by_election")

    def test_admits_diplomacy_with_trade_bridge(self):
        item = self.scorer.score(
            self._raw(
                "Sanctions expand on energy export ban package",
                "Foreign ministers discuss cargo routes and import quotas",
                region="mena",
            )
        )
        self.assertIsNotNone(item)
        self.assertIn(item.category, {"diplomacy", "commodity_diplomacy"})

    def test_region_weight_prefers_mena(self):
        mena = self.scorer.score(
            self._raw("Wheat cargo export from Black Sea", region="mena")
        )
        west = self.scorer.score(
            self._raw("Wheat cargo export from Black Sea", region="west")
        )
        self.assertIsNotNone(mena)
        self.assertIsNotNone(west)
        self.assertGreater(mena.final_score, west.final_score)

    def test_taiwan_slant_cap(self):
        regions = _load("regions.json")
        items = []
        for i, (sid, slant) in enumerate(
            [("ltn", "pan_green"), ("taipei_times", "pan_green"), ("ltn", "pan_green")]
        ):
            it = self.scorer.score(
                RawItem(
                    source_id=sid,
                    source_name=sid,
                    region="taiwan",
                    source_lang="en",
                    title=f"Copper import quota and diplomatic summit {i}",
                    summary="Ambassador negotiates copper import supply",
                    url=f"https://example.test/tw/{i}",
                    published_at="2026-08-03T10:00:00+00:00",
                    slant=slant,
                    raw_xml_hash=f"tw{i}",
                )
            )
            self.assertIsNotNone(it)
            items.append(it)
        bal = apply_regional_and_taiwan_balance(items, limit=10, regions_cfg=regions)
        pan_green = [x for x in bal if (x.slant or "") == "pan_green"]
        self.assertLessEqual(len(pan_green), 2)


class ParseAndBuildTests(unittest.TestCase):
    def test_parse_fixture(self):
        body = (ROOT / "tests" / "fixtures" / "oilprice.xml").read_bytes()
        items = parse_feed_xml(
            body,
            source_id="oilprice",
            source_name="OilPrice",
            region="commodity_specialist",
            source_lang="en",
            max_items=10,
        )
        self.assertGreaterEqual(len(items), 3)

    def test_detect_russian(self):
        self.assertEqual(
            detect_lang("Россия обсуждает экспорт пшеницы"),
            "ru",
        )

    def test_build_from_fixtures(self):
        # Only use the few fixture files we created: map via temporary sources override is hard;
        # call scorer path via fixture_dir — enabled sources without fixtures are skipped.
        doc = build_ticker(
            limit=20,
            fetch_live=False,
            translate=False,
            fixture_dir=ROOT / "tests" / "fixtures",
        )
        self.assertEqual(doc["schema_version"], "ticker-v1")
        self.assertGreaterEqual(doc["stats"]["selected_items"], 1)
        # No pure sports / local election should survive if present in fixture scoring
        titles = " ".join(i["title"]["original"].lower() for i in doc["items"])
        self.assertNotIn("football transfer", titles)
        # local election may be admitted now — only pure sports/noise rejected
        cats = {i["category"] for i in doc["items"]}
        self.assertTrue(
            cats.issubset(
                {
                    "commodity",
                    "diplomacy",
                    "commodity_diplomacy",
                    "election",
                    "cabinet_reshuffle",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()

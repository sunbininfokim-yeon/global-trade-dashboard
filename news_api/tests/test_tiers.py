"""Unit tests for geo/info mapping (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from news_api.tiers import (  # noqa: E402
    NewsTier,
    legacy_geo_letter_to_int,
    map_legacy_scored_fields,
)


class LegacyMapTests(unittest.TestCase):
    def test_letters(self):
        self.assertEqual(legacy_geo_letter_to_int("A"), 1)
        self.assertEqual(legacy_geo_letter_to_int("B"), 2)
        self.assertEqual(legacy_geo_letter_to_int("C"), 3)
        self.assertEqual(legacy_geo_letter_to_int(None), 4)

    def test_korea_india_tier2(self):
        t = NewsTier()
        self.assertEqual(t.geo_for_iso("KOR"), 2)
        self.assertEqual(t.geo_for_iso("IND"), 2)
        self.assertEqual(t.geo_for_iso("USA"), 1)
        self.assertEqual(t.geo_for_iso("UKR"), 3)

    def test_pair_rank_user_rules(self):
        t = NewsTier()
        # (2,2) > (1,3) ; (1,3) == (3,2) ; (3,2) > (2,3)
        self.assertGreater(t.pair_rank(2, 2), t.pair_rank(1, 3))
        self.assertEqual(t.pair_rank(1, 3), t.pair_rank(3, 2))
        self.assertGreater(t.pair_rank(3, 2), t.pair_rank(2, 3))

    def test_amsterdam_hub(self):
        t = NewsTier()
        r = t.resolve(
            text="Port of Rotterdam congestion hits Amsterdam barge market",
            iso3="NLD",
            info_grade=2,
        )
        self.assertEqual(r.geo_base, 3)
        self.assertEqual(r.geo_effective, 2)
        self.assertTrue(any("nl_shipping" in x for x in r.hub_boost_ids) or r.hub_boost_ids)

    def test_ukraine_war_escape(self):
        t = NewsTier()
        r = t.resolve(
            text="Ukraine says full-scale invasion intensifies near Kyiv",
            iso3="UKR",
            info_grade=3,
        )
        self.assertTrue(r.elevated)
        self.assertEqual(r.info, 1)
        self.assertLessEqual(r.geo_effective, 2)

    def test_map_legacy_bridge(self):
        m = map_legacy_scored_fields(
            country_tier_letter="A",
            info_grade_old=3,
            text="Local election results in France matter little globally",
            iso3="FRA",
        )
        self.assertEqual(m["letter_only_geo"], 1)
        # France is tier 2 in new table even if letter was A
        self.assertEqual(m["geo_base"], 2)
        self.assertEqual(m["info"], 3)


if __name__ == "__main__":
    unittest.main()

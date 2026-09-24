"""Offline tests for next-release labels. No network."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor.release_calendar import apply_release_calendar, next_business_day, schedule_for  # noqa: E402


def _pack() -> dict:
    def ind(iid, **extra):
        base = {
            "id": iid, "value": 1.0, "asof": "2026-08-31", "quality": "demo",
            "source": "fixture_synth", "refresh_tier": "monthly",
        }
        base.update(extra)
        return base

    return {
        "countries": [{
            "iso3": "USA",
            "indicators": [
                ind("cpi_yoy", quality="live", source="bls", asof="2026-07-31", refresh_tier="monthly"),
                ind("bond_10y", quality="live_latest", source="fred", asof="2026-09-22", refresh_tier="market_daily", category="rates"),
                ind("fed_total_assets", refresh_tier="weekly"),
                ind("sovereign_cds_5y"),
                ind("gdp_yoy", quality="engine", source="World Bank", asof="2025-12-31", refresh_tier="quarterly"),
            ],
            "categories": {
                "inflation": [{"id": "cpi_yoy", "value": 1.0, "asof": "2026-07-31"}],
            },
        }, {
            "iso3": "ZAF",
            "indicators": [
                ind("cpi_yoy"),
                ind("us_fx_watch", refresh_tier="semiannual", source="treasury"),
            ],
            "categories": {},
        }],
    }


class TestReleaseCalendar(unittest.TestCase):
    def test_next_business_day_skips_weekend(self):
        self.assertEqual(next_business_day(date(2026, 9, 24)), date(2026, 9, 25))
        self.assertEqual(next_business_day(date(2026, 9, 25)), date(2026, 9, 28))

    def test_live_us_cpi_window_is_after_the_reference_month(self):
        doc = _pack()
        apply_release_calendar(doc, today=date(2026, 9, 24))
        cpi = doc["countries"][0]["indicators"][0]
        self.assertEqual(cpi["value"], 1.0)
        self.assertEqual(cpi["next_release_basis"], "typical_window")
        self.assertIsNone(cpi["next_release_on"])
        self.assertEqual(cpi["next_release_window"], {"start": "2026-10-10", "end": "2026-10-14"})
        chip = doc["countries"][0]["categories"]["inflation"][0]
        self.assertEqual(chip["next_release_window"]["start"], "2026-10-10")

    def test_fixture_cpi_does_not_trust_the_month_end_asof(self):
        doc = _pack()
        apply_release_calendar(doc, today=date(2026, 9, 24))
        zaf = doc["countries"][1]["indicators"][0]
        self.assertIn("합성값", zaf["next_release_note_ko"])
        self.assertEqual(zaf["next_release_window"], {"start": "2026-09-15", "end": "2026-09-24"})

    def test_market_and_thursday_and_cds(self):
        doc = _pack()
        apply_release_calendar(doc, today=date(2026, 9, 24))
        by = {i["id"]: i for i in doc["countries"][0]["indicators"]}
        self.assertEqual(by["bond_10y"]["next_release_on"], "2026-09-25")
        monthly = {
            "id": "bond_10y", "quality": "live_latest", "source": "fred:IRLTLT01KRM156N",
            "asof": "2026-08-01", "refresh_tier": "market_daily", "category": "rates",
        }
        stamped = schedule_for(monthly, iso3="KOR", today=date(2026, 9, 24))
        self.assertEqual(stamped["next_release_basis"], "typical_window")
        self.assertEqual(stamped["next_release_window"], {"start": "2026-10-01", "end": "2026-10-20"})
        self.assertIsNone(stamped["next_release_on"])
        self.assertEqual(by["fed_total_assets"]["next_release_on"], "2026-09-24")
        self.assertEqual(by["sovereign_cds_5y"]["next_release_basis"], "not_automated")
        self.assertIsNone(by["sovereign_cds_5y"]["next_release_on"])
        self.assertIn("2025", by["gdp_yoy"]["next_release_note_ko"])


if __name__ == "__main__":
    unittest.main()

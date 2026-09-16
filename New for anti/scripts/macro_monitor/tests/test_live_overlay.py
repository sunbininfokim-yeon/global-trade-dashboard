"""Regression test for the live-overlay asof labeling bug.

overlay_live() previously labeled a FRED-sourced point with the monthly
grid's current-month-end date (dates[-1]) instead of the date FRED itself
reports for that observation -- for a weekly series like TGA (WTREGEN) this
could overstate freshness by up to three weeks. No network calls: the fetch
functions are mocked so this runs offline like the rest of the suite.
"""
from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from macro_monitor.live_overlay import overlay_live


def _indicator(ind_id: str) -> dict:
    return {
        "id": ind_id,
        "value": 100.0,
        "display": "100",
        "format": "bn0",
        "quality": "fixture_synth",
        "asof": "2020-01-01",
        "history": {
            "5y": {"dates": ["2026-08-31", "2026-09-30"], "values": [100.0, 100.0]},
            "10y": {"dates": ["2026-08-31", "2026-09-30"], "values": [100.0, 100.0]},
        },
    }


def _universe() -> dict:
    return {
        "countries": [
            {
                "iso3": "USA",
                "indicators": [_indicator("tga")],
                "categories": {"liquidity": [{"id": "tga", "display": "100", "value": 100.0, "asof": "2020-01-01"}]},
            }
        ]
    }


class TestOverlayLiveAsof(unittest.TestCase):
    @patch("macro_monitor.live_overlay.fetch_fred_worker_latest")
    def test_pins_the_real_observation_date_not_the_month_grid_end(self, mock_fetch):
        # WTREGEN is weekly -- FRED's real print (2026-09-09) is well before
        # the current month's grid end (2026-09-30).
        mock_fetch.return_value = (date(2026, 9, 9), 883335.0)
        universe = _universe()

        overlay_live(universe, asof=date(2026, 9, 16))

        tga = universe["countries"][0]["indicators"][0]
        self.assertEqual(tga["asof"], "2026-09-09")
        self.assertNotEqual(tga["asof"], "2026-09-30")
        self.assertAlmostEqual(tga["value"], 883.335, places=3)  # scale 1e-3, mn -> bn


if __name__ == "__main__":
    unittest.main()

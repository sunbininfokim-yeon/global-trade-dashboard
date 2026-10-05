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


def _grid_indicator(ind_id: str, *, fmt: str = "number1", category: str = "fx") -> dict:
    """A card as the engine builds it: fixture history on the month-end grid up to the current month, and
    an observed_at left over from the build."""
    dates = [f"2025-{m:02d}-28" for m in range(1, 13)] + ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31",
                                                         "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"]
    return {"id": ind_id, "category": category, "value": 100.0, "display": "100.0", "format": fmt, "quality": "fixture_synth",
            "asof": "2026-08-31", "observed_at": "2026-08-31",
            "history": {"5y": {"dates": list(dates), "values": [100.0] * len(dates)}, "10y": {"dates": list(dates), "values": [100.0] * len(dates)}}}


def _months(last_bar: date, n: int = 130) -> list[tuple[date, float]]:
    """Yahoo-style monthly bars stamped on the 1st, ending at `last_bar`'s month."""
    out, y, m = [], last_bar.year, last_bar.month
    for i in range(n):
        out.append((date(y, m, 1), 100.0 + (n - i)))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return sorted(out)


class TestYahooDates(unittest.TestCase):
    def run_overlay(self, pts, last_obs, asof=date(2026, 9, 26)):
        universe = {"countries": [{"iso3": "JPN", "indicators": [_grid_indicator("usdjpy")],
                                   "categories": {"fx": [{"id": "usdjpy", "display": "100.0", "value": 100.0, "asof": "2026-08-31",
                                                          "observed_at": "2026-08-31"}]}}]}
        with patch("macro_monitor.live_overlay.fetch_yahoo", return_value=(pts, last_obs)), \
                patch("macro_monitor.live_overlay.fetch_bok_worker", side_effect=RuntimeError("offline")), \
                patch("macro_monitor.ratings_wiki.fetch_agency_tables", side_effect=RuntimeError("offline")):
            overlay_live(universe, asof=asof)
        c = universe["countries"][0]
        return c["indicators"][0], c["categories"]["fx"][0]

    def test_a_running_month_is_dated_by_its_last_price_not_by_the_month_end(self):
        ind, chip = self.run_overlay(_months(date(2026, 9, 1)), date(2026, 9, 25))
        self.assertEqual((ind["asof"], ind["observed_at"]), ("2026-09-25", "2026-09-25"))
        self.assertEqual(ind["history"]["5y"]["dates"][-1], "2026-09-25")             # not 2026-09-30, which has not happened
        self.assertEqual(ind["history"]["5y"]["dates"][-2], "2026-08-31")
        self.assertEqual((chip["asof"], chip["observed_at"]), ("2026-09-25", "2026-09-25"))
        self.assertEqual(ind["quality"], "live")

    def test_a_month_without_a_bar_is_left_empty_not_filled_with_the_last_value(self):
        ind, chip = self.run_overlay(_months(date(2026, 8, 1)), date(2026, 8, 28))         # Yahoo has nothing for September
        self.assertEqual((ind["asof"], ind["observed_at"]), ("2026-08-28", "2026-08-28"))       # the last price that exists
        self.assertIsNone(ind["history"]["5y"]["values"][-1])                                  # September: no observation
        self.assertEqual(ind["value"], ind["history"]["5y"]["values"][-2])

    def test_without_a_price_timestamp_the_run_date_is_the_upper_bound(self):
        ind, _ = self.run_overlay(_months(date(2026, 9, 1)), None)
        self.assertEqual(ind["asof"], "2026-09-26")                       # today, never the 30th


class TestOtherDates(unittest.TestCase):
    def test_a_pinned_latest_value_moves_the_last_point_to_its_own_date(self):
        from macro_monitor.live_overlay import _pin_latest

        ind = _grid_indicator("kospi", category="equity")
        _pin_latest(ind, 7081.0, "bok:ecos_keystat", "2026-09-23")
        self.assertEqual(ind["history"]["5y"]["dates"][-1], "2026-09-23")
        self.assertEqual(ind["history"]["5y"]["values"][-1], 7081.0)
        self.assertEqual(ind["history"]["5y"]["dates"][-2], "2026-08-31")
        other_month = _grid_indicator("x")
        _pin_latest(other_month, 1.0, "s", "2026-08-15")                       # a different month: the grid label stays
        self.assertEqual(other_month["history"]["5y"]["dates"][-1], "2026-09-30")

    def test_bok_rows_use_their_own_cycle_date(self):
        from macro_monitor.live_overlay import _cycle_to_date

        today = date(2026, 9, 26)
        self.assertEqual(_cycle_to_date("20260924", today), date(2026, 9, 24))
        self.assertEqual(_cycle_to_date("202608", today), date(2026, 8, 31))
        self.assertEqual(_cycle_to_date("2026Q2", today), date(2026, 6, 30))
        self.assertEqual(_cycle_to_date("202609", today), date(2026, 9, 26))      # a month still running: capped at the run date
        self.assertEqual(_cycle_to_date("garbage", today), today)

    @patch("macro_monitor.live_overlay.fetch_fred_worker_latest")
    def test_a_derived_spread_is_as_old_as_its_oldest_input(self, mock_fetch):
        mock_fetch.side_effect = lambda sid: (date(2026, 9, 24), 4.2) if sid == "DGS10" else (date(2026, 9, 22), 3.9)
        universe = {"countries": [{"iso3": "USA", "indicators": [_indicator("bond_10y"), _indicator("bond_2y"), _indicator("spread_10y2y")],
                                   "categories": {}}]}
        for ind in universe["countries"][0]["indicators"]:
            ind["format"] = "pct2"
        with patch("macro_monitor.live_overlay.fetch_yahoo", side_effect=RuntimeError("offline")), \
                patch("macro_monitor.live_overlay.fetch_bok_worker", side_effect=RuntimeError("offline")), \
                patch("macro_monitor.ratings_wiki.fetch_agency_tables", side_effect=RuntimeError("offline")):
            overlay_live(universe, asof=date(2026, 9, 26))
        spread = next(i for i in universe["countries"][0]["indicators"] if i["id"] == "spread_10y2y")
        self.assertEqual((spread["asof"], spread["observed_at"]), ("2026-09-22", "2026-09-22"))


class TestHeadlineSync(unittest.TestCase):
    def test_headline_follows_the_live_card(self):
        from macro_monitor.live_overlay import _sync_chips
        pack = {"categories": {"fx": [{"id": "usdchf"}]},
                "headlines": [{"id": "usdchf", "display": "0.812", "data_status": "demo"}, {"id": "smi", "display": "12,200"}]}
        _sync_chips(pack, {"id": "usdchf", "value": 0.834, "display": "0.834", "asof": "2026-09-30", "data_status": "live"})
        self.assertEqual(pack["headlines"][0], {"id": "usdchf", "display": "0.834", "data_status": "live"})
        self.assertEqual(pack["headlines"][1]["display"], "12,200")


if __name__ == "__main__":
    unittest.main()

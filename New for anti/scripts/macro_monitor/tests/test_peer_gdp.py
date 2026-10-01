"""Offline tests for the World Bank real-GDP-growth peer overlay."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from macro_monitor.peer_gdp import build_snapshot, fetch_gdp_growth


class TestFetchGdpGrowth(unittest.TestCase):
    @patch("macro_monitor.peer_gdp._get_json")
    def test_drops_null_years_and_sorts_ascending(self, mock_get):
        mock_get.return_value = [
            {"page": 1},
            [
                {"date": "2026", "value": None},  # not published yet
                {"date": "2025", "value": 2.16138195623856},
                {"date": "2024", "value": 2.79318715363841},
            ],
        ]
        observations = fetch_gdp_growth("USA")
        self.assertEqual([o["date"] for o in observations], ["2024-12-31", "2025-12-31"])
        self.assertEqual(observations[-1]["value"], 2.1614)  # rounded, not truncated

    @patch("macro_monitor.peer_gdp._get_json")
    def test_empty_series_returns_empty_list_not_error(self, mock_get):
        mock_get.return_value = [{"page": 1}, []]
        self.assertEqual(fetch_gdp_growth("XXX"), [])


class TestBuildSnapshot(unittest.TestCase):
    @patch("macro_monitor.peer_gdp.fetch_gdp_growth")
    def test_one_country_failing_does_not_drop_the_others(self, mock_fetch):
        def side_effect(iso3, **kwargs):
            if iso3 == "RUS":
                raise RuntimeError("boom")
            return [{"date": "2025-12-31", "value": 1.0}]

        mock_fetch.side_effect = side_effect
        snapshot = build_snapshot(countries=("USA", "RUS", "JPN"))
        self.assertEqual(snapshot["countries"]["USA"]["status"], "ok")
        self.assertEqual(snapshot["countries"]["JPN"]["status"], "ok")
        self.assertEqual(snapshot["countries"]["RUS"]["status"], "error")
        self.assertEqual(snapshot["countries"]["RUS"]["observations"], [])


if __name__ == "__main__":
    unittest.main()

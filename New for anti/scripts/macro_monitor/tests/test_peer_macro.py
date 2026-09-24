"""Offline tests for the non-US peer macro graft. Network is injected."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor.peer_macro import apply_peer_macro  # noqa: E402


def _indicator(iid: str, *, quality: str = "demo", value: float = 1.0) -> dict:
    return {
        "id": iid,
        "format": "pct2",
        "value": value,
        "display": f"{value:.2f}%",
        "asof": "2026-08-31",
        "observed_at": "2026-08-31",
        "quality": quality,
        "source": "fixture_synth",
        "data_status": "demo",
        "history": {
            "5y": {"dates": ["2026-08-31"], "values": [value]},
            "10y": {"dates": ["2026-08-31"], "values": [value]},
        },
    }


def _pack() -> dict:
    return {
        "countries": [
            {
                "iso3": "ZAF",
                "indicators": [
                    _indicator("sagb_10y", value=10.8),
                    _indicator("cpi_yoy", value=4.8),
                    _indicator("jse_top40", value=72000.0),
                ],
                "categories": {
                    "rates": [{"id": "sagb_10y", "display": "10.80%", "value": 10.8, "asof": "2026-08-31"}],
                },
            },
            {
                "iso3": "USA",
                "indicators": [_indicator("bond_10y", quality="live_latest", value=4.7)],
            },
            {
                "iso3": "EMU",
                "indicators": [_indicator("deposit_facility", value=4.0)],
            },
        ]
    }


class TestPeerMacro(unittest.TestCase):
    def test_grafts_observation_date_not_month_end(self):
        doc = _pack()

        def fred(series_id: str):
            if series_id == "IRLTLT01ZAM156N":
                return date(2026, 8, 1), 8.75
            raise RuntimeError(f"unexpected {series_id}")

        def yahoo(symbol: str):
            if symbol == "^J200.JO":
                return date(2026, 9, 22), 104073.0
            raise RuntimeError(f"unexpected {symbol}")

        stats = apply_peer_macro(
            doc, today=date(2026, 9, 23), retrieved_at="2026-09-23T12:00:00Z",
            fred=fred, yahoo=yahoo,
        )
        self.assertIn("ZAF:sagb_10y", stats["ok"])
        self.assertIn("ZAF:jse_top40", stats["ok"])
        bond = doc["countries"][0]["indicators"][0]
        self.assertEqual(bond["asof"], "2026-08-01")
        self.assertEqual(bond["observed_at"], "2026-08-01")
        self.assertEqual(bond["value"], 8.75)
        self.assertEqual(bond["display"], "8.75%")
        self.assertEqual(bond["source"], "fred:IRLTLT01ZAM156N")
        self.assertEqual(bond["quality"], "live_latest")
        self.assertEqual(bond["data_status"], "live_latest")
        self.assertEqual(bond["retrieved_at"], "2026-09-23T12:00:00Z")
        self.assertEqual(bond["history"]["5y"]["dates"], ["2026-08-31"])
        self.assertEqual(bond["history"]["5y"]["values"], [8.75])
        self.assertEqual(bond["history"]["5y"]["real_points_from_end"], 1)
        chip = doc["countries"][0]["categories"]["rates"][0]
        self.assertEqual(chip["asof"], "2026-08-01")
        self.assertEqual(chip["value"], 8.75)

        cpi = doc["countries"][0]["indicators"][1]
        self.assertEqual(cpi["source"], "fixture_synth")
        self.assertEqual(cpi["asof"], "2026-08-31")
        self.assertEqual(cpi["value"], 4.8)

        usa = doc["countries"][1]["indicators"][0]
        self.assertEqual(usa["value"], 4.7)
        self.assertEqual(usa["source"], "fixture_synth")

    def test_failed_fetch_does_not_overwrite(self):
        doc = _pack()

        def fred(series_id: str):
            raise RuntimeError("down")

        def yahoo(symbol: str):
            raise RuntimeError("down")

        stats = apply_peer_macro(
            doc, today=date(2026, 9, 23), retrieved_at="2026-09-23T12:00:00Z",
            fred=fred, yahoo=yahoo,
        )
        self.assertFalse(stats["ok"])
        self.assertTrue(stats["fail"])
        bond = doc["countries"][0]["indicators"][0]
        self.assertEqual(bond["value"], 10.8)
        self.assertEqual(bond["asof"], "2026-08-31")
        self.assertEqual(bond["source"], "fixture_synth")

    def test_stale_print_is_not_grafted(self):
        doc = _pack()

        def fred(series_id: str):
            if series_id == "ECBDFR":
                return date(2024, 1, 1), 4.0
            raise RuntimeError("skip")

        stats = apply_peer_macro(
            doc, today=date(2026, 9, 23), retrieved_at="2026-09-23T12:00:00Z",
            fred=fred, yahoo=lambda symbol: (_ for _ in ()).throw(RuntimeError("skip")),
        )
        self.assertIn("EMU:deposit_facility:stale 2024-01-01", stats["fail"])
        facility = doc["countries"][2]["indicators"][0]
        self.assertEqual(facility["value"], 4.0)
        self.assertEqual(facility["source"], "fixture_synth")


if __name__ == "__main__":
    unittest.main()

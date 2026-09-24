"""Offline tests for keyless CPI and policy grafts. No network."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from macro_monitor.keyless_prints import (  # noqa: E402
    all_items_cpi_title,
    apply_keyless_prints,
    parse_bcb_latest,
    parse_boe_csv,
    parse_ons_latest,
    yoy_from_month_index,
)
from macro_monitor.release_calendar import schedule_for  # noqa: E402


def _indicator(iid: str, *, quality: str = "demo", value: float = 1.0, fmt: str = "pct1") -> dict:
    return {
        "id": iid,
        "format": fmt,
        "value": value,
        "display": f"{value:.1f}%",
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
        "countries": [{
            "iso3": "GBR",
            "indicators": [
                _indicator("cpi_yoy", value=2.8),
                _indicator("core_cpi_yoy", value=3.3),
                _indicator("bank_rate", value=4.25, fmt="pct2"),
            ],
            "categories": {
                "inflation": [{"id": "cpi_yoy", "display": "2.8%", "value": 2.8, "asof": "2026-08-31"}],
            },
        }, {
            "iso3": "CAN",
            "indicators": [
                _indicator("cpi_yoy", value=2.4),
                _indicator("boc_overnight", value=2.75, fmt="pct2"),
            ],
            "categories": {},
        }, {
            "iso3": "BRA",
            "indicators": [
                _indicator("ipca", value=4.5),
                _indicator("selic_rate", value=13.25, fmt="pct2"),
            ],
            "categories": {},
        }, {
            "iso3": "USA",
            "indicators": [_indicator("cpi_yoy", quality="live", value=3.3)],
            "categories": {},
        }],
    }


class TestKeylessPrints(unittest.TestCase):
    def test_ons_uses_the_reference_month_not_the_chart_grid(self):
        observed, value = parse_ons_latest({
            "description": {"title": "CPI ANNUAL RATE 00: ALL ITEMS 2015=100"},
            "months": [
                {"year": "2026", "month": "July", "value": "2.9"},
                {"year": "2026", "month": "August", "value": "3.1"},
            ],
        }, ("ANNUAL RATE", "ALL ITEMS"))
        self.assertEqual(observed, date(2026, 8, 1))
        self.assertEqual(value, 3.1)

    def test_wrong_ons_title_is_refused(self):
        with self.assertRaises(RuntimeError):
            parse_ons_latest({
                "description": {"title": "CPI 12mth: Excluding Energy, food"},
                "months": [{"year": "2026", "month": "August", "value": "2.6"}],
            }, ("ALL ITEMS",))

    def test_bcb_ignores_a_date_after_today(self):
        observed, value = parse_bcb_latest([
            {"data": "23/09/2026", "valor": "13.75"},
            {"data": "04/11/2026", "valor": "99.00"},
        ], today=date(2026, 9, 24))
        self.assertEqual((observed, value), (date(2026, 9, 23), 13.75))

    def test_boe_takes_the_latest_row(self):
        observed, value = parse_boe_csv(
            "DATE,IUDBEDR\n21 Sep 2026,3.75\n22 Sep 2026,3.75\n",
            today=date(2026, 9, 24),
        )
        self.assertEqual((observed, value), (date(2026, 9, 22), 3.75))

    def test_statcan_yoy_requires_the_all_items_index(self):
        self.assertTrue(all_items_cpi_title("Canada;All-items"))
        self.assertTrue(all_items_cpi_title("Consumer Price Index, all-items, Canada"))
        self.assertFalse(all_items_cpi_title("Canada;All-items excluding food and energy"))
        observed, value = yoy_from_month_index([
            (date(2025, 8, 1), 164.8),
            (date(2026, 8, 1), 169.8),
        ])
        self.assertEqual(observed, date(2026, 8, 1))
        self.assertEqual(value, 3.0)

    def test_failed_fetch_keeps_the_previous_card(self):
        doc = _pack()

        def boom():
            raise RuntimeError("down")

        stats = apply_keyless_prints(
            doc, today=date(2026, 9, 24), retrieved_at="2026-09-24T00:00:00Z",
            fetchers={"gbr_cpi": boom},
        )
        self.assertIn("GBR:cpi_yoy", stats["fail"][0])
        cpi = doc["countries"][0]["indicators"][0]
        self.assertEqual(cpi["value"], 2.8)
        self.assertEqual(cpi["source"], "fixture_synth")
        self.assertEqual(cpi["asof"], "2026-08-31")

    def test_stale_print_is_not_grafted(self):
        doc = _pack()
        stats = apply_keyless_prints(
            doc, today=date(2026, 9, 24), retrieved_at="2026-09-24T00:00:00Z",
            fetchers={"gbr_cpi": lambda: (date(2025, 12, 1), 2.0)},
        )
        self.assertIn("stale", stats["fail"][0])
        self.assertEqual(doc["countries"][0]["indicators"][0]["value"], 2.8)

    def test_graft_pins_observation_date_and_chip(self):
        doc = _pack()
        stats = apply_keyless_prints(
            doc, today=date(2026, 9, 24), retrieved_at="2026-09-24T06:00:00Z",
            fetchers={
                "gbr_cpi": lambda: (date(2026, 8, 1), 3.1),
                "gbr_core": lambda: (date(2026, 8, 1), 2.6),
                "gbr_bank_rate": lambda: (date(2026, 9, 22), 3.75),
                "can_overnight": lambda: (date(2026, 9, 22), 2.25),
                "bra_ipca": lambda: (date(2026, 8, 1), 4.22),
                "bra_selic": lambda: (date(2026, 9, 24), 13.75),
                "can_cpi": lambda: (_ for _ in ()).throw(RuntimeError("metadata down")),
            },
        )
        self.assertIn("GBR:cpi_yoy", stats["ok"])
        self.assertIn("BRA:selic_rate", stats["ok"])
        self.assertTrue(any(row.startswith("CAN:cpi_yoy") for row in stats["fail"]))
        cpi = doc["countries"][0]["indicators"][0]
        self.assertEqual(cpi["asof"], "2026-08-01")
        self.assertEqual(cpi["value"], 3.1)
        self.assertEqual(cpi["source"], "ons:D7G7")
        self.assertEqual(cpi["quality"], "live_latest")
        self.assertEqual(cpi["history"]["5y"]["dates"][-1], "2026-08-31")
        self.assertEqual(cpi["history"]["5y"]["values"][-1], 3.1)
        self.assertEqual(cpi["history"]["5y"]["real_points_from_end"], 1)
        chip = doc["countries"][0]["categories"]["inflation"][0]
        self.assertEqual(chip["value"], 3.1)
        self.assertEqual(chip["asof"], "2026-08-01")
        usa = doc["countries"][3]["indicators"][0]
        self.assertEqual(usa["value"], 3.3)
        self.assertEqual(usa["quality"], "live")

    def test_boc_overnight_has_no_invented_release_day(self):
        fields = schedule_for(
            {"id": "boc_overnight", "quality": "live_latest", "asof": "2026-09-22"},
            iso3="CAN", today=date(2026, 9, 24),
        )
        self.assertIsNone(fields["next_release_on"])
        self.assertIn("회의", fields["next_release_note_ko"])


if __name__ == "__main__":
    unittest.main()

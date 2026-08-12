#!/usr/bin/env python3
"""Tests for US regime + transmission (no network)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.us_scenarios import build_transmission, classify_name, classify_universe


class TestUsScenarios(unittest.TestCase):
    def test_downside_put_regime(self):
        row = {
            "symbol": "TEST",
            "spot": {"day_return": -0.03, "premarket_gap": -0.02},
            "options": {
                "put_call_volume": 1.5,
                "put_call_oi": 1.2,
                "call_volume": 10000,
                "put_volume": 15000,
            },
            "finra_short": {"short_chg_pct": 10.0, "days_to_cover": 2.0},
        }
        out = classify_name(row)
        self.assertIn("downside_put_bid", out["regimes"])
        self.assertEqual(out["primary_channel"], "downside")
        self.assertIn(out["stress_level"], ("watch", "high"))

    def test_upside_call_regime(self):
        row = {
            "symbol": "TEST",
            "spot": {"day_return": 0.03},
            "options": {
                "put_call_volume": 0.4,
                "put_call_oi": 0.5,
                "call_volume": 80000,
                "put_volume": 20000,
            },
            "finra_short": {"short_chg_pct": -2.0},
        }
        out = classify_name(row)
        self.assertIn("upside_call_bid", out["regimes"])
        self.assertEqual(out["primary_channel"], "upside")

    def test_transmission_joins_graph(self):
        us = {
            "as_of": "2026-08-08",
            "source_priority_used": ["finra_short", "yahoo_spot_options_fallback"],
            "disclaimer_ko": "test",
            "names": [
                {
                    "symbol": "MU",
                    "spot": {"day_return": -0.04},
                    "options": {
                        "put_call_volume": 1.4,
                        "put_call_oi": 1.1,
                        "call_volume": 20000,
                        "put_volume": 30000,
                    },
                    "finra_short": {"short_chg_pct": 12.0},
                }
            ],
        }
        regimes = classify_universe(us)
        graph = {
            "edges": [
                {
                    "id": "mu_hynix_peer",
                    "us": "MU",
                    "kr": "000660",
                    "edge_type": "peer_memory",
                    "weight": 0.9,
                }
            ]
        }
        tx = build_transmission(us, regimes, graph)
        self.assertEqual(tx["schema_version"], "us-kr-transmission-v1")
        self.assertTrue(tx["channels"]["downside"]["heat"] > 0)
        self.assertIn("000660", tx["channels"]["downside"]["kr_tickers"])
        self.assertEqual(tx["global_spillover"]["title_en"], "Global Spillover Effect")
        self.assertEqual(tx["global_spillover"]["headline"], tx["headline"])
        self.assertEqual(tx["why_short_ko"], tx["why_ko"])
        # no banned nicknames in payload
        blob = json.dumps(tx, ensure_ascii=False).lower()
        self.assertNotIn("leopold", blob)

    def test_tier_b_merge(self):
        us = {
            "as_of": "2026-08-08",
            "source_priority_used": ["cboe_options"],
            "names": [
                {
                    "symbol": "AVGO",
                    "spot": {"day_return": -0.03},
                    "options": {
                        "put_call_volume": 1.4,
                        "put_call_oi": 1.1,
                        "call_volume": 20000,
                        "put_volume": 30000,
                    },
                    "finra_short": {"short_chg_pct": 5.0},
                }
            ],
        }
        regimes = classify_universe(us)
        graph = {"edges": []}
        disc = {
            "discovered_edges": [
                {
                    "id": "disc_avgo_000660",
                    "us": "AVGO",
                    "kr": "000660",
                    "weight": 0.8,
                    "score": 0.5,
                    "corr_us_close_kr_open": {"corr": 0.5, "corr_us_down": 0.4},
                }
            ]
        }
        tx = build_transmission(us, regimes, graph, discovered=disc)
        self.assertGreater(tx["tier_b_edges_fired"], 0)
        self.assertIn("000660", tx["channels"]["downside"]["kr_tickers"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for stale-but-explicit public-observation fallback behavior."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_market_microstructure import preserve_unobserved_public_observations  # noqa: E402


def observed(value: int) -> dict:
    return {"value": value, "quality": "observed", "source": "official"}


class TestPreservePublicObservations(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = {
            "as_of": "2026-09-09",
            "unrelated": {"quality": "missing"},
            "market_letf_derivatives_ratios": observed(10),
            "letf_category_share": observed(20),
            "deposit_credit": {**observed(30), "as_of": "2026-09-08"},
            "short_interest_meta": observed(40),
            "flows_kospi_market": {**observed(50), "date_raw": "2026.09.07"},
            "public_extras": {
                "letf_category_share": observed(20),
                "deposit_credit": {**observed(30), "as_of": "2026-09-08"},
                "short_interest": observed(40),
                "kospi_investor_flows": {**observed(60), "latest": {"date_raw": "2026.09.07"}},
            },
        }
        self.missing = {
            "as_of": "2026-09-12",
            "unrelated": {"quality": "missing"},
            "market_letf_derivatives_ratios": {"quality": "missing"},
            "letf_category_share": None,
            "deposit_credit": {"quality": "missing"},
            "short_interest_meta": {"quality": "missing"},
            "flows_kospi_market": None,
            "public_extras": {
                "letf_category_share": None,
                "deposit_credit": {"quality": "missing"},
                "short_interest": {"quality": "missing"},
                "kospi_investor_flows": {"quality": "missing"},
                "errors": ["FinanceDataReader unavailable"],
            },
        }

    def test_failed_collectors_keep_prior_values_with_observation_dates(self) -> None:
        out = preserve_unobserved_public_observations(
            copy.deepcopy(self.missing), self.previous
        )
        self.assertEqual(out["market_letf_derivatives_ratios"]["quality"], "carried_forward")
        self.assertEqual(out["market_letf_derivatives_ratios"]["as_of"], "2026-09-09")
        self.assertEqual(out["market_letf_derivatives_ratios"]["carried_at"], "2026-09-12")
        self.assertEqual(out["letf_category_share"]["quality"], "carried_forward")
        self.assertEqual(out["deposit_credit"]["as_of"], "2026-09-08")
        self.assertEqual(out["flows_kospi_market"]["as_of"], "2026-09-07")
        self.assertEqual(
            out["public_extras"]["kospi_investor_flows"]["quality"],
            "carried_forward",
        )
        self.assertEqual(out["public_extras"]["errors"], ["FinanceDataReader unavailable"])
        self.assertEqual(out["unrelated"], self.missing["unrelated"])

        next_missing = copy.deepcopy(self.missing)
        next_missing["as_of"] = "2026-09-13"
        next_out = preserve_unobserved_public_observations(next_missing, out)
        self.assertEqual(next_out["market_letf_derivatives_ratios"]["as_of"], "2026-09-09")
        self.assertEqual(next_out["market_letf_derivatives_ratios"]["carried_at"], "2026-09-13")

    def test_current_observation_is_not_replaced_and_gets_its_date(self) -> None:
        current = copy.deepcopy(self.missing)
        current["market_letf_derivatives_ratios"] = observed(99)
        out = preserve_unobserved_public_observations(current, self.previous)
        ratios = out["market_letf_derivatives_ratios"]
        self.assertEqual(ratios["quality"], "observed")
        self.assertEqual(ratios["value"], 99)
        self.assertEqual(ratios["as_of"], "2026-09-12")
        self.assertNotIn("carried_at", ratios)


if __name__ == "__main__":
    unittest.main()

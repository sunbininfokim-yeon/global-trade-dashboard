"""Decision-contract tests for U.S. macro quality models."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from build_us_macro_quality import build_snapshot
from macro_monitor.us_quality import (
    assess_current_cpi_pathway,
    assess_lag_evidence,
    audit_point_in_time,
    classify_employment_quality,
    classify_gdp_quality,
    compare_fomc_meetings,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "config" / "us_macro_quality.spec.json").read_text(encoding="utf-8"))


def release(release_id: str, published_at: str) -> dict:
    return {
        "source_id": "bls_cpi",
        "release_id": release_id,
        "published_at": published_at,
        "reference_period": "2026-07",
        "vintage": "first",
        "source_url": "https://www.bls.gov/news.release/cpi.toc.htm",
        "artifact_sha256": "abc",
        "quality": "observed",
        "retrieved_at": "2026-08-12T12:31:00Z",
    }


class TestUsMacroQuality(unittest.TestCase):
    def test_point_in_time_audit_blocks_future_release(self):
        rows = [
            release("available", "2026-08-12T12:30:00Z"),
            release("future", "2026-08-13T12:30:00Z"),
        ]
        audit = audit_point_in_time(rows, "2026-08-12T13:00:00Z")
        self.assertFalse(audit["passed"])
        self.assertEqual([row["release_id"] for row in audit["leaked"]], ["future"])

    def test_employment_classifies_government_support_and_keeps_adp_separate(self):
        result = classify_employment_quality(
            {
                "total_nfp_k": 100,
                "private_k": 55,
                "government_k": 45,
                "private_cyclical_k": 10,
                "private_defensive_k": 35,
                "three_month_diffusion_pct": 47,
                "avg_weekly_hours_change_3m": -0.1,
                "adp_private_k": 80,
            }
        )
        self.assertEqual(result["state"], "government_supported")
        self.assertEqual(result["government_share_pct"], 45.0)
        self.assertTrue(any("ADP" in warning for warning in result["warnings"]))

    def test_employment_requires_breadth_for_private_broadening(self):
        result = classify_employment_quality(
            {
                "total_nfp_k": 190,
                "private_k": 180,
                "government_k": 10,
                "private_cyclical_k": 90,
                "private_defensive_k": 60,
                "three_month_diffusion_pct": 58,
                "avg_weekly_hours_change_3m": 0.0,
            }
        )
        self.assertEqual(result["state"], "private_broadening")

    def test_gdp_uses_contributions_and_private_final_sales(self):
        result = classify_gdp_quality(
            {
                "real_gdp_pct": 2.8,
                "final_sales_private_domestic_purchasers_pct": 2.3,
                "contributions_pp": {
                    "personal_consumption": 1.6,
                    "residential_investment": 0.1,
                    "structures": 0.1,
                    "equipment": 0.2,
                    "intellectual_property": 0.2,
                    "inventory_change": 0.1,
                    "federal_government": 0.1,
                    "state_local_government": 0.1,
                    "exports": 0.2,
                    "imports": -0.1,
                },
            }
        )
        self.assertEqual(result["state"], "private_demand_led")

    def test_fomc_reports_dissent_and_roster_changes_without_scores(self):
        previous = {
            "meeting_date": "2026-06-17",
            "eligible_voters": ["a", "b"],
            "votes": [
                {"person_id": "a", "name": "A", "vote": "for"},
                {"person_id": "b", "name": "B", "vote": "for"},
            ],
        }
        current = {
            "meeting_date": "2026-07-29",
            "eligible_voters": ["a", "c"],
            "votes": [
                {"person_id": "a", "name": "A", "vote": "against", "dissent_direction": "tighter", "evidence": "statement"},
                {"person_id": "c", "name": "C", "vote": "for"},
            ],
        }
        result = compare_fomc_meetings(previous, current)
        self.assertEqual(result["current_dissents"]["directions"], {"tighter": 1})
        self.assertEqual(result["roster_changes"]["new_voters"], ["c"])
        self.assertNotIn("hawk_score", result)

    def test_cpi_lag_support_requires_every_gate(self):
        strong = assess_lag_evidence(
            {
                "leakage_audit_passed": True,
                "oos_n": 60,
                "expected_direction_holds": True,
                "adjacent_lags_supported": 3,
                "rolling_sign_stability": 0.75,
                "oos_improvement_vs_best_baseline_pct": 7.0,
                "uncertainty_passed": True,
                "regime_stable": True,
            }
        )
        self.assertEqual(strong["status"], "historically_supported")
        leaked = assess_lag_evidence({"leakage_audit_passed": False, "oos_n": 100})
        self.assertEqual(leaked["status"], "invalid_leakage")

    def test_measurement_link_never_becomes_a_signal(self):
        result = assess_current_cpi_pathway(
            {"id": "rent_oer", "type": "measurement_link"},
            historical_status="historically_supported",
            source_impulse_now=True,
            target_response_observed=True,
        )
        self.assertEqual(result["current_state"], "context_only")
        self.assertFalse(result["display_eligible"])

    def test_supported_market_hypothesis_can_only_enter_candidate_window(self):
        result = assess_current_cpi_pathway(
            {"id": "auto_cost_to_insurance", "type": "market_hypothesis"},
            historical_status="historically_supported",
            source_impulse_now=True,
        )
        self.assertEqual(result["current_state"], "candidate_lag_window")
        self.assertEqual(result["interpretation"], "current_relevance_not_causal_finding_or_forecast")

    def test_empty_build_keeps_hypotheses_unvalidated(self):
        doc = build_snapshot({}, SPEC, generated_at="2026-08-12T00:00:00Z")
        self.assertEqual(doc["source"]["quality"], "partial_or_empty")
        candidates = doc["inflation_quality"]["relationship_policy"]["internal_candidates"]
        self.assertTrue(all(row["status"] == "hypothesis" for row in candidates))
        self.assertEqual(doc["inflation_quality"]["lag_evidence"], [])


if __name__ == "__main__":
    unittest.main()

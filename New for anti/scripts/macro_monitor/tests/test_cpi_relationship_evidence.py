from __future__ import annotations

import unittest

from macro_monitor.cpi.relationship_evidence import (
    assess_watch_phase,
    build_evidence_snapshot,
    classify_backtest,
)


def history(*, latest: float, prior: float = 0.0) -> dict[str, float]:
    rows = {}
    for year in range(2020, 2026):
        for month in range(1, 13):
            rows[f"{year}-{month:02d}"] = prior + ((month % 3) - 1) * 0.05
    rows["2026-01"] = latest
    return rows


class TestCpiRelationshipEvidence(unittest.TestCase):
    def test_practical_watch_is_not_promoted_to_validated(self):
        result = classify_backtest({
            "id": "parts_to_repair",
            "relationship_map_id": "vehicle_parts_to_repair",
            "coverage": {"first_month": "2011-02", "last_month": "2026-01"},
            "out_of_sample": {"rmse_improvement_pct": 1.5, "diebold_mariano": {"pvalue": 0.44}},
            "best_lag_out_of_sample_exploratory": {
                "lag_months": 10, "rmse_improvement_pct": 4.2,
                "diebold_mariano": {"pvalue": 0.087},
            },
            "conditional_predictive_test": {"fdr_qvalue": 0.03},
        })
        self.assertEqual(result["status"], "weak_watch_candidate")

    def test_starting_phase_requires_source_impulse_without_target_response(self):
        relation = {
            "id": "parts_to_repair", "type": "market_hypothesis",
            "source_ids": ["parts"], "target_ids": ["repair"], "lag_months": [1, 3],
        }
        phase = assess_watch_phase(
            relation,
            series={"parts": history(latest=1.2), "repair": history(latest=0.0)},
            item_labels={"parts": "부품", "repair": "정비"},
        )
        self.assertEqual(phase["phase"], "starting")
        self.assertEqual(phase["interpretation"], "relationship_watch_only_not_causal_finding_or_forecast")

    def test_measurement_link_never_receives_inflation_phase(self):
        mapping = {
            "driver_frontier": [],
            "items": [{"id": "rent", "label_ko": "임차료"}, {"id": "oer", "label_ko": "OER"}],
            "relationships": [{
                "id": "rent_oer", "type": "measurement_link",
                "source_ids": ["rent"], "target_ids": ["oer"], "lag_months": [0, 6],
            }],
        }
        result = build_evidence_snapshot(
            mapping, backtest_rows=[], series={"rent": history(latest=0.4), "oer": history(latest=0.3)},
            generated_at="2026-01-31T00:00:00Z",
        )
        row = result["relationships"][0]
        self.assertEqual(row["evidence_tier"], "official_methodology")
        self.assertEqual(row["phase"]["phase"], "not_applicable")


if __name__ == "__main__":
    unittest.main()

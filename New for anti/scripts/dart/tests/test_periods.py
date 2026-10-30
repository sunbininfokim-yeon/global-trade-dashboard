"""Period-integrity contract tests.  All inputs are synthetic and offline."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.periods import (  # noqa: E402
    PeriodContractError,
    discrete_quarters_from_ytd,
    fiscal_period_metadata,
    point_in_time_quarters,
    quarterly_fcf_from_ytd,
    reconcile_fcf,
)


class TestFiscalPeriodMetadata(unittest.TestCase):
    def test_non_december_fiscal_year_is_not_calendar_hardcoded(self):
        periods = fiscal_period_metadata("2025-03-31")
        self.assertEqual(periods["fiscal_year"], 2025)
        self.assertEqual(periods["quarters"]["Q1"]["period_end"], "2024-06-30")
        self.assertEqual(periods["quarters"]["Q2"]["period_end"], "2024-09-30")
        self.assertEqual(periods["quarters"]["Q3"]["period_end"], "2024-12-31")
        self.assertEqual(periods["quarters"]["Q4"]["period_end"], "2025-03-31")

    def test_reported_period_ends_are_retained_and_checked(self):
        periods = fiscal_period_metadata(
            "2025-12-31",
            report_ends={"Q1": "2025-03-30", "H1": "2025-06-29", "Q3": "2025-09-28", "FY": "2025-12-31"},
        )
        self.assertEqual(periods["quarters"]["Q2"]["period_end"], "2025-06-29")
        self.assertEqual(periods["quarters"]["Q2"]["endpoint_origin"], "reported")
        with self.assertRaisesRegex(PeriodContractError, "fy_end_mismatch"):
            fiscal_period_metadata("2025-12-31", report_ends={"FY": "2025-12-30"})

    def test_public_converter_rejects_incomplete_metadata(self):
        with self.assertRaisesRegex(PeriodContractError, "missing_quarter_metadata:Q4"):
            discrete_quarters_from_ytd(
                {"Q1": 10},
                periods={"quarters": {"Q1": {}, "Q2": {}, "Q3": {}}},
            )


class TestDartYtdQuarterConversion(unittest.TestCase):
    def setUp(self):
        self.periods = fiscal_period_metadata("2025-12-31")

    def test_ytd_flows_become_discrete_quarters(self):
        got = discrete_quarters_from_ytd(
            {"Q1": 10, "H1": 31, "Q3": 48, "FY": 70},
            periods=self.periods,
            metric_id="CFO",
        )
        self.assertEqual([got[q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")], [10.0, 21.0, 17.0, 22.0])
        self.assertEqual(got["Q4"]["derivation"], "FY_ytd_minus_Q3_ytd")
        self.assertEqual(got["Q2"]["period_kind"], "flow_discrete_quarter")

    def test_missing_predecessor_suppresses_only_that_quarter(self):
        got = discrete_quarters_from_ytd(
            {"H1": 31, "Q3": 48, "FY": 70}, periods=self.periods, metric_id="CFO"
        )
        self.assertIsNone(got["Q2"]["value"])
        self.assertEqual(got["Q2"]["reason"], "missing:predecessor_ytd_Q1")
        self.assertEqual(got["Q3"]["value"], 17.0)
        self.assertEqual(got["Q4"]["value"], 22.0)

    def test_explicit_direct_quarter_precedes_matching_ytd_subtraction(self):
        got = discrete_quarters_from_ytd(
            {"Q1": 10, "H1": 31, "Q3": 48, "FY": 70},
            direct_values={"Q2": 21, "Q3": 17},
            periods=self.periods,
            metric_id="REVENUE",
        )
        self.assertEqual(got["Q2"]["value"], 21.0)
        self.assertEqual(got["Q2"]["derivation"], "reported_direct_quarter")
        self.assertEqual(got["Q2"]["ytd_derived_value"], 21.0)
        self.assertEqual(got["Q3"]["derivation"], "reported_direct_quarter")

    def test_direct_and_ytd_conflict_is_unavailable(self):
        got = discrete_quarters_from_ytd(
            {"Q1": 10, "H1": 31},
            direct_values={"Q2": 20},
            periods=self.periods,
            metric_id="REVENUE",
        )
        self.assertIsNone(got["Q2"]["value"])
        self.assertEqual(got["Q2"]["reason"], "conflict:direct_quarter_vs_ytd_derivation")
        self.assertEqual(got["Q2"]["direct_value"], 20.0)
        self.assertEqual(got["Q2"]["ytd_derived_value"], 21.0)

    def test_balances_are_not_differenced(self):
        got = point_in_time_quarters(
            {"Q1": 100, "H1": 130, "Q3": 90, "FY": 120}, periods=self.periods, metric_id="CASH"
        )
        self.assertEqual([got[q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")], [100.0, 130.0, 90.0, 120.0])
        self.assertEqual(got["Q3"]["derivation"], "reported_point_in_time_not_differenced")
        self.assertEqual(got["Q3"]["period_kind"], "balance_point_in_time")


class TestFcfPeriodIntegrity(unittest.TestCase):
    def setUp(self):
        self.periods = fiscal_period_metadata("2025-12-31")

    def test_fcf_reconciles_annual_and_discrete_quarters(self):
        cfo = {"Q1": 20, "H1": 55, "Q3": 80, "FY": 110}
        capex = {"Q1": -8, "H1": -20, "Q3": -31, "FY": -45}
        quarters = quarterly_fcf_from_ytd(cfo, capex, periods=self.periods)
        self.assertEqual([quarters[q]["value"] for q in ("Q1", "Q2", "Q3", "Q4")], [12.0, 23.0, 14.0, 16.0])
        check = reconcile_fcf(cfo, capex, quarters, absolute_tolerance=0.0001)
        self.assertEqual(check["status"], "ok")
        self.assertTrue(check["reconciled"])
        self.assertEqual(check["annual_fcf"], 65.0)
        self.assertEqual(check["quarter_sum"], 65.0)

    def test_lg_chem_style_annual_q4_difference_is_not_equated(self):
        # Q4 is the FY-minus-9M residual, while annual FCF is the entire FY.
        cfo = {"Q1": 20, "H1": 55, "Q3": 80, "FY": 110}
        capex = {"Q1": -8, "H1": -20, "Q3": -31, "FY": -45}
        quarters = quarterly_fcf_from_ytd(cfo, capex, periods=self.periods)
        self.assertEqual(quarters["Q4"]["value"], 16.0)
        self.assertEqual(reconcile_fcf(cfo, capex, quarters)["annual_fcf"], 65.0)
        self.assertNotEqual(quarters["Q4"]["value"], 65.0)

    def test_reconciliation_detects_a_real_mismatch_and_missing_quarters(self):
        cfo = {"Q1": 20, "H1": 55, "Q3": 80, "FY": 110}
        capex = {"Q1": -8, "H1": -20, "Q3": -31, "FY": -45}
        quarters = quarterly_fcf_from_ytd(cfo, capex, periods=self.periods)
        quarters["Q4"] = {**quarters["Q4"], "value": 15.0}
        mismatch = reconcile_fcf(cfo, capex, quarters, absolute_tolerance=0.5)
        self.assertEqual(mismatch["status"], "mismatch")
        self.assertFalse(mismatch["reconciled"])
        self.assertEqual(mismatch["delta"], -1.0)

        incomplete = quarterly_fcf_from_ytd({"Q1": 20, "H1": 55, "FY": 110}, capex, periods=self.periods)
        check = reconcile_fcf(cfo, capex, incomplete)
        self.assertEqual(check["status"], "incomplete")
        self.assertIsNone(check["reconciled"])
        self.assertIn("Q3", check["missing_quarters"])


if __name__ == "__main__":
    unittest.main()

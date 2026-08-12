#!/usr/bin/env python3
"""No-network tests for observed KOSPI investor-flow archiving."""

from __future__ import annotations

import unittest

from market_microstructure.investor_flow_history import append_points


class TestInvestorFlowHistory(unittest.TestCase):
    def test_append_keeps_observed_net_flow_and_replaces_date(self):
        history = append_points({}, [{
            "observed_as_of": "2026-08-11",
            "foreign_net_eok": -120.0,
            "retail_net_eok": 100.0,
            "institution_net_eok": 20.0,
        }], source="fixture")
        got = append_points(history, [{
            "observed_as_of": "2026-08-11",
            "foreign_net_eok": -125.0,
            "retail_net_eok": 101.0,
            "institution_net_eok": 24.0,
        }], source="fixture2")
        self.assertEqual(got["n_points"], 1)
        self.assertEqual(got["points"][0]["date"], "2026-08-11")
        self.assertEqual(got["points"][0]["foreign_net_eok"], -125.0)
        self.assertEqual(got["quality"], "observed")


if __name__ == "__main__":
    unittest.main()

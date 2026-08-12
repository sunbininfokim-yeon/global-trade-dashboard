#!/usr/bin/env python3
"""No-network tests for global leveraged price-path chart contract."""

from __future__ import annotations

import unittest

import pandas as pd

from build_global_leverage_paths import rebased_pair


class TestGlobalLeveragePaths(unittest.TestCase):
    def test_rebased_pair_aligns_shared_dates_at_100(self):
        dates = pd.to_datetime(["2026-08-10", "2026-08-11", "2026-08-12"])
        leveraged = pd.Series([10.0, 12.0, 9.0], index=dates)
        benchmark = pd.Series([20.0, 21.0, 19.0], index=dates)
        points = rebased_pair(leveraged, benchmark)
        self.assertEqual(points[0]["leveraged_index"], 100.0)
        self.assertEqual(points[0]["benchmark_index"], 100.0)
        self.assertEqual(points[-1]["leveraged_index"], 90.0)
        self.assertEqual(points[-1]["benchmark_index"], 95.0)


if __name__ == "__main__":
    unittest.main()

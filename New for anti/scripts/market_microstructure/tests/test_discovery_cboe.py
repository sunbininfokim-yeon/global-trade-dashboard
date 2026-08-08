#!/usr/bin/env python3
"""Offline tests for Cboe aggregate + corr helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fetch_cboe_public import _aggregate_chain  # noqa: E402
from market_microstructure.us_kr_discovery import _align_us_to_next_kr, _corr_pack  # noqa: E402


class TestCboeAggregate(unittest.TestCase):
    def test_put_call_from_occ(self):
        opts = [
            {"option": "MU260821C00100000", "volume": 100, "open_interest": 10, "iv": 0.4},
            {"option": "MU260821P00100000", "volume": 200, "open_interest": 20, "iv": 0.5},
            {"option": "MU260828C00100000", "volume": 50, "open_interest": 5, "iv": 0.3},
        ]
        out = _aggregate_chain(opts, spot=100.0)
        self.assertEqual(out["call_volume"], 150.0)
        self.assertEqual(out["put_volume"], 200.0)
        self.assertAlmostEqual(out["put_call_volume"], 200 / 150, places=4)
        self.assertEqual(out["source"].split()[0], "Cboe")
        self.assertNotIn("leopold", str(out).lower())


class TestCorrHelpers(unittest.TestCase):
    def test_align_and_corr(self):
        us = pd.Series(
            {
                "2026-01-02": -0.03,
                "2026-01-03": 0.01,
                "2026-01-06": -0.02,
                "2026-01-07": 0.02,
            }
        )
        # pad more points
        idx = pd.bdate_range("2025-06-01", periods=80)
        import numpy as np

        rng = np.random.default_rng(0)
        us = pd.Series(rng.normal(0, 0.02, len(idx)), index=idx)
        kr = pd.Series(0.6 * us.values + rng.normal(0, 0.01, len(idx)), index=idx + pd.Timedelta(days=1))
        # shift KR index to next business-ish day already
        df = _align_us_to_next_kr(us, kr)
        pack = _corr_pack(df)
        self.assertGreaterEqual(pack["n"], 20)
        self.assertIsNotNone(pack["corr"])
        self.assertGreater(pack["corr"], 0.3)


if __name__ == "__main__":
    unittest.main()

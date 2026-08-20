#!/usr/bin/env python3
"""Pure contract tests for KRX field normalization (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_microstructure.krx_client import etf_metrics  # noqa: E402


class TestKrxClient(unittest.TestCase):
    def test_observed_net_assets_take_precedence_over_market_cap(self):
        out = etf_metrics(
            {
                "INVSTASST_NETASST_TOTAMT": "1,234",
                "MKTCAP": "9,999",
                "ACC_TRDVAL": "100",
            }
        )
        self.assertEqual(out["aum_krw"], 1234.0)
        self.assertEqual(out["aum_source"], "INVSTASST_NETASST_TOTAMT")
        self.assertEqual(out["aum_quality"], "observed")

    def test_market_cap_fallback_is_explicit_proxy(self):
        out = etf_metrics({"MKTCAP": "9,999", "ACC_TRDVAL": "100"})
        self.assertEqual(out["aum_krw"], 9999.0)
        self.assertEqual(out["aum_source"], "MKTCAP")
        self.assertEqual(out["aum_quality"], "proxy")

    def test_missing_aum_is_not_coerced_to_observed_zero(self):
        out = etf_metrics({"ACC_TRDVAL": "100"})
        self.assertIsNone(out["aum_krw"])
        self.assertIsNone(out["aum_source"])
        self.assertEqual(out["aum_quality"], "missing")


if __name__ == "__main__":
    unittest.main()

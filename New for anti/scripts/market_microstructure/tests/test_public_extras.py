#!/usr/bin/env python3
"""No-network contract tests for public market-wide extras."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch_kr_public_extras as extras  # noqa: E402
from build_deposit_credit import build_payload  # noqa: E402


class TestPublicExtras(unittest.TestCase):
    def test_freesis_is_preferred_and_preserves_stress_components(self):
        observed = {
            "as_of": "2026-08-12",
            "quality": "observed",
            "credit_over_deposit_pct": 27.1,
            "uncollected_eok": 1000.0,
            "forced_sale_eok": 10.0,
            "components": [{"key": "uncollected"}],
            "ui_display": {"exclude_keys": ["collateral_loan"]},
        }
        with patch.object(extras, "fetch_freesis_funding_credit", return_value=observed), patch.object(
            extras, "fetch_naver_deposit_credit"
        ) as naver:
            got = extras.fetch_deposit_credit()
        self.assertEqual(got["source_mode"], "freesis")
        self.assertEqual(got["uncollected_eok"], 1000.0)
        naver.assert_not_called()

    def test_naver_fallback_is_explicit(self):
        fallback = {"as_of": "2026-08-11", "quality": "observed"}
        with patch.object(extras, "fetch_freesis_funding_credit", side_effect=RuntimeError("down")), patch.object(
            extras, "fetch_naver_deposit_credit", return_value=fallback
        ):
            got = extras.fetch_deposit_credit()
        self.assertEqual(got["source_mode"], "naver_fallback")
        self.assertIn("down", got["staleness_reason"])

    def test_deposit_output_keeps_market_scope(self):
        observed = {"as_of": "2026-08-12", "quality": "observed", "components": []}
        with patch("build_deposit_credit.fetch_deposit_credit", return_value=observed):
            payload = build_payload()
        self.assertEqual(payload["schema"], "deposit_credit_v1")
        self.assertIn("시장 전체", payload["market_scope_ko"])

    def test_program_trading_starts_as_an_explicit_missing_contract(self):
        got = extras.program_trading_contract()
        self.assertEqual(got["quality"], "missing")
        self.assertIsNone(got["arbitrage_net_eok"])
        self.assertIsNone(got["non_arbitrage_net_eok"])
        self.assertIn("투자자별 수급이 아님", got["note_ko"])


if __name__ == "__main__":
    unittest.main()

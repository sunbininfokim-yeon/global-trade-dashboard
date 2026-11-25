#!/usr/bin/env python3
"""Covered-call supply: index-name rules and the call-notional estimate."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_covered_call_supply import K200_MULTIPLIER, build, is_k200_covered_call, parse_rule  # noqa: E402


class TestRules(unittest.TestCase):
    def test_rules_read_off_index_names(self):
        r = parse_rule("코스피 200 타겟 15% 위클리 커버드콜 지수", "KODEX 200타겟위클리커버드콜")
        self.assertEqual((r["kind"], r["tenor"], r["target_premium_pct"]), ("target_premium", "weekly", 15.0))
        r = parse_rule("코스피 200 위클리 고정 30% 커버드콜 지수", "PLUS 200커버드콜액티브")
        self.assertEqual((r["kind"], r["tenor"], r["coverage_pct"], r["otm_pct"]), ("fixed_coverage", "weekly", 30.0, 0.0))
        r = parse_rule("코스피 200 커버드콜 5% OTM", "KODEX 200커버드콜액티브")
        self.assertEqual((r["tenor"], r["coverage_pct"], r["otm_pct"]), ("monthly", 100.0, 5.0))
        r = parse_rule("코스피 200 위클리 커버드콜 ATM 지수", "RISE 200위클리커버드콜")
        self.assertEqual((r["tenor"], r["coverage_pct"], r["otm_pct"]), ("weekly", 100.0, 0.0))
        self.assertTrue(parse_rule("코스피 200 KTB 혼합 위클리 고정 10% 커버드콜 지수", "x")["mixed_with_bonds"])
        self.assertEqual(parse_rule(None, "XYZ 200커버드콜")["kind"], "unknown")

    def test_leveraged_wrappers_excluded(self):
        self.assertFalse(is_k200_covered_call("마이티 200커버드콜ATM레버리지"))
        self.assertTrue(is_k200_covered_call("TIGER 200커버드콜"))
        self.assertFalse(is_k200_covered_call("TIGER 반도체TOP10커버드콜액티브"))


class TestEstimate(unittest.TestCase):
    def test_weekly_monthly_and_target_estimates(self):
        seed = {"2026-09-07": {
            "W": {"name": "W 200위클리커버드콜", "index_name": "코스피 200 위클리 커버드콜 ATM 지수", "mcap_krw": 520e9},
            "M": {"name": "M 200커버드콜", "index_name": "코스피 200 커버드콜 ATM 지수", "mcap_krw": 520e9},
            "T": {"name": "T 200타겟위클리커버드콜", "index_name": "코스피 200 타겟 15% 위클리 커버드콜 지수", "mcap_krw": 52e9},
        }}
        out = build(seed, None, {"2026-09-07": 1000.0}, None)
        h = out["history"][-1]
        self.assertEqual(h["total_mcap_krw"], round(520e9 + 520e9 + 52e9))
        # weekly 520억 + monthly 520억 ÷ (52/12) = 120억 → 640억/주
        self.assertEqual(h["est_fixed_call_notional_per_week_krw"], round(520e9 + 520e9 * 12 / 52))
        self.assertEqual(h["est_fixed_call_contracts_per_week"], round((520e9 + 520e9 * 12 / 52) / (1000.0 * K200_MULTIPLIER)))
        self.assertEqual(h["est_target_premium_per_week_krw"], round(52e9 * 0.15 / 52))

    def test_previous_history_is_kept_and_new_day_appended(self):
        seed = {"2026-09-07": {"W": {"name": "W 200위클리커버드콜", "index_name": None, "mcap_krw": 1e9}}}
        first = build(seed, None, {}, None)
        live = ("2026-11-24", {"W": {"name": "W 200위클리커버드콜", "index_name": None, "mcap_krw": 2e9}})
        second = build({}, live, {}, first)
        self.assertEqual([h["date"] for h in second["history"]], ["2026-09-07", "2026-11-24"])
        self.assertIsNone(second["history"][-1]["est_fixed_call_contracts_per_week"])  # no K200 close: no contracts


if __name__ == "__main__":
    unittest.main()

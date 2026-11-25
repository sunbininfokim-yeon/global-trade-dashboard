#!/usr/bin/env python3
"""CTA trend model on KOSPI 200 futures: signal, flip prices, scenarios."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_krx_cta as cta  # noqa: E402


def zigzag_trend(n: int, drift: float) -> list[float]:
    """Trend with alternating noise so the 60-day vol is never zero."""
    p, out = 100.0, []
    for i in range(n):
        p *= math.exp(drift + (0.01 if i % 2 else -0.01))
        out.append(p)
    return out


class TestSignal(unittest.TestCase):
    def test_strong_uptrend_is_max_long_and_downtrend_max_short(self):
        up = zigzag_trend(400, 0.01)
        s, comps = cta.signal_at(up, len(up) - 1)
        self.assertAlmostEqual(s, 1.0)
        self.assertTrue(all(v == 1.0 for v in comps.values()))
        down = zigzag_trend(400, -0.01)
        self.assertAlmostEqual(cta.signal_at(down, len(down) - 1)[0], -1.0)

    def test_component_is_clipped_zscore(self):
        prices = zigzag_trend(400, 0.0)
        t = len(prices) - 1
        vol = cta.daily_vol(prices, t)
        comps = cta.components(prices, t, vol)
        for k in cta.LOOKBACKS:
            z = math.log(prices[t] / prices[t - k]) / (vol * math.sqrt(k))
            self.assertAlmostEqual(comps[k], max(-1, min(1, z)))

    def test_too_short_history_has_no_signal(self):
        self.assertEqual(cta.signal_at(zigzag_trend(200, 0.01), 199), (None, None))


class TestBuild(unittest.TestCase):
    def _flow(self, prices):
        dates = cta.next_weekdays("2025-01-01", len(prices))
        return {"dates": dates, "futures_front": {"close": prices, "contract": ["202503"] * len(prices)},
                "flow": {"futures": {"foreign_net": [1.0] * len(prices)}}}

    def test_flip_price_is_tomorrows_reference_close(self):
        prices = zigzag_trend(400, 0.002)
        out = cta.build(self._flow(prices))
        t = len(prices) - 1
        for f in out["latest"]["flips"]:
            self.assertAlmostEqual(f["flip_price"], round(prices[t + 1 - f["k"]], 2))
            self.assertAlmostEqual(f["dist_pct"], round((prices[t + 1 - f["k"]] / prices[t] - 1) * 100, 2))

    def test_scenarios_order_and_flat_start(self):
        prices = zigzag_trend(400, 0.0)
        out = cta.build(self._flow(prices))
        sc = out["scenarios"]
        self.assertEqual(len(sc["flat"]), cta.HORIZON)
        self.assertEqual(len(sc["dates_est"]), cta.HORIZON)
        # After a month, a bigger up move never leaves a lower signal than a smaller one.
        self.assertGreaterEqual(sc["up_big"][-1], sc["up_small"][-1])
        self.assertGreaterEqual(sc["up_small"][-1], sc["flat"][-1])
        self.assertGreaterEqual(sc["flat"][-1], sc["down_small"][-1])
        self.assertGreaterEqual(sc["down_small"][-1], sc["down_big"][-1])

    def test_missing_close_is_skipped_not_filled(self):
        prices = zigzag_trend(400, 0.001)
        flow = self._flow(prices)
        flow["futures_front"]["close"][100] = None
        out = cta.build(flow)
        self.assertNotIn(flow["dates"][100], out["history"]["dates"])

    def test_threshold_calendar_marks_near_references(self):
        prices = [100.0] * 400
        prices = [p * (1.0001 if i % 2 else 0.9999) for i, p in enumerate(prices)]
        cal = cta.threshold_calendar(prices, cta.next_weekdays("2025-01-01", 400))
        self.assertEqual(len(cal), cta.HORIZON)
        self.assertEqual(cal[0]["near"], list(cta.LOOKBACKS))  # flat market: every reference is within 5%


    def test_trigger_zero_puts_signal_at_zero(self):
        prices = zigzag_trend(400, -0.002)
        trig = cta.trigger_levels(prices)
        z = trig["zero"]["price"]
        self.assertAlmostEqual(cta.signal_at(prices + [z], len(prices))[0], 0.0, places=3)
        self.assertGreater(z, prices[-1])  # a short is turned by a rally

    def test_vol_target_exposure_scales_and_caps(self):
        vol = 0.15 / math.sqrt(cta.TRADING_DAYS)  # realized == target
        self.assertAlmostEqual(cta.exposure(0.5, vol), 0.5)
        self.assertAlmostEqual(cta.exposure(-1.0, vol / 10), -cta.MAX_EXPOSURE)
        self.assertIsNone(cta.exposure(None, vol))

    def test_model_pnl_earns_on_a_trend_and_scenarios_carry_pnl(self):
        prices = zigzag_trend(400, 0.003)
        out = cta.build(self._flow(prices))
        self.assertGreater(out["latest"]["pnl_pct"], 0)
        sp = out["scenarios"]["pnl_pct"]
        self.assertEqual(sp["flat"][-1], 0.0)
        self.assertGreater(sp["up_big"][-1], sp["down_big"][-1])  # long book gains on a rally

    def test_spot_series_replaces_futures_and_has_no_rolls(self):
        prices = zigzag_trend(400, 0.001)
        flow = self._flow(prices)
        k200 = {d: p * 1.01 for d, p in zip(flow["dates"], prices)}
        out = cta.build(flow, k200)
        self.assertIn("지수", out["price_source_ko"])
        self.assertEqual(out["rolls"], [])
        self.assertAlmostEqual(out["latest"]["close"], prices[-1] * 1.01)

    def test_lead_lag_correlation_keys(self):
        dates = cta.next_weekdays("2020-01-01", 300)
        sig = [math.sin(i / 7) for i in range(300)]
        flow = {d: math.sin(i / 7) - math.sin((i - 1) / 7) for i, d in enumerate(dates)}
        wc = cta.weekly_corr(dates, sig, flow)
        for key in ("corr", "next_week", "prev_week", "when_long", "when_short"):
            self.assertIn(key, wc)
        self.assertGreater(wc["corr"], 0.5)


if __name__ == "__main__":
    unittest.main()

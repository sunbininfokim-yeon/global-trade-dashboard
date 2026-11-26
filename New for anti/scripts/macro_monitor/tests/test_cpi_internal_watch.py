import unittest

from macro_monitor.cpi.forward_validation import shift
from macro_monitor.cpi.internal_watch import AUTO, INS, NEW, REPAIR, assess, features, vehicle


class InternalWatchTests(unittest.TestCase):
    def test_spike_uses_only_prior_calendar_months(self):
        t = "2026-10"
        data = {shift(t, -i): .1 for i in range(1, 25)}
        data.update({t: .2, shift(t, 1): 50})
        self.assertTrue(features(data, t)["positive_spike"])
        data.pop(shift(t, -2))
        self.assertIsNone(features(data, t)["avg_3m_mom_pct"])
        self.assertIsNone(features(data, t)["positive_spike"])

    def test_insurance_is_not_automatically_terminal(self):
        f = {k: dict(mom_pct=-.1, avg_3m_mom_pct=0, positive_spike=False) for k in AUTO}
        f[INS].update(mom_pct=2, positive_spike=True)
        self.assertEqual(vehicle(f), "possible_residual_insurance_pressure")
        f[REPAIR]["mom_pct"] = .3
        self.assertEqual(vehicle(f), "insurance_spike_unresolved")
        f[NEW]["positive_spike"] = True
        self.assertEqual(vehicle(f), "vehicle_price_pressure_watch")
        del f[REPAIR]
        self.assertEqual(vehicle(f), "insufficient_data")

    def test_no_movers_or_external_required(self):
        result = assess({"series": []}, {"relationships": [
            dict(id="rent", type="measurement_link", source_ids=["rent"], target_ids=["oer"]),
            dict(id="external", type="external_input_required")]}, "2026-10")
        self.assertFalse(result["forecast_active"])
        self.assertEqual(result["internal_paths"][0]["missing_ids"], ["rent", "oer"])
        self.assertEqual(len(result["internal_paths"]), 1)

    def test_replay_excludes_right_censored_events(self):
        from macro_monitor.cpi.internal_watch import replay
        start = "2020-01"
        months = [shift(start, i) for i in range(28)]
        auto = {k: dict.fromkeys(months, .1) for k in AUTO}
        auto[NEW][months[-4]] = 1
        for m in months[-3:]:
            for k in AUTO:
                auto[k][m] = 2
        self.assertEqual(replay(auto, months[-2])["results"]["new"]["flagged"], [0, 0])
        self.assertEqual(replay(auto, months[-1])["results"]["new"]["flagged"], [1, 1])

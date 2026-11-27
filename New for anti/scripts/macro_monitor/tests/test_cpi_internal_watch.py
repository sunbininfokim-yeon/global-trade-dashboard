import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from build_us_cpi_internal_watch import SCHEMA, make_report, publish
from macro_monitor.cpi.monthly import shift
from macro_monitor.cpi.internal_watch import AUTO, INS, NEW, REPAIR, assess, features, vehicle


class InternalWatchTests(unittest.TestCase):
    def test_artifact_uses_latest_observed_headline_and_requires_official_history(self):
        series = {"id": "all_items", "series_id": "CUSR0000SA0", "observations": [
            {"date": "2026-09", "data_status": "observed", "index": 100.0},
            {"date": "2026-10", "data_status": "observed", "index": 102.0},
            {"date": "2026-11", "data_status": "not_published", "index": None},
        ]}
        history = {"schema_version": "us-cpi-api-history-v1",
                   "source": {"data_status": "official_observed"}, "series": [series]}
        mapping = {"relationships": []}
        report = make_report(history, mapping)
        self.assertEqual(report["reference_period"], "2026-10")
        self.assertAlmostEqual(report["items"]["all_items"]["mom_pct"], 2)
        history["retrieved_at"] = "irrelevant API retrieval timestamp"
        self.assertEqual(make_report(history, mapping), report)
        with self.assertRaises(ValueError):
            make_report(history, mapping, "2026-11")
        history["source"]["data_status"] = "fixture_synth"
        with self.assertRaises(ValueError):
            make_report(history, mapping)

    def test_publish_deterministic_and_preserves_newer_month(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "internal.json"
            report = {"schema_version": SCHEMA, "reference_period": "2026-10"}
            self.assertTrue(publish(report, path))
            body = path.read_bytes()
            self.assertFalse(publish(report, path))
            with self.assertRaises(ValueError):
                publish({**report, "reference_period": "2026-09"}, path)
            self.assertEqual(path.read_bytes(), body)

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

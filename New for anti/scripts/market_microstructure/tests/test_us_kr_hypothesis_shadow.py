import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import us_kr_hypothesis_actions as actions
import us_kr_hypothesis_shadow as shadow


TARGET = "2026-11-09"
NOW = shadow.stamp("2026-11-08T07:00:00+00:00")


def model():
    families = {}
    for name, (ticker, features) in shadow.FAMILIES.items():
        coeff = {"mean": [0] * len(features), "scale": [1] * len(features),
                 "coef": [1] * len(features), "intercept": 0}
        heads = {head: {"model": coeff, "calibration": {"slope": 1, "intercept": 0, "at_zero_slope": False}}
                 for head in shadow.HEADS}
        families[name] = {"ticker": ticker, "features": features, "heads": heads}
    out = {"schema_version": shadow.VERSION, "created_at": "2026-11-08T00:00:00+00:00",
           "training_cutoff": "2026-11-06", "models": families,
           "implementation_sha256": shadow.implementation_hashes(),
           "runtime_versions": shadow.runtime_versions()}
    return {**out, "model_id": shadow.digest(out)}


def snapshot():
    kr, us = shadow.calendars()
    timing = shadow.sessions(TARGET, kr, us)
    symbols = set(shadow.INDEX_NAMES + shadow.SYMBOLS)
    return {
        "collected_at": "2026-11-08T06:59:00+00:00",
        "us": {s: [{"date": timing["us_previous"], "close": 100},
                   {"date": timing["us_date"], "close": 101}] for s in symbols},
        "kr": {shadow.SAMSUNG: [
            {"date": d, "open": 100 + i, "close": 100 + i}
            for i, d in enumerate(shadow.window(kr, timing["kr_date"], 20))
        ]},
        "samsung_flow": [{"ticker": shadow.SAMSUNG, "source_screen": "12009", "date": timing["kr_date"],
                          "quality": "observed", "collected_at": "2026-11-06T10:00:00+00:00",
                          "market_total_buy_krw": 100, "foreign_net_krw": 11,
                          "other_foreign_net_krw": -1, "foreign_total_net_krw": 10}],
    }


class ShadowTest(unittest.TestCase):
    def test_missing_optional_inputs_leave_independent_baselines_available(self):
        data = snapshot()
        data["samsung_flow"][0]["date"] = "2026-11-05"
        del data["us"]["NASDAQSOX"]
        forecasts, missing = shadow.predict(model(), data, TARGET, NOW)
        self.assertEqual(set(forecasts), {"kospi_indices_two", "kospi_us8", "samsung_price_us"})
        self.assertEqual(set(missing), {"kospi_indices_three", "samsung_price_us_foreign"})
        self.assertEqual(forecasts["kospi_us8"]["us_date"], "2026-11-06")

    def test_no_stale_us_close_or_future_flow_observation(self):
        data = snapshot()
        data["us"]["NASDAQSOX"][1]["date"] = "2026-11-04"
        data["samsung_flow"][0]["collected_at"] = "2026-11-08T07:00:01+00:00"
        forecasts, missing = shadow.predict(model(), data, TARGET, NOW)
        self.assertNotIn("kospi_indices_three", forecasts)
        self.assertIn("samsung_price_us_foreign", missing)

    def test_inconsistent_cash_totals_do_not_block_other_families(self):
        data = snapshot()
        data["samsung_flow"][0]["foreign_total_net_krw"] = 30
        forecasts, missing = shadow.predict(model(), data, TARGET, NOW)
        self.assertIn("samsung_price_us", forecasts)
        self.assertIn("kospi_indices_three", forecasts)
        self.assertIn("disagrees", missing["samsung_price_us_foreign"])

    def test_cutoff_and_replay_are_separate(self):
        late = shadow.stamp("2026-11-08T23:31:00+00:00")
        with self.assertRaisesRegex(ValueError, "cutoff passed"):
            shadow.predict(model(), snapshot(), TARGET, late)
        replay, _ = shadow.predict(model(), snapshot(), TARGET, late, replay=True)
        self.assertEqual({r["status"] for r in replay.values()}, {"replay"})

    def test_first_record_survives_retry_and_evaluates_only_after_close(self):
        frozen = model()
        forecasts, _ = shadow.predict(frozen, snapshot(), TARGET, NOW)
        outcomes = {"collected_at": "2026-11-09T06:45:00+00:00", "kr": {
            "KOSPI": [{"date": "2026-11-06", "close": 100}, {"date": TARGET, "open": 101, "close": 98}],
            shadow.SAMSUNG: [{"date": "2026-11-06", "close": 100}, {"date": TARGET, "open": 100, "close": 99}],
        }}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for record in forecasts.values():
                path = shadow.first_path(root, record)
                self.assertTrue(shadow.write_once(path, record))
                self.assertFalse(shadow.write_once(path, {"changed": True}))
                self.assertEqual(shadow.read(path), record)
                for head in record["scores"].values():
                    self.assertAlmostEqual(head["up_probability"] + head["down_probability"], 1.)
            early = {**outcomes, "collected_at": "2026-11-09T04:45:00+00:00"}
            before = shadow.score(root, frozen, early, shadow.stamp("2026-11-09T07:00:00+00:00"))
            with self.assertRaisesRegex(ValueError, "postdates evaluation"):
                shadow.score(root, frozen, outcomes, shadow.stamp("2026-11-09T05:00:00+00:00"))
            after = shadow.score(root, frozen, outcomes, shadow.stamp("2026-11-09T07:00:00+00:00"))
            key = "kospi_indices_three_vs_kospi_indices_two"
            self.assertEqual(before[key]["opening"]["candidate"]["n"], 0)
            self.assertEqual(after[key]["opening"]["candidate"]["actual_up"], 1)
            self.assertEqual(after[key]["closing"]["candidate"]["actual_down"], 1)
            self.assertEqual(after["samsung_price_us_foreign_vs_samsung_price_us"]["opening"]["candidate"]["n"], 0)


class ActionsTest(unittest.TestCase):
    def test_weekend_plan_retries_only_until_all_families_are_recorded(self):
        frozen = model()
        data = snapshot()
        data["samsung_flow"] = []
        records, _ = shadow.predict(frozen, data, TARGET, NOW)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for record in records.values():
                shadow.write_once(shadow.first_path(root, record), record)
            retry = actions.plan(root, frozen, NOW)
            self.assertEqual(retry["target"], TARGET)
            self.assertTrue(retry["run"])
            self.assertEqual(retry["pending_families"], ["samsung_price_us_foreign"])
            late = actions.plan(root, frozen, shadow.stamp("2026-11-08T23:30:00+00:00"), TARGET)
            self.assertFalse(late["run"])
            self.assertIn("cutoff", late["reason"])
            full, _ = shadow.predict(frozen, snapshot(), TARGET, NOW)
            record = full["samsung_price_us_foreign"]
            shadow.write_once(shadow.first_path(root, record), record)
            self.assertFalse(actions.plan(root, frozen, NOW)["run"])

    def test_snapshot_adapter_scores_kospi_with_partial_outcomes(self):
        frozen = model()
        records, _ = shadow.predict(frozen, snapshot(), TARGET, NOW)
        outcomes = {
            "collected_at": "2026-11-09T07:00:00+00:00",
            "candidates": [{"ticker": "KOSPI", "rows": [
                {"date": "2026-11-06", "close": 100}, {"date": TARGET, "open": 101, "close": 98},
            ]}],
            "errors": [{"ticker": "005930", "missing_sessions": [TARGET]},
                       {"ticker": "000660", "missing_sessions": [TARGET]}],
        }
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for record in records.values():
                shadow.write_once(shadow.first_path(root, record), record)
            report = actions.evaluate_snapshot(root, frozen, outcomes, shadow.stamp("2026-11-09T08:00:00+00:00"))
            self.assertEqual(report["status"], "partial_outcomes")
            self.assertEqual(report["outcome_errors"], outcomes["errors"][:1])
            result = report["comparisons"]["kospi_indices_three_vs_kospi_indices_two"]
            self.assertEqual(result["opening"]["candidate"]["actual_up"], 1)
            self.assertEqual(result["closing"]["candidate"]["actual_down"], 1)


if __name__ == "__main__":
    unittest.main()

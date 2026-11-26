import json
import unittest

import numpy as np

from build_us_cpi_forward_validation import CONFIG, MonthlyPriceTable, run
from macro_monitor.cpi.external_backtest import ExternalBacktestError
from macro_monitor.cpi.forward_validation import candidate_specs, evaluate, monthly_changes, scan_lags, shift


def configs():
    return [json.loads((CONFIG / f"{name}.json").read_text()) for name in (
        "cpi_vehicle_chain_backtest_v1", "cpi_external_backtest_v1", "cpi_structure.map",
    )]


class ForwardValidationTests(unittest.TestCase):
    def test_missing_month_does_not_create_a_two_month_mom(self):
        result = monthly_changes([("2025-09", 100), ("2025-11", 102), ("2025-12", 103)])
        self.assertEqual(list(result), ["2025-12"])
        self.assertAlmostEqual(result["2025-12"], 100 / 102)

    def test_existing_catalog_only_and_release_constraints(self):
        specs = candidate_specs(*configs())
        self.assertEqual(len(specs), 6)
        self.assertEqual(sum(spec["mode"] == "includes_lag_zero_nowcast" for spec in specs), 2)
        self.assertEqual({name for spec in specs for name, lag in spec["terms"] if lag == 0},
                         {"brent_spot", "jet_fuel_us_gulf_coast_spot"})

    def test_does_not_fit_to_holdout_outcomes(self):
        months = [shift("2011-01", i) for i in range(86)]
        rng = np.random.default_rng(42)
        source = dict(zip(months, rng.normal(size=len(months))))
        target = {month: 0.8 * source[shift(month, -1)] for month in months[1:]}
        spec = {"id": "test", "relationship_map_id": None, "target": "y", "controls": [],
                "terms": [("x", 1)], "calendar_effects": False, "minimum_train": 72,
                "mode": "lagged_inputs_only"}
        kwargs = {"cutoff": months[-4], "through": months[-1]}
        report = evaluate(spec, {"x": source, "y": target}, **kwargs)
        changed = dict(target)
        changed[months[-3]] += 100
        changed[months[-1]] -= 100
        replay = evaluate(spec, {"x": source, "y": changed}, **kwargs)
        # A month cannot use its own outcome, even after changing its actual.
        # Earlier holdout outcomes may legitimately feed later target lags.
        for index in (0, 2):
            for model in ("baseline", "extended"):
                self.assertAlmostEqual(report["monthly_replay"][index][model],
                                       replay["monthly_replay"][index][model])
        self.assertEqual(report["training"]["last"], months[-4])
        self.assertAlmostEqual(report["holdout"]["extended_rmse_pp"], 0)
        self.assertEqual(report["activation"], "disabled")

        del source[months[-2]]
        missing = evaluate(spec, {"x": source, "y": target}, **kwargs)
        self.assertEqual(missing["holdout"]["n"], 2)
        self.assertIsNone(missing["holdout"]["rmse_improvement_pct"])
        self.assertEqual(missing["unscored_months"][months[-1]]["missing_inputs"],
                         [{"series": "x", "month": months[-2], "lag": 1}])

    def test_eia_table_preserves_blank_month_positions(self):
        parser = MonthlyPriceTable()
        values = ["1.0", "", "2.0"] + [""] * 9
        parser.feed("<tr><td class='B4'>&nbsp;2026</td>" +
                    "".join(f"<td class='B3'>{v}</td>" for v in values) + "</tr>")
        self.assertEqual(parser.points, [("2026-01", 1), ("2026-03", 2)])

    def test_lag_selection_is_pre_cutoff_and_nowcast_is_separate(self):
        months = [shift("2011-01", i) for i in range(185)]
        rng = np.random.default_rng(84)
        source = dict(zip(months, rng.normal(size=len(months))))
        target = {m: 0.8 * source[shift(m, -2)] + 0.05 * rng.normal() for m in months[2:]}
        spec = {"id": "test", "relationship_map_id": None, "target": "y", "controls": [],
                "terms": [("x", i) for i in range(5)], "calendar_effects": False,
                "minimum_train": 72, "mode": "includes_lag_zero_nowcast"}
        kwargs = {"cutoff": months[-4], "through": months[-1]}
        first, nowcast = scan_lags(spec, {"x": source, "y": target}, **kwargs)
        self.assertEqual(first["selected_lag_months"], 2)
        self.assertEqual(first["validation_last"], kwargs["cutoff"])
        self.assertEqual(first["positive_coefficient_share_by_input"]["x"], 1)
        self.assertEqual(len({m["n"] for m in first["validation_by_lag"].values()}), 1)
        self.assertEqual(nowcast["candidate_lags_months"], [0])
        self.assertEqual(nowcast["mode"], "same_month_nowcast")
        self.assertLess(first["replay"]["holdout"]["extended_rmse_pp"], 0.2)
        for m in months[-3:]:
            target[m] = 1000 * source[m]
        second = scan_lags(spec, {"x": source, "y": target}, **kwargs)[0]
        self.assertEqual(first["validation_by_lag"], second["validation_by_lag"])
        self.assertEqual(second["selected_lag_months"], 2)
        self.assertNotEqual(first["replay"]["holdout"], second["replay"]["holdout"])

    def test_source_failure_is_partial_and_keyless(self):
        def unavailable(series_id, *, api_key, start):
            self.assertEqual(api_key, "")
            raise ExternalBacktestError("request failed")

        def unavailable_eia():
            raise OSError("request failed")

        history = {"series": [{"series_id": "CUSR0000SA0", "observations": [
            {"date": m, "index": v, "data_status": "observed"}
            for m, v in [("2026-09", 100), ("2026-10", 101)]
        ]}]}
        report = run(history, *configs(), cutoff="2026-07", through=None, vehicle_only=False,
                     fetch=unavailable, fetch_jet=unavailable_eia)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["holdout_through"], "2026-10")
        self.assertTrue(all(row["status"] == "source_unavailable" for row in report["relationships"]))


if __name__ == "__main__":
    unittest.main()

"""Detour results are derived scenarios, not live traffic or route eligibility."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from build_snapshot import build_snapshot
from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures
from shipping_capacity.engine import required_capacity_dwt, route_operational_profile
from shipping_capacity.route_alternatives import load_arctic_route_reference, service_detour_comparison


ROOT = Path(__file__).resolve().parents[1]


class RouteAlternativesTests(unittest.TestCase):
    def setUp(self):
        self.route = {
            "distance_nm_one_way": 9600,
            "speed_knots": 20,
            "port_days_round_trip": 10,
            "chokepoints": [
                {"id": "suez", "reroute_receiver_id": "cape_good_hope", "reroute_extra_nm_one_way": 2400, "exposure_share": 0.6},
                {"id": "bab_el_mandeb", "reroute_receiver_id": "cape_good_hope", "reroute_extra_nm_one_way": 2400, "exposure_share": 0.6},
                {"id": "hormuz", "reroute_available": False, "reroute_extra_nm_one_way": 0},
            ],
        }
        self.baseline = {"baseline_required_dwt": 1_000_000, "allocated_dwt_with_reserve": 1_100_000}

    def _comparison(self, input_status="observed_bilateral_weight_with_route_allocation_proxy"):
        return service_detour_comparison(route_operational_profile(self.route), self.baseline, input_status)

    def test_detour_preserves_flow_and_counts_shared_cape_once(self):
        cape, blocked = self._comparison()["options"]
        self.assertEqual(cape["bypassed_chokepoint_ids"], ["suez", "bab_el_mandeb"])
        self.assertEqual(cape["additional_nm_one_way"], 2400)
        self.assertEqual(cape["additional_sailing_days_one_way"], 5)
        self.assertEqual(cape["additional_cycle_days_round_trip"], 10)
        self.assertEqual(cape["cycle_days_round_trip"], 60)
        self.assertEqual(cape["additional_required_dwt"], 120_000)
        self.assertEqual(cape["additional_required_dwt_pct"], 12.0)
        self.assertEqual(cape["required_dwt_with_detour"], 1_120_000)
        self.assertEqual(cape["requires_open_chokepoint_ids"], ["hormuz"])
        self.assertEqual(blocked["blocking_chokepoint_id"], "hormuz")

    def test_different_cape_assumptions_are_not_collapsed(self):
        self.route["chokepoints"][1]["exposure_share"] = 0.4
        options = self._comparison()["options"]
        self.assertEqual(len({row["id"] for row in options}), 3)
        self.assertEqual([row["additional_required_dwt"] for row in options[:2]], [120_000, 80_000])

    def test_no_sea_detour_does_not_publish_zero_or_cape_fallback(self):
        blocked = self._comparison()["options"][1]
        self.assertEqual(blocked["status"], "no_same_port_sea_detour")
        for field in ("additional_nm_one_way", "additional_sailing_days_one_way", "additional_required_dwt"):
            self.assertIsNone(blocked[field])
        self.assertEqual(blocked["bypassed_chokepoint_ids"], [])

    def test_seed_has_distance_but_no_absolute_capacity(self):
        comparison = self._comparison("scenario_seed_replace_with_comtrade")
        cape = comparison["options"][0]
        self.assertEqual(cape["additional_sailing_days_one_way"], 5)
        self.assertIsNone(comparison["baseline_required_dwt"])
        self.assertIsNone(cape["additional_required_dwt"])

    def test_verified_network_path_is_not_vessel_eligibility(self):
        self.route["chokepoints"].append({
            "id": "malacca", "reroute_extra_nm_one_way": 600, "exposure_share": 1,
            "distance_evidence": {"id": "open_network", "status": "verified_open_network_distance", "reroute_traversed_passages": ["sunda"]},
        })
        sunda = self._comparison()["options"][-1]
        self.assertEqual(sunda["status"], "conditional_geometry_only")
        self.assertEqual(sunda["label_ko"], "순다 경유 가정")
        self.assertEqual(sunda["distance_evidence_id"], "open_network")

    def test_arctic_alternatives_stay_on_same_port_pair_and_never_infer_dwt(self):
        data = {
            "from_ko": "부산", "to_ko": "로테르담", "speed_kn": 14.0, "note_ko": "시험용 항구쌍",
            "routes": [{"id": k, "nm": nm, "days": days} for k, nm, days in (
                ("suez", 10000, 30), ("nsr", 8000, 25), ("cape", 14000, 40),
            )],
        }
        with patch.object(Path, "read_text", return_value=json.dumps({"route_line": {"compare": data}})):
            result = load_arctic_route_reference(Path("unused"))
        self.assertEqual(result["status"], "conditional_port_pair_reference")
        self.assertEqual([row["difference_days_round_trip_transit"] for row in result["routes"]], [0, 20, -10])
        self.assertTrue(all(row["additional_required_dwt"] is None for row in result["routes"]))
        data["from_ko"] = "상하이"
        with patch.object(Path, "read_text", return_value=json.dumps({"route_line": {"compare": data}})):
            result = load_arctic_route_reference(Path("unused"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["routes"], [])

    def test_arctic_reference_missing_or_invalid_degrades_without_inventing_value(self):
        self.assertEqual(load_arctic_route_reference(ROOT / "not-present.json")["routes"], [])
        with patch.object(Path, "read_text", return_value="{ malformed }"):
            self.assertEqual(load_arctic_route_reference(Path("unused"))["status"], "unavailable")

    def test_real_route_bundle_matches_original_formula_and_schema(self):
        snapshot = build_snapshot(ROOT / "config")
        bundle = build_artifact_bundle(snapshot)
        screen = bundle["screen"]
        loaded = {row["id"]: row for row in snapshot["routes"]}
        route = loaded["asia_north_europe_container"]
        cap = route["baseline"]
        profile = route["operational_profile"]["detour_comparison"]
        cape = next(option for option in profile["options"] if option["id"] == "cape_good_hope")
        expected_delta = required_capacity_dwt(
            cap["capacity_driver_annual_tonnes"] * cape["exposed_flow_share"],
            cape["additional_cycle_days_round_trip"],
            cap["capacity_driver_utilization"],
        )
        self.assertAlmostEqual(cape["additional_required_dwt"] / expected_delta, 1, places=6)
        self.assertGreater(cape["additional_required_dwt"], 0)
        schema = json.loads((ROOT / "schemas/shipping_capacity_v1.schema.json").read_text())
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(screen)), [])
        self.assertEqual(golden_contract_failures(screen, bundle["diagnostics"], bundle["scenario_grid"]), [])
        self.assertEqual(screen["arctic_route_reference"], bundle["diagnostics"]["arctic_route_reference"])


if __name__ == "__main__":
    unittest.main()

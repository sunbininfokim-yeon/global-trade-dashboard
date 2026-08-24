"""Contracts for the reproducible open-network detour-distance evidence."""

from __future__ import annotations

import unittest
from pathlib import Path

from build_snapshot import build_snapshot
from shipping_capacity.route_distances import attach_distance_evidence, load_json


ROOT = Path(__file__).resolve().parents[1]


class RouteDistancePipelineTests(unittest.TestCase):
    def test_checked_in_evidence_quality_gates_malacca_exposures(self) -> None:
        routes = load_json(ROOT / "config" / "routes.json")
        evidence = load_json(ROOT / "config" / "route_distance_observations.json")
        attach_distance_evidence(routes, evidence)
        malacca = [
            exposure["distance_evidence"]
            for route in routes
            for exposure in route.get("chokepoints", [])
            if exposure["id"] == "malacca"
        ]
        self.assertEqual(len(malacca), 4)
        self.assertTrue(
            all(row["status"] == "verified_open_network_distance" for row in malacca)
        )
        self.assertTrue(all(row["reroute_extra_nm"] > 0 for row in malacca))

    def test_snapshot_publishes_malacca_by_ship_type_with_evidence(self) -> None:
        snapshot = build_snapshot(ROOT / "config")
        malacca = next(
            scenario for scenario in snapshot["scenarios"]
            if scenario["id"] == "malacca_100pct_28d"
        )
        summary = next(
            row for row in snapshot["scenario_summary"]
            if row["id"] == malacca["id"]
        )
        self.assertEqual(
            {row["ship_type"] for row in summary["ship_type_breakdown"]},
            {"container", "tanker"},
        )
        route = next(
            row for row in snapshot["routes"]
            if row["id"] == "asia_north_europe_container"
        )
        profile = next(
            row for row in route["operational_profile"]["chokepoint_alternatives"]
            if row["chokepoint_id"] == "malacca"
        )
        self.assertEqual(
            profile["distance_evidence"]["status"],
            "verified_open_network_distance",
        )
        self.assertGreater(profile["reroute_extra_nm_one_way"], 0)

    def test_distance_evidence_mismatch_fails_closed(self) -> None:
        routes = [
            {
                "id": "test_route",
                "distance_nm_one_way": 1000,
                "chokepoints": [
                    {
                        "id": "test_chokepoint",
                        "reroute_extra_nm_one_way": 900,
                        "distance_evidence_id": "test_evidence",
                    }
                ],
            }
        ]
        evidence = {
            "maximum_baseline_distance_deviation_fraction": 0.12,
            "maximum_reroute_extra_distance_deviation_nm": 25,
            "routes": [
                {
                    "id": "test_evidence",
                    "route_id": "test_route",
                    "chokepoint_id": "test_chokepoint",
                    "normal_distance_nm": 1000,
                    "reroute_distance_nm": 1100,
                    "reroute_extra_nm": 100,
                    "path_status": "verified_open_network_path",
                    "source": {},
                    "warning_ko": "test",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "failed quality gate"):
            attach_distance_evidence(routes, evidence)

    def test_cape_receiver_is_modelled_only_for_configured_suez_detours(self) -> None:
        snapshot = build_snapshot(ROOT / "config")
        suez = next(
            row for row in snapshot["scenario_summary"] if row["id"] == "suez_100pct_28d"
        )
        receiver = next(row for row in suez["reroute_receivers"] if row["id"] == "cape_good_hope")
        self.assertEqual(receiver["source_chokepoint_id"], "suez")
        self.assertGreater(receiver["rerouted_cargo_tonnes_horizon"], 0)
        self.assertGreater(receiver["additional_service_capacity_dwt"], 0)
        self.assertEqual(
            receiver["status"], "modelled_reroute_receiver_not_observed_traffic"
        )
        bab = next(
            row
            for row in snapshot["scenario_summary"]
            if row["id"] == "bab_el_mandeb_100pct_28d"
        )
        self.assertEqual(bab["reroute_receivers"][0]["source_chokepoint_id"], "bab_el_mandeb")
        malacca = next(
            row for row in snapshot["scenario_summary"] if row["id"] == "malacca_100pct_28d"
        )
        self.assertEqual(malacca["reroute_receivers"], [])

    def test_gibraltar_and_oresund_intake_remains_inactive_until_route_gates_pass(self) -> None:
        intake = load_json(ROOT / "config" / "chokepoint_route_intake.json")
        comtrade = load_json(ROOT / "config" / "comtrade_routes.json")
        configured_ids = {row["route_id"] for row in comtrade["routes"]}
        self.assertEqual(intake["status"], "free_data_collection_pending")
        self.assertEqual(
            {row["chokepoint_id"] for row in intake["candidates"]},
            {"gibraltar", "oresund"},
        )
        for candidate in intake["candidates"]:
            self.assertTrue(candidate["activation_status"].startswith("inactive_"))
            self.assertIn(candidate["comtrade_route_id"], configured_ids)


if __name__ == "__main__":
    unittest.main()

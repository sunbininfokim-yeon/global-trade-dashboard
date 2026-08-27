"""Regression checks for fields consumed by the static shipping UI."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT.parent.parent / "public" / "data" / "shipping_capacity_v1.json"
SHIPPING_UI = ROOT.parent.parent / "shipping.js"
INDEX_HTML = ROOT.parent.parent / "index.html"


class ShippingUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.shipping_ui_source = SHIPPING_UI.read_text(encoding="utf-8")
        cls.index_html_source = INDEX_HTML.read_text(encoding="utf-8")

    def test_shipping_ui_consumes_delivery_v2_without_shadow_calculations(self) -> None:
        source = self.shipping_ui_source
        for required_token in (
            "shipping-ui-delivery-v2",
            "ui_delivery_contract",
            "ship_type_breakdown",
            "risk_context",
            "env?.pathways",
            "operational_profile",
        ):
            self.assertIn(required_token, source)

        for retired_ui_assumption in (
            "NET_ZERO_PATHWAYS",
            "eu_reinforced",
            "1 - shortfall",
            "CHOKEPOINT_CONTEXT",
        ):
            self.assertNotIn(retired_ui_assumption, source)

    def test_shipping_navigation_matches_the_three_screen_information_architecture(self) -> None:
        source = self.index_html_source
        for target in ("shipping_fleet", "shipping_routes", "shipping_chokepoints"):
            self.assertIn(f'data-target="{target}"', source)
        self.assertIn(">항로 운항 선복량</a>", source)
        self.assertNotIn('data-target="shipping_scenarios"', source)
        self.assertNotIn('data-target="shipping_environment"', source)
        self.assertRegex(source, r'<script src="shipping\.js\?v=\d+"></script>')

    def test_fleet_and_route_cards_have_explicit_display_fields(self) -> None:
        fleet_rows = self.snapshot["fleet"]["fleet_by_type"]
        self.assertTrue(all(row["ship_type"] and row["dwt"] > 0 for row in fleet_rows))

        for route in self.snapshot["routes"]:
            self.assertIn(route["input_status"], {
                "observed_bilateral_sea_weight",
                "observed_bilateral_weight_with_route_allocation_proxy",
                "comtrade_manufactured_weight_extrapolation_proxy",
            })
            interval = route["baseline"]["interval"]["baseline_required_dwt"]
            self.assertLessEqual(interval["p10"], interval["p50"])
            self.assertLessEqual(interval["p50"], interval["p90"])

    def test_chokepoint_display_uses_the_declared_portwatch_metric(self) -> None:
        live_by_id = self.snapshot["chokepoints_live"]
        for display in self.snapshot["live_display"]:
            metric = live_by_id[display["chokepoint_id"]]["metrics"][display["metric_key"]]
            self.assertEqual(display["metric_unit"], "estimated_trade_tonnes_per_day")
            self.assertIn("추정", display["headline_label_ko"])
            self.assertAlmostEqual(display["trade_volume_shortfall_fraction"], metric["observed_trade_volume_shortfall_fraction"])
            self.assertAlmostEqual(display["remaining_trade_volume_ratio"], metric["remaining_trade_volume_ratio"])

    def test_published_ui_delivery_contract_has_no_calculation_gap(self) -> None:
        contract = self.snapshot["ui_delivery_contract"]
        self.assertEqual(contract["contract_version"], "shipping-ui-delivery-v2")
        self.assertEqual(contract["calculation_owner"], "python_shipping_capacity_engine")
        self.assertEqual(
            set(contract["views"]),
            {"global_fleet", "route_service", "chokepoint_detail", "environment"},
        )
        simulator = contract["views"]["chokepoint_detail"]
        self.assertEqual(
            simulator["input_fields"],
            ["base_scenario_id", "closure_pct", "duration_days"],
        )
        self.assertIn("summary.ship_type_breakdown[]", simulator["result_fields"])
        self.assertIn("summary.reroute_receivers[]", simulator["result_fields"])
        self.assertIn("null", contract["unavailable_value_rule"])
        route_service = contract["views"]["route_service"]
        self.assertEqual(route_service["title_ko"], "항로 운항 선복량")
        self.assertEqual(
            route_service["tabs"], ["all", "container", "dry_bulk", "tanker"]
        )
        self.assertIn("global container-TEU", route_service["container_teu_rule"])

    def test_chokepoints_publish_risk_context_for_detail_cards(self) -> None:
        for chokepoint in self.snapshot["chokepoints"]:
            context = chokepoint["risk_context"]
            self.assertTrue(context["primary_constraint_label_ko"])
            self.assertTrue(context["mechanism_ko"])
            if chokepoint["scenario_availability"] == "observed_monitor_only_no_route_model":
                self.assertIn("일별 통항 관측 모니터", context["scenario_interpretation_ko"])
            else:
                self.assertIn("실효 통행제약률", context["scenario_interpretation_ko"])

    def test_global_observation_only_chokepoints_publish_daily_average_contract(self) -> None:
        expected_ids = {"malacca", "cape_good_hope", "gibraltar", "oresund"}
        chokepoints = {row["id"]: row for row in self.snapshot["chokepoints"]}
        self.assertTrue(expected_ids.issubset(chokepoints))
        for chokepoint_id in expected_ids:
            self.assertEqual(
                chokepoints[chokepoint_id]["scenario_availability"],
                "observed_monitor_only_no_route_model",
            )
            status = self.snapshot["chokepoints_live"][chokepoint_id]
            averages = status["daily_averages"]
            metric = status["metrics"]["all"]
            self.assertEqual(
                averages["latest_daily_observation"]["date"],
                status["history"][-1]["date"],
            )
            self.assertAlmostEqual(
                averages["trailing_7d_average"]["value"],
                metric["current_7d_mean_estimated_trade_tonnes"],
            )
            self.assertAlmostEqual(
                averages["prior_28d_average"]["value"],
                metric["prior_28d_mean_estimated_trade_tonnes"],
            )

    def test_scenario_grid_has_backlog_and_commercial_constraint_metrics(self) -> None:
        base_ids = {row["id"] for row in self.snapshot["scenario_summary"]}
        for row in self.snapshot["ui_scenario_grid"]["rows"]:
            self.assertIn(row["base_scenario_id"], base_ids)
            for field in (
                "operational_capacity_absorbed_dwt",
                "commercial_capacity_gap_dwt",
                "backlog_cargo_tonnes_horizon",
                "trapped_loaded_dwt",
                "insurance_excluded_dwt",
                "weighted_traffic_change_pct",
                "ship_type_breakdown",
                "reroute_receivers",
            ):
                self.assertIn(field, row["summary"])
            for ship_type in row["summary"]["ship_type_breakdown"]:
                self.assertIn(ship_type["ship_type"], {"container", "dry_bulk", "tanker"})

    def test_full_closure_grid_publishes_cape_receiver_for_suez_and_bab(self) -> None:
        for base_scenario_id, chokepoint_id in (
            ("suez_100pct_28d", "suez"),
            ("bab_el_mandeb_100pct_28d", "bab_el_mandeb"),
        ):
            row = next(
                item
                for item in self.snapshot["ui_scenario_grid"]["rows"]
                if item["base_scenario_id"] == base_scenario_id
                and item["closure_pct"] == 100
                and item["duration_days"] == 28
            )
            receiver = next(
                item
                for item in row["summary"]["reroute_receivers"]
                if item["id"] == "cape_good_hope"
            )
            self.assertEqual(receiver["source_chokepoint_id"], chokepoint_id)
            self.assertGreater(receiver["rerouted_cargo_tonnes_horizon"], 0)
            self.assertGreater(receiver["rerouted_in_transit_cargo_tonnes_horizon"], 0)
            self.assertGreater(receiver["additional_service_capacity_dwt"], 0)
            self.assertEqual(
                receiver["status"], "modelled_reroute_receiver_not_observed_traffic"
            )


if __name__ == "__main__":
    unittest.main()

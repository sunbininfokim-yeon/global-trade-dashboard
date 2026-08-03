#!/usr/bin/env python3
"""Build the frontend-ready shipping_capacity_v1.json snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shipping_capacity.engine import estimate_interval, simulate_route
from shipping_capacity.portwatch import PortWatchClient


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    return value


def aggregate_scenario(scenario: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    affected = [row for row in results if row["affected_flow_share"] > 0]
    baseline = sum(row["baseline_required_dwt"] for row in affected)
    disrupted = sum(row["disrupted_required_dwt"] for row in affected)
    absorbed = sum(row["operational_capacity_absorbed_dwt"] for row in affected)
    gap = sum(row["capacity_gap_dwt"] for row in affected)
    lost = sum(row["lost_cargo_tonnes_horizon"] for row in affected)
    if affected:
        deliverable = sum(
            row["deliverable_flow_index"] * row["baseline_required_dwt"] for row in affected
        ) / baseline
    else:
        deliverable = 1.0
    return {
        "id": scenario["id"],
        "name_ko": scenario["name_ko"],
        "chokepoint_id": scenario["chokepoint_id"],
        "closure_fraction": scenario["closure_fraction"],
        "duration_days": scenario["duration_days"],
        "affected_route_count": len(affected),
        "affected_baseline_dwt": baseline,
        "disrupted_required_dwt": disrupted,
        "operational_capacity_absorbed_dwt": absorbed,
        "capacity_gap_dwt": gap,
        "lost_cargo_tonnes_horizon": lost,
        "weighted_deliverable_flow_index": deliverable,
        "weighted_traffic_change_pct": (deliverable - 1.0) * 100.0,
    }


def build_snapshot(config_dir: Path, *, fetch_portwatch: bool = False) -> dict[str, Any]:
    fleet = load_json(config_dir / "fleet_2025.json")
    chokepoints = load_json(config_dir / "chokepoints.json")
    routes = load_json(config_dir / "routes.json")
    scenarios = load_json(config_dir / "scenarios.json")
    fleet_by_type = {row["ship_type"]: row["dwt"] for row in fleet["fleet_by_type"]}

    live_status: dict[str, Any] = {}
    live_errors: list[dict[str, str]] = []
    if fetch_portwatch:
        client = PortWatchClient()
        for chokepoint in chokepoints:
            try:
                live_status[chokepoint["id"]] = client.fetch_status(chokepoint["portwatch_id"])
            except Exception as exc:  # A partial upstream outage must not erase the snapshot.
                live_errors.append({"chokepoint_id": chokepoint["id"], "error": str(exc)})

    route_outputs: list[dict[str, Any]] = []
    scenario_rows: dict[str, list[dict[str, Any]]] = {scenario["id"]: [] for scenario in scenarios}
    for route in routes:
        type_fleet = fleet_by_type[route["ship_type"]]
        baseline = simulate_route(route, None, type_fleet)
        baseline_interval = estimate_interval(route, None, type_fleet)
        stress_results = []
        for scenario in scenarios:
            result = simulate_route(route, scenario, type_fleet)
            scenario_rows[scenario["id"]].append(result)
            if result["affected_flow_share"] > 0:
                result["interval"] = estimate_interval(route, scenario, type_fleet)
                stress_results.append(result)

        live_results = []
        for exposure in route.get("chokepoints", []):
            status = live_status.get(exposure["id"])
            metric = status and status.get("metrics", {}).get(route["ship_type"])
            if not metric:
                continue
            live_scenario = {
                "id": f"live_{exposure['id']}",
                "chokepoint_id": exposure["id"],
                "closure_fraction": metric["observed_shortfall_fraction"],
                "duration_days": 28,
                "horizon_days": 28,
                "waiting_days": exposure.get("default_waiting_days", 0),
            }
            live_result = simulate_route(route, live_scenario, type_fleet)
            live_result["observation_latest_date"] = status.get("latest_date")
            live_result["portwatch_capacity_ratio"] = metric["capacity_ratio"]
            live_result["signal_type"] = "observed_capacity_shortfall_proxy_not_literal_closure"
            live_results.append(live_result)

        route_outputs.append(
            {
                "id": route["id"],
                "name_ko": route["name_ko"],
                "name_en": route["name_en"],
                "ship_type": route["ship_type"],
                "origin": route["origin"],
                "destination": route["destination"],
                "input_status": route["input_status"],
                "input_sources": route["input_sources"],
                "annual_cargo_tonnes": route["annual_cargo_tonnes"],
                "baseline": {**baseline, "interval": baseline_interval},
                "stress_tests": stress_results,
                "live_observed": live_results,
            }
        )

    scenario_summary = [
        aggregate_scenario(scenario, scenario_rows[scenario["id"]]) for scenario in scenarios
    ]
    return rounded(
        {
            "schema_version": "shipping-capacity-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": {
                "name": "Route Cycle Capacity + Chokepoint Shock",
                "version": "1.0.0",
                "formula": "required_dwt = annual_cargo_tonnes * round_trip_cycle_days / (365 * utilization)",
                "uncertainty": "P10/P50/P90 parameter range; not an event-probability forecast",
            },
            "data_policy": {
                "observed": "UNCTAD fleet baseline and optional IMF PortWatch daily capacity",
                "estimated": "route DWT derived from cargo flow, distance, speed, utilization and reserve",
                "scenario": "closure, reroute, wait and cancellation assumptions",
                "warning": "Route capacity is DWT-equivalent demand, not a vessel-by-vessel AIS inventory.",
            },
            "sources": [
                {
                    "name": "UNCTAD Review of Maritime Transport 2025, table II.5",
                    "url": "https://unctad.org/system/files/official-document/rmt2025ch2_en.pdf",
                },
                {
                    "name": "IMF PortWatch Daily Chokepoints Data (ArcGIS REST)",
                    "url": "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query",
                },
                {
                    "name": "UN Comtrade quantity/net-weight methodology",
                    "url": "https://comtradeapi.un.org/files/v1/app/wiki/MethodologyGuideforComtradePlus.pdf",
                },
            ],
            "fleet": fleet,
            "chokepoints": chokepoints,
            "chokepoints_live": live_status,
            "live_fetch_errors": live_errors,
            "routes": route_outputs,
            "scenario_summary": scenario_summary,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "generated" / "shipping_capacity_v1.json",
    )
    parser.add_argument("--fetch-portwatch", action="store_true")
    args = parser.parse_args()
    snapshot = build_snapshot(args.config_dir, fetch_portwatch=args.fetch_portwatch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

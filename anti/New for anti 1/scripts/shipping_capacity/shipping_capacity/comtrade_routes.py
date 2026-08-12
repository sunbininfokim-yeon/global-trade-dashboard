"""UN Comtrade bilateral net-weight adapter for representative shipping routes."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
WATER_MOT_CODE = 2100
TOTAL_MOT_CODE = 0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def select_net_weight_rows(
    rows: list[dict[str, Any]],
    *,
    water_mot_code: int = WATER_MOT_CODE,
    total_mot_code: int = TOTAL_MOT_CODE,
) -> dict[str, Any]:
    """Select water-mode rows per bilateral commodity cell without double-counting totals."""

    cells: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("partner2Code") not in (None, 0):
            continue
        if row.get("customsCode") not in (None, "C00"):
            continue
        if str(row.get("mosCode", "0")) != "0":
            continue
        weight = _number(row.get("netWgt"))
        if weight is None or weight < 0:
            continue
        key = (
            row.get("reporterCode"),
            row.get("partnerCode"),
            row.get("flowCode"),
            row.get("cmdCode"),
            row.get("period"),
        )
        cells[key].append(row)

    selected: list[dict[str, Any]] = []
    water_cell_count = 0
    fallback_cell_count = 0
    for candidates in cells.values():
        water = [row for row in candidates if row.get("motCode") == water_mot_code]
        total = [row for row in candidates if row.get("motCode") == total_mot_code]
        chosen = water or total
        if not chosen:
            continue
        selected.extend(chosen)
        if water:
            water_cell_count += 1
        else:
            fallback_cell_count += 1

    net_weight_kg = sum(float(row["netWgt"]) for row in selected)
    estimated_kg = sum(
        float(row["netWgt"])
        for row in selected
        if bool(row.get("isNetWgtEstimated"))
    )
    cell_count = water_cell_count + fallback_cell_count
    primary_value = sum(float(row.get("primaryValue") or 0.0) for row in selected)
    return {
        "net_weight_tonnes": net_weight_kg / 1000.0,
        "selected_row_count": len(selected),
        "bilateral_commodity_cell_count": cell_count,
        "water_mode_cell_count": water_cell_count,
        "all_mode_fallback_cell_count": fallback_cell_count,
        "water_mode_cell_share": water_cell_count / cell_count if cell_count else 0.0,
        "estimated_net_weight_share": estimated_kg / net_weight_kg if net_weight_kg else 0.0,
        "primary_value_usd": primary_value,
        "transport_scope": (
            "sea_water_reported"
            if cell_count and fallback_cell_count == 0
            else "mixed_sea_and_all_mode_proxy"
            if water_cell_count
            else "all_mode_proxy"
        ),
    }


class ComtradeRouteClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: int = 120,
        max_retries: int = 4,
    ) -> None:
        if not api_key:
            raise ValueError("UN Comtrade API key is required")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def fetch_rows(
        self,
        *,
        reporter_codes: list[int],
        partner_codes: list[int],
        cmd_codes: list[str],
        period: str,
        flow_code: str = "X",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for start in range(0, len(cmd_codes), 6):
            params = {
                "reporterCode": ",".join(str(value) for value in reporter_codes),
                "period": period,
                "partnerCode": ",".join(str(value) for value in partner_codes),
                "cmdCode": ",".join(cmd_codes[start : start + 6]),
                "flowCode": flow_code,
            }
            request = Request(
                COMTRADE_URL + "?" + urlencode(params),
                headers={
                    "Ocp-Apim-Subscription-Key": self.api_key,
                    "Accept": "application/json",
                    "User-Agent": "global-trade-dashboard-shipping/1.0",
                },
            )
            for attempt in range(self.max_retries + 1):
                try:
                    with urlopen(request, timeout=self.timeout_seconds) as response:
                        payload = json.load(response)
                    break
                except HTTPError as exc:
                    retryable = exc.code == 429 or 500 <= exc.code < 600
                    if not retryable or attempt >= self.max_retries:
                        raise
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (2**attempt)
                    print(
                        f"[comtrade_routes] HTTP {exc.code}; retrying in {delay:.0f}s "
                        f"({attempt + 1}/{self.max_retries})",
                        flush=True,
                    )
                    time.sleep(delay)
            if payload.get("error"):
                raise RuntimeError(f"UN Comtrade error: {payload['error']}")
            rows.extend(payload.get("data") or [])
            print(
                "[comtrade_routes] "
                f"period={period} reporters={len(reporter_codes)} partners={len(partner_codes)} "
                f"HS={params['cmdCode']} rows={len(payload.get('data') or [])}",
                flush=True,
            )
        return rows


def _direction_result(
    client: ComtradeRouteClient,
    spec: dict[str, Any],
    config: dict[str, Any],
    period: str,
) -> dict[str, Any]:
    cmd_codes = spec.get("cmd_codes")
    if cmd_codes is None:
        cmd_codes = config[spec["cmd_codes_ref"]]
    rows = client.fetch_rows(
        reporter_codes=spec["reporter_codes"],
        partner_codes=spec["partner_codes"],
        cmd_codes=cmd_codes,
        period=period,
        flow_code=spec.get("flow_code", "X"),
    )
    selected = select_net_weight_rows(
        rows,
        water_mot_code=int(config.get("water_transport_code", WATER_MOT_CODE)),
        total_mot_code=int(config.get("total_transport_code", TOTAL_MOT_CODE)),
    )
    value_basis = None
    value_expansion_factor = 1.0
    if spec.get("value_cmd_codes_ref"):
        value_rows = client.fetch_rows(
            reporter_codes=spec["reporter_codes"],
            partner_codes=spec["partner_codes"],
            cmd_codes=config[spec["value_cmd_codes_ref"]],
            period=period,
            flow_code=spec.get("flow_code", "X"),
        )
        value_basis = select_net_weight_rows(
            value_rows,
            water_mot_code=int(config.get("water_transport_code", WATER_MOT_CODE)),
            total_mot_code=int(config.get("total_transport_code", TOTAL_MOT_CODE)),
        )
        sample_value = selected["primary_value_usd"]
        if sample_value <= 0 or selected["net_weight_tonnes"] <= 0:
            raise RuntimeError("container HS4 sample has no usable value/weight basis")
        value_expansion_factor = value_basis["primary_value_usd"] / sample_value
        if not 1.0 <= value_expansion_factor <= 8.0:
            raise RuntimeError(
                f"container value expansion factor outside safety range: {value_expansion_factor:.3f}"
            )
    allocation = float(spec.get("allocation_fraction", 1.0))
    observed = selected["net_weight_tonnes"] * value_expansion_factor
    allocated = observed * allocation
    minimum = float(spec.get("minimum_annual_cargo_tonnes", 0.0))
    maximum = float(spec.get("maximum_annual_cargo_tonnes", float("inf")))
    if not minimum <= allocated <= maximum:
        raise RuntimeError(
            f"allocated annual cargo {allocated:.0f} outside quality range "
            f"[{minimum:.0f}, {maximum:.0f}]"
        )
    uncertainty_fraction = (
        0.35
        if value_basis is not None
        else 0.12
        if allocation == 1.0 and selected["transport_scope"] == "sea_water_reported"
        else 0.30
    )
    return {
        **selected,
        "period": period,
        "cmd_codes": cmd_codes,
        "reporter_codes": spec["reporter_codes"],
        "partner_codes": spec["partner_codes"],
        "source_net_weight_tonnes": observed,
        "sample_net_weight_tonnes": selected["net_weight_tonnes"],
        "sample_primary_value_usd": selected["primary_value_usd"],
        "broad_manufactured_primary_value_usd": (
            value_basis["primary_value_usd"] if value_basis is not None else None
        ),
        "value_expansion_factor": value_expansion_factor,
        "allocation_fraction": allocation,
        "allocation_basis": spec.get("allocation_basis"),
        "reporting_flow_code": spec.get("flow_code", "X"),
        "quality_range_tonnes": {"minimum": minimum, "maximum": maximum},
        "annual_cargo_tonnes": allocated,
        "uncertainty_fraction": uncertainty_fraction,
        "input_status": (
            "comtrade_manufactured_weight_extrapolation_proxy"
            if value_basis is not None
            else
            "observed_bilateral_sea_weight"
            if allocation == 1.0 and selected["transport_scope"] == "sea_water_reported"
            else "observed_bilateral_weight_with_route_allocation_proxy"
        ),
    }


def fetch_route_flows(config: dict[str, Any], client: ComtradeRouteClient) -> dict[str, Any]:
    period = str(config["period"])
    route_results = []
    route_errors = []
    for route_spec in config["routes"]:
        try:
            if route_spec.get("directions"):
                directions = []
                for direction in route_spec["directions"]:
                    directions.append(
                        {
                            "direction_id": direction["direction_id"],
                            **_direction_result(client, direction, config, period),
                        }
                    )
                route_results.append(
                    {
                        "route_id": route_spec["route_id"],
                        "directions": directions,
                        "annual_cargo_tonnes": max(
                            (row["annual_cargo_tonnes"] for row in directions),
                            default=0.0,
                        ),
                    }
                )
            else:
                route_results.append(
                    {
                        "route_id": route_spec["route_id"],
                        **_direction_result(client, route_spec, config, period),
                    }
                )
        except Exception as exc:
            route_errors.append({"route_id": route_spec["route_id"], "error": str(exc)})
    return {
        "status": "fetched" if not route_errors else "partial_quality_gated",
        "source": "UN Comtrade annual bilateral net weight",
        "source_url": "https://comtradeapi.un.org/data/v1/get/C/A/HS",
        "period": period,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "method": "water-mode row preferred per reporter-partner-flow-commodity cell; all-mode total used only as fallback",
        "routes": route_results,
        "route_errors": route_errors,
    }


def merge_route_results(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Preserve the last valid route value when a refresh is rate-limited or fails."""

    if not previous:
        return current
    routes = {row["route_id"]: row for row in previous.get("routes", [])}
    routes.update({row["route_id"]: row for row in current.get("routes", [])})
    attempted = {
        row["route_id"] for row in current.get("routes", []) + current.get("route_errors", [])
    }
    errors = {
        row["route_id"]: row
        for row in previous.get("route_errors", [])
        if row["route_id"] not in attempted
    }
    errors.update({row["route_id"]: row for row in current.get("route_errors", [])})
    merged = {**current, "routes": list(routes.values()), "route_errors": list(errors.values())}
    merged["status"] = "fetched" if not errors else "partial_quality_gated"
    merged["preserved_previous_route_ids"] = sorted(
        row["route_id"]
        for row in current.get("route_errors", [])
        if row["route_id"] in routes
    )
    return merged


def apply_route_flows(
    routes: list[dict[str, Any]],
    route_data: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not route_data or route_data.get("status") not in {"fetched", "partial_quality_gated"}:
        return routes
    by_id = {row["route_id"]: row for row in route_data.get("routes", [])}
    updated = json.loads(json.dumps(routes))
    for route in updated:
        observed = by_id.get(route["id"])
        if not observed:
            continue
        if route.get("directions") and observed.get("directions"):
            direction_by_id = {
                row["direction_id"]: row for row in observed["directions"]
            }
            for direction in route["directions"]:
                flow = direction_by_id.get(direction["id"])
                if not flow:
                    continue
                direction["annual_cargo_tonnes"] = flow["annual_cargo_tonnes"]
                direction["input_status"] = flow["input_status"]
                direction["data_provenance"] = flow
            route["annual_cargo_tonnes"] = observed["annual_cargo_tonnes"]
            statuses = {row["input_status"] for row in observed["directions"]}
            route["input_status"] = (
                "observed_bilateral_sea_weight"
                if statuses == {"observed_bilateral_sea_weight"}
                else "comtrade_manufactured_weight_extrapolation_proxy"
                if statuses == {"comtrade_manufactured_weight_extrapolation_proxy"}
                else "observed_bilateral_weight_with_route_allocation_proxy"
            )
            uncertainty = max(row["uncertainty_fraction"] for row in observed["directions"])
            route["data_provenance"] = {
                "period": route_data["period"],
                "directions": observed["directions"],
            }
        else:
            route["annual_cargo_tonnes"] = observed["annual_cargo_tonnes"]
            route["input_status"] = observed["input_status"]
            route["data_provenance"] = observed
            uncertainty = observed["uncertainty_fraction"]
        cargo = float(route["annual_cargo_tonnes"])
        route.setdefault("uncertainty", {})["annual_cargo_tonnes_low"] = cargo * (1.0 - uncertainty)
        route["uncertainty"]["annual_cargo_tonnes_high"] = cargo * (1.0 + uncertainty)
        route["input_sources"] = [
            f"UN Comtrade {route_data['period']} bilateral netWeight",
            "Route distance and allocation assumptions",
        ]
    return updated


def _read_api_key(path: Path | None) -> str | None:
    if path:
        text = path.read_text(encoding="utf-8").strip()
        if ":" in text:
            return text.split(":", 1)[1].strip().splitlines()[0]
        return text
    return os.environ.get("COMTRADE_SUBSCRIPTION_KEY") or os.environ.get("COMTRADE_API_KEY")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=root / "config" / "comtrade_routes.json")
    parser.add_argument("--output", type=Path, default=root / "config" / "comtrade_route_flows.json")
    parser.add_argument("--period")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--route-id", action="append", dest="route_ids")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.period:
        config["period"] = args.period
    if args.route_ids:
        wanted = set(args.route_ids)
        config["routes"] = [row for row in config["routes"] if row["route_id"] in wanted]
        missing = wanted - {row["route_id"] for row in config["routes"]}
        if missing:
            raise SystemExit(f"unknown route id(s): {', '.join(sorted(missing))}")
    key = _read_api_key(args.api_key_file)
    if not key:
        raise SystemExit("COMTRADE_SUBSCRIPTION_KEY is required")
    result = fetch_route_flows(config, ComtradeRouteClient(key))
    previous = None
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
    result = merge_route_results(previous, result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(result['routes'])} routes)")


if __name__ == "__main__":
    main()

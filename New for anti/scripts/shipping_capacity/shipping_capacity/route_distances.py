"""Reproducible open-network audit for route and chokepoint-detour distances."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def calculate_distance_observations(inputs: dict[str, Any]) -> dict[str, Any]:
    """Calculate open-network nautical-mile distances without altering model inputs.

    The result is an evidence layer.  The capacity model still reads its
    versioned route configuration, and only accepts an exposure when this
    evidence agrees within declared tolerances.
    """

    try:
        import searoute as sr
    except ImportError as exc:  # pragma: no cover - exercised in the workflow
        raise RuntimeError("searoute is required to refresh route distance evidence") from exc

    rows = []
    for item in inputs.get("routes", []):
        origin = item["origin"]["coordinates"]
        destination = item["destination"]["coordinates"]
        normal = sr.searoute(
            origin,
            destination,
            units="naut",
            restrictions=item["normal_restrictions"],
            return_passages=True,
        ).properties
        reroute = sr.searoute(
            origin,
            destination,
            units="naut",
            restrictions=item["reroute_restrictions"],
            return_passages=True,
        ).properties
        normal_passages = normal.get("traversed_passages", [])
        reroute_passages = reroute.get("traversed_passages", [])
        normal_nm = float(normal["length"])
        reroute_nm = float(reroute["length"])
        expected_normal = item["expected_normal_passage"]
        expected_reroute = item["expected_reroute_passage"]
        path_status = (
            "verified_open_network_path"
            if expected_normal in normal_passages
            and expected_reroute in reroute_passages
            and item["chokepoint_id"] not in reroute_passages
            and reroute_nm > normal_nm
            else "rejected_path_topology"
        )
        rows.append(
            {
                "id": item["id"],
                "route_id": item["route_id"],
                "chokepoint_id": item["chokepoint_id"],
                "origin": item["origin"],
                "destination": item["destination"],
                "normal_distance_nm": normal_nm,
                "reroute_distance_nm": reroute_nm,
                "reroute_extra_nm": reroute_nm - normal_nm,
                "normal_traversed_passages": normal_passages,
                "reroute_traversed_passages": reroute_passages,
                "path_status": path_status,
                "source": inputs["source"],
                "warning_ko": "공개 해상네트워크 최단경로 추정치이며 실제 항해계획·선사 스케줄·항만 기항순서가 아닙니다."
            }
        )
    return {
        "status": "open_network_distance_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": inputs["methodology"],
        "maximum_baseline_distance_deviation_fraction": inputs["maximum_baseline_distance_deviation_fraction"],
        "maximum_reroute_extra_distance_deviation_nm": inputs["maximum_reroute_extra_distance_deviation_nm"],
        "routes": rows,
    }


def attach_distance_evidence(
    routes: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> None:
    """Attach quality-gated evidence to configured exposures in place."""

    by_id = {row["id"]: row for row in evidence.get("routes", [])}
    max_baseline = float(evidence.get("maximum_baseline_distance_deviation_fraction", 0.12))
    max_extra = float(evidence.get("maximum_reroute_extra_distance_deviation_nm", 25))
    for route in routes:
        for exposure in route.get("chokepoints", []):
            evidence_id = exposure.get("distance_evidence_id")
            if not evidence_id:
                continue
            row = by_id.get(evidence_id)
            if row is None:
                raise ValueError(f"missing route distance evidence: {evidence_id}")
            if row["route_id"] != route["id"] or row["chokepoint_id"] != exposure["id"]:
                raise ValueError(f"route distance evidence mismatch: {evidence_id}")
            baseline = float(route["distance_nm_one_way"])
            baseline_deviation = abs(baseline - float(row["normal_distance_nm"])) / baseline
            extra_deviation = abs(
                float(exposure.get("reroute_extra_nm_one_way", 0))
                - float(row["reroute_extra_nm"])
            )
            accepted = (
                row["path_status"] == "verified_open_network_path"
                and baseline_deviation <= max_baseline
                and extra_deviation <= max_extra
            )
            exposure["distance_evidence"] = {
                "id": evidence_id,
                "status": "verified_open_network_distance" if accepted else "distance_evidence_outside_tolerance",
                "normal_distance_nm": row["normal_distance_nm"],
                "reroute_distance_nm": row["reroute_distance_nm"],
                "reroute_extra_nm": row["reroute_extra_nm"],
                "baseline_distance_deviation_fraction": baseline_deviation,
                "reroute_extra_distance_deviation_nm": extra_deviation,
                "source": row["source"],
                "warning_ko": row["warning_ko"],
            }
            if not accepted:
                raise ValueError(f"route distance evidence failed quality gate: {evidence_id}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=root / "config" / "route_distance_inputs.json")
    parser.add_argument("--output", type=Path, default=root / "config" / "route_distance_observations.json")
    args = parser.parse_args()
    payload = calculate_distance_observations(load_json(args.inputs))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

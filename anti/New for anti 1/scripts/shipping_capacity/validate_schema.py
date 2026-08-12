#!/usr/bin/env python3
"""Validate the public shipping snapshot against its JSON Schema contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from shipping_capacity.artifacts import golden_contract_failures


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT.parent.parent / "public" / "data" / "shipping_capacity_v1.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas" / "shipping_capacity_v1.schema.json",
    )
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(snapshot), key=lambda error: list(error.path))
    if errors:
        for error in errors[:50]:
            path = ".".join(str(value) for value in error.absolute_path) or "<root>"
            print(f"{path}: {error.message}")
        raise SystemExit(f"schema validation failed with {len(errors)} error(s)")
    grid = snapshot["ui_scenario_grid"]
    actual_keys = {row["key"] for row in grid["rows"]}
    expected_keys = {
        f"{scenario['id']}|{closure_pct}|{duration_days}"
        for scenario in snapshot["scenarios"]
        for closure_pct in grid["closure_pct_options"]
        for duration_days in grid["duration_day_options"]
    }
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise SystemExit(
            "ui scenario grid contract failed: "
            f"missing={missing[:10]} extra={extra[:10]}"
        )
    print(f"schema validation passed: {args.snapshot}")
    artifact_pairs = (
        (
            args.snapshot.parent / "shipping_capacity_diagnostics_v1.json",
            ROOT / "schemas" / "shipping_capacity_diagnostics_v1.schema.json",
        ),
        (
            args.snapshot.parent / "shipping_capacity_backtests_v1.json",
            ROOT / "schemas" / "shipping_capacity_backtests_v1.schema.json",
        ),
    )
    loaded = {}
    for artifact_path, schema_path in artifact_pairs:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        artifact_errors = sorted(
            Draft202012Validator(
                artifact_schema, format_checker=FormatChecker()
            ).iter_errors(artifact),
            key=lambda error: list(error.path),
        )
        if artifact_errors:
            raise SystemExit(
                f"schema validation failed for {artifact_path}: "
                f"{artifact_errors[0].message}"
            )
        loaded[artifact["artifact_type"]] = artifact
        print(f"schema validation passed: {artifact_path}")
    failures = golden_contract_failures(snapshot, loaded["model_diagnostics"])
    if failures:
        raise SystemExit(f"golden contract failed: {failures[:20]}")
    if len({snapshot["bundle_id"], *(row["bundle_id"] for row in loaded.values())}) != 1:
        raise SystemExit("artifact bundle id mismatch")
    print("golden screen/diagnostics contract passed")


if __name__ == "__main__":
    main()

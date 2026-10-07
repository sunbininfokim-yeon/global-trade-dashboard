#!/usr/bin/env python3
"""Rebuild observation presentation from existing, matching diagnostics.

No network, collection, model fitting, or scenario recalculation occurs here.
Source observation timestamps remain unchanged.
"""
import argparse
import json
from pathlib import Path

from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / "public/data")
    args = parser.parse_args()
    names = {"screen": "shipping_capacity_v1.json", "diagnostics": "shipping_capacity_diagnostics_v1.json", "scenario_grid": "shipping_capacity_scenario_grid_v1.json", "backtests": "shipping_capacity_backtests_v1.json"}
    existing = {key: json.loads((args.data_dir / name).read_text()) for key, name in names.items()}
    if len({row["bundle_id"] for row in existing.values()}) != 1:
        raise SystemExit("Existing bundle mismatch; preserve files and refresh source bundle first")
    bundle = build_artifact_bundle(existing["diagnostics"])
    # Diagnostics deliberately omit historical calibration/event records.
    # Keep the existing backtest artifact intact rather than rebuilding it
    # from a diagnostic cache that cannot supply those records.
    bundle["backtests"] = {**existing["backtests"], "bundle_id": bundle["screen"]["bundle_id"]}
    failures = golden_contract_failures(bundle["screen"], bundle["diagnostics"], bundle["scenario_grid"])
    if failures:
        raise SystemExit(f"Contract failures: {failures}")
    for key, name in names.items():
        (args.data_dir / name).write_text(json.dumps(bundle[key], ensure_ascii=False, indent=2) + "\n")
    print(f"Updated observation presentation only; bundle {bundle['screen']['bundle_id']}")


if __name__ == "__main__":
    main()

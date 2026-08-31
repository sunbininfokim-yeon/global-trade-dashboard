#!/usr/bin/env python3
"""Refresh vehicle backtests and publish a minimal CPI relationship evidence pack."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi.api import fetch_series  # noqa: E402
from macro_monitor.cpi.relationship_evidence import build_evidence_snapshot  # noqa: E402
from macro_monitor.cpi.vehicle_chain_backtest import (  # noqa: E402
    _fdr,
    bls_monthly_mom,
    run_relationship,
)
from publish_cpi_structure import publish  # noqa: E402


PUBLIC = ROOT.parent.parent / "public" / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build U.S. CPI relationship evidence from official BLS histories")
    parser.add_argument("--vehicle-config", type=Path, default=ROOT / "config" / "cpi_vehicle_chain_backtest_v1.json")
    parser.add_argument("--mapping", type=Path, default=ROOT / "config" / "cpi_structure.map.json")
    parser.add_argument("--backtest-out", type=Path, default=PUBLIC / "us_cpi_vehicle_chain_backtest_v1.json")
    parser.add_argument("--evidence-out", type=Path, default=PUBLIC / "us_cpi_relationship_evidence_v1.json")
    parser.add_argument("--structure-out", type=Path, default=PUBLIC / "us_cpi_structure_v1.json")
    parser.add_argument("--external-backtest", type=Path, default=PUBLIC / "us_cpi_external_backtest_v1.json")
    parser.add_argument("--cpi-history", type=Path, default=PUBLIC / "us_cpi_api_history_v1.json")
    args = parser.parse_args()

    config = json.loads(args.vehicle_config.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    series = {}
    if args.cpi_history.exists():
        history = json.loads(args.cpi_history.read_text(encoding="utf-8"))
        by_id = {row["id"]: row for row in history.get("series", [])}
        if all(name in by_id for name in config["source"]["series"]):
            series = {
                name: {
                    row["date"]: float(row["mom_pct"])
                    for row in by_id[name].get("observations", [])
                    if row.get("mom_pct") is not None
                }
                for name in config["source"]["series"]
            }
    if not series:
        end_year = datetime.now(timezone.utc).year
        raw = fetch_series(
            list(config["source"]["series"].values()),
            registration_key=os.environ.get("BLS_API_KEY", ""),
            start_year=int(config["sample"]["start_year"]),
            end_year=end_year,
        )
        series = {
            name: bls_monthly_mom(raw, series_id)
            for name, series_id in config["source"]["series"].items()
        }
    rows = [
        run_relationship(spec, series=series, minimum_train_months=config["sample"]["minimum_train_months"])
        for spec in config["relationships"]
    ]
    _fdr(rows)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    backtest = {
        "schema_version": config["schema_version"],
        "model": "us_cpi_vehicle_chain_backtest",
        "retrieved_at": generated_at,
        "data_status": "official_observed_current_vintage",
        "scope": "Minimal metrics only; raw BLS histories are not stored.",
        "sample": config["sample"],
        "source": config["source"],
        "input_history": str(args.cpi_history.name) if args.cpi_history.exists() else "direct_bls_api",
        "relationships": rows,
        "activation_policy": config["activation_policy"],
    }
    evidence_rows = list(rows)
    if args.external_backtest.exists():
        external = json.loads(args.external_backtest.read_text(encoding="utf-8"))
        evidence_rows.extend(external.get("relationships", []))
    evidence = build_evidence_snapshot(mapping, backtest_rows=evidence_rows, series=series, generated_at=generated_at)
    for path, document in ((args.backtest_out, backtest), (args.evidence_out, evidence)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    published = publish(source=args.mapping, out=args.structure_out, evidence_path=args.evidence_out)

    print(f"wrote {args.backtest_out}")
    print(f"wrote {args.evidence_out} reference_period={evidence['reference_period']}")
    print(f"published {args.structure_out} evidence_attached={published['evidence_attached']}")
    for row in evidence["relationships"]:
        tests = row.get("tests") or []
        if tests or row["phase"]["phase"] not in {"not_applicable", "insufficient_data"}:
            print(
                f"  {row['relationship_id']}: tier={row['evidence_tier']} "
                f"phase={row['phase']['phase']} tests={[test['status'] for test in tests]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

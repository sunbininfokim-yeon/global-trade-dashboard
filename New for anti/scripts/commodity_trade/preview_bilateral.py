"""Offline migration audit of the existing mineral snapshot; never fetches.

This creates a review artifact, NOT a production feed. Legacy data lost World
totals, estimation flags and some null values; those cannot be reconstructed.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import tempfile

from bilateral import ContractError, build_partition, country_view, partner_code


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT.parent.parent / "public/data/mineral_trade_stage2_v1.json"


def legacy_reporter_codes() -> dict[str, str]:
    # Read the existing registry literal without importing its generic 'sources'
    # module into (and potentially clobbering) the commodity_trade package.
    module = ast.parse((ROOT.parent / "mineral_trade_stage2/sources.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "M49" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ContractError("legacy reporter registry missing")


def convert_snapshot(document: dict, reporter_codes: dict[str, str]) -> dict:
    out = {"schema": "bilateral-migration-review-v1", "not_for_publication": True,
           "source_generated_at": document.get("generated_at"), "partitions": [], "diagnostics": []}
    for index, item in enumerate(document.get("resolved", [])):
        if item.get("ok") is not True:
            out["diagnostics"].append({"record": index, "reason": "legacy_record_not_ok"})
            continue
        focus_iso = item.get("reporter")
        try:
            focus = partner_code(reporter_codes[focus_iso])
        except (KeyError, ContractError):
            out["diagnostics"].append({"record": index, "reason": "unknown_reporter"})
            continue
        mirror = item.get("source") == "mirror_import"
        legs = item.get("legs", []) if mirror else [item]
        if not legs:
            out["diagnostics"].append({"record": index, "reason": "missing_mirror_legs"})
        for leg_index, leg in enumerate(legs):
            try:
                reporter_iso = str(leg.get("via", "")).removeprefix("comtrade_") if mirror else focus_iso
                reporter = partner_code(reporter_codes[reporter_iso])
                grain = leg.get("grain")
                freq = {"year": "A", "month": "M"}.get(grain)
                per = str(leg.get("period") or leg.get("as_of") or "").replace("-", "")
                warnings = ["legacy_snapshot_not_revalidated", "world_totals_not_retained",
                            "estimation_flags_not_retained", "source_scope_and_hs_version_unknown",
                            "legacy_direction_may_have_been_dropped"]
                normalized = []
                for p in leg.get("partners", []):
                    flow = {"EXPORT": "X", "IMPORT": "M"}.get(p.get("flow"), p.get("flow"))
                    code = partner_code(p.get("partner_code"))
                    if mirror and code != focus:
                        raise ContractError("mirror leg does not match requested focus country")
                    if (item.get("view") == "importer" and flow != "M") or (mirror and flow != "M"):
                        warnings.append("legacy_view_direction_conflict")
                    weight, value = p.get("net_wgt"), p.get("primary_value")
                    quality = {"is_reported": None, "is_net_weight_estimated": None,
                               "legacy_raw_net_weight": weight, "legacy_raw_trade_value": value}
                    # The legacy parser used float(value or 0). Its zeros can be
                    # either missing or explicit; do not guess which they were.
                    if weight == 0 or value == 0:
                        warnings.append("legacy_zero_ambiguous")
                    normalized.append({"partner": code, "flow": flow,
                                       "period": str(p.get("period") or per),
                                       "metrics": {"net_weight_kg": None if weight == 0 else weight,
                                                   "trade_value_usd": None if value == 0 else value},
                                       "quality": quality})
                meta = {"source": "legacy_mineral_snapshot", "scope_id": "unknown",
                        "hs_version": "unknown", "value_basis": "unknown", "reporter": reporter,
                        "hs": leg.get("hs_used"), "period": per, "frequency": freq}
                partition = build_partition(meta, normalized)
                partition["legacy"] = {"record": index, "leg": leg_index, "source": item.get("source"),
                                       "focus_iso3": focus_iso, "reporter_iso3": reporter_iso,
                                       "commodity_label": item.get("commodity"), "warnings": sorted(set(warnings))}
                partition["focus_rows"] = country_view(partition, focus)
                out["partitions"].append(partition)
            except (KeyError, TypeError, ContractError):
                out["diagnostics"].append({"record": index, "leg": leg_index, "reason": "legacy_contract_error"})
    out["summary"] = {
        "partitions": len(out["partitions"]),
        "focus_rows": sum(len(p["focus_rows"]) for p in out["partitions"]),
        "diagnostics": len(out["diagnostics"]),
        "direction_conflicts": sum("legacy_view_direction_conflict" in p["legacy"]["warnings"] for p in out["partitions"]),
        "ambiguous_zero_partitions": sum("legacy_zero_ambiguous" in p["legacy"]["warnings"] for p in out["partitions"]),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, help="optional review JSON path, never a public/data path")
    args = parser.parse_args()
    if args.output and "public" in args.output.resolve().parts:
        parser.error("migration reviews must not be published under public/")
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error("input must not be overwritten")
    document = json.loads(args.input.read_text(encoding="utf-8"))
    result = convert_snapshot(document, legacy_reporter_codes())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                                             prefix=".bilateral-review-", delete=False) as stream:
                path = Path(stream.name)
                json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, args.output)
        finally:
            if path and path.exists():
                path.unlink()
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 1 if result["diagnostics"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

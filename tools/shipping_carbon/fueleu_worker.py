"""Private subprocess entry point; never imported by the shipping server."""
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FUEL_ROOT = ROOT.parent / "fueleu"
sys.path.insert(0, str(FUEL_ROOT))
import engine as fuel_engine
import mrv_supply


def engine_receipt():
    return {name: hashlib.sha256((FUEL_ROOT / name).read_bytes()).hexdigest()
            for name in ("engine.py", "mrv_supply.py")}


def complete_row(row):
    required = ("fuel", "co2", "ch4", "n2o", "between", "departed", "arrived", "in_port")
    reasons = [key for key in required if row.get(key) is None or
               not math.isfinite(row[key]) or row[key] < 0]
    if not reasons and (row["fuel"] <= 0 or row["co2"] <= 0):
        reasons.append("nonpositive_fuel_or_co2")
    if not reasons:
        scoped = row["between"] + row["in_port"] + .5 * (row["departed"] + row["arrived"])
        if scoped > row["co2"] + max(1e-6, row["co2"] * 1e-4):
            reasons.append("scope_exceeds_total")
    return reasons


def audit(payload):
    raw = Path(payload["file"]).read_bytes()
    prior_raw = Path(payload["baseline_file"]).read_bytes()
    year = int(payload["year"])
    rows = list(mrv_supply.read_workbook(raw, year))
    prior = list(mrv_supply.read_workbook(prior_raw, year - 1))
    baseline = {t: sum(r["ship_type"] == t for r in prior) for t in mrv_supply.COUNT_MATCHED_TYPES}
    fields = ("fuel", "co2", "ch4", "n2o", "between", "departed", "arrived", "in_port", "hours")
    coverage = {key: {"missing": sum(r.get(key) is None for r in rows),
                     "nonfinite": sum(r.get(key) is not None and not math.isfinite(r[key]) for r in rows),
                     "observed_zero": sum(r.get(key) == 0 for r in rows)} for key in fields}
    imo_counts = Counter(str(r["imo"]) for r in rows)
    duplicate_imos = {k for k, n in imo_counts.items() if n > 1}
    reasons = Counter()
    strict = []
    for row in rows:
        missing = complete_row(row)
        if str(row["imo"]) in duplicate_imos:
            missing.append("duplicate_imo")
        reasons.update(missing)
        if not missing:
            strict.append(row)

    def run(name, source_rows, counts=None):
        if counts is None:
            selected = [r for r in source_rows if r["ship_type"] not in mrv_supply.OUT_OF_FUELEU_TYPES]
            dropped = {"offshore": len(source_rows) - len(selected)}
        else:
            selected, dropped = mrv_supply.size_filter(source_rows, year, counts)
        result = mrv_supply.aggregate(selected, years=(year, 2030, 2035))
        return {"id": name, "input_reports": len(source_rows), "selected_reports": len(selected),
                "dropped": dropped, "total": result["total"],
                "with_bio_assumption": result["total_with_bio_assumption"],
                "unestimated": result["unestimated"], "skipped": result["skipped"]}

    scenarios = [run("claude_current_proxy", rows, baseline),
                 run("complete_fields_same_proxy", strict, baseline),
                 run("complete_fields_no_size_proxy", strict),
                 run("complete_fields_proxy_count_minus20pct", strict, {k: int(n * .8) for k, n in baseline.items()}),
                 run("complete_fields_proxy_count_plus20pct", strict, {k: int(n * 1.2) for k, n in baseline.items()})]
    # Known input challenges demonstrate behavior; they are not real ships.
    sample = {"imo": "0000000", "ship_type": "test_only", "fuel": 1000., "co2": 3151.,
              "ch4": .05, "n2o": .18, "between": 0., "departed": 3151., "arrived": 0., "in_port": 0., "hours": 1000.}
    challenges = []
    for name, missing in (("missing_n2o", ("n2o",)), ("missing_route", ("between", "departed", "arrived", "in_port"))):
        row = dict(sample, **{k: None for k in missing})
        source = mrv_supply.estimate_ship(row)
        challenges.append({"id": name, "input_kind": "synthetic_validation_only",
            "claude_status": source["status"], "claude_intensity": source.get("intensity"),
            "claude_energy_mj": source.get("fueleu_energy_mj"),
            "strict_status": "held", "missing_fields": complete_row(row)})
    return {"schema": "fueleu_independent_audit_v1", "status": "observed_source_audit", "year": year,
            "source_sha256": hashlib.sha256(raw).hexdigest(), "baseline_sha256": hashlib.sha256(prior_raw).hexdigest(),
            "implementation_sha256": engine_receipt(), "full_reports": len(rows), "strict_usable_reports": len(strict),
            "required_fields_present_reports": sum(all(r.get(k) is not None and math.isfinite(r[k]) for k in fields if k != "hours") for r in rows),
            "duplicate_imo_count": len(duplicate_imos), "coverage": coverage, "excluded_reasons": dict(reasons),
            "baseline_proxy_counts": baseline, "scenarios": scenarios, "validation_challenges": challenges,
            "scope": "full reports only; no official ship balance; proxy sensitivity is not a confidence interval; 2030/2035 hold fleet and fuel fixed"}


def combined(payload):
    from combined_finance import calculate
    return calculate(payload["inputs"], payload["reference"], fuel_engine, engine_receipt())


if __name__ == "__main__":
    try:
        p = json.load(sys.stdin)
        if p.get("mode") == "audit":
            result = audit(p)
        elif p.get("mode") == "combined":
            result = combined(p)
        elif p.get("mode") == "validate_row":
            result = {"source": mrv_supply.estimate_ship(p["row"]), "held_fields": complete_row(p["row"])}
        else:
            raise ValueError("Unknown adapter mode")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))

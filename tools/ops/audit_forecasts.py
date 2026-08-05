#!/usr/bin/env python3
"""Audit public forecast JSONs against DATA_LAYOUT health rules.

Usage (repo root):
  python3 tools/ops/audit_forecasts.py
  python3 tools/ops/audit_forecasts.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "New for anti" / "public" / "data"

FORECAST_FILES = [
    "yield_forecast.json",
    "brazil_yield_forecast.json",
    "argentina_yield_forecast.json",
    "australia_yield_forecast.json",
    "china_yield_forecast.json",
    "indonesia_yield_forecast.json",
    "india_yield_forecast.json",
]


def skill_blob(entry: dict):
    skill = entry.get("skill") or {}
    if isinstance(skill.get("yield"), dict):
        return skill["yield"]
    return skill if isinstance(skill, dict) else {}


def point_of(entry: dict):
    if isinstance(entry.get("point"), (int, float)):
        return entry["point"]
    y = entry.get("yield_kg_ha")
    if isinstance(y, dict) and isinstance(y.get("point"), (int, float)):
        return y["point"]
    return None


def iter_crops(regions: dict):
    for key, region in (regions or {}).items():
        if not isinstance(region, dict):
            continue
        crops = region.get("crops")
        if isinstance(crops, dict):
            for ck, crop in crops.items():
                if isinstance(crop, dict):
                    yield f"{key}/{ck}", crop, region
        else:
            yield key, region, region


def audit_file(path: Path) -> dict:
    if not path.exists():
        return {"file": path.name, "ok": False, "error": "missing", "rows": []}

    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for name, entry, parent in iter_crops(doc.get("regions") or {}):
        skill = skill_blob(entry)
        skill_vs = skill.get("skill_vs_trend_only")
        beats = skill.get("beats_trend")
        low = skill.get("low_confidence")
        gate = skill.get("climate_gate") or (entry.get("yield_kg_ha") or {}).get("climate_gate")
        fa = entry.get("forecast_available", parent.get("forecast_available", True))
        pt = point_of(entry)
        flags = []
        if pt is None and fa is not False:
            flags.append("missing_point")
        if beats is False:
            flags.append("beats_trend_false")
        if low is True:
            flags.append("low_confidence")
        if isinstance(skill_vs, (int, float)) and skill_vs < 0.20:
            flags.append("skill_below_0.20")
        if isinstance(gate, dict) and "insufficient" in str(gate.get("status", "")):
            flags.append("climate_gate_stopped")
        rows.append(
            {
                "model": name,
                "point": pt,
                "skill_vs_trend": skill_vs,
                "beats_trend": beats,
                "flags": flags,
            }
        )

    weak = [r for r in rows if r["flags"]]
    return {
        "file": path.name,
        "ok": True,
        "country": doc.get("country"),
        "season": doc.get("season"),
        "n_models": len(rows),
        "n_flagged": len(weak),
        "rows": rows,
        "flagged": weak,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reports = [audit_file(DATA / name) for name in FORECAST_FILES]
    if args.json:
        json.dump(reports, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print(f"DATA dir: {DATA}\n")
    total_flag = 0
    for rep in reports:
        if not rep["ok"]:
            print(f"❌ {rep['file']}: {rep['error']}")
            continue
        total_flag += rep["n_flagged"]
        mark = "⚠" if rep["n_flagged"] else "✓"
        print(
            f"{mark} {rep['file']}  models={rep['n_models']}  flagged={rep['n_flagged']}  "
            f"season={rep.get('season')}"
        )
        for r in rep["flagged"][:12]:
            print(f"    · {r['model']}: {', '.join(r['flags'])}  "
                  f"skill={r['skill_vs_trend']} beats={r['beats_trend']}")
        if rep["n_flagged"] > 12:
            print(f"    … +{rep['n_flagged'] - 12} more")
    print(f"\nTotal flagged model rows: {total_flag}")
    missing = [r for r in reports if not r["ok"]]
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

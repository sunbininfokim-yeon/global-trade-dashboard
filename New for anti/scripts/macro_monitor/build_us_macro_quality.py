#!/usr/bin/env python3
"""Build a U.S. macro quality snapshot from point-in-time input JSON.

Collectors are intentionally separate.  This builder applies the preregistered
classification contract to official-release extracts produced by later Terra
mapping/collection jobs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.us_quality import (  # noqa: E402
    assess_lag_evidence,
    build_document_index,
    classify_employment_quality,
    classify_gdp_quality,
    compare_fomc_meetings,
)
from macro_monitor.us_quality.contracts import validate_release_envelope  # noqa: E402


DEFAULT_SPEC = ROOT / "config" / "us_macro_quality.spec.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_macro_quality_v1.json"


def _load(path: Path | None, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path else default


def build_snapshot(inputs: dict[str, Any], spec: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    releases = list(inputs.get("releases") or [])
    invalid = [
        {"release_id": row.get("release_id"), "errors": errors}
        for row in releases
        if (errors := validate_release_envelope(row))
    ]

    employment_input = inputs.get("employment")
    employment = None
    if isinstance(employment_input, dict):
        employment = classify_employment_quality(
            employment_input,
            **{
                key: spec["employment"][key]
                for key in (
                    "government_support_share_pct",
                    "defensive_lead_share_pct",
                    "breadth_floor_pct",
                    "hours_drop_floor",
                )
            },
        )

    gdp_input = inputs.get("gdp")
    gdp = None
    if isinstance(gdp_input, dict):
        gdp = classify_gdp_quality(
            gdp_input,
            private_demand_floor=spec["gdp"]["private_demand_floor"],
            dominance_margin_pp=spec["gdp"]["dominance_margin_pp"],
        )

    meetings = list(inputs.get("fomc_meetings") or [])
    fomc = compare_fomc_meetings(meetings[-2], meetings[-1]) if len(meetings) >= 2 else None

    lag_results = []
    thresholds = spec["backtest"]
    for row in inputs.get("cpi_lag_results") or []:
        lag_results.append(
            {
                "hypothesis_id": row.get("hypothesis_id"),
                **assess_lag_evidence(
                    row,
                    minimum_oos=thresholds["minimum_oos"],
                    minimum_adjacent_lags=thresholds["minimum_adjacent_lags"],
                    minimum_sign_stability=thresholds["minimum_sign_stability"],
                    minimum_oos_improvement_pct=thresholds["minimum_oos_improvement_pct"],
                ),
            }
        )

    return {
        "schema_version": "us-macro-quality-v1",
        "generated_at": generated_at,
        "source": {
            "kind": "point_in_time_official_release_extracts",
            "quality": "observed" if releases and not invalid else "partial_or_empty",
        },
        "contract_audit": {
            "release_count": len(releases),
            "invalid_release_count": len(invalid),
            "invalid_releases": invalid,
        },
        "policy_committee": {
            "comparison": fomc,
            "meeting_count": len(meetings),
            "current_roster": inputs.get("fomc_current_roster"),
            "collector": inputs.get("collector"),
        },
        "employment_quality": employment,
        "gdp_quality": gdp,
        "inflation_quality": {
            "relationship_policy": spec["cpi_relationship_policy"],
            "lag_evidence": lag_results,
        },
        "official_documents": build_document_index(inputs.get("official_documents") or []),
        "limitations": [
            "구성 상태는 전망·투자신호·좋고 나쁨의 점수가 아닙니다.",
            "CPI 관계는 point-in-time 표본외 검증을 통과하기 전까지 가설입니다.",
            "FOMC는 공개 표결과 공식 문서만 사용하며 숨은 성향을 추정하지 않습니다.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build U.S. macro quality snapshot")
    parser.add_argument("--input", type=Path, help="Point-in-time extracted input JSON")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    spec = _load(args.spec, {})
    inputs = _load(args.input, {})
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    doc = build_snapshot(inputs, spec, generated_at=generated_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.print_stats:
        print(f"wrote {args.out}")
        print(f"releases={doc['contract_audit']['release_count']} invalid={doc['contract_audit']['invalid_release_count']}")
        print(f"cpi_lag_results={len(doc['inflation_quality']['lag_evidence'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

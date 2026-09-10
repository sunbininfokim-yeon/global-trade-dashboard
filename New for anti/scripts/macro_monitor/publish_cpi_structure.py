#!/usr/bin/env python3
"""Publish the CPI relationship map to public/data/, where the browser can reach it.

config/cpi_structure.map.json is the source of truth (hand-curated, edited
directly), but scripts/ is entirely excluded from the deployed asset bundle
(.assetsignore: "Everything here would otherwise be downloadable straight
from the site" -- true of the Python pipeline, not of this reference data).
mmEnsureCpiStructure() in macro.js already tries
/public/data/us_cpi_structure_v1.json first, ahead of a
/scripts/macro_monitor/... fallback that works against a local dev server
but returns the SPA's index.html (200, not JSON) in production -- this
script is what makes the preferred path actually exist.

Run this after editing the map by hand; there is no build step in between,
just a copy, so nothing here needs re-deriving.
"""

from __future__ import annotations

import json
from pathlib import Path

SRC = Path(__file__).resolve().parent / "config" / "cpi_structure.map.json"
OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "us_cpi_structure_v1.json"
EVIDENCE = Path(__file__).resolve().parents[2] / "public" / "data" / "us_cpi_relationship_evidence_v1.json"


def publish(*, source: Path = SRC, out: Path = OUT, evidence_path: Path = EVIDENCE) -> dict:
    """Publish the map and, when available, attach the latest small evidence pack."""
    doc = json.loads(source.read_text(encoding="utf-8"))
    evidence = None
    if evidence_path.exists():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        by_id = {row["relationship_id"]: row for row in evidence.get("relationships", [])}
        for relation in doc.get("relationships", []):
            row = by_id.get(relation["id"])
            if not row:
                continue
            relation["evidence"] = row
            relation["evidence_tier"] = row["evidence_tier"]
            relation["evidence_label_ko"] = row["evidence_label_ko"]
            phase = row.get("phase") or {}
            if phase.get("summary_ko"):
                relation["current_watch_ko"] = phase["summary_ko"]
                phase_label = phase.get("label_ko") or "관계 관찰"
                relation["mechanism_ko"] = (
                    f"{relation.get('mechanism_ko', '').rstrip()} "
                    f"현재 관찰 — {phase_label}: {phase['summary_ko']}"
                ).strip()
            tests = row.get("tests") or []
            if tests:
                summaries = []
                for test in tests:
                    lag = test.get("best_lag_months")
                    improvement = test.get("best_lag_rmse_improvement_pct")
                    pvalue = test.get("best_lag_dm_pvalue")
                    metric = (
                        f"최적 후보 {lag}개월 · 표본외 RMSE {improvement:+.2f}% · DM p={pvalue:.3f}"
                        if lag is not None and improvement is not None and pvalue is not None
                        else "검증 수치 불충분"
                    )
                    summaries.append(f"{test['label_ko']} ({metric})")
                relation["evidence_status"] = " / ".join(summaries)
            elif row["evidence_tier"] == "official_methodology":
                relation["evidence_status"] = "BLS 공식 산식·표본 설계에 따른 측정상 연결"
        doc["evidence_summary"] = {
            "schema_version": evidence.get("schema_version"),
            "generated_at": evidence.get("generated_at"),
            "reference_period": evidence.get("reference_period"),
            "policy": evidence.get("policy"),
        }
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"document": doc, "evidence_attached": evidence is not None}


def main() -> int:
    result = publish()
    doc = result["document"]
    print(f"published {SRC} -> {OUT}")
    print(f"  {len(doc.get('relationships', []))} relationships, {len(doc.get('items', []))} items")
    print(f"  evidence_attached={result['evidence_attached']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

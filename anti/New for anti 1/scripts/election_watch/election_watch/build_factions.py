"""Normalize House + LDP factions for elections board. Missing → 없음, unknown → 불명."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"
OUT = CFG / "extracted"
OUT.mkdir(parents=True, exist_ok=True)

없음 = "없음"
불명 = "불명"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _members_field(snapshot: Any) -> Any:
    if snapshot is None:
        return 불명
    if isinstance(snapshot, dict):
        members = snapshot.get("members")
        if members:
            return {
                "count": snapshot.get("count") or len(members),
                "as_of": snapshot.get("snapshot_date") or snapshot.get("as_of") or 불명,
                "source_id": snapshot.get("source_id") or 불명,
                "members": members,
            }
        if snapshot.get("count"):
            return {"count": snapshot["count"], "members": 불명}
    return 불명


def build_usa_house_factions() -> Dict[str, Any]:
    raw = json.loads((CFG / "usa_house_factions.json").read_text(encoding="utf-8"))
    parties_out = {}
    for pid, block in (raw.get("parties") or {}).items():
        factions = []
        for f in block.get("factions") or []:
            roster = _members_field(f.get("members_snapshot"))
            factions.append(
                {
                    "id": f.get("id"),
                    "abbr": (f.get("id") or "").upper(),
                    "name_en": f.get("name_en") or 불명,
                    "spectrum": f.get("spectrum") or 불명,
                    "roster_mode": f.get("roster_mode") or 불명,
                    "roster_official": f.get("roster_official")
                    if "roster_official" in f
                    else 불명,
                    "confidence": f.get("confidence") or 불명,
                    "url": f.get("url") or 없음,
                    "members": roster,
                    "note": f.get("note") or f.get("caveat") or 없음,
                }
            )
        parties_out[pid] = {"factions": factions}
    return {
        "chamber": "house",
        "as_of": raw.get("as_of") or _now(),
        "senate_factions": 없음,  # 미국 상원은 하원형 파벌 추적 대상 아님
        "parties": parties_out,
        "source_file": "usa_house_factions.json",
    }


def build_jpn_ldp_factions() -> Dict[str, Any]:
    raw = json.loads((CFG / "jpn_ldp_factions.json").read_text(encoding="utf-8"))
    factions_out = []
    for f in raw.get("factions") or []:
        counts = f.get("counts") or []
        n_latest = counts[-1].get("n_approx") if counts else 불명
        members = f.get("members_snapshot")
        factions_out.append(
            {
                "id": f.get("id"),
                "abbr": (f.get("id") or "").upper(),
                "name_ko": f.get("name_ko") or 불명,
                "name_ja": f.get("name_ja") or 불명,
                "status": f.get("status") or 불명,
                "head_figures": f.get("head_figures")
                or f.get("head_figures_historical")
                or 불명,
                "n_approx_latest": n_latest if n_latest is not None else 불명,
                "members": members if members else 불명,
                "confidence": f.get("confidence") or 불명,
                "crosscheck_sources": f.get("crosscheck_sources") or 없음,
            }
        )
    return {
        "party_abbr": "LDP",
        "as_of": raw.get("as_of") or _now(),
        "other_parties_factions": 없음,  # CDP/Ishin/Komeito 당내 파벌 미추적
        "factions": factions_out,
        "source_file": "jpn_ldp_factions.json",
    }


def main() -> int:
    doc = {
        "generated_at": _now(),
        "null_policy": {
            "없음": "해당 제도/데이터 없음 (존재하지 않음)",
            "불명": "존재할 수 있으나 확보·확정 못 함",
            "priority": ["없음", "불명"],
        },
        "USA": build_usa_house_factions(),
        "JPN": build_jpn_ldp_factions(),
    }
    path = OUT / "factions_board.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(path),
                "usa_house_faction_groups": sum(
                    len(p["factions"]) for p in doc["USA"]["parties"].values()
                ),
                "usa_senate_factions": doc["USA"]["senate_factions"],
                "jpn_ldp_factions": len(doc["JPN"]["factions"]),
                "jpn_other_parties_factions": doc["JPN"]["other_parties_factions"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

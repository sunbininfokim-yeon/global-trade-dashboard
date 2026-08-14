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


def _display_count(faction: Dict[str, Any]) -> Any:
    """Return a source-authored UI count; never derive overlapping caucus totals here."""
    if faction.get("display_count") is not None:
        return faction["display_count"]
    snapshot = faction.get("members_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("count") is not None:
        return {
            "value": snapshot["count"],
            "scope": "members_snapshot",
            "as_of": snapshot.get("snapshot_date") or snapshot.get("as_of") or 불명,
            "confidence": faction.get("confidence") or 불명,
        }
    return 불명


def build_usa_house_factions() -> Dict[str, Any]:
    raw = json.loads((CFG / "usa_house_factions.json").read_text(encoding="utf-8"))
    parties_out = {}
    # v4 source uses by_party. Keep the legacy key as a compatibility fallback.
    source_parties = raw.get("by_party") or raw.get("parties") or {}
    party_ids = {"Democratic": "dem", "Republican": "gop"}
    for source_pid, block in source_parties.items():
        pid = party_ids.get(source_pid, source_pid)
        factions = []
        for f in block.get("factions") or []:
            roster = _members_field(f.get("members_snapshot"))
            factions.append(
                {
                    "id": f.get("id"),
                    "abbr": (f.get("id") or "").upper(),
                    "name_ko": f.get("name_ko") or 불명,
                    "name_en": f.get("name_en") or 불명,
                    "spectrum": f.get("spectrum") or 불명,
                    "spectrum_ko": f.get("spectrum_ko") or 불명,
                    "status": f.get("status") or "formal_caucus",
                    "roster_mode": f.get("roster_mode") or 불명,
                    "roster_official": f.get("roster_official")
                    if "roster_official" in f
                    else f.get("roster_mode") == "official_caucus_site",
                    "confidence": f.get("confidence") or 불명,
                    "url": f.get("url") or 없음,
                    "display_count": _display_count(f),
                    "members": roster,
                    "current_house_dsa_members": f.get("current_house_dsa_members"),
                    "primary_winners_2026_safe_D": f.get("primary_winners_2026_safe_D"),
                    "broader_mamdani_aligned": f.get("broader_mamdani_aligned"),
                    "sources": f.get("sources") or 없음,
                    "note": f.get("note_ko") or f.get("note") or f.get("caveat") or 없음,
                }
            )
        parties_out[pid] = {
            "source_key": source_pid,
            "party_ko": block.get("party_ko") or 불명,
            "party_en": block.get("party_en") or 불명,
            "factions": factions,
        }
    return {
        "chamber": "house",
        "as_of": raw.get("as_of") or _now(),
        "count_policy": "overlap_allowed; display_count is per-group and must not be summed",
        "senate_factions": 없음,  # 미국 상원은 하원형 파벌 추적 대상 아님
        "parties": parties_out,
        "ui_notes_ko": raw.get("ui_notes_ko"),
        "source_file": "usa_house_factions.json",
    }


def build_jpn_ldp_factions() -> Dict[str, Any]:
    raw = json.loads((CFG / "jpn_ldp_factions.json").read_text(encoding="utf-8"))
    factions_out = []
    grouped = raw.get("by_status") or {"legacy": {"factions": raw.get("factions") or []}}
    for group_id, group in grouped.items():
        for f in group.get("factions") or []:
            counts = f.get("counts") or []
            n_latest = f.get("n_approx_latest")
            if n_latest is None:
                n_latest = f.get("n_approx")
            if n_latest is None and counts:
                n_latest = counts[-1].get("n_approx")
            members = f.get("members_snapshot")
            factions_out.append(
                {
                    "id": f.get("id"),
                    "abbr": (f.get("id") or "").upper(),
                    "group_id": group_id,
                    "group_label_ko": group.get("label_ko") or 불명,
                    "name_ko": f.get("name_ko") or 불명,
                    "name_ja": f.get("name_ja") or 불명,
                    "status": f.get("status") or 불명,
                    "head": f.get("head"),
                    "head_figures": f.get("head_figures")
                    or f.get("head_figures_historical")
                    or f.get("figures_ko")
                    or 불명,
                    "spectrum_ko": f.get("spectrum_ko") or 불명,
                    "n_approx_latest": n_latest if n_latest is not None else 불명,
                    "n_as_of": f.get("n_as_of") or 불명,
                    "n_source": f.get("n_source") or 없음,
                    "members": members if members else 불명,
                    "confidence": f.get("confidence") or 불명,
                    "crosscheck_sources": f.get("crosscheck_sources") or 없음,
                    "note": f.get("note") or 없음,
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

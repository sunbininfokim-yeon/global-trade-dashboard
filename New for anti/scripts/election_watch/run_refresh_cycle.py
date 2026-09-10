#!/usr/bin/env python3
"""Run a review-first election source refresh and UI-contract build cycle.

The cycle can fetch approved raw source pages and rebuild derived JSON, but it
never promotes raw text into profiles/calendars automatically. Each fetch is
reported as pending review, so facts remain source-reviewed rather than inferred.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TARGETS_PATH = ROOT / "config" / "source_watch_targets.json"
REPORT_PATH = ROOT / "config" / "extracted" / "source_refresh_report_v1.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_targets(countries: set[str]) -> list[dict[str, Any]]:
    targets = load_json(TARGETS_PATH).get("targets", [])
    return [target for target in targets if not countries or target.get("iso3") in countries]


def source_status(target: dict[str, Any]) -> dict[str, Any]:
    raw = ROOT / target["raw_path"]
    meta_path = raw.with_name(f"{raw.name}.meta.json")
    failure_path = raw.with_name(f"{raw.name}.fetch_error.json")
    entry = {
        "target_id": target["id"],
        "iso3": target["iso3"],
        "url": target["url"],
        "raw_path": target["raw_path"],
        "review_fields": target.get("review_fields", []),
    }
    if not meta_path.exists():
        if failure_path.exists():
            failure = load_json(failure_path)
            return {
                **entry,
                "status": failure.get("review_status", "fetch_failed_needs_alternative_source"),
                "attempted_at": failure.get("attempted_at"),
                "error": failure.get("error"),
            }
        return {**entry, "status": "not_captured_or_fetch_failed"}
    meta = load_json(meta_path)
    return {
        **entry,
        "status": meta.get("review_status", "pending_manual_text_review"),
        "fetched_at": meta.get("fetched_at"),
        "final_url": meta.get("final_url"),
        "http_status": meta.get("http_status"),
        "bytes": meta.get("bytes"),
        "sha256": meta.get("sha256"),
    }


def run(command: list[str]) -> int:
    print("$", " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", action="append", default=[], help="ISO3 filter; repeatable")
    parser.add_argument("--fetch", action="store_true", help="Fetch source pages before reporting")
    parser.add_argument("--overwrite-raw", action="store_true", help="Replace existing raw caches during fetch")
    parser.add_argument(
        "--build-derived",
        action="store_true",
        help="Rebuild factions, board, calendar master, and UI readiness manifest after reporting",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print selected work without fetching, writing, or rebuilding")
    args = parser.parse_args()
    countries = {country.upper() for country in args.country}
    targets = selected_targets(countries)
    if not targets:
        parser.error("No source targets matched the requested country filter")

    if args.dry_run:
        for target in targets:
            print(f"DRY-RUN fetch/review: {target['id']} ({target['iso3']})")
        if args.build_derived:
            print(
                "DRY-RUN derived rebuild: election_watch.extract_usa_committees + "
                "election_watch.extract_usa_senate_terms + "
                "election_watch.build_factions + "
                "build_board.py + build_calendar_master.py + build_ui_manifest.py"
            )
        return 0

    fetch_exit = 0
    if args.fetch:
        command = [sys.executable, "capture_sources.py", "--fetch"]
        for country in sorted(countries):
            command.extend(["--country", country])
        if args.overwrite_raw:
            command.append("--overwrite")
        fetch_exit = run(command)

    statuses = [source_status(target) for target in targets]
    report = {
        "schema": "election_source_refresh_report_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetch_requested": bool(args.fetch),
        "fetch_exit_code": fetch_exit if args.fetch else None,
        "policy_ko": "원문 캐시는 자동 갱신할 수 있으나 profile/calendar/extracted 반영은 사람의 공개원문 검토 후에만 한다.",
        "sources": statuses,
        "next_action": "Review raw cache + metadata, patch verified fields, then run run_refresh_cycle.py --build-derived."
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", REPORT_PATH)

    build_exit = 0
    if args.build_derived:
        build_exit = run([sys.executable, "-m", "election_watch.extract_usa_committees"])
        if build_exit == 0:
            build_exit = run([sys.executable, "-m", "election_watch.extract_usa_senate_terms"])
        if build_exit == 0:
            build_exit = run([sys.executable, "-m", "election_watch.build_factions"])
        if build_exit == 0:
            build_exit = run([sys.executable, "build_board.py", "--no-betting", "--print-stats"])
        if build_exit == 0:
            build_exit = run([sys.executable, "build_calendar_master.py"])
        if build_exit == 0:
            build_exit = run([sys.executable, "build_ui_manifest.py"])
    return 1 if fetch_exit or build_exit else 0


if __name__ == "__main__":
    raise SystemExit(main())

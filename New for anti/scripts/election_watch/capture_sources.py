#!/usr/bin/env python3
"""Cache explicitly-approved public election source pages for manual text review.

This command never changes profiles, calendars, or board output. It only saves the
specified source page and a provenance sidecar. Run with --fetch to allow network
access; without it the command is a dry run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
TARGETS_PATH = ROOT / "config" / "source_watch_targets.json"
USER_AGENT = "election-watch-source-review/1.0 (+manual-public-source-review)"


def load_targets() -> list[dict[str, Any]]:
    payload = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise ValueError("source_watch_targets.json must contain targets[]")
    return targets


def choose_targets(
    targets: list[dict[str, Any]], countries: set[str], target_ids: set[str]
) -> list[dict[str, Any]]:
    selected = [
        target
        for target in targets
        if (not countries or target.get("iso3") in countries)
        and (not target_ids or target.get("id") in target_ids)
    ]
    if not selected:
        raise ValueError("No source targets matched the requested filter")
    return selected


def fetch_one(target: dict[str, Any], timeout: float, max_bytes: int, overwrite: bool) -> str:
    raw_rel = target.get("raw_path")
    url = target.get("url")
    if not isinstance(raw_rel, str) or not isinstance(url, str):
        raise ValueError(f"Invalid target: {target.get('id')}")
    output = ROOT / raw_rel
    meta_path = output.with_name(f"{output.name}.meta.json")
    if output.exists() and not overwrite:
        return f"SKIP {target['id']}: {output.relative_to(ROOT)} exists (use --overwrite)"

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.1"})
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - URL comes from reviewed config
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"Response exceeds --max-bytes ({max_bytes})")
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        final_url = response.geturl()
        status = getattr(response, "status", None)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    metadata = {
        "target_id": target["id"],
        "iso3": target.get("iso3"),
        "requested_url": url,
        "final_url": final_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "http_status": status,
        "content_type": content_type,
        "charset": charset,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "role": target.get("role"),
        "review_fields": target.get("review_fields", []),
        "review_status": "pending_manual_text_review"
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"FETCHED {target['id']}: {output.relative_to(ROOT)} ({len(body)} bytes)"


def record_failure(target: dict[str, Any], error: Exception) -> Path:
    """Persist failed fetch provenance without replacing a prior successful cache."""
    raw_rel = target.get("raw_path")
    if not isinstance(raw_rel, str):
        raise ValueError(f"Invalid target: {target.get('id')}")
    output = ROOT / raw_rel
    failure_path = output.with_name(f"{output.name}.fetch_error.json")
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_id": target.get("id"),
        "iso3": target.get("iso3"),
        "requested_url": target.get("url"),
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
        "review_status": "fetch_failed_needs_alternative_source",
    }
    failure_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return failure_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", action="append", default=[], help="ISO3 country filter; repeatable")
    parser.add_argument("--target", action="append", default=[], help="Target id filter; repeatable")
    parser.add_argument("--fetch", action="store_true", help="Fetch approved source pages; otherwise dry-run")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing raw cache and sidecar")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    parser.add_argument("--max-bytes", type=int, default=5_000_000, help="Maximum response size per source")
    args = parser.parse_args()

    try:
        selected = choose_targets(
            load_targets(),
            {country.upper() for country in args.country},
            set(args.target),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not args.fetch:
        for target in selected:
            print(f"DRY-RUN {target['id']}: {target['url']} -> {target['raw_path']}")
        print("No files written. Re-run with --fetch after approving the target list.")
        return 0

    failures = 0
    for target in selected:
        try:
            print(fetch_one(target, args.timeout, args.max_bytes, args.overwrite))
        except (HTTPError, URLError, OSError, ValueError) as exc:
            failures += 1
            failure_path = record_failure(target, exc)
            print(f"ERROR {target['id']}: {exc} (recorded {failure_path.relative_to(ROOT)})", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

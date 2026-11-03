#!/usr/bin/env python3
"""Publish config/china_leader_appointments.json for the China party screen.

The screen reads public/data/elections_cn_leaders_v1.json.  This step copies the
reviewed source file after checking the rules the UI relies on:

* every URL is http(s);
* every dated event either names its source URL or says why it has none;
* each of the 31 provincial secretaries has a matching government head;
* government-head status is one of the four known values, and only an
  ``elected`` head may carry an election event.

    python3 build_cn_leaders_public.py          # write
    python3 build_cn_leaders_public.py --check  # fail if the published file differs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "config" / "china_leader_appointments.json"
TARGET = ROOT.parents[1] / "public" / "data" / "elections_cn_leaders_v1.json"
SCHEMA = "china_leader_appointments_v1"
HEAD_STATUS = {"elected", "acting", "vacant", "secretary_concurrent"}


def _events(node, path=""):
    if isinstance(node, dict):
        if "date" in node and ("url" in node or "note_ko" in node):
            yield path, node
        for key, value in node.items():
            yield from _events(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _events(value, f"{path}[{i}]")


def _urls(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if (key == "url" or key.endswith("_url")) and value is not None:
                yield f"{path}.{key}", value
            else:
                yield from _urls(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _urls(value, f"{path}[{i}]")


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not data.get("as_of"):
        errors.append("as_of missing")
    for path, url in _urls(data):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            errors.append(f"{path}: not an http(s) URL: {url!r}")
    for path, event in _events(data):
        if event.get("date") and not event.get("url") and not event.get("note_ko"):
            errors.append(f"{path}: dated event without url or note_ko")
    secretaries = data.get("provincial_secretaries") or []
    heads = {h.get("region_ko"): h for h in data.get("government_heads") or []}
    if len(secretaries) != 31:
        errors.append(f"expected 31 provincial secretaries, got {len(secretaries)}")
    for sec in secretaries:
        if sec.get("region_ko") not in heads:
            errors.append(f"{sec.get('region_ko')}: no government head")
    for region, head in heads.items():
        status = head.get("status")
        if status not in HEAD_STATUS:
            errors.append(f"{region}: unknown head status {status!r}")
        if head.get("elected") and status != "elected":
            errors.append(f"{region}: {status} head carries an election event")
        if status == "vacant" and head.get("name_zh"):
            errors.append(f"{region}: vacant head has a name")
    return errors


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    text = render(data)
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET.name} is stale; run build_cn_leaders_public.py", file=sys.stderr)
            return 1
        print("ok")
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

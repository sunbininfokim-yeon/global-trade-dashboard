#!/usr/bin/env python3
"""Compare New for anti/public/locales/ko.json and New for anti/public/locales/en.json key sets (1:1).

Ignores meta keys starting with "__".
Exit 0 on match; exit 1 with missing/extra keys listed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KO = ROOT / "New for anti" / "public" / "locales" / "ko.json"
EN = ROOT / "New for anti" / "public" / "locales" / "en.json"


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("__"):
                continue
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, key))
            else:
                out[key] = v
    else:
        out[prefix] = obj
    return out


def load(path: Path) -> dict:
    if not path.is_file():
        print(f"MISSING FILE: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return flatten(json.load(f))


def main() -> int:
    ko = load(KO)
    en = load(EN)
    ko_keys = set(ko)
    en_keys = set(en)
    missing = sorted(ko_keys - en_keys)
    extra = sorted(en_keys - ko_keys)
    empty_en = sorted(k for k, v in en.items() if isinstance(v, str) and not v.strip())
    todo = []
    # optional meta block retained only in en / either file under __todos__
    for path in (KO, EN):
        raw = json.loads(path.read_text(encoding="utf-8"))
        todos = raw.get("__todos__") or {}
        if isinstance(todos, dict):
            for k, reason in todos.items():
                todo.append(f"  {k}: {reason}")

    print(f"ko keys: {len(ko_keys)}")
    print(f"en keys: {len(en_keys)}")
    ok = True
    if missing:
        ok = False
        print(f"\nMISSING in en.json ({len(missing)}):")
        for k in missing:
            print(f"  - {k}")
    if extra:
        ok = False
        print(f"\nEXTRA in en.json ({len(extra)}):")
        for k in extra:
            print(f"  + {k}")
    if empty_en:
        ok = False
        print(f"\nEMPTY en values ({len(empty_en)}):")
        for k in empty_en:
            print(f"  · {k}")
    if todo:
        print(f"\nTODO notes ({len(todo)}):")
        print("\n".join(todo))
    if ok:
        print("\nOK: key sets match 1:1")
        return 0
    print("\nFAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

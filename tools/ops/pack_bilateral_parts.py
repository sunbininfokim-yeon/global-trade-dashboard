#!/usr/bin/env python3
"""Deploy-time only: fold commodity_trade_bilateral_v1/parts/*.json into shards.

Workers Free serves at most 20,000 static asset files per version. The monthly Comtrade
collector writes one content-addressed file per partition (8,449 by 2026-11-24), which pushed
the bundle to 20,759 and every deploy failed. In the CI checkout, before `wrangler deploy`, this
groups the parts by the first three hex characters of their name into
commodity_trade_bilateral_v1/shards/<abc>.json = {"<name>.json": <part>, ...} (at most 4,096
files, ~2 parts each) and removes parts/ from the workspace. Git keeps the parts; the collector
is unchanged; trade-monthly.js reads a part from its shard and falls back to parts/ when no shard
exists (local static servers).

  python3 tools/ops/pack_bilateral_parts.py            # in the deploy job, from the repo root
  python3 tools/ops/pack_bilateral_parts.py --check    # count only
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "New for anti" / "public" / "data" / "commodity_trade_bilateral_v1"
PREFIX = 3


def shard_key(name: str) -> str:
    return name[:PREFIX]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    parts = sorted((BASE / "parts").glob("*.json"))
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in parts:
        groups[shard_key(p.name)].append(p)
    print(f"{len(parts)} parts -> {len(groups)} shards")
    if a.check or not parts:
        return 0
    out = BASE / "shards"
    out.mkdir(exist_ok=True)
    for key, files in groups.items():
        doc = {f.name: json.loads(f.read_text(encoding="utf-8")) for f in files}
        (out / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.rmtree(BASE / "parts")
    return 0


if __name__ == "__main__":
    sys.exit(main())

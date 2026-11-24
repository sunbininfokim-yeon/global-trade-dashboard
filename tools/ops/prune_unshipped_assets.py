#!/usr/bin/env python3
"""Drop generated files no page can reach from the deploy checkout.

Cloudflare's Workers Free plan caps a version at 20,000 static assets. On
2026-11-24 the bundle reached 20,119 and every deploy failed. Most of the
excess is commodity_trade_bilateral_v1/parts/*.json that the bilateral index
no longer lists (7,168 of 7,808 on that day): content-addressed parts whose
newer copies replaced them. The browser only ever opens a part through the
index (trade-monthly.js loadPart), so an unlisted part is unreachable.

Runs in the deploy job on the throwaway checkout, never on the repository:
git keeps the files and the collectors are untouched. Prints the asset count
after pruning and fails if it is still over the cap, naming the biggest
folders, so the next overflow says where to look.
"""

import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "New for anti")
BILATERAL = os.path.join(ROOT, "public", "data", "commodity_trade_bilateral_v1")
CAP = 20000


def prune_bilateral(base=BILATERAL):
    index = os.path.join(base, "index.json")
    parts = os.path.join(base, "parts")
    if not (os.path.exists(index) and os.path.isdir(parts)):
        return 0
    with open(index, encoding="utf-8") as f:
        listed = {e["path"] for e in json.load(f).get("entries", []) if e.get("path")}
    if not listed:
        return 0          # an empty index means something broke; ship as is
    removed = 0
    for name in os.listdir(parts):
        if f"parts/{name}" not in listed:
            os.remove(os.path.join(parts, name))
            removed += 1
    return removed


def ignored(rel, patterns):
    import fnmatch
    return any(fnmatch.fnmatch(rel, p) or rel.split("/")[0] == p.rstrip("/") for p in patterns)


def count_assets(root=ROOT):
    patterns = []
    path = os.path.join(root, ".assetsignore")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            patterns = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    total, by_dir = 0, {}
    for d, _, files in os.walk(root):
        for name in files:
            rel = os.path.relpath(os.path.join(d, name), root).replace(os.sep, "/")
            if rel.startswith(".git") or ignored(rel, patterns):
                continue
            total += 1
            top = "/".join(rel.split("/")[:3])
            by_dir[top] = by_dir.get(top, 0) + 1
    return total, by_dir


def main():
    removed = prune_bilateral()
    total, by_dir = count_assets()
    print(f"pruned {removed} unlisted bilateral parts; {total} assets to upload (cap {CAP})")
    if total > CAP:
        for k, v in sorted(by_dir.items(), key=lambda kv: -kv[1])[:8]:
            print(f"  {v:6d}  {k}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

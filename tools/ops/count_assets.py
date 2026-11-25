#!/usr/bin/env python3
"""Fail before `wrangler deploy` when the asset bundle would exceed the Workers Free file limit.

Counts files under the assets directory minus .assetsignore patterns (gitignore-style subset:
'dir', 'dir/**', '*.ext', plain names), and exits 1 above LIMIT so the failure names the cause
instead of an opaque Cloudflare API error.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "New for anti"
LIMIT = 20_000


def patterns() -> list[str]:
    f = ROOT / ".assetsignore"
    if not f.exists():
        return []
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def ignored(rel: str, pats: list[str]) -> bool:
    for p in pats:
        base = p[:-3] if p.endswith("/**") else p
        if rel == base or rel.startswith(base.rstrip("/") + "/") or fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(Path(rel).name, p):
            return True
    return False


def main() -> int:
    pats = patterns()
    files = [p for p in ROOT.rglob("*") if p.is_file() and not ignored(p.relative_to(ROOT).as_posix(), pats)]
    n = len(files)
    top: dict[str, int] = {}
    for p in files:
        parts = p.relative_to(ROOT).parts
        k = "/".join(parts[:3]) if parts[0] == "public" else parts[0]
        top[k] = top.get(k, 0) + 1
    print(f"asset files: {n} (limit {LIMIT})")
    for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {v:6d}  {k}")
    return 1 if n > LIMIT else 0


if __name__ == "__main__":
    sys.exit(main())

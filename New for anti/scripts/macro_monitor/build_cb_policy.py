#!/usr/bin/env python3
"""Assemble public/data/cb_policy_v1.json (KOR + JPN policy-board panels) from
config/bok_mpc_v1.json and config/boj_mpm_v1.json (build_bok_mpc.py / build_boj_mpm.py).

Offline: reads only the two config files. A bank whose file is missing or empty is
left out rather than filled in.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect.assemble import assemble_bok, assemble_boj  # noqa: E402

BOK_IN = ROOT / "config" / "bok_mpc_v1.json"
BOJ_IN = ROOT / "config" / "boj_mpm_v1.json"
OUT = ROOT.parent.parent / "public" / "data" / "cb_policy_v1.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    today = date.today()
    banks = {}
    for iso3, path, fn in (("KOR", BOK_IN, assemble_bok), ("JPN", BOJ_IN, assemble_boj)):
        block = fn(_load(path), today=today)
        if block:
            block["retrieved_at"] = _load(path).get("retrieved_at")
            banks[iso3] = block
    if not banks:
        print("no collected policy-board data; nothing written", file=sys.stderr)
        return 1
    doc = {
        "schema_version": "cb-policy-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "note_ko": "정책위원회 공식 자료의 결정·표결·문구를 옮긴 것입니다. 문구 변화는 비교일 뿐 성향 점수가 아닙니다.",
        **banks,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for iso3, b in banks.items():
        d = b["decision"]
        print(f"{iso3}: {d['meeting_date']} {d['prior_rate_pct']}% -> {d['rate_pct']}% ({d['majority']}), "
              f"{len(b['statement_diffs'])} diff(s), next meeting {b['schedule']['next_meeting_date']}")
    print(f"-> {OUT}  ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Assemble public/data/cb_policy_v1.json (KOR + JPN + GBR + EMU policy-board panels) from
config/{bok_mpc,boj_mpm,boe_mpc,ecb_gc}_v1.json (build_bok_mpc.py / build_boj_mpm.py /
build_boe_mpc.py / build_ecb_gc.py).

Offline: reads only the four config files. A bank whose file is missing or empty is
left out rather than filled in.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.cb_collect.assemble import assemble_boe, assemble_bok, assemble_boj, assemble_ecb  # noqa: E402

BOK_IN = ROOT / "config" / "bok_mpc_v1.json"
BOJ_IN = ROOT / "config" / "boj_mpm_v1.json"
BOE_IN = ROOT / "config" / "boe_mpc_v1.json"
ECB_IN = ROOT / "config" / "ecb_gc_v1.json"
OUT = ROOT.parent.parent / "public" / "data" / "cb_policy_v1.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    today = date.today()
    banks = {}
    for iso3, path, fn in (("KOR", BOK_IN, assemble_bok), ("JPN", BOJ_IN, assemble_boj),
                           ("GBR", BOE_IN, assemble_boe), ("EMU", ECB_IN, assemble_ecb)):
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
    # generated_at moves only when the content does: a quiet day leaves the file byte-identical, so the
    # scheduled run commits nothing (a daily timestamp-only commit is a daily deploy for no change)
    previous = _load(OUT)
    if previous and {k: v for k, v in previous.items() if k != "generated_at"} == {k: v for k, v in doc.items() if k != "generated_at"}:
        doc["generated_at"] = previous["generated_at"]
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for iso3, b in banks.items():
        d = b["decision"]
        print(f"{iso3}: {d['meeting_date']} {d['prior_rate_pct']}% -> {d['rate_pct']}% ({d['majority']}), "
              f"{len(b['statement_diffs'])} diff(s), next meeting {b['schedule']['next_meeting_date']}")
    print(f"-> {OUT}  ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

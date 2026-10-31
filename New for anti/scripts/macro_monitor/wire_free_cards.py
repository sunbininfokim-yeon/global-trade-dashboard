#!/usr/bin/env python3
"""Attach every card listed in config/free_cards_v1.json (see macro_monitor/free_cards.py).

    python3 wire_free_cards.py            # read enabled entries, update the pack and the status file
    python3 wire_free_cards.py --probe    # read every entry that names a reader (disabled ones too), print, write nothing
    python3 wire_free_cards.py --check    # validate the registry only

A card that cannot be read keeps what the pack has and its failure is counted in
config/free_cards_status_v1.json. Keyless. Exit status 1 when an enabled entry failed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import free_cards as fc  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor import world_public_series as wps  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def check(entries: list[dict]) -> int:
    bad = 0
    seen = set()
    for e in entries:
        key = f"{e.get('iso3')}/{e.get('id')}"
        errs = fc.validate(e)
        if key in seen:
            errs.append("duplicate")
        seen.add(key)
        if errs:
            bad += 1
            print(f"  {key}: {'; '.join(errs)}")
    on = sum(1 for e in entries if e.get("enabled", True))
    print(f"registry: {len(entries)} entries, {on} enabled, {bad} invalid")
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    missing = [f"{c['iso3']}/{i['id']}" for c in pack["countries"] for i in c["indicators"]
               if i.get("hidden") and f"{c['iso3']}/{i['id']}" not in seen]
    if missing:                                   # not an error: a new fixture card simply has no entry yet
        print(f"  hidden cards with no registry entry ({len(missing)}): {', '.join(missing[:20])}")
    return 1 if bad else 0


def probe(entries: list[dict]) -> int:
    fetch = wps.Fetch()
    for e in entries:
        if not (e.get("read") or {}).get("reader"):
            continue
        key = f"{e['iso3']}/{e['id']}{'' if e.get('enabled', True) else ' (disabled)'}"
        try:
            got = fc.apply_ops(fc.read(fetch, e["read"]), e.get("ops") or [], fetch)
            pts = got[0] if isinstance(got, tuple) else got
            print(f"  ok   {key:34s} {pts[-1][0]}  {pts[-1][1]:.4g}  ({len(pts)} obs)")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {key:34s} {str(exc)[:140]}")
    return 0


def main(argv: list[str]) -> int:
    entries = fc.load_registry()
    if "--check" in argv:
        return check(entries)
    if check(entries):
        return 1
    if "--probe" in argv:
        return probe(entries)

    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    status = json.loads(fc.STATUS.read_text(encoding="utf-8")) if fc.STATUS.exists() else {}
    cache = json.loads(fc.CACHE.read_text(encoding="utf-8")) if fc.CACHE.exists() else {}
    fetch, now, failures = wps.Fetch(), ups.now_iso(), []
    for iso, group in fc.enabled_by_country(entries).items():
        country = by_iso.get(iso)
        if not country:
            failures.append(f"{iso}: not in the pack")
            continue
        cards, patches = [fc.to_card(e) for e in group], {}
        for c in cards:
            key = f"{iso}/{c.spec.id}"
            try:
                got = c.read(fetch)
                pts, last_day = got if isinstance(got, tuple) else (got, None)
                pts = fc.merge_cache(cache, key, pts)
                patches[c.spec.id] = wps.build_patch(c, (pts, last_day) if last_day else pts, retrieved_at=now)
                fc.update_status(status, key, ok=True, now=now, patch=patches[c.spec.id])
            except Exception as exc:  # noqa: BLE001 -- one card must not block the others
                fc.update_status(status, key, ok=False, now=now, error=str(exc))
                failures.append(f"{key}: {str(exc)[:160]}")
        result = wps.apply_country(country, cards, patches, retrieved_at=now)
        print(f"{iso}: {len(patches)}/{len(cards)} read, changed {result['changed'] or 'none'}")
        for sid, p in patches.items():
            print(f"  {sid:22s} {p['display']:>12s}  {p['reference_period']}")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    # one card per line: a day that adds a month changes one line of the diff
    lines = [f"{json.dumps(k)}:{json.dumps(v, separators=(',', ':'))}" for k, v in sorted(cache.items())]
    fc.CACHE.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    fc.STATUS.write_text(json.dumps(dict(sorted(status.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

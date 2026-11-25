#!/usr/bin/env python3
"""US marketable debt: weighted average maturity, bills share and maturity wall (MSPD), plus the 30-year
yield around Treasury's debt-management actions -> USA card `ust_debt_wam` (see macro_monitor/ust_maturity.py).

    python3 wire_ust_maturity.py             # new months only
    python3 wire_ust_maturity.py --rebuild   # every month again (adds duration to the cached history)

Monthly summaries are kept in config/ust_mspd_wam_v1.json; each run fetches only months after the last
one. A source that cannot be read leaves the card as it was and exits 1. Keyless.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ust_auctions as ua  # noqa: E402
from macro_monitor import ust_maturity as um  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
CACHE = ROOT / "config" / "ust_mspd_wam_v1.json"
EVENTS = ROOT / "config" / "ust_toolkit_events_v1.json"
FEED = ROOT / "config" / "ust_toolkit_feed_v1.json"


def toolkit(dgs30: list[tuple[str, float]], events: list[dict], since: str) -> dict:
    """The 30-year yield from `since`, and its change 1, 5 and 20 trading days after each action."""
    pts = [(d, v) for d, v in dgs30 if d >= since]
    dates = [d for d, _ in pts]
    out = []
    for e in events:
        i = next((k for k, d in enumerate(dates) if d >= e["date"]), None)
        if i is None:
            continue
        base = pts[i - 1][1] if i > 0 else pts[i][1]       # the close before the action
        chg = {f"d{n}_bp": (round((pts[i + n - 1][1] - base) * 100) if i + n - 1 < len(pts) else None) for n in (1, 5, 20)}
        out.append({**e, "on": dates[i], "before_pct": base, **chg})
    return {"series": {"dates": dates, "values": [v for _, v in pts]}, "events": out,
            "label_ko": "미국 30년 국채금리(%)", "source": "FRED DGS30"}


def duration_inputs():
    """FRED par-curve series and a SOMA lookup (latest Wednesday on or before a month end)."""
    curves = {sid: ups.fetch_fred(sid) for sid in um.CURVE_IDS}
    dates = um.soma_dates()

    def soma_for(month_end: str):
        asof = max((d for d in dates if d <= month_end), default=None)
        return (asof, um.fetch_soma(asof)) if asof else None
    return curves, soma_for


def main() -> int:
    now, failed = ups.now_iso(), 0
    rebuild = "--rebuild" in sys.argv
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"schema": "ust_mspd_wam_v1", "months": []}
    months = [] if rebuild else cache["months"]
    try:
        rows = um.fetch_rows(months[-1]["date"] if months else None)
        try:
            curves, soma_for = duration_inputs() if rows else (None, None)
        except Exception as exc:  # noqa: BLE001 -- WAM still goes in; duration waits for the next run
            print(f"FAILED duration inputs: {exc}", file=sys.stderr)
            curves, soma_for = None, None
            failed += 1
        new = um.monthly(rows, curves, soma_for)
        cache["months"] = months
        if new:
            months += new
            cache["months"] = months
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED mspd: {exc}", file=sys.stderr)
        failed += 1
    if not months:
        return 1
    card = um.card(months, now)

    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    prev = next((i for i in usa["indicators"] if i["id"] == card["id"]), None)
    try:
        events = json.loads(EVENTS.read_text(encoding="utf-8"))["items"]
        feed = json.loads(FEED.read_text(encoding="utf-8"))["items"] if FEED.exists() else []
        # Refunding and buyback releases from the feed are marked too; a hand-written entry for the same
        # release (same URL) keeps its shorter Korean title.
        have = {e["url"] for e in events}
        events = sorted(events + [{"date": f["date"], "kind": f["kind"], "title": f["title"], "url": f["url"]}
                                  for f in feed if f["kind"] in ("refunding", "buyback") and f["url"] not in have],
                        key=lambda e: e["date"])
        card["toolkit_feed"] = feed[:15]
        since = min([e["date"] for e in events] + [months[-1]["date"]])
        since = f"{int(since[:4]) - 1}{since[4:]}"                   # a year of context before the first action
        card["toolkit"] = toolkit(ups.fetch_fred("DGS30"), events, since)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED toolkit: {exc}", file=sys.stderr)
        failed += 1
        if prev and prev.get("toolkit"):
            card["toolkit"] = prev["toolkit"]
    if prev and {**prev, "retrieved_at": None} == {**card, "retrieved_at": None}:
        card["retrieved_at"] = prev.get("retrieved_at")
    ua.upsert(usa, card)
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"{card['id']}: {card['display']} ({card['reference_period']}), bills {months[-1]['bills_share_pct']:.1f}%")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

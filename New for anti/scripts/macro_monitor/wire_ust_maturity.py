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
STATEMENTS = ROOT / "config" / "ust_refunding_statements_v1.json"
QRA = ROOT.parent.parent / "public" / "data" / "qra_engine_v1.json"


def outlook(months: list[dict]) -> dict | None:
    """Bills share and WAM for the next quarters from Treasury's estimates and auction sizes, plus the same
    method run from the start of the last finished quarter against what actually happened."""
    from macro_monitor import ust_projection as pj
    st = json.loads(STATEMENTS.read_text(encoding="utf-8"))["items"] if STATEMENTS.exists() else []
    if not st or not QRA.exists():
        return None
    quarters = pj.quarter_estimates(json.loads(QRA.read_text(encoding="utf-8"))["events"])
    by = {m["date"][:7]: m for m in months}
    base = months[-1]["date"]

    def rows_for(month_end: str) -> list[dict]:
        return [r for r in um.fetch_rows(um.prev_month_end(month_end)) if r["record_date"] == month_end]

    latest = st[-1]
    path = pj.project(rows_for(base), base, quarters, pj.parse_auction_table(latest["text"]),
                      pj.parse_tips(latest["text"], latest["date"]), 6)
    # Backtest: the last quarter with an actual, from its first month-end before, with the statement of that quarter.
    done = sorted(k for k, v in quarters.items() if "actual" in v)
    check = None
    if done:
        q0 = done[-1]
        b0 = um.prev_month_end(f"{q0}-01")
        stq = next((x for x in st if x["date"][:7] >= q0), None)
        if stq and b0[:7] in by:
            bt = pj.project(rows_for(b0), b0, {q0: {"estimate": quarters[q0]["estimate"]}},
                            pj.parse_auction_table(stq["text"]), pj.parse_tips(stq["text"], stq["date"]), 3)
            errs = [(p["month"], round(p["bills_share_pct"] - by[p["month"]]["bills_share_pct"], 2),
                     round(p["wam_months"] - by[p["month"]]["wam_months"], 2)) for p in bt if p["month"] in by]
            if errs:
                check = {"quarter": q0, "base": b0, "statement": stq["url"], "errors": errs,
                         "bills_pp_mean": round(sum(e[1] for e in errs) / len(errs), 2),
                         "wam_m_mean_abs": round(sum(abs(e[2]) for e in errs) / len(errs), 2)}
    return {"base": base, "path": path, "statement": latest["url"], "backtest": check}


def refunding_diff(feed: list[dict]) -> dict | None:
    """Store each refunding policy statement the feed has seen (text fetched once) and compare the last two."""
    from macro_monitor import ust_refunding_diff as rd
    from macro_monitor import ust_toolkit_feed as tf
    doc = json.loads(STATEMENTS.read_text(encoding="utf-8")) if STATEMENTS.exists() else {"schema": "ust_refunding_statements_v1", "items": []}
    have = {x["url"] for x in doc["items"]}
    added = False
    for f in feed:
        if f["kind"] == "refunding" and "refunding statement" in f["title"].lower() and f["url"] not in have \
                and "home.treasury.gov" in f["url"]:
            text = rd.statement_text(tf._curl(f["url"]))
            if len(text) > 500:
                doc["items"].append({"date": f["date"], "url": f["url"], "title": f["title"], "text": text})
                added = True
    doc["items"].sort(key=lambda x: x["date"])
    if added:
        STATEMENTS.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if len(doc["items"]) < 2:
        return None
    return rd.compare(doc["items"][-2], doc["items"][-1])


def toolkit(dgs30: list[tuple[str, float]], events: list[dict], since: str,
            tp: list[tuple[str, float]] | None = None) -> dict:
    """The 30-year yield from `since`, and its change 1, 5 and 20 trading days after each action. With `tp`
    (10-year term premium, %), the term premium on the same dates and its change 5 and 20 days after."""
    pts = [(d, v) for d, v in dgs30 if d >= since]
    dates = [d for d, _ in pts]
    tpd = dict(tp or [])
    out = []
    for e in events:
        i = next((k for k, d in enumerate(dates) if d >= e["date"]), None)
        if i is None:
            continue
        base = pts[i - 1][1] if i > 0 else pts[i][1]       # the close before the action
        chg = {f"d{n}_bp": (round((pts[i + n - 1][1] - base) * 100) if i + n - 1 < len(pts) else None) for n in (1, 5, 20)}
        if tpd:
            t0 = tpd.get(dates[i - 1] if i > 0 else dates[i])
            for n in (5, 20):
                j = i + n - 1
                t1 = tpd.get(dates[j]) if j < len(dates) else None
                chg[f"tp_d{n}_bp"] = round((t1 - t0) * 100) if t0 is not None and t1 is not None else None
        out.append({**e, "on": dates[i], "before_pct": base, **chg})
    res = {"series": {"dates": dates, "values": [v for _, v in pts]}, "events": out,
           "label_ko": "미국 30년 국채금리(%)", "source": "FRED DGS30"}
    if tpd:
        res["term_premium"] = {"values": [tpd.get(d) for d in dates], "label_ko": "10년 기간 프리미엄(%)",
                               "source": "FRED THREEFYTP10 (연준 이사회 Kim-Wright 모형)"}
    return res


def duration_inputs():
    """FRED par-curve series, a SOMA lookup (latest Wednesday on or before a month end), buybacks by month."""
    curves = {sid: ups.fetch_fred(sid) for sid in um.CURVE_IDS}
    bought = um.fetch_buyback_details()
    dates = um.soma_dates()

    def soma_for(month_end: str):
        asof = max((d for d in dates if d <= month_end), default=None)
        return (asof, um.fetch_soma(asof)) if asof else None
    return curves, soma_for, bought


def main() -> int:
    now, failed = ups.now_iso(), 0
    rebuild = "--rebuild" in sys.argv
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"schema": "ust_mspd_wam_v1", "months": []}
    months = [] if rebuild else cache["months"]
    try:
        rows = um.fetch_rows(months[-1]["date"] if months else None)
        try:
            curves, soma_for, bought = duration_inputs() if rows else (None, None, None)
        except Exception as exc:  # noqa: BLE001 -- WAM still goes in; duration waits for the next run
            print(f"FAILED duration inputs: {exc}", file=sys.stderr)
            curves, soma_for, bought = None, None, None
            failed += 1
        new = um.monthly(rows, curves, soma_for, bought)
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
        try:
            um.add_buyers_panel(card, months, um.fetch_bill_buyers())
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED bill buyers: {exc}", file=sys.stderr)
            failed += 1
            old_p = next((x for x in (prev or {}).get("panels", []) if x["id"] == "bill_buyers"), None)
            if old_p:
                card["panels"].append(old_p)
        try:
            ol = outlook(months)
            if ol and ol["path"]:
                um.add_outlook_panels(card, months, ol)
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED outlook: {exc}", file=sys.stderr)
            failed += 1
        try:
            rdiff = refunding_diff(feed)
            if rdiff:
                card["refunding_diff"] = rdiff
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED refunding diff: {exc}", file=sys.stderr)
            failed += 1
            if prev and prev.get("refunding_diff"):
                card["refunding_diff"] = prev["refunding_diff"]
        since = min([e["date"] for e in events] + [months[-1]["date"]])
        since = f"{int(since[:4]) - 1}{since[4:]}"                   # a year of context before the first action
        try:
            tp = ups.fetch_fred("THREEFYTP10")
        except Exception as exc:  # noqa: BLE001 -- the yield panel goes out without it
            print(f"FAILED term premium: {exc}", file=sys.stderr)
            tp, failed = None, failed + 1
        card["toolkit"] = toolkit(ups.fetch_fred("DGS30"), events, since, tp)
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

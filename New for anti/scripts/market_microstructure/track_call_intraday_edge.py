#!/usr/bin/env python3
"""Prospective tracker: foreign KOSPI200 call flow -> next session KOSPI open-to-close.

Claude, 2026-11-08, at the user's request ("Track it"). The thesis is a small,
casino-style edge (about 52%), not big predictive power. Retrospective search
(2019-2026, about 65 signal/outcome/ticker tests) found this one borderline
candidate: KOSPI +4.9bp/day, NW t 1.94, hit 52.1%. Because it was picked from
many tests, only results AFTER the rule was frozen count. This script records
them; it never refits, retunes or reselects anything.

The rule is fixed in RULE below and its sha256 is checked on every run. Any
change needs a new rule id and a new ledger, never an edit of this one.

Ledger: data/manifests/edge_tracking/call_intraday_v1.json
  rows[target_date] are written once (position fields) and completed once
  (outcome fields). Existing values are never overwritten; if a later source
  revision would change a recorded signal, it is logged in `revisions` instead.

Run from the repository root:
  python "New for anti/scripts/market_microstructure/track_call_intraday_edge.py"
"""
import argparse
import ast
import hashlib
import json
import math
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOARD = ROOT / "New for anti/public/data/derivatives_board_v1.json"
LEDGER = ROOT / "data/manifests/edge_tracking/call_intraday_v1.json"

RULE = {
    "id": "call_intraday_v1",
    "registered": "2026-11-08",
    "signal": "KRX 15007 KOSPI200 call options, foreign net_krw / market_total buy_krw, on KR session d",
    "reference": "median of the same ratio over the 60 observed sessions before d (d excluded); at least 40 required",
    "position": "+1 if signal > reference, -1 if signal < reference, 0 if equal; applied to the next KRX session t after d",
    "outcome_primary": "KOSPI index open-to-close return on t (Naver daily chart)",
    "outcome_secondary": "005930 open-to-close return on t (report only, not a decision input)",
    "first_target": "2026-11-09",
    "cost_reference_bp": 2.0,
    "decision": ("No decision before 250 scored primary targets. At 250: the edge is supported if the mean primary "
                 "pnl is at least the 2bp cost reference AND Newey-West(5) t >= 2.0 on gross pnl. Otherwise it is "
                 "not supported. Interim numbers are progress only."),
    "retrospective_reference": {"period": "2019-04..2026-11", "mean_bp": 4.9, "nw_t": 1.94, "hit": 0.521,
                                "note": "selected from about 65 tests; not evidence on its own"},
}
RULE_SHA = hashlib.sha256(json.dumps(RULE, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
TICKERS = {"KOSPI": "primary", "005930": "secondary"}
NAVER = ("https://m.stock.naver.com/front-api/external/chart/domestic/info?symbol={s}"
         "&requestType=1&startTime={a}&endTime={b}&timeframe=day")


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def call_series(board):
    rows = board["kr"]["investor_nets"]["detailed_15007"]["products"]["options_call"]["series"]
    out = {}
    for r in rows:
        try:
            if r.get("quality") != "observed":
                continue
            buy = r["market_total"]["buy_krw"]
            if not buy or buy <= 0:
                continue
            out[r["date"]] = r["foreign"]["net_krw"] / buy
        except (KeyError, TypeError):
            continue
    return dict(sorted(out.items()))


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def fetch_bars(symbol, start, end, get=None):
    get = get or (lambda u: urllib.request.urlopen(
        urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode())
    text = get(NAVER.format(s=symbol, a=start.replace("-", ""), b=end.replace("-", "")))
    rows = ast.literal_eval(text.strip())[1:]
    return {f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:]}": {"open": float(r[1]), "close": float(r[4])} for r in rows}


def next_session(day, is_session):
    d = date.fromisoformat(day)
    for _ in range(21):
        d += timedelta(days=1)
        if is_session(d.isoformat()):
            return d.isoformat()
    return None


def nw_t(x, lags=5):
    n = len(x)
    if n < lags + 2:
        return None
    m = sum(x) / n
    d = [v - m for v in x]
    var = sum(v * v for v in d) / n
    for l in range(1, lags + 1):
        var += 2 * (1 - l / (lags + 1)) * sum(d[i] * d[i - l] for i in range(l, n)) / n
    return m / math.sqrt(var / n) if var > 0 else None


def summarize(rows, key):
    pnl = [r[key]["pnl_bp"] for r in rows if r.get(key) and r["position"] != 0]
    if not pnl:
        return {"n": 0}
    return {"n": len(pnl), "mean_bp": round(sum(pnl) / len(pnl), 2),
            "hit": round(sum(p > 0 for p in pnl) / len(pnl), 4),
            "nw_t": None if nw_t(pnl) is None else round(nw_t(pnl), 3),
            "mean_net_of_cost_bp": round(sum(pnl) / len(pnl) - RULE["cost_reference_bp"], 2)}


def update(ledger, board, bars, is_session, stamp):
    if ledger.get("rule_sha256", RULE_SHA) != RULE_SHA:
        raise SystemExit("rule changed: register a new rule id and ledger instead of editing call_intraday_v1")
    ledger.update(rule=RULE, rule_sha256=RULE_SHA)
    rows = ledger.setdefault("rows", {})
    revisions = ledger.setdefault("revisions", [])
    series = call_series(board)
    days = list(series)
    for i, d in enumerate(days):
        t = next_session(d, is_session)
        if t is None or t < RULE["first_target"]:
            continue
        history = [series[x] for x in days[max(0, i - 60):i]]
        if len(history) < 40:
            continue
        sig, ref = series[d], median(history)
        pos = (sig > ref) - (sig < ref)
        if t in rows:
            if rows[t]["signal_date"] == d and abs(rows[t]["signal"] - sig) > 1e-12:
                revisions.append({"target_date": t, "seen_at": stamp, "recorded_signal": rows[t]["signal"],
                                  "source_now": sig, "kept": "recorded"})
            continue
        rows[t] = {"target_date": t, "signal_date": d, "signal": sig, "reference_median": ref,
                   "position": pos, "recorded_at": stamp}
    for t, r in rows.items():
        for sym, role in TICKERS.items():
            if role in r or t not in bars.get(sym, {}):
                continue
            b = bars[sym][t]
            ret = b["close"] / b["open"] - 1
            r[role] = {"symbol": sym, "open": b["open"], "close": b["close"], "open_to_close": ret,
                       "pnl_bp": r["position"] * ret * 1e4, "scored_at": stamp}
        if "primary" in r and "recorded_after_outcome" not in r:
            # Mechanical rule, so late recording cannot bias it, but it is disclosed.
            r["recorded_after_outcome"] = r["recorded_at"] > r["primary"]["scored_at"]
    ordered = [rows[k] for k in sorted(rows)]
    ledger["rows"] = {r["target_date"]: r for r in ordered}
    ledger["summary"] = {"primary": summarize(ordered, "primary"), "secondary": summarize(ordered, "secondary"),
                         "pending_outcome": [r["target_date"] for r in ordered if "primary" not in r],
                         "decision_at_n": 250, "updated_at": stamp}
    return ledger


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--board", type=Path, default=BOARD)
    p.add_argument("--ledger", type=Path, default=LEDGER)
    args = p.parse_args()
    board = json.loads(args.board.read_text())
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else {
        "schema_version": "edge-tracking-v1", "created_at": now_utc()}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bars = {s: fetch_bars(s, "2026-08-01", today) for s in TICKERS}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from option_direction_model import calendar
    from research_direction_diagnostics import ReviewedCalendar
    cal = ReviewedCalendar(calendar())
    update(ledger, board, bars, cal.is_session, now_utc())
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")
    s = ledger["summary"]
    print(json.dumps({"rule_sha256": RULE_SHA[:12], "rows": len(ledger["rows"]), "primary": s["primary"],
                      "secondary": s["secondary"], "pending": s["pending_outcome"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Fed policy path implied by 30-day fed funds futures (CBOT ZQ), meeting by meeting.

The same arithmetic CME FedWatch publishes (its numbers are licensed; the futures prices are not):
  * a contract settles at 100 - the month's average effective fed funds rate, so each month's price
    gives the market's expected average rate for that month;
  * in a month with an FOMC decision on day d of N, the average is (d * pre + (N - d) * post) / N, where
    pre is the rate going in and post the rate after the decision (effective the next day);
  * pre comes from the month before when that month has no meeting (its average is the rate), else from
    the previous meeting's post; post comes from the month after when that month has no meeting, else
    from the formula above -- the formula is noisy for a decision late in the month, the next month's
    contract is not.
The expected change at a meeting splits into the two 25bp steps around it (a +15bp expectation reads as
60% for +25bp, 40% for no change). Cumulative odds across meetings use the total change from today the
same way: a simplification of FedWatch's full probability tree, stated in the card.

Prices come from Yahoo Finance through the dashboard Worker (ZQ<month code><yy>.CBT).
"""

from __future__ import annotations

import calendar
import json
import math
import subprocess
from datetime import date, datetime, timezone
from typing import Any

MONTH_CODE = "FGHJKMNQUVXZ"
WORKER_YF = ("https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/macro?source=yfinance"
             "&symbol={sym}&interval=1d&range=2y")
USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
STEP = 0.25


def symbol(ym: str) -> str:
    return f"ZQ{MONTH_CODE[int(ym[5:7]) - 1]}{ym[2:4]}.CBT"


def add_months(ym: str, n: int) -> str:
    t = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def fetch_contract(ym: str, timeout: int = 40) -> list[tuple[str, float]]:
    """Daily closes of the contract for month `ym`, oldest first. curl: the Worker refuses urllib."""
    proc = subprocess.run(["curl", "-sS", "-L", "-m", str(timeout), "-A", USER_AGENT, WORKER_YF.format(sym=symbol(ym))],
                          check=False, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"{symbol(ym)}: curl rc={proc.returncode}")
    return parse_chart(json.loads(proc.stdout.decode("utf-8")))


def parse_chart(doc: Any) -> list[tuple[str, float]]:
    res = ((doc or {}).get("chart") or {}).get("result") or []
    if not res:
        raise ValueError("no chart")
    r = res[0]
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = {}
    for ts, c in zip(r.get("timestamp") or [], closes):
        if c is not None:
            out[datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()] = float(c)
    return sorted(out.items())


def path(rates: dict[str, float], meetings: list[str], today: str, effr: float) -> list[dict[str, Any]]:
    """rates: YYYY-MM -> implied average rate (100 - price). meetings: decision dates (YYYY-MM-DD) after
    `today`. One row per meeting the contracts reach: pre, post, change and the move odds."""
    meet = {m[:7]: m for m in meetings if m > today}
    cur = today[:7]
    rows: list[dict[str, Any]] = []
    prev_post: float | None = None
    for ym in sorted(meet):
        if ym not in rates:
            break
        d = int(meet[ym][8:10])
        n = calendar.monthrange(int(ym[:4]), int(ym[5:7]))[1]
        before = add_months(ym, -1)
        if prev_post is not None and before in meet:
            pre = prev_post
        elif ym == cur:
            pre = effr
        elif before in rates and before not in meet:
            pre = rates[before]
        else:
            pre = prev_post if prev_post is not None else effr
        after = add_months(ym, 1)
        if after in rates and after not in meet:
            post = rates[after]
        else:
            post = (rates[ym] - pre * d / n) / ((n - d) / n)
        rows.append({"date": meet[ym], "pre": round(pre, 4), "post": round(post, 4),
                     "change_bp": round((post - pre) * 100, 1)})
        prev_post = post
    return rows


def split(change: float) -> dict[float, float]:
    """An expected change (percentage points) as odds on the two 25bp steps around it."""
    lo = math.floor(change / STEP + 1e-9)
    frac = change / STEP - lo
    out = {round(lo * STEP, 2): round(1 - frac, 4)}
    if frac > 1e-6:
        out[round((lo + 1) * STEP, 2)] = round(frac, 4)
    return out


def range_label(lower: float) -> str:
    return f"{lower:.2f}–{lower + STEP:.2f}%"


def enrich(rows: list[dict[str, Any]], start: float, lower_now: float) -> list[dict[str, Any]]:
    """Move odds at each meeting and the most likely target range after it (from the total change)."""
    for r in rows:
        r["move_odds"] = {f"{int(round(k * 100)):+d}": v for k, v in split(r["post"] - r["pre"]).items()}
        tot = split(r["post"] - start)
        r["cum_bp"] = round((r["post"] - start) * 100, 1)
        r["range_odds"] = [{"range": range_label(lower_now + k), "p": v}
                           for k, v in sorted(tot.items(), key=lambda kv: -kv[1])]
    return rows


def headline(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """('인상 63%', '12/9 FOMC 인상 63% · 동결 37%') for the next meeting."""
    r = rows[0]
    md = f"{int(r['date'][5:7])}/{int(r['date'][8:10])}"
    odds = sorted(r["move_odds"].items(), key=lambda kv: -kv[1])
    name = {"+0": "동결", "+25": "인상", "-25": "인하", "+50": "50bp 인상", "-50": "50bp 인하"}
    word = lambda k: name.get(k, f"{k}bp")  # noqa: E731
    top = odds[0]
    chip = f"{word(top[0])} {top[1] * 100:.0f}%"
    full = f"{md} FOMC " + " · ".join(f"{word(k)} {v * 100:.0f}%" for k, v in odds)
    return chip, full


def today_iso() -> str:
    return date.today().isoformat()

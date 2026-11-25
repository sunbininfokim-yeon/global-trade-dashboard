"""Where the bills share and the WAM go over the next two quarters, from Treasury's own numbers.

  * net borrowing per calendar quarter: Treasury's privately-held net marketable borrowing estimates
    (the Monday of each refunding, qra_engine_v1.json);
  * gross coupon issuance per month: the auction-size table in the refunding statement (the quarter just
    done and the one ahead; months beyond repeat the last quarter's pattern -- Treasury's guidance is to
    hold sizes), TIPS from the statement's TIPS paragraph;
  * coupon maturities per month: the Monthly Statement of the Public Debt, security by security;
  * bills take the rest: bills net = net borrowing - (coupon gross - coupon maturities).

Then the stock is stepped forward a month at a time: securities age, matured coupons leave, new coupons
enter at their tenor, the bill stock changes by its net and keeps its average remaining maturity.

Simplifications, stated on the card: net borrowing is spread evenly over the quarter's months; the Fed's
own bill purchases at auction (SOMA add-ons) are not added; TIPS are at par without inflation accrual.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

TENOR_YEARS = {"2-Year": 2, "3-Year": 3, "5-Year": 5, "7-Year": 7, "10-Year": 10, "20-Year": 20, "30-Year": 30, "FRN": 2}
MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
MONTH_NAMES = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                                "September", "October", "November", "December"])}
QUARTER = re.compile(r"(January|April|July|October)\s*[–-]\s*(March|June|September|December)\s+(20\d\d)")


def parse_auction_table(text: str) -> dict[str, dict[str, float]]:
    """{'YYYY-MM': {'2-Year': 69, ..., 'FRN': 28}} from '2-Year 3-Year ... FRN May-26 69 58 70 44 42 16 25 28 ...'."""
    m = re.search(r"2-Year 3-Year 5-Year 7-Year 10-Year 20-Year 30-Year FRN((?: [A-Z][a-z]{2}-\d{2}(?: \d+(?:\.\d+)?){8})+)", text)
    if not m:
        return {}
    cols = list(TENOR_YEARS)
    out = {}
    for mon, yy, vals in re.findall(r"([A-Z][a-z]{2})-(\d{2})((?: \d+(?:\.\d+)?){8})", m.group(1)):
        out[f"20{yy}-{MONTHS[mon]:02d}"] = dict(zip(cols, map(float, vals.split())))
    return out


def parse_tips(text: str, statement_date: str) -> dict[str, tuple[float, float]]:
    """{'YYYY-MM': (tenor years, size bn)} from 'the November 10-year TIPS reopening auction size at $19 billion'."""
    out = {}
    y0, m0 = int(statement_date[:4]), int(statement_date[5:7])
    for mon, ten, size in re.findall(r"the (\w+) (\d+)-year TIPS[^$]*?\$(\d+(?:\.\d+)?) billion", text):
        if mon not in MONTH_NAMES:
            continue
        mm = MONTH_NAMES[mon]
        yy = y0 + (1 if mm < m0 - 2 else 0)            # 'January' in a November statement is next year
        out[f"{yy}-{mm:02d}"] = (float(ten), float(size))
    return out


def quarter_estimates(events: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """{'2026-10': {'estimate': 618, 'actual': None}, ...} keyed by the quarter's first month; the newest
    refunding's estimate wins, an actual from any later refunding is attached."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for e in sorted(events, key=lambda e: e["id"]):
        for q in (e.get("estimates") or {}).get("quarters", []):
            m = QUARTER.search(q.get("period") or "")
            if not m or q.get("net_borrowing_bn") is None:
                continue
            key = f"{m.group(3)}-{MONTH_NAMES[m.group(1)]:02d}"
            out[key][q["kind"]] = float(q["net_borrowing_bn"])
    return dict(out)


def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + n
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def issuance_for(month: str, table: dict[str, dict[str, float]], tips: dict[str, tuple[float, float]]) -> tuple[list, str]:
    """[(tenor years, size bn)] for a month, and where it came from ('table' / 'repeat')."""
    src = "table"
    row = table.get(month)
    k = 3
    while row is None and k <= 12:                 # hold sizes: the same month of the last quarter in the table
        row, src = table.get(_add_months(month, -k)), "repeat"
        k += 3
    out = [(TENOR_YEARS[t], v) for t, v in (row or {}).items()]
    t = tips.get(month)
    k = 3
    while t is None and k <= 12:
        t = tips.get(_add_months(month, -k))
        k += 3
    if t:
        out.append(t)
    return out, src


def project(rows: list[dict[str, Any]], base: str, quarters: dict[str, dict[str, float]],
            table: dict[str, dict[str, float]], tips: dict[str, tuple[float, float]], months: int = 6) -> list[dict[str, Any]]:
    """Step the base month's stock forward. rows: that month's MSPD Table III rows."""
    from .ust_maturity import CLASS, _num
    b0 = date.fromisoformat(base)
    coupons: list[list[float]] = []                 # [amount, years to maturity]
    bills_amt = bills_w = 0.0
    for r in rows:
        cls = CLASS.get(r.get("security_class1_desc"))
        amt = _num(r.get("outstanding_amt"))
        if cls is None or amt is None or r.get("maturity_date") in (None, "null"):
            continue
        yrs = (date.fromisoformat(r["maturity_date"]) - b0).days / 365.25
        if yrs <= 0:
            continue
        amt /= 1000.0
        if cls == "bills":
            bills_amt += amt
            bills_w += amt * yrs
        else:
            coupons.append([amt, yrs])
    bills_wam = bills_w / bills_amt                 # kept constant: bills roll into the same mix
    out = []
    ym = base[:7]
    for k in range(1, months + 1):
        ym = _add_months(ym, 1)
        q = f"{ym[:4]}-{((int(ym[5:7]) - 1) // 3) * 3 + 1:02d}"
        nb = (quarters.get(q) or {}).get("estimate")
        if nb is None:
            break
        dt = 1 / 12
        matured = sum(a for a, y in coupons if y <= dt)
        coupons = [[a, y - dt] for a, y in coupons if y > dt]
        issues, src = issuance_for(ym, table, tips)
        gross = sum(s for _, s in issues)
        coupons += [[s, t] for t, s in issues]
        bills_net = nb / 3 - (gross - matured)
        bills_amt += bills_net
        total = bills_amt + sum(a for a, _ in coupons)
        wam = (bills_amt * bills_wam + sum(a * y for a, y in coupons)) / total * 12
        out.append({"month": ym, "net_borrowing_bn": round(nb / 3, 1), "coupon_gross_bn": round(gross, 1),
                    "coupon_maturing_bn": round(matured, 1), "bills_net_bn": round(bills_net, 1),
                    "bills_share_pct": round(bills_amt / total * 100, 2), "wam_months": round(wam, 2),
                    "total_bn": round(total, 1), "sizes": src})
    return out

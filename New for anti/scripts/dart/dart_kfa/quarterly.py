"""Quarter-end series for the calculator's card detail box: EV and its parts.

Every point is a balance-sheet date for which a filing exists, so nothing is
interpolated:

    FY-1 end (FY report, 전기)  ->  FY Q1, H1, Q3  ->  FY end  ->  FY+1 Q1, H1, Q3

Balances come from that date's report; flows are LTM (FY + current YTD − prior
YTD from the same report, or the full year at a year end). Debt uses the
engine's own reported-basis ids (pe_cr_inputs.json: borrowings, bonds, leases)
so the quarterly 순차입금 is the same definition as the net_debt_reported card.

Market cap at a quarter end = that month's closing price × the share count
supplied by the caller (the latest one: buy-backs and issues in between are
not replayed, and the series says so).
"""
from __future__ import annotations

from .investor_metrics import _num, _pick, _spec

BS_KEYS = ("cash", "equity", "parent_equity", "current_assets", "current_liabilities", "liabilities",
           "borrowings_short", "borrowings_current_portion", "bonds_current", "debt_current_total",
           "borrowings_long", "bonds_noncurrent", "lease_current", "lease_noncurrent")
FLOW_KEYS = ("revenue", "op")


def _vals(rows, keys, field):
    spec = _spec()
    out = {}
    for k in keys:
        sj, ids, names = spec[k]
        row, _ = _pick(rows or [], sj, ids, names)
        if row:
            v = _num(row.get(field))
            if v is not None:
                out[k] = v
    return out


def _debt(b):
    current = b.get("debt_current_total")
    if current is None:
        parts = [b.get(k) for k in ("borrowings_short", "borrowings_current_portion", "bonds_current")]
        current = sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None
    rest = [b.get(k) for k in ("borrowings_long", "bonds_noncurrent")]
    lease = [b.get(k) for k in ("lease_current", "lease_noncurrent")]
    if current is None and all(r is None for r in rest):
        return None, None, None
    borrow = (current or 0) + sum(r for r in rest if r is not None)
    lease_total = sum(x for x in lease if x is not None) if any(x is not None for x in lease) else None
    short = current
    return borrow + (lease_total or 0), lease_total, short


def dart_points(fy: int, fy_rows: list, prior_fy_rows: list | None, quarters: dict, next_quarters: dict) -> list[dict]:
    """fy_rows: FY report rows; quarters / next_quarters: {'Q1'|'H1'|'Q3': rows} of FY and FY+1."""
    ends = {"Q1": "03-31", "H1": "06-30", "Q3": "09-30"}
    annual_now = _vals(fy_rows, FLOW_KEYS, "thstrm_amount")
    annual_prev = _vals(fy_rows, FLOW_KEYS, "frmtrm_amount")
    pts = []

    def add(period_end, report, bal, ltm):
        if bal:
            pts.append({"period_end": period_end, "report": report, "balances": bal, "ltm": ltm})

    add(f"{fy - 1}-12-31", "FY-1", _vals(fy_rows, BS_KEYS, "frmtrm_amount"), annual_prev)
    for year, qs, base in ((fy, quarters, annual_prev), (fy + 1, next_quarters, annual_now)):
        for bucket in ("Q1", "H1", "Q3"):
            rows = qs.get(bucket)
            if not rows:
                continue
            ytd = _vals(rows, FLOW_KEYS, "thstrm_add_amount") or _vals(rows, FLOW_KEYS, "thstrm_amount")
            prior = _vals(rows, FLOW_KEYS, "frmtrm_add_amount") or _vals(rows, FLOW_KEYS, "frmtrm_q_amount")
            ltm = {k: base[k] + ytd[k] - prior[k] for k in FLOW_KEYS if None not in (base.get(k), ytd.get(k), prior.get(k))}
            add(f"{year}-{ends[bucket]}", f"{bucket} {year}", _vals(rows, BS_KEYS, "thstrm_amount"), ltm)
        if year == fy:
            add(f"{fy}-12-31", f"FY {fy}", _vals(fy_rows, BS_KEYS, "thstrm_amount"), annual_now)
    return pts


def series(points: list[dict], *, closes: dict | None = None, shares: float | None = None,
           pref_closes: dict | None = None, pref_shares: float | None = None) -> dict:
    """points -> per-quarter metrics. closes: {'YYYYMM': close}."""
    out = []
    for p in sorted(points, key=lambda x: x["period_end"]):
        b, ltm = p["balances"], p.get("ltm") or {}
        gross, lease, short = _debt(b)
        cash = b.get("cash")
        net_debt = gross - cash if gross is not None and cash is not None else None
        nci = b["equity"] - b["parent_equity"] if b.get("equity") is not None and b.get("parent_equity") is not None else None
        ym = p["period_end"][:4] + p["period_end"][5:7]
        cap = common_cap = pref_cap = None
        if closes and shares and closes.get(ym):
            common_cap = closes[ym] * shares
            if pref_closes and pref_shares and pref_closes.get(ym):
                pref_cap = pref_closes[ym] * pref_shares
            cap = common_cap + (pref_cap or 0)
        ev = cap + net_debt + (nci or 0) if cap is not None and net_debt is not None else None
        op = ltm.get("op")
        row = {
            "period_end": p["period_end"], "report": p["report"],
            "market_cap": cap, "common_cap": common_cap, "preferred_cap": pref_cap, "price": (closes or {}).get(ym), "net_debt": net_debt, "gross_debt": gross,
            "lease": lease, "short_term_debt": short, "cash": cash, "nci": nci, "ev": ev,
            "revenue_ltm": ltm.get("revenue"), "op_ltm": op,
            "ev_to_ebit": ev / op if ev is not None and op and op > 0 else None,
            "current_ratio": b["current_assets"] / b["current_liabilities"]
            if b.get("current_assets") is not None and b.get("current_liabilities") else None,
            "debt_ratio": b["liabilities"] / b["equity"] if b.get("liabilities") is not None and b.get("equity") else None,
        }
        out.append(row)
    return {"points": out,
            "basis": "분기말 재무상태표(해당 분기·반기보고서) + LTM 손익(FY + 당기 누적 − 전기 동기 누적). "
                     "시가총액은 해당 월말 종가 × 현재 상장주식수(그 사이 자사주 소각·증자는 반영하지 않음)."}


def parse_fchart(xml: str) -> dict:
    """Naver fchart monthly XML -> {'YYYYMM': close}."""
    import re
    return {m.group(1)[:6]: float(m.group(2)) for m in re.finditer(r'data="(\d{8})\|[^|]*\|[^|]*\|[^|]*\|([\d.]+)\|', xml)}

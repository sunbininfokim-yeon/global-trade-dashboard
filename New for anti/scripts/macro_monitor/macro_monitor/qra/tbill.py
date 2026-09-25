"""T-bill auction sizes for the QRA maturity tab, from Fiscal Data.

The TBAC financing table only recommends *coupon* auction sizes, so the
maturity tab had no bill row at all. Bill sizes are announced week by week
and published by Fiscal Data (`auctions_query`, offering_amt is the announced
size, total_accepted appears once the auction has settled).

What this deliberately does not do:

* No quarter total that pretends to be complete. Auctions are announced about a
  week ahead, so a quarter that is still running only has the auctions
  announced so far; the block says which date it runs through and how many of
  its auctions already have results.
* No net figure. Bill auctions are mostly the rollover of bills that mature the
  same week, so the gross size is not borrowing. The only net-ish number shown
  is the change in bills outstanding between two month-ends (MSPD table 1),
  labelled as such.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from .fiscaldata import BASE, _get

_MONTHS = {
    m: i for i, m in enumerate(
        ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
         "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"], start=1)
}
_QUARTER_LABEL = re.compile(r"([A-Z]+)\s+(\d{4})\s*-\s*([A-Z]+)\s+(\d{4})")
_TERM_WEEKS = re.compile(r"^(\d+)-Week$", re.I)


def quarter_window(label: str) -> Optional[Dict[str, str]]:
    """'AUGUST 2026-OCTOBER 2026 QUARTER' -> {'start': '2026-08-01', 'end': '2026-10-31'}.

    None when the label does not read that way; the caller reports it instead
    of guessing a window.
    """
    m = _QUARTER_LABEL.search((label or "").upper())
    if not m or m.group(1) not in _MONTHS or m.group(3) not in _MONTHS:
        return None
    sy, sm, ey, em = int(m.group(2)), _MONTHS[m.group(1)], int(m.group(4)), _MONTHS[m.group(3)]
    start = date(sy, sm, 1)
    end = date(ey + (em == 12), em % 12 + 1, 1)  # first day of the following month
    return {"start": start.isoformat(), "end": date.fromordinal(end.toordinal() - 1).isoformat()}


def _get_retry(url: str, tries: int = 3) -> dict:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            return _get(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Fiscal Data request failed after {tries} tries: {last}")


def fetch_bill_auctions(start: str, end: str) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({
        "filter": f"security_type:eq:Bill,auction_date:gte:{start},auction_date:lte:{end}",
        "sort": "auction_date",
        "page[size]": "500",
        "fields": "auction_date,issue_date,security_term,offering_amt,total_accepted,"
                  "cash_management_bill_cmb,announcemt_date,reopening,cusip",
    })
    doc = _get_retry(f"{BASE}/v1/accounting/od/auctions_query?{q}")
    meta = doc.get("meta") or {}
    rows = doc.get("data") or []
    if meta.get("total-count") not in (None, len(rows)):
        raise RuntimeError(f"bill auctions truncated: {len(rows)} of {meta.get('total-count')}")
    return rows


def fetch_bills_outstanding(months: int = 3) -> List[Dict[str, Any]]:
    """Marketable bills outstanding at recent month-ends, $ billions (MSPD table 1)."""
    q = urllib.parse.urlencode({
        "filter": "security_type_desc:eq:Marketable,security_class_desc:eq:Bills",
        "sort": "-record_date",
        "page[size]": str(months),
        "fields": "record_date,total_mil_amt",
    })
    doc = _get_retry(f"{BASE}/v1/debt/mspd/mspd_table_1?{q}")
    out = []
    for row in doc.get("data") or []:
        try:
            out.append({"date": row["record_date"], "bn": round(float(row["total_mil_amt"]) / 1000.0, 1)})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _amount_bn(raw: Any) -> Optional[float]:
    if raw in (None, "", "null"):
        return None
    try:
        return float(raw) / 1e9
    except (TypeError, ValueError):
        return None


def _term_key(row: Dict[str, Any]) -> tuple[int, str, str]:
    """(sort order, id suffix, label) — 4-Week -> (4, '4w', '4W'); cash management bills pooled."""
    if str(row.get("cash_management_bill_cmb") or "").lower() == "yes":
        return 999, "cmb", "CMB"
    m = _TERM_WEEKS.match(str(row.get("security_term") or "").strip())
    if m:
        w = int(m.group(1))
        return w, f"{w}w", f"{w}W"
    term = str(row.get("security_term") or "?").strip()
    return 998, re.sub(r"\W+", "", term.lower()) or "other", term


def summarize(
    rows: List[Dict[str, Any]],
    *,
    quarter_label: str,
    window: Dict[str, str],
    outstanding: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    by_term: Dict[tuple, Dict[str, Any]] = {}
    sized = pending = no_size = 0
    last_auction = last_result = None
    for row in rows:
        size = _amount_bn(row.get("offering_amt"))
        if size is None:
            no_size += 1
            continue
        sized += 1
        key = _term_key(row)
        slot = by_term.setdefault(key, {"n": 0, "n_auctioned": 0, "offering_bn": 0.0})
        slot["n"] += 1
        slot["offering_bn"] += size
        auctioned = _amount_bn(row.get("total_accepted")) is not None
        if auctioned:
            slot["n_auctioned"] += 1
            last_result = max(last_result or row["auction_date"], row["auction_date"])
        else:
            pending += 1
        last_auction = max(last_auction or row["auction_date"], row["auction_date"])

    terms = [
        {
            "id": f"bill_{key[1]}",
            "label": key[2],
            "n": slot["n"],
            "n_auctioned": slot["n_auctioned"],
            "offering_bn": round(slot["offering_bn"], 1),
        }
        for key, slot in sorted(by_term.items())
    ]
    total = round(sum(t["offering_bn"] for t in terms), 1)
    complete = bool(sized) and date.fromisoformat(window["end"]) < today and pending == 0

    out: Optional[Dict[str, Any]] = None
    if outstanding:
        latest = outstanding[0]
        prev = outstanding[1] if len(outstanding) > 1 else None
        out = {
            "asof": latest["date"],
            "bills_bn": latest["bn"],
            "change_prev_month_bn": round(latest["bn"] - prev["bn"], 1) if prev else None,
            "prev_asof": prev["date"] if prev else None,
        }

    return {
        "schema_version": 1,
        "source": "fiscaldata.auctions_query (Bill) + mspd_table_1",
        "url": "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/",
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "quarter_label": quarter_label,
        "window": window,
        "basis": "offering_amt: announced auction size, gross of the bills that mature; not net borrowing",
        "complete": complete,
        "through_auction_date": last_auction,
        "through_result_date": last_result,
        "n_auctions": sized,
        "n_with_results": sized - pending,
        "n_announced_only": pending,
        "n_without_size": no_size,
        "total_offering_bn": total if sized else None,
        "by_term": terms,
        "outstanding": out,
        "reason_missing": None if sized else "no bill auctions found in the quarter window",
    }


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def _md(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day}"


def note_ko(block: Dict[str, Any]) -> str:
    if not block.get("n_auctions"):
        return "T-bill 경매 규모를 받지 못했습니다 (Fiscal Data에 해당 분기 경매가 없음)."
    start = block["window"]["start"]
    through = block["through_auction_date"]
    head = (
        f"T-bill 경매 규모 ($B) · 분기 {_md(start)}~{_md(block['window']['end'])} 중 "
        f"{_md(start)}~{_md(through)} 경매 {block['n_auctions']}회 합계 ${_fmt(block['total_offering_bn'])}B"
    )
    if block["complete"]:
        head += " (분기 전체)"
    else:
        head += (
            f". 분기가 아직 끝나지 않았고 경매는 약 1주 전에 공시되므로 분기 전체 합이 아닙니다 "
            f"(결과 확정 {block['n_with_results']}회, 나머지 {block['n_announced_only']}회는 공시된 규모)"
        )
    tail = ". 만기 도래한 T-bill의 차환이 대부분이라 순발행이 아니며 쿠폰과 척도가 달라 따로 표시합니다."
    out = block.get("outstanding")
    if out and out.get("bills_bn") is not None:
        tail += f" 참고: 시장성 T-bill 발행잔액 ${_fmt(out['bills_bn'])}B ({out['asof']}, MSPD)"
        chg = out.get("change_prev_month_bn")
        if chg is not None:
            tail += f", 전월말 대비 {'+' if chg >= 0 else '-'}${_fmt(abs(chg))}B"
        tail += "."
    return head + tail


BILL_NOTE_MARK = "T-bill은 포함하지 않습니다."
BILL_NOTE_REPLACED = "T-bill은 아래에 따로 표시합니다 (척도가 다름)."


def graft(by_id: Dict[str, Any], block: Dict[str, Any]) -> bool:
    """Put the bill rows into qra_issuance.components (and the TGA mirror).

    Idempotent: previous bill rows (kind == 'bill') are dropped first. Returns
    False without touching anything when the block has no sized auctions.
    """
    ind = by_id.get("qra_issuance")
    if not ind or not block.get("n_auctions"):
        return False

    def strip(rows: Any) -> List[Dict[str, Any]]:
        return [r for r in (rows or []) if r.get("kind") != "bill"]

    coupons = strip(ind.get("components"))
    bills = [
        {
            "id": t["id"],
            "kind": "bill",
            "label_ko": f"T-bill {t['label']}",
            "tenor": t["label"].lower(),
            "value": t["offering_bn"],
            "n_auctions": t["n"],
        }
        for t in block["by_term"]
    ]
    ind["components"] = coupons + bills
    ind["tbill"] = {
        "quarter_label": block["quarter_label"],
        "window": block["window"],
        "complete": block["complete"],
        "through_auction_date": block["through_auction_date"],
        "n_auctions": block["n_auctions"],
        "n_with_results": block["n_with_results"],
        "total_offering_bn": block["total_offering_bn"],
        "outstanding": block["outstanding"],
        "note_ko": note_ko(block),
        "source_url": block["url"],
        "retrieved_at": block["retrieved_at"],
    }
    if isinstance(ind.get("components_note_ko"), str):
        ind["components_note_ko"] = ind["components_note_ko"].replace(BILL_NOTE_MARK, BILL_NOTE_REPLACED)

    tga = by_id.get("tga")
    if tga is not None and "maturity_components" in tga:
        tga["maturity_components"] = strip(tga.get("maturity_components")) + bills
        tga["maturity_table"] = strip(tga.get("maturity_table")) + [
            {"kind": "bill", "label_ko": b["label_ko"], "tenor": b["tenor"], "value_bn": b["value"]}
            for b in bills
        ]
    return True

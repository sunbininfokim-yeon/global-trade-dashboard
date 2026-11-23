"""수주잔고 (order backlog) from the "매출 및 수주상황" section of a periodic report.

Korean filers in order-driven industries (조선, 건설, 기계, 방산, 플랜트) put a
backlog table in II. 사업의 내용 > 매출 및 수주상황 every quarter. The layout
varies, but the columns come from a short vocabulary:

    품목 | 수주일자 | 납기 | 수주총액 | 기납품액 | 수주잔고          (삼성중공업, 한화오션)
    품목 | ... | 기초계약잔액 | 신규계약액 | 기납품액 | 수주잔고      (HD한국조선해양)
    구분 | 주요 계약명 | 기초 | 증감 | 매출계상액 | 기말              (두산에너빌리티)

often with a 수량 / 금액 sub-header under each group. The parser maps each
group heading to opening / new / total / delivered / backlog, reads the
amounts of each row (taking every second number under a 수량·금액 header),
and checks the roll-forward: 기초 + 신규 − 매출 = 기말, or 수주총액 − 기납품
= 잔고, within 1 %. Tables that do not parse cleanly are reported as such;
nothing is inferred from text.

The XBRL `TransactionPriceAllocatedToRemainingPerformanceObligations` tag
would be the textbook source, but it is annual-only and filers tag it per
segment, per counterparty or not at all, so it is not used here.
"""
from __future__ import annotations

import re

from .regulatory_capital import number as cell_number
from .regulatory_capital import report_tables, unit_scale

HEADING = re.compile(r"수주\s*(?:상황|현황|잔고\s*현황)")
GROUPS = (
    ("opening", re.compile(r"기초")),
    ("total", re.compile(r"수주\s*총액|계약\s*총액|총\s*계약|도급\s*액|계약\s*금액")),
    ("new", re.compile(r"신규|증감|당기\s*수주|수주\s*금액|수주액")),
    ("delivered", re.compile(r"기납품|매출\s*계상|기성|납품|매출액|매출인식|완성\s*공사")),
    ("backlog", re.compile(r"잔고|잔액|기말")),
)
TOTAL_ROW = re.compile(r"^(합계|총계|계|합계\(.*\))$")
GRAND_TOTAL = re.compile(r"합\s*계|총\s*계")
DATE_CELL = re.compile(r"^[\s'’~]*\d{2,4}[./-]\d{1,2}([./-]\d{1,2})?")
SECTION_END = re.compile(r"위험\s*관리|주요\s*계약\s*및\s*연구|연구\s*개발\s*활동|III\.\s*재무에")
TOP_ITEMS = 12
CATEGORY_CELLS = {"국내", "해외", "국 내", "해 외", "수출", "내수"}


def _group(cell: str) -> str | None:
    text = re.sub(r"\(\*?\d*\)|\*\d+", "", cell or "")
    for key, rx in GROUPS:
        if rx.search(text):
            return key
    return None


def _amounts(row, n_groups: int, pairs: bool):
    nums = [cell_number(c) for c in row[1:] if not DATE_CELL.match(c or "")]
    nums = [x for x in nums if x is not None]
    if pairs and len(nums) == 2 * n_groups:
        return nums[1::2]
    if len(nums) == n_groups:
        return nums
    if pairs and len(nums) > n_groups:
        return nums[-n_groups:]   # quantities left as '-' leave only the amounts at the end
    return None


def parse_backlog_table(table: dict) -> dict | None:
    rows = table["rows"]
    if len(rows) < 2:
        return None
    head = rows[0]
    groups = [g for g in (_group(c) for c in head) if g]
    # A heading row like ['수주총액', '기납품액', '수주잔고'] may come one row down.
    if "backlog" not in groups and len(rows) > 2:
        head = rows[1]
        groups = [g for g in (_group(c) for c in head) if g]
    if "backlog" not in groups or len(groups) != len(set(groups)):
        return None
    pairs = any("수량" in " ".join(r) for r in rows[:3])
    start = next((i for i, r in enumerate(rows) if i > 0 and not all(c in ("수량", "금액", "") for c in r)
                  and _amounts(r, len(groups), pairs) is not None), None)
    if start is None:
        return None
    items, total = [], None
    for r in rows[start:]:
        amounts = _amounts(r, len(groups), pairs)
        if amounts is None:
            continue
        rec = dict(zip(groups, amounts))
        label = re.sub(r"\s+", " ", r[0]).strip()
        # 구분 | 공사명 | ... : a 국내/해외 category cell before the project name
        if label in CATEGORY_CELLS and len(r) > 1 and cell_number(r[1]) is None and not DATE_CELL.match(r[1] or ""):
            name = re.sub(r"\s+", " ", r[1]).strip()
            label = f"{name} ({label})"
        elif label == "기타":
            label = "기타 (그 외 현장·품목)"
        compact = label.replace(" ", "")
        if TOTAL_ROW.match(compact) or (GRAND_TOTAL.search(label) and "소계" not in compact):
            total = rec               # the last grand-total row wins (현대건설 "국내 / 해외 합계")
        elif "소계" in compact:
            continue
        else:
            items.append({"item": label, **rec})
    if total is None:
        if not items:
            return None
        total = {g: sum(i[g] for i in items if i.get(g) is not None) for g in groups}
        total_from = "sum_of_rows"
    else:
        total_from = "total_row"
    scale = unit_scale(table["before"] + " " + " ".join(" ".join(r) for r in rows[:2]))
    if scale is None:
        return None
    scaled = {g: v * scale for g, v in total.items()}
    check = None
    if all(k in total for k in ("opening", "new", "delivered")):
        expect = total["opening"] + total["new"] - total["delivered"]
        check = abs(expect - total["backlog"]) <= 0.01 * max(abs(total["backlog"]), 1)
    elif all(k in total for k in ("total", "delivered")):
        expect = total["total"] - total["delivered"]
        check = abs(expect - total["backlog"]) <= 0.01 * max(abs(total["backlog"]), 1)
    return {
        "columns": groups, "quantity_and_amount": pairs, "scale": scale, "total_from": total_from,
        "backlog": scaled["backlog"], "opening": scaled.get("opening"), "new_orders": scaled.get("new"),
        "contract_total": scaled.get("total"), "delivered": scaled.get("delivered"),
        "roll_forward_ok": check,
        "item_count": len(items),
        "items": [{**{"item": i["item"]}, **{("new_orders" if g == "new" else "contract_total" if g == "total" else g):
                                            (i[g] * scale if i.get(g) is not None else None) for g in groups}}
                  for i in sorted(items, key=lambda i: -(i.get("backlog") or 0))[:TOP_ITEMS]],
    }


def _part_label(before: str) -> str | None:
    tail = before[-120:]
    m = re.findall(r"부문\s*[:：]\s*([^\s(]{2,30})", tail) or re.findall(r"\d\)\s*([^\s(]{2,30})", tail[-80:])
    m = [x for x in m if "수주" not in x]
    return m[-1] if m else None


def backlog_from_report(doc: str, *, receipt: str, period_end: str) -> dict:
    """Backlog tables in the 수주상황 section. A table qualifies when the text
    just before it mentions 수주 or its header has 잔고/잔액. When the section
    has several tables with the same columns (현대건설: 1) 현대건설,
    2) 현대엔지니어링), they are per-company parts and are summed."""
    out = {"receipt": receipt, "period_end": period_end}
    if not HEADING.search(doc):
        out["status"] = "no_section"
        return out
    tables = list(report_tables(doc))
    first = None
    parts = []
    for t in tables:
        head = " ".join(" ".join(r) for r in t["rows"][:2])
        if "무형자산" in t["before"][-200:]:
            continue
        if not (re.search(r"수주", t["before"][-250:]) or re.search(r"잔고|잔액", head)):
            continue
        if first is not None:
            between = doc[first["end"]:t["start"]]
            if SECTION_END.search(re.sub(r"<[^>]+>", " ", between)):
                break
        parsed = parse_backlog_table(t)
        # Only a table whose total row closes (기초+신규−매출=잔고 or 총액−납품=잔고)
        # is a backlog table; a bare 잔액 column (related-party balances) is not.
        if not parsed or parsed["roll_forward_ok"] is not True:
            continue
        if first is None:
            first = t
        elif parsed["columns"] != parts[0]["columns"]:
            continue
        if any(abs(p["backlog"] - parsed["backlog"]) <= 0.001 * max(abs(parsed["backlog"]), 1) for p in parts):
            continue          # the same table repeated (이마트: 신세계I&C in two places)
        parts.append({**parsed, "part": _part_label(t["before"])})
        first = t
    if not parts:
        out["status"] = "not_parsed"
        return out
    if len(parts) == 1:
        out.update(parts[0], status="parsed")
        out.pop("part", None)
        return out
    keys = ("backlog", "opening", "new_orders", "contract_total", "delivered")
    agg = {k: (sum(p[k] for p in parts) if all(p.get(k) is not None for p in parts) else None) for k in keys}
    out.update(parts[0], **agg, status="parsed",
               roll_forward_ok=all(p["roll_forward_ok"] is not False for p in parts),
               parts=[{"part": p["part"], "backlog": p["backlog"], "new_orders": p.get("new_orders"),
                       "item_count": p["item_count"]} for p in parts],
               items=sorted(({**i, "item": f"{i['item']} · {p['part']}" if p.get("part") else i["item"]}
                             for p in parts for i in p["items"]), key=lambda i: -(i.get("backlog") or 0))[:TOP_ITEMS],
               item_count=sum(p["item_count"] for p in parts),
               note="같은 절의 회사별 수주 표를 합산")
    out.pop("part", None)
    return out

"""Regulatory capital ratios read from DART periodic-report tables.

Neither fnlttSinglAcntAll nor the original XBRL carries regulatory capital:
K-ICS (insurers), Basel III (banks / bank holding companies), 순자본비율 NCR
(securities) and 조정자기자본비율 (card / capital companies) are computed on
supervisory bases -- required capital, risk-weighted assets, total risk --
that the financial statements do not contain. Every 사업보고서 / 분기보고서
of these filers prints them as a small table ("재무건전성 / 자본적정성").
This module finds those tables in the report body (OpenDART document.xml)
and returns the numbers with their location.

Rules (checked against FY2025 reports of DB생명, 삼성생명, DB손해보험,
KB금융, 키움증권, 현대카드, 현대캐피탈 and DB생명's 2026 반기보고서):

* A table qualifies by its row labels, not by where it sits. A label may be in
  the first or second cell (현대카드 puts a category in the first).
* The first qualifying table whose current-period cell is a number wins,
  skipping tables introduced as "정정 전" (DB손해보험 prints both). Holding
  companies print subsidiaries' tables too; the filer's own came first in
  every report checked, and the heading before the table travels with the
  result so a reader can see which entity it describes.
* Period columns come from the header row; columns headed 증감/비고/변동/대비
  are dropped (현대캐피탈's third column is "전기 대비 증감", not a year).
  Column k is the report's period end minus k fiscal years (interim reports:
  the interim date, then the two prior December year ends).
* Unit from the "(단위: ...)" note just before the table (or in its first row).
* K-ICS: ratio cross-checked against A/B (0.15%p); the 경과조치 전 ratio and
  the 연결/별도 basis are read from the footnote under the table.

No regulatory number is estimated; a filer without the table gets nothing.
"""
from __future__ import annotations

import re
from datetime import date

UNIT_SCALE = (("십억원", 10**9), ("억원", 10**8), ("백만원", 10**6), ("천원", 10**3), ("원", 1))
EXCLUDED_HEADER = re.compile(r"증감|비고|변동|대비|증가")

# Regulatory thresholds. Statutory prompt-corrective-action tiers where the
# regulation defines them; nothing firm-specific (D-SIB buffers, supervisory
# "recommended" levels) is added.
THRESHOLDS = {
    "kics": [
        {"ratio": 1.00, "label": "경영개선권고", "basis": "보험업감독규정 적기시정조치: 지급여력비율 100% 미만"},
        {"ratio": 0.50, "label": "경영개선요구", "basis": "지급여력비율 50% 미만"},
        {"ratio": 0.00, "label": "경영개선명령", "basis": "지급여력비율 0% 미만"},
    ],
    "ncr": [
        {"ratio": 1.00, "label": "경영개선권고", "basis": "금융투자업규정 적기시정조치: 순자본비율 100% 미만"},
        {"ratio": 0.50, "label": "경영개선요구", "basis": "순자본비율 50% 미만"},
        {"ratio": 0.00, "label": "경영개선명령", "basis": "순자본비율 0% 미만"},
    ],
    "credit_finance": {
        "card": [{"ratio": 0.08, "label": "경영지도비율", "basis": "여신전문금융업감독규정 제8조: 신용카드업자 조정자기자본비율 8% 이상"}],
        "other": [{"ratio": 0.07, "label": "경영지도비율", "basis": "여신전문금융업감독규정 제8조: 신용카드업자 외 여신전문금융회사 7% 이상"}],
    },
}
# Basel III minimum and minimum + capital conservation buffer (2.5%p).
BASEL_MINIMUMS = {
    "cet1_ratio": {"minimum": 0.045, "with_conservation_buffer": 0.07},
    "tier1_ratio": {"minimum": 0.06, "with_conservation_buffer": 0.085},
    "total_ratio": {"minimum": 0.08, "with_conservation_buffer": 0.105},
}

# kind -> (row patterns, required keys, key read as the "current" check, ratio keys)
SPECS = {
    "kics": ({
        "ratio": re.compile(r"지급여력\s*비율"),
        "available": re.compile(r"가용자본|지급여력\s*금액|^지급여력\s*\(A\)"),
        "required": re.compile(r"요구자본|지급여력\s*기준"),
    }, ("available", "required", "ratio"), "ratio", {"ratio"}),
    "basel": ({
        "cet1_ratio": re.compile(r"^보통주자본비율"),
        "tier1_ratio": re.compile(r"^기본자본비율"),
        "total_ratio": re.compile(r"^(총자본비율|BIS\s*비율|총자기자본비율)"),
        "rwa": re.compile(r"^위험가중자산(\s*\(|$|합계)"),
        "cet1": re.compile(r"^보통주자본(?!비율)"),
        "tier1": re.compile(r"^기본자본(?!비율)"),
        "total_capital": re.compile(r"^(총\s?자기자본|자기자본|총자본(합계)?)(?!비율)"),
    }, ("cet1_ratio", "tier1_ratio", "total_ratio"), "total_ratio", {"cet1_ratio", "tier1_ratio", "total_ratio"}),
    "ncr": ({
        "ratio": re.compile(r"순자본\s*비율"),
        "ncr_capital": re.compile(r"영업용\s*순자본"),
        "total_risk": re.compile(r"총\s*위\s*험\s*액"),
        "required_equity": re.compile(r"필요\s*유지\s*자기자본"),
    }, ("ratio", "ncr_capital", "total_risk"), "ratio", {"ratio"}),
    "credit_finance": ({
        "ratio": re.compile(r"조정\s*자기자본\s*비율"),
        "adjusted_equity": re.compile(r"^조정\s*자기자본(?!\s*비율)"),
        "adjusted_assets": re.compile(r"^조정\s*총자산"),
    }, ("ratio",), "ratio", {"ratio"}),
}


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def report_tables(doc: str):
    for m in re.finditer(r"<TABLE[^>]*>.*?</TABLE>", doc, re.S | re.I):
        rows = []
        for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", m.group(0), re.S | re.I):
            cells = [_text(c) for c in re.findall(r"<T[DHE][^>]*>(.*?)</T[DHE]>", tr, re.S | re.I)]
            if cells:
                rows.append(cells)
        yield {"start": m.start(), "end": m.end(), "rows": rows,
               "before": _text(doc[max(0, m.start() - 600):m.start()])[-300:]}


def number(cell: str):
    s = (cell or "").replace(",", "").replace(" ", "").replace("%", "")
    if not s or s in {"-", "–", "—"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def unit_scale(text: str):
    m = re.findall(r"단위\s*[:：]\s*([^),]+)", text)
    if not m:
        return None
    unit = m[-1].replace(" ", "")
    for name, scale in UNIT_SCALE:
        if unit.startswith(name):
            return scale
    return None


def period_ends(period_end: str, n: int = 3):
    """Column dates: the report's period end, then prior December year ends.

    Annual FY2025 -> 2025-12-31, 2024-12-31, 2023-12-31; 2026 반기 ->
    2026-06-30, 2025-12-31, 2024-12-31 (DB생명 "제38기 2분기 / 제37기 / 제36기").
    December fiscal years only."""
    year = date.fromisoformat(period_end).year
    return [period_end] + [f"{year - k}-12-31" for k in range(1, n)]


def _header(rows):
    header = next((r for r in rows if len(r) >= 3 and re.fullmatch(r"(구\s*분|관련지표)", r[0] or "")), None)
    return header or next((r for r in rows if len(r) >= 2), [])


def _header_periods(rows):
    return sum(1 for c in _header(rows)[1:] if c and not EXCLUDED_HEADER.search(c))


def _first_column_year_ok(rows, period_end):
    """A history table ("14년 말 / 15년9월말 ...", 신한지주) must not pass for
    the current period: if the first period header names a year, it has to be
    the report's own year."""
    cells = [c for c in _header(rows)[1:] if c and not EXCLUDED_HEADER.search(c)]
    if not cells:
        return True
    head = cells[0]
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", head)]
    years += [2000 + int(y) for y in re.findall(r"(?<!\d)(\d{2})\s*년", head)]
    return not years or date.fromisoformat(period_end).year in years


def _row_map(rows, patterns):
    """The label is the text cell right before the first number, in the first
    two cells: "총자본비율 | 기본자본비율 | 0.1521" (KB·신한 notes) labels
    기본자본비율; "자본의 적정성 | 조정자기자본비율 | 16.79" (현대카드)."""
    found = {}
    for r in rows:
        for idx in (1, 0):
            if idx >= len(r) or number(r[idx]) is not None or not r[idx]:
                continue
            label = r[idx]
            hit = next((k for k, p in patterns.items() if k not in found and p.search(label)), None)
            if hit:
                found[hit] = (r, idx)
                break
    return found


def _values(entry, n):
    row, idx = entry
    return [number(c) for c in row[idx + 1: idx + 1 + n]]


SMALL_RATIO_KINDS = {"basel", "credit_finance"}


def _ratio(entry, n, kind):
    """Percent cells -> fraction. 은행·여전 ratios are 2-20%, so a bare value
    under 1.5 without a % sign is already a fraction (신한 notes: 0.1594)."""
    row, idx = entry
    out = []
    for c in row[idx + 1: idx + 1 + n]:
        v = number(c)
        if v is not None and not ("%" not in (c or "") and kind in SMALL_RATIO_KINDS and abs(v) < 1.5):
            v = v / 100
        out.append(round(v, 8) if v is not None else None)
    return out


def _first_table(doc, kind, period_end):
    patterns, required, current, _ = SPECS[kind]
    for t in report_tables(doc):
        if "정정 전" in t["before"][-80:] or "정정전" in t["before"][-80:]:
            continue
        rows = _row_map(t["rows"], patterns)
        if not all(k in rows for k in required):
            continue
        if not _first_column_year_ok(t["rows"], period_end):
            continue
        n = _header_periods(t["rows"]) or 1
        values = _values(rows[current], n)
        if not values or values[0] is None:
            continue
        return t, rows, n
    return None, None, 0


def extract(doc: str, kind: str, *, period_end: str, receipt: str, subtype: str | None = None):
    """One report -> {kind, points:[{period_end, <measure>...}], source, ...} or None."""
    table, rows, n = _first_table(doc, kind, period_end)
    if not table:
        return None
    _, _, _, ratio_keys = SPECS[kind]
    scale = unit_scale(table["before"]) or unit_scale(" ".join(" ".join(r) for r in table["rows"][:2]))
    ends = period_ends(period_end, n)
    per = {}
    for key, entry in rows.items():
        is_ratio = key in ratio_keys
        if not is_ratio and scale is None:
            continue
        values = _ratio(entry, n, kind) if is_ratio else _values(entry, n)
        for end, v in zip(ends, values):
            if v is not None:
                per.setdefault(end, {})[key] = v if is_ratio else v * scale
    points = [{"period_end": e, **per[e]} for e in ends if e in per]
    out = {"kind": kind, "status": "reported", "points": points,
           "source": {"url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                      "heading": table["before"][-160:], "unit_scale": scale}}
    if kind == "kics":
        for p in points:
            a, b = p.get("available"), p.get("required")
            p["ratio_matches_a_over_b"] = (abs(a / b - p["ratio"]) <= 0.0015) if a is not None and b else None
        note = _text(doc[table["end"]:table["end"] + 4000])[:900]
        out["note"] = note[:400]
        out["scope"] = "CFS" if "연결" in note[:300] else ("OFS" if "별도" in note[:300] else None)
        pre = None
        m = re.search(r"경과조치\s*(?:적용\s*)?전[^%]{0,40}?([\d.]+)\s*%", note)
        if m:
            pre = {"ratio": round(float(m.group(1)) / 100, 8), "period_end": period_end}
            amounts = re.search(r"지급여력\s*([\d,]+)\s*(백만원|억원|십억원|천원)?[^,)]*,\s*지급여력기준\s*([\d,]+)",
                                note[m.start():m.start() + 200])
            if amounts:
                s = dict(UNIT_SCALE).get(amounts.group(2) or "", scale or 1)
                pre["available"] = float(amounts.group(1).replace(",", "")) * s
                pre["required"] = float(amounts.group(3).replace(",", "")) * s
        out["pre_transitional"] = pre
        out["transitional_applied"] = bool(pre) or "경과조치 후" in note
        out["thresholds"] = THRESHOLDS["kics"]
    elif kind == "basel":
        out["minimums"] = BASEL_MINIMUMS
    elif kind == "ncr":
        out["thresholds"] = THRESHOLDS["ncr"]
    elif kind == "credit_finance":
        out["thresholds"] = THRESHOLDS["credit_finance"]["card" if subtype == "card" else "other"]
    return out


def regulatory_from_reports(reports, *, kind: str, subtype: str | None = None):
    """reports: [{kind: FY|Q1|H1|Q3, period_end, receipt, doc}] newest first.

    One series per measure, deduplicated by period end. An interim report
    contributes only its own period-end column; its prior-year columns repeat
    the annual report's, which wins for those dates."""
    merged, latest = {}, None
    for r in reports:
        res = extract(r["doc"], kind, period_end=r["period_end"], receipt=r["receipt"], subtype=subtype)
        if not res:
            continue
        if latest is None:
            latest = res
        for i, p in enumerate(res["points"]):
            if r["kind"] != "FY" and i > 0:
                continue
            if r["kind"] == "FY" or p["period_end"] not in merged:
                merged[p["period_end"]] = {**p, "receipt": r["receipt"], "report": r["kind"]}
    if latest is None:
        return None
    latest = dict(latest)
    latest["series"] = [merged[k] for k in sorted(merged)]
    return latest


def regulatory_kind(entity_class: str | None, name: str | None):
    """Which table to look for, from the engine's entity class and the name."""
    name = name or ""
    if entity_class == "insurance" or re.search(r"생명|화재|손해보험|해상|보험", name):
        return "kics", None
    if entity_class == "bank" or re.search(r"은행|금융지주", name):
        return "basel", None
    if re.search(r"증권|투자증권", name):
        return "ncr", None
    if entity_class == "specialized_credit_finance" or re.search(r"카드|캐피탈", name):
        return "credit_finance", "card" if "카드" in name else "other"
    return None, None

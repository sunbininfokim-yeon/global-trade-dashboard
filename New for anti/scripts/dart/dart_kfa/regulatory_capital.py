"""Regulatory capital ratios read from DART periodic-report tables.

Neither fnlttSinglAcntAll nor the original XBRL carries regulatory capital:
K-ICS (insurers) and Basel III capital (banks, bank holding companies) are
computed on supervisory bases -- required capital, risk-weighted assets --
that the financial statements do not contain. Every 사업보고서 / 분기보고서
of these filers does print them, as a small table in "II. 사업의 내용 >
재무건전성 / 자본적정성". This module finds those tables in the report body
(OpenDART document.xml) and returns the numbers with their location.

Rules (all checked against DB생명·삼성생명·DB손해보험·KB금융 FY2025 reports):

* A table qualifies by its *row labels*, not by where it sits: K-ICS needs an
  available-capital (A) row, a required-capital (B) row and a ratio row;
  Basel needs CET1 / Tier 1 / total ratio rows and an RWA row.
* The first qualifying table whose current-period cell is a number wins,
  skipping tables introduced as "정정 전" (DB손해보험 prints both). Holding
  companies print subsidiaries' tables too; the filer's own comes first in
  every report checked, and the heading text before the table travels with
  the result so a reader can see which entity it describes.
* Unit from the "(단위: ...)" note just before the table.
* Column 0 is the report's period end; columns 1 and 2 are the two prior
  fiscal year ends (annual report: FY-1, FY-2; interim report: FY-1, FY-2
  measured from the interim's own fiscal year).
* K-ICS: the ratio is cross-checked against A/B (0.15%p); the 경과조치 전
  ratio is read from the footnote when the filer discloses it.

No regulatory number is estimated. A filer without the table gets nothing.
"""
from __future__ import annotations

import re
from datetime import date

UNIT_SCALE = (("십억원", 10**9), ("억원", 10**8), ("백만원", 10**6), ("천원", 10**3), ("원", 1))

# 보험업감독규정 적기시정조치 (K-ICS): <100% 경영개선권고, <50% 요구, <0% 명령.
KICS_THRESHOLDS = [
    {"ratio": 1.00, "label": "경영개선권고", "basis": "보험업감독규정 적기시정조치: 지급여력비율 100% 미만"},
    {"ratio": 0.50, "label": "경영개선요구", "basis": "지급여력비율 50% 미만"},
    {"ratio": 0.00, "label": "경영개선명령", "basis": "지급여력비율 0% 미만"},
]
# Basel III minimum and minimum + capital conservation buffer (2.5%p).
# D-SIB and countercyclical buffers vary by bank and are not added here.
BASEL_MINIMUMS = {
    "cet1_ratio": {"minimum": 0.045, "with_conservation_buffer": 0.07},
    "tier1_ratio": {"minimum": 0.06, "with_conservation_buffer": 0.085},
    "total_ratio": {"minimum": 0.08, "with_conservation_buffer": 0.105},
}

KICS_ROWS = {
    "available": re.compile(r"(가용자본|지급여력금액|^지급여력\s*\(A\))"),
    "required": re.compile(r"(요구자본|지급여력기준)"),
    "ratio": re.compile(r"지급여력비율"),
}
BASEL_ROWS = {
    "cet1_ratio": re.compile(r"^보통주자본비율"),
    "tier1_ratio": re.compile(r"^기본자본비율"),
    "total_ratio": re.compile(r"^(총자본비율|BIS\s*비율|총자기자본비율)"),
    "rwa": re.compile(r"^위험가중자산(\s*\(|$|합계)"),
    "cet1": re.compile(r"^보통주자본(?!비율)"),
    "tier1": re.compile(r"^기본자본(?!비율)(계)?"),
    "total_capital": re.compile(r"^(총\s?자기자본|자기자본|총자본(합계)?)(?!비율)"),
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


def unit_scale(before: str):
    m = re.findall(r"단위\s*[:：]\s*([^),]+)", before)
    if not m:
        return None
    unit = m[-1].replace(" ", "")
    for name, scale in UNIT_SCALE:
        if unit.startswith(name):
            return scale
    return None


def period_ends(report_kind: str, period_end: str):
    """Column dates: the report's own period end, then the two prior FY ends.

    Annual FY2025 -> 2025-12-31, 2024-12-31, 2023-12-31; 2026 반기 ->
    2026-06-30, 2025-12-31, 2024-12-31 (DB생명 "제38기 2분기 / 제37기 / 제36기").
    December fiscal years only; other year ends are not mapped."""
    year = date.fromisoformat(period_end).year
    return [period_end, f"{year - 1}-12-31", f"{year - 2}-12-31"]


def _row_map(rows, patterns):
    found = {}
    for r in rows:
        label = r[0] if r else ""
        for key, pat in patterns.items():
            if key not in found and pat.search(label):
                found[key] = r
                break
    return found


def _first_table(doc, patterns, required_keys, current_key):
    for t in report_tables(doc):
        if "정정 전" in t["before"][-80:]:
            continue
        rows = _row_map(t["rows"], patterns)
        if not all(k in rows for k in required_keys):
            continue
        if number((rows[current_key] + [None, None])[1] or "") is None:
            continue
        return t, rows
    return None, None


def _series(row, ends, *, ratio=False, scale=1):
    out = []
    for i, end in enumerate(ends):
        cell = row[1 + i] if len(row) > 1 + i else None
        v = number(cell or "")
        if v is None:
            continue
        out.append({"period_end": end, "value": v / 100 if ratio else v * scale})
    return out


def kics(doc: str, *, report_kind: str, period_end: str, receipt: str):
    table, rows = _first_table(doc, KICS_ROWS, ("available", "required", "ratio"), "ratio")
    if not table:
        return None
    scale = unit_scale(table["before"]) or unit_scale(" ".join(" ".join(r) for r in table["rows"][:1]))
    if scale is None:
        return {"status": "unavailable", "reason": "missing:unit"}
    ends = period_ends(report_kind, period_end)
    avail = _series(rows["available"], ends, scale=scale)
    req = _series(rows["required"], ends, scale=scale)
    ratio = _series(rows["ratio"], ends, ratio=True)
    points = []
    for r in ratio:
        a = next((x["value"] for x in avail if x["period_end"] == r["period_end"]), None)
        b = next((x["value"] for x in req if x["period_end"] == r["period_end"]), None)
        check = None
        if a is not None and b:
            check = abs(a / b - r["value"]) <= 0.0015
        points.append({"period_end": r["period_end"], "ratio": r["value"], "available": a, "required": b,
                       "ratio_matches_a_over_b": check})
    # The footnotes (주1~3: 연결 기준, 경과조치 전 비율) sit in a one-cell table
    # right after the K-ICS table, so read the following text tables included.
    after = _text(doc[table["end"]:table["end"] + 4000])
    note = after[:900]
    scope = "CFS" if "연결" in note[:300] else ("OFS" if "별도" in note[:300] else None)
    pre = None
    m = re.search(r"경과조치\s*(?:적용\s*)?전[^%]{0,40}?([\d.]+)\s*%", note)
    if m:
        pre = {"ratio": float(m.group(1)) / 100, "period_end": period_end}
        amounts = re.search(r"지급여력\s*([\d,]+)\s*(백만원|억원|십억원|천원)?[^,)]*,\s*지급여력기준\s*([\d,]+)", note[m.start():m.start() + 200])
        if amounts:
            s = dict(UNIT_SCALE).get(amounts.group(2) or "", scale)
            pre["available"] = float(amounts.group(1).replace(",", "")) * s
            pre["required"] = float(amounts.group(3).replace(",", "")) * s
    return {
        "kind": "kics", "status": "reported", "scope": scope, "points": points,
        "pre_transitional": pre, "transitional_applied": bool(pre) or "경과조치 후" in note,
        "thresholds": KICS_THRESHOLDS,
        "source": {"url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}", "heading": table["before"][-160:],
                   "note": note[:400], "unit_scale": scale},
    }


def basel(doc: str, *, report_kind: str, period_end: str, receipt: str):
    table, rows = _first_table(doc, BASEL_ROWS, ("cet1_ratio", "tier1_ratio", "total_ratio"), "total_ratio")
    if not table:
        return None
    scale = unit_scale(table["before"])
    ends = period_ends(report_kind, period_end)
    out = {"kind": "basel", "status": "reported", "points": [], "minimums": BASEL_MINIMUMS,
           "source": {"url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}", "heading": table["before"][-160:],
                      "unit_scale": scale}}
    per = {}
    for key in ("cet1_ratio", "tier1_ratio", "total_ratio"):
        for p in _series(rows[key], ends, ratio=True):
            per.setdefault(p["period_end"], {})[key] = p["value"]
    if scale:
        for key in ("rwa", "cet1", "tier1", "total_capital"):
            if key in rows:
                for p in _series(rows[key], ends, scale=scale):
                    per.setdefault(p["period_end"], {})[key] = p["value"]
    out["points"] = [{"period_end": e, **per[e]} for e in ends if e in per]
    return out


def regulatory_from_reports(reports, *, sector: str):
    """reports: [{kind: FY|Q1|H1|Q3, period_end, receipt, doc}] newest first.

    Returns one series per measure, deduplicated by period end: an interim
    report contributes only its own period-end column (its prior-year
    columns repeat the annual report's)."""
    fn = kics if sector == "insurance" else basel
    merged, latest = {}, None
    for r in reports:
        res = fn(r["doc"], report_kind=r["kind"], period_end=r["period_end"], receipt=r["receipt"])
        if not res or res.get("status") != "reported":
            continue
        if latest is None:
            latest = res
        for i, p in enumerate(res["points"]):
            if r["kind"] != "FY" and i > 0:
                continue
            merged.setdefault(p["period_end"], {**p, "receipt": r["receipt"]})
    if latest is None:
        return None
    latest = dict(latest)
    latest["series"] = [merged[k] for k in sorted(merged)]
    return latest

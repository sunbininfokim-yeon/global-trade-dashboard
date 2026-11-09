"""Monthly Korean bank delinquency from the FSS press release "국내은행의 원화대출 연체율 현황".

FISIS (kr_bank_credit.py) is quarterly. The FSS also publishes a monthly release, as a PDF only, with
the month-end delinquency rate (1 month+ overdue) by segment, the month's new delinquencies, the
delinquencies cleared, and the new-delinquency rate. This module reads those PDFs (2018-04 onward).

Each release states the month just ended (and the previous month) in fixed sentences
("가계대출 연체율(0.45%)은 전월말(0.42%) 대비 ...") -- the text is read first because the tables'
headers changed several times. Date-labelled rows ("(’25.8월) (’26.3월) ... / 신규 연체채권 규모(조원):
3.0 2.7 ...", "구분 ’25.8 ’25.9 ... / 연체율 0.61 0.51 ...") fill the months whose release is missing.
A later release overwrites an earlier one's figure for the same month.

Banks clear delinquent loans at quarter ends (write-offs and sales), so the rate rises inside a
quarter and drops in March / June / September / December; the panels say so.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .kr_npl_release import BASE, _get, pdf_text

CACHE = Path(__file__).resolve().parent.parent / "config" / "kr_delinq_monthly_v1.json"
LIST_URL = BASE + "/fss/bbs/B0000188/list.do?menuNo=200218&searchCnd=1&searchWrd=%EC%9B%90%ED%99%94%EB%8C%80%EC%B6%9C%20%EC%97%B0%EC%B2%B4%EC%9C%A8&pageIndex={page}"

Q = r"[’'′‘`´]?"


def list_releases(pages: int = 1) -> list[dict[str, str]]:
    import html  # noqa: PLC0415

    out = []
    for page in range(1, pages + 1):
        s = _get(LIST_URL.format(page=page)).decode("utf-8", "replace")
        for part in re.split(r'(?=<td class="title"><a href="/fss/bbs/B0000188/view\.do\?nttId=)', s)[1:]:
            m = re.search(r'nttId=(\d+)[^"]*">([^<]+)</a>', part)
            if not m:
                continue
            title = html.unescape(m.group(2)).strip()
            if "원화대출 연체율" not in title:
                continue
            files = re.findall(r'href="(/fss/cmmn/file/fileDown\.do[^"]+)">\s*<i[^>]*></i><span class="name">([^<]+)</span>', part)
            pdf = [html.unescape(u) for u, n in files if n.lower().endswith(".pdf")]
            if pdf:
                out.append({"id": m.group(1), "title": title, "pdf": BASE + pdf[0]})
    return out


def release_month(title: str) -> str | None:
    m = re.search(r"(\d{2}|\d{4})\s*(?:\.|년)\s*(\d{1,2})\s*월\s*말", title)
    if not m:
        return None
    y = m.group(1)
    return f"{y if len(y) == 4 else '20' + y}{int(m.group(2)):02d}"


def _prev(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:6]) - 1
    return f"{y - 1}12" if m == 0 else f"{y}{m:02d}"


# key -> regex on whitespace-free text; group 1 = this month, optional group 2 = previous month
SENTENCES = {
    "total": r"원화대출연체율\*?(?:\([^)]*\))?[은는]([\d.]+)%로(?:전월말\(([\d.]+)%\))?",
    "corp": r"(?<![대소])기업대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "large": r"대기업대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "sme": r"중소기업대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "sme_corp": r"중소법인연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "soho": r"개인사업자대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "hh": r"(?<!\()가계대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "mort": r"주택담보대출연체율(?:\(([\d.]+)%\)[은는]전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "hhcredit": r"신용대출등\)의연체율(?:\(([\d.]+)%\)[은는]?전월말\(([\d.]+)%\)|\(([\d.]+)%\)|[은는]([\d.]+)%)",
    "new_amt": r"월중신규연체발생액\*?\(([\d.]+)조?원\)",
    "cleared": r"연체채권정리규모\*?\(([\d.]+)조원\)",
    "new_rate": r"신규연체율\([^)]*\)[은는]([\d.]+)%",
}


def _sentences(text: str, cur: str, out: dict[str, dict[str, float]]) -> None:
    flat = re.sub(r"\s+", "", text)
    for k, pat in SENTENCES.items():
        m = re.search(pat, flat)
        if not m:
            continue
        g = [x for x in m.groups()]
        if len(g) == 1:
            vals = (g[0], None)
        elif len(g) == 2:
            vals = (g[0], g[1])
        else:                                   # (cur, prev) | cur-in-parens | cur-after-은
            vals = (g[0], g[1]) if g[0] else (g[2] or (g[3] if len(g) > 3 else None), None)
        try:
            if vals[0]:
                out.setdefault(cur, {})[k] = float(vals[0])
            if vals[1]:
                out.setdefault(_prev(cur), {}).setdefault(k, float(vals[1]))
        except ValueError:
            pass


DATE = re.compile(Q + r"(\d{2})\.(\d{1,2})(?:월중|월|말)?(?=[\s)]|$)")


def _dated_rows(text: str, out: dict[str, dict[str, float]]) -> None:
    """Rows under a header of dates: '(’25.8월) (’26.3월) ...' / '구분 ’25.8 ’25.9 ...'."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        dates = [f"20{y}{int(m):02d}" for y, m in DATE.findall(line) if 1 <= int(m) <= 12]
        if len(dates) < 3 or "말" in line and "구분" not in line and "(" not in line:
            continue
        for row in lines[i + 1: i + 4]:
            r = re.sub(r"\s+", "", row)
            key = ("new_amt" if "신규연체채권규모" in r else "cleared" if "연체채권정리규모" in r
                   else "total" if r.startswith("연체율") else None)
            if not key:
                continue
            nums = re.findall(r"(?<![\d.])(\d+\.\d+)", row.split(":")[-1] if ":" in row else row)
            if len(nums) == len(dates):
                for ym, v in zip(dates, nums):
                    out.setdefault(ym, {}).setdefault(key, float(v))
    # '신규연체율(%):(’25.8)0.12→(’26.4)0.12→...'
    for chain in re.findall(r"신규연체율\s*\(%\)\s*:?([^\n]*)", text):
        for y, m, v in re.findall(r"\(" + Q + r"(\d{2})\.(\d{1,2})\)\s*([\d.]+)", chain):
            out.setdefault(f"20{y}{int(m):02d}", {}).setdefault("new_rate", float(v))


def parse(text: str, cur: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    _sentences(text, cur, out)
    side: dict[str, dict[str, float]] = {}
    _dated_rows(text, side)
    for ym, f in side.items():
        for k, v in f.items():
            out.setdefault(ym, {}).setdefault(k, v)
    return out


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def load() -> dict[str, Any]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {"releases": {}}


def save(doc: dict[str, Any]) -> bool:
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    old = CACHE.read_text(encoding="utf-8") if CACHE.exists() else ""
    if text != old:
        CACHE.write_text(text, encoding="utf-8")
        return True
    return False


def update(doc: dict[str, Any], pages: int = 1) -> list[str]:
    added = []
    for r in list_releases(pages):
        if r["id"] in doc["releases"]:
            continue
        cur = release_month(r["title"])
        if not cur:
            continue
        months = parse(pdf_text(_get(r["pdf"])), cur)
        if cur not in months:
            continue
        doc["releases"][r["id"]] = {"title": r["title"], "month": cur, "m": months}
        added.append(cur)
    return added


def merged(doc: dict[str, Any]) -> dict[str, dict[str, float]]:
    """month -> field -> value. The release for a month wins for that month; otherwise later wins."""
    out: dict[str, dict[str, float]] = {}
    rels = sorted(doc["releases"].values(), key=lambda r: r["month"])
    for rel in rels:                          # side values, later releases first-class
        for ym, f in rel["m"].items():
            if ym != rel["month"]:
                out.setdefault(ym, {}).update(f)
    for rel in rels:                          # each month's own release last, so it wins
        out.setdefault(rel["month"], {}).update(rel["m"].get(rel["month"], {}))
    return {k: v for k, v in sorted(out.items()) if v}


# --------------------------------------------------------------------------
# Card
# --------------------------------------------------------------------------

SOURCE_NOTE = "금융감독원 월별 보도자료 '국내은행의 원화대출 연체율 현황' PDF에서 읽은 값."


def _label(ym: str) -> str:
    return f"{ym[2:4]}.{int(ym[4:6])}"


def build(doc: dict[str, Any], n: int = 24) -> dict[str, Any] | None:
    m = merged(doc)
    total = {k: f["total"] for k, f in m.items() if "total" in f}
    if len(total) < 6:
        return None
    keys = sorted(total)[-n:]
    g = lambda k, f, sign=1: (round(sign * m[k][f], 2) if f in m.get(k, {}) else None)  # noqa: E731
    flow_keys = [k for k in keys if "new_amt" in m[k] or "cleared" in m[k]]
    return {
        "label": "대출 연체율(월)", "unit": "%", "format": "pct2",
        "note_ko": "국내은행 원화대출 연체율(1개월 이상 원리금 연체, 월말, %). 금감원 월별 발표로, 분기 자료보다 두 달가량 빠릅니다. "
                   "은행이 분기말(3·6·9·12월)에 연체채권을 상각·매각해서 분기 중 오르고 분기말에 떨어지는 톱니 모양이 정상이니, 같은 달끼리(전년 동월) 비교하세요. " + SOURCE_NOTE,
        "points": [(f"{k[:4]}-{k[4:6]}-01", v) for k, v in sorted(total.items())],
        "panels": [
            {"id": "m_segments", "compare_ko": "직전 달", "label": "부문별(월)", "type": "lines", "unit": "%", "dates": [_label(k) for k in keys],
             "series": [{"label": lab, "values": [g(k, f) for k in keys]}
                        for lab, f in (("대기업", "large"), ("중소법인", "sme_corp"), ("개인사업자", "soho"),
                                       ("주택담보대출", "mort"), ("신용대출 등", "hhcredit"), ("전체", "total"))],
             "note_ko": "부문별 월말 연체율(%). 분기말마다 떨어지는 것은 상각·매각 때문입니다. " + SOURCE_NOTE},
            {"id": "m_flow", "compare_ko": "직전 달", "label": "신규연체·정리(월)", "type": "stack", "unit": "조원", "dates": [_label(k) for k in flow_keys],
             "series": [{"label": "신규연체 발생", "values": [g(k, "new_amt") for k in flow_keys]},
                        {"label": "연체채권 정리", "values": [g(k, "cleared", -1) for k in flow_keys]}],
             "line": {"label": "연체채권 증감", "values": [round(m[k]["new_amt"] - m[k]["cleared"], 2)
                                                         if "new_amt" in m[k] and "cleared" in m[k] else None for k in flow_keys]},
             "note_ko": "그달 새로 1개월 이상 연체된 금액(+)과 상각·매각 등으로 정리한 금액(−), 조원. 정리 막대는 분기말 달에 크게 튀고, 신규연체 막대가 꾸준히 커지는지가 핵심입니다. " + SOURCE_NOTE},
            {"id": "m_new_rate", "compare_ko": "직전 달", "label": "신규연체율(월)", "type": "bars", "unit": "%", "dates": [_label(k) for k in keys],
             "series": [{"label": "신규연체율", "values": [g(k, "new_rate") for k in keys]}],
             "note_ko": "그달 신규연체 발생액 / 전월말 대출잔액(%). 상각·매각의 영향을 받지 않아 분기말 톱니가 없는, 가장 깨끗한 선행 신호입니다. " + SOURCE_NOTE},
        ],
    }

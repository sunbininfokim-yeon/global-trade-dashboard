"""Korean bank NPL flows from the FSS quarterly press release "국내은행 부실채권 현황(잠정)".

FISIS (the API behind kr_bank_credit.py) has NPL stocks but not the flows: how much was newly
classified as non-performing in a quarter, and how it left the book (written off, sold, recovered
through collateral, returned to normal). The FSS publishes those only in a PDF press release each
quarter. This module finds the releases on fss.or.kr, extracts the PDF text and reads three tables:

* 신규발생 (new NPLs): total, 기업 (대기업 / 중소기업), 가계 (주담대), 신용카드.
* 정리실적 (resolved NPLs): total, 상·매각 (write-off + sale), 정상화 등 (collateral recovery,
  return to normal, debt-equity swaps), and by sector. The quarter's split of 상각 vs 매각 vs 담보처분
  vs 정상화 is read from the release text, which states it for the quarter just ended.
* 부문별 부실채권비율 (NPL ratio by segment): 대기업, 중소법인, 개인사업자, 주택담보대출,
  신용대출 등, 신용카드 -- mortgage NPLs are not in the API at all.

The layout changed over the years (2013-18: long tables with year totals; 2019-: a 4-column table
of [2 years ago, 1 year ago, previous quarter, this quarter]; year-end releases since 2019: annual
totals). Every column is assigned to a quarter from the table header and the release's own quarter,
and a table whose header does not line up is skipped, not guessed. Q4 of an annual-only year is
annual minus Q1-Q3. A later release overwrites an earlier one's figure for the same quarter
(preliminary -> final).

Cache: config/kr_npl_release_v1.json (one entry per release read, so the daily job only downloads new
ones). PDF text extraction needs pdfplumber.
"""

from __future__ import annotations

import html
import io
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

CACHE = Path(__file__).resolve().parent.parent / "config" / "kr_npl_release_v1.json"
BASE = "https://www.fss.or.kr"
LIST_URL = BASE + "/fss/bbs/B0000188/list.do?menuNo=200218&searchCnd=1&searchWrd=%EB%B6%80%EC%8B%A4%EC%B1%84%EA%B6%8C%20%ED%98%84%ED%99%A9&pageIndex={page}"
UA = {"User-Agent": "Mozilla/5.0 (macro-monitor; public data)"}

# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def _get(url: str, timeout: int = 90) -> bytes:
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 -- retried, then raised
            last = exc
    raise RuntimeError(f"FSS fetch failed: {url[:90]}: {last}")


def list_releases(pages: int = 1) -> list[dict[str, str]]:
    """The NPL press releases on the FSS board, newest first: ntt id, title, PDF link."""
    out = []
    for page in range(1, pages + 1):
        s = _get(LIST_URL.format(page=page)).decode("utf-8", "replace")
        for part in re.split(r'(?=<td class="title"><a href="/fss/bbs/B0000188/view\.do\?nttId=)', s)[1:]:
            m = re.search(r'nttId=(\d+)[^"]*">([^<]+)</a>', part)
            if not m:
                continue
            title = html.unescape(m.group(2)).strip()
            if "국내은행" not in title or "부실채권 현황" not in title or "PF" in title:
                continue
            files = re.findall(r'href="(/fss/cmmn/file/fileDown\.do[^"]+)">\s*<i[^>]*></i><span class="name">([^<]+)</span>', part)
            pdf = [html.unescape(u) for u, n in files if n.lower().endswith(".pdf")]
            if pdf:
                out.append({"id": m.group(1), "title": title, "pdf": BASE + pdf[0]})
    return out


def pdf_text(data: bytes) -> str:
    import pdfplumber  # noqa: PLC0415 -- only the fetch step needs it

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


# --------------------------------------------------------------------------
# Quarters
# --------------------------------------------------------------------------


def release_quarter(title: str) -> str | None:
    """'26.6말 / '21년말 / 20.1분기말 / 18년 3분기말 / 14.12월말 -> yyyymm of the quarter end."""
    t = title.replace(" ", "")
    m = re.search(r"(\d{2})년말", t)
    if m:
        return f"20{m.group(1)}12"
    m = re.search(r"(\d{2})(?:\.|년)([1-4])분기말", t)
    if m:
        return f"20{m.group(1)}{int(m.group(2)) * 3:02d}"
    m = re.search(r"(\d{2})\.(\d{1,2})(?:월)?말", t)
    if m and int(m.group(2)) in (3, 6, 9, 12):
        return f"20{m.group(1)}{int(m.group(2)):02d}"
    return None


def _shift(ym: str, n: int) -> str:
    i = int(ym[:4]) * 4 + (int(ym[4:6]) // 3 - 1) + n
    return f"{i // 4}{(i % 4 + 1) * 3:02d}"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

NUM = re.compile(r"[△+\-]?\d[\d,]*(?:\.\d+)?|-")


def _val(tok: str) -> float:
    if tok == "-":
        return 0.0
    neg = tok.startswith(("△", "-"))
    v = float(tok.lstrip("△+-").replace(",", ""))
    return -v if neg else v


def _groups(line: str) -> list[tuple[str, list[float]]]:
    """'기업여신1) 5.0 4.9 4.1 5.7 +0.8 +1.6 형상·매각 3.2 ...' -> [(label, numbers), ...]."""
    line = re.sub(r"(?<=\d)(△|\+)", r" \1", line)
    out: list[tuple[str, list[float]]] = []
    label: list[str] = []
    nums: list[float] = []
    for tok in line.split():
        if NUM.fullmatch(tok) and not (tok == "-" and not out and not nums and not label):
            nums.append(_val(tok))
            continue
        if nums:
            out.append((" ".join(label), nums))
            label, nums = [], []
        label.append(tok)
    if nums:
        out.append((" ".join(label), nums))
    return out


def _key(label: str, side: str) -> str | None:
    lab = re.sub(r"[\s\d)]", "", label)
    if side == "new":
        for kw, k in (("신규발생", "new_total"), ("대기업", "new_large"), ("중소기업", "new_sme"), ("기업여신", "new_corp"),
                      ("주담대", "new_mort"), ("가계신용", "new_hhcredit"), ("가계여신", "new_hh"), ("신용카드", "new_card")):
            if kw in lab:
                return k
        return None
    for kw, k in (("정리실적", "res_total"), ("대손상각", "res_writeoff"), ("상·매각", "res_wo_sale"), ("상‧매각", "res_wo_sale"),
                  ("상ㆍ매각", "res_wo_sale"), ("매각", "res_sale"), ("담보처분", "res_collateral"), ("정상화", "res_normal"),
                  ("기타", "res_other"), ("중소기업", "res_sme"), ("기업여신", "res_corp"), ("가계신용", "res_hhcredit"),
                  ("가계여신", "res_hh"), ("신용카드", "res_card")):
        if kw in lab:
            if k == "res_normal" and "등" in lab:
                return "res_normal_etc"
            return k
    return None


HEAD_TOK = re.compile(r"([1-4])/4[pP]?|([1-4])Q중[pP]?|계")
RES_ONLY = ("정리실적", "매각", "정상화", "대손상각", "담보처분", "기타")


def _long_columns(header: list[str], cur: str) -> list[str] | None:
    """Long-table header tokens ('3/4', '4Q중', '계') -> quarter yyyymm or 'Y2017'; None if inconsistent."""
    toks = []
    for line in header:
        for t in line.split():
            m = HEAD_TOK.fullmatch(t)
            if m:
                toks.append(m.group(1) or m.group(2) or "계")
    if len(toks) < 5:
        return None
    year, q = int(cur[:4]), int(cur[4:6]) // 3
    cols: list[str] = []
    seen_q = False
    for t in reversed(toks):
        if t == "계":
            if seen_q:
                year -= 1
            cols.append(f"Y{year}")
            seen_q = False
            continue
        cols.append(f"{year}{int(t) * 3:02d}")
        seen_q = True
    cols.reverse()
    # the last quarter column must be the release's own quarter
    qs = [c for c in cols if not c.startswith("Y")]
    if not qs or qs[-1] != cur:
        return None
    # totals belong to the year of the quarters before them
    fixed = []
    for i, c in enumerate(cols):
        if c.startswith("Y"):
            prev = next((cols[j] for j in range(i - 1, -1, -1) if not cols[j].startswith("Y")), None)
            fixed.append(f"Y{prev[:4]}" if prev else c)
        else:
            fixed.append(c)
    return fixed


def _put(store: dict, col: str, key: str, v: float) -> None:
    if col.startswith("Y"):
        store["annual"].setdefault(col[1:], {})[key] = v
    else:
        store["q"].setdefault(col, {})[key] = v


def _narrative_split(sect: str, store: dict, cur: str) -> None:
    """'정리규모 ... 대손상각(1.4조원), 매각(2.5조원), 담보처분을 통한 여신회수(1.2조원), 여신 정상화(0.8조원)'."""
    m = re.search(r"정리규모[^□]*", sect)
    if not m:
        return
    s = re.sub(r"\s+", "", m.group(0))
    before = re.sub(r"\s+", "", sect[max(0, m.start() - 40): m.start()])
    annual = cur.endswith("12") and "년중" in before and "분기" not in before
    found = {}
    for k, pat in (("res_writeoff", r"대손상각\(?([\d.]+)조원"), ("res_sale", r"(?<![상·‧ㆍ])매각\(?([\d.]+)조원"),
                   ("res_collateral", r"담보처분[^()]{0,12}회수\(([\d.]+)조원"), ("res_normal", r"정상화\(([\d.]+)조원")):
        mm = re.search(pat, s)
        if mm:
            found[k] = float(mm.group(1))
    if not found:
        return
    if annual:
        store["annual"].setdefault(cur[:4], {}).update(found)
    else:
        store["q"].setdefault(cur, {}).update(found)


def _flow_section(text: str) -> str:
    a = re.search(r"신규발생\s*및\s*정리|신규발생\s*부실채권|부실채권\s*신규발생", text)
    if not a:
        return ""
    b = re.search(r"\n\s*3\.\s*부문별|부문별\s*부실채권비율", text[a.start():])
    return text[a.start(): a.start() + b.start()] if b else text[a.start(): a.start() + 6000]


def _parse_flows(text: str, cur: str, store: dict) -> list[str]:
    sect = _flow_section(text)
    notes = []
    if not sect:
        return ["no flow section"]
    lines = sect.splitlines()
    mode = "new"
    header: list[str] = []
    cols: list[str] | None = None
    seen_new: set[str] = set()
    side_by_side = False
    for line in lines:
        if "정리실적" in line and "추이" in line:
            mode, header, cols = "res", [], None
            continue
        if "신규발생" in line and "추이" in line:
            mode, header, cols = "new", [], None
            continue
        gs = _groups(line)
        if not gs or not gs[0][0] or len(gs[0][1]) < 3:
            if sum(bool(HEAD_TOK.fullmatch(t)) for t in line.split()) >= 3:
                header.append(line)
            continue
        if len(gs) >= 2:                      # side by side: new | resolved
            sides = [("new", gs[0]), ("res", gs[1])]
            side_by_side = True
        else:
            lab = re.sub(r"\s", "", gs[0][0])
            side = "res" if (mode == "res" or any(k in lab for k in RES_ONLY)) else "new"
            # a resolved-side row that wrapped onto a line of its own ('기업여신' twice)
            if side == "new" and side_by_side and _key(gs[0][0], "new") in seen_new:
                side = "res"
            sides = [(side, gs[0])]
        for side, (label, nums) in sides:
            k = _key(label, side)
            if not k:
                continue
            if side == "new":
                seen_new.add(k)
            n = len(nums)
            if n == 6:                        # [-8q, -4q, -1q, 0] + two changes
                for off, v in zip((-8, -4, -1, 0), nums[:4]):
                    _put(store, _shift(cur, off), k, v)
            elif n == 4 and cur.endswith("12"):   # annual: [Y-2, Y-1, Y] + change
                y = int(cur[:4])
                for yy, v in zip((y - 2, y - 1, y), nums[:3]):
                    _put(store, f"Y{yy}", k, v)
            elif n >= 7:
                if cols is None:
                    cols = _long_columns(header, cur)
                if cols is None or len(cols) != n:
                    notes.append(f"{k}: header does not match {n} values")
                    continue
                for c, v in zip(cols, nums):
                    _put(store, c, k, v)
    _narrative_split(sect, store, cur)
    return notes


RATIO_KEYS = (("중소법인", "npl_smecorp"), ("개인사업자", "npl_soho"), ("대기업", "npl_large"), ("중소기업", "npl_sme"),
              ("기업여신", "npl_corp"), ("주택담보", "npl_mort"), ("신용대출", "npl_hhcredit"), ("가계여신", "npl_hh"),
              ("신용카드", "npl_card"), ("총여신", "npl_total"), ("부실채권비율", "npl_total"))


def _parse_ratios(text: str, cur: str, store: dict) -> list[str]:
    """The 9-quarter 부문별 부실채권비율 table (columns must be consecutive quarters ending at `cur`)."""
    idx = [m.start() for m in re.finditer(r"부문별\s*부실채권비율", text)]
    for i in idx:
        sect = text[i: i + 3500]
        unit = sect.find("(단위")
        if unit < 0:
            continue
        sect = sect[unit:]
        end = re.search(r"\n\s*(?:4\.|주\s*:)", sect)
        sect = sect[: end.start()] if end else sect
        months: list[int] = []
        rows = []
        for line in sect.splitlines()[1:]:
            gs = _groups(line)
            if gs and gs[0][0] and len(gs[0][1]) >= 9:
                rows.append(gs[0])
            elif not rows:
                months += [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?:월)?말", line)]
        if len(months) < 9 or not rows:
            continue
        months = months[:9] if len(months) >= 9 else months
        cols = [_shift(cur, off) for off in range(-8, 1)]
        if [int(c[4:6]) for c in cols] != months[:9]:
            continue
        for label, nums in rows:
            lab = re.sub(r"[\s\d)]", "", label)
            k = next((k for kw, k in RATIO_KEYS if kw in lab), None)
            if k:
                for c, v in zip(cols, nums[:9]):
                    store["q"].setdefault(c, {})[k] = v
        return []
    # fall back to the text: the quarter just ended only
    flat = re.sub(r"\s+", "", text)
    for kw, k in (("대기업여신", "npl_large"), ("중소법인여신", "npl_smecorp"), ("개인사업자여신", "npl_soho"),
                  ("주택담보대출", "npl_mort"), ("신용카드채권", "npl_card")):
        m = re.search(kw + r"[^%\d]{0,14}?\(?([\d.]+)%", flat)
        if m:
            store["q"].setdefault(cur, {}).setdefault(k, float(m.group(1)))
    return ["ratio table not aligned; text only"]


def parse(text: str, cur: str) -> dict[str, Any]:
    store: dict[str, Any] = {"q": {}, "annual": {}}
    notes = _parse_flows(text, cur, store) + _parse_ratios(text, cur, store)
    store["notes"] = notes
    return store


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
    """Read releases not in the cache yet. Returns the quarters added."""
    added = []
    for r in list_releases(pages):
        if r["id"] in doc["releases"]:
            continue
        cur = release_quarter(r["title"])
        if not cur:
            continue
        parsed = parse(pdf_text(_get(r["pdf"])), cur)
        if not parsed["q"] and not parsed["annual"]:
            continue
        doc["releases"][r["id"]] = {"title": r["title"], "quarter": cur, **parsed}
        added.append(cur)
    return added


def merged(doc: dict[str, Any]) -> dict[str, dict[str, float]]:
    """quarter -> field -> value; later releases win, Q4 of annual-only years derived."""
    q: dict[str, dict[str, float]] = {}
    annual: dict[str, dict[str, float]] = {}
    for rel in sorted(doc["releases"].values(), key=lambda r: r["quarter"]):
        for ym, fields in rel.get("q", {}).items():
            q.setdefault(ym, {}).update(fields)
        for y, fields in rel.get("annual", {}).items():
            annual.setdefault(y, {}).update(fields)
    for y, fields in annual.items():
        q4 = q.setdefault(f"{y}12", {})
        for k, v in fields.items():
            if k in q4:
                continue
            parts = [q.get(f"{y}{m:02d}", {}).get(k) for m in (3, 6, 9)]
            if all(p is not None for p in parts):
                q4[k] = round(v - sum(parts), 2)
    # derived: 상·매각 and 정상화 등 for the long-table years
    for fields in q.values():
        if "res_wo_sale" not in fields and "res_writeoff" in fields and "res_sale" in fields:
            fields["res_wo_sale"] = round(fields["res_writeoff"] + fields["res_sale"], 2)
        if "res_normal_etc" not in fields and "res_total" in fields and "res_wo_sale" in fields:
            fields["res_normal_etc"] = round(fields["res_total"] - fields["res_wo_sale"], 2)
    return {k: v for k, v in sorted(q.items()) if v}


# --------------------------------------------------------------------------
# Panels for the 부실채권비율 card (see kr_bank_credit.build)
# --------------------------------------------------------------------------

SOURCE_NOTE = "금융감독원 보도자료 '국내은행 부실채권 현황(잠정)' PDF에서 읽은 값(분기별, 나중 보도자료의 수정치 우선)."


def _label(ym: str) -> str:
    return f"{ym[2:4]}.{int(ym[4:6]) // 3}Q"


def panels(doc: dict[str, Any], n: int = 16) -> list[dict[str, Any]]:
    q = merged(doc)
    keys = [k for k, f in q.items() if "new_total" in f and "res_total" in f][-n:]
    if len(keys) < 4:
        return []
    dates = [_label(k) for k in keys]
    g = lambda k, f, sign=1: (round(sign * q[k][f], 2) if f in q[k] else None)  # noqa: E731

    def other(k: str) -> float | None:
        f = q[k]
        if not all(x in f for x in ("new_total", "new_large", "new_sme", "new_hh")):
            return None
        return round(max(f["new_total"] - f["new_large"] - f["new_sme"] - f["new_hh"], 0.0), 2)

    out = [{
        "id": "npl_flow", "label": "신규·정리", "type": "stack", "unit": "조원", "dates": dates,
        "series": [
            {"label": "신규(대기업)", "values": [g(k, "new_large") for k in keys]},
            {"label": "신규(중소기업)", "values": [g(k, "new_sme") for k in keys]},
            {"label": "신규(가계)", "values": [g(k, "new_hh") for k in keys]},
            {"label": "신규(카드·기타)", "values": [other(k) for k in keys]},
            {"label": "상각·매각", "values": [g(k, "res_wo_sale", -1) for k in keys]},
            {"label": "정상화·담보회수 등", "values": [g(k, "res_normal_etc", -1) for k in keys]},
        ],
        "line": {"label": "순증(신규 − 정리)", "values": [round(q[k]["new_total"] - q[k]["res_total"], 2) for k in keys]},
        "note_ko": "분기 중 새로 부실(고정이하)로 분류된 여신(+)과 부실에서 빠져나간 여신(−). 선이 0보다 위면 부실채권 잔액이 늘어난 분기입니다. "
                   "상각·매각이 크면 은행이 부실을 장부에서 털어 낸 것이라, 부실비율이 낮아도 신규 발생이 같이 커지고 있는지 봐야 합니다. " + SOURCE_NOTE,
    }]
    split = [k for k in keys if any(f in q[k] for f in ("res_writeoff", "res_sale"))]
    if len(split) >= 4:
        out.append({
            "id": "npl_resolution", "label": "정리 방식", "type": "bars", "unit": "조원", "dates": [_label(k) for k in split],
            "series": [{"label": lab, "values": [g(k, f) for k in split]}
                       for lab, f in (("대손상각", "res_writeoff"), ("매각", "res_sale"),
                                      ("담보처분 회수", "res_collateral"), ("정상화", "res_normal"))],
            "note_ko": "분기 중 부실채권이 정리된 방식(조원). 대손상각·매각은 손실을 확정하고 장부에서 지우는 것이고, 담보처분·정상화는 실제로 회수되거나 연체가 풀린 것입니다. "
                       "보도자료 본문의 분기 수치라 일부 분기는 비어 있습니다. " + SOURCE_NOTE,
        })
    rk = [k for k, f in q.items() if "npl_mort" in f and "npl_large" in f][-n:]
    if len(rk) >= 4:
        out.append({
            "id": "npl_segments", "label": "부문별 부실비율", "type": "lines", "unit": "%", "dates": [_label(k) for k in rk],
            "series": [{"label": lab, "values": [g(k, f) for k in rk]}
                       for lab, f in (("대기업", "npl_large"), ("중소법인", "npl_smecorp"), ("개인사업자", "npl_soho"),
                                      ("주택담보대출", "npl_mort"), ("신용대출 등", "npl_hhcredit"), ("신용카드", "npl_card"))],
            "note_ko": "부문별 고정이하여신비율(%, 분기말). 주택담보대출·신용대출 구분은 FISIS API에 없고 보도자료에만 있습니다. " + SOURCE_NOTE,
        })
    return out

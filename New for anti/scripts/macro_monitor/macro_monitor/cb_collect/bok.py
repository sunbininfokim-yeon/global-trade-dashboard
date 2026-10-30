"""Bank of Korea Monetary Policy Board (금융통화위원회): decision, named dissent,
statement wording, calendar, roster, minutes.

Everything is read from bok.or.kr (Korean, no key). Four pieces:

  * the 통화정책방향 press release (board P0000559): the rate decision, the
    Committee's assessment, and -- since the February 2026 meeting -- one closing
    sentence with the vote ("위원 6명은 찬성하였으며, 황건일 위원은 ... 의견을 나타냈다").
    That sentence names only the *dissenters*; the members who voted for are not
    listed, so the for-side is the attendees of that meeting minus the dissenters.
  * the minutes (board B0000245, released ~19 days later): the attendee list.
  * the yearly meeting calendar (통화정책방향 결정회의 일정).
  * the members page (name, role, term).

The list pages are filled by an ajax call (listCont.do); the detail pages need a
menuNo or they answer 404.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from .common import collapse, fetch_bytes, fetch_text, pdf_text
from .hwp import hwp_paragraphs

BASE = "https://www.bok.or.kr"
LIST_URL = f"{BASE}/portal/singl/newsData/listCont.do"
SCHEDULE_URL = f"{BASE}/portal/singl/crncyPolicyDrcMtg/listYear.do?mtgSe=A&menuNo=200755"
ROSTER_URL = f"{BASE}/portal/main/contents.do?menuNo=201696"
PRESS_BOARD, PRESS_MENU = "P0000559", "200690"      # 통화정책 보도자료
MINUTES_BOARD, MINUTES_MENU = "B0000245", "200789"   # 금융통화위원회 의사록


def detail_url(board: str, ntt_id: str, menu: str) -> str:
    return f"{BASE}/portal/bbs/{board}/view.do?nttId={ntt_id}&menuNo={menu}"


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------

def search_url(keyword: str, page: int = 1, page_unit: int = 100) -> str:
    q = {"pageIndex": str(page), "pageUnit": str(page_unit), "targetDepth": "4", "menuNo": "200789",
         "syncMenuChekKey": "0", "depthSubMain": "", "subMainAt": "", "searchCnd": "1", "searchKwd": keyword}
    return f"{LIST_URL}?{urllib.parse.urlencode(q)}"


def parse_search(html: str) -> list[dict[str, str]]:
    """Rows of a search result: title, board id, nttId, registration date (YYYY-MM-DD)."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for li in soup.find_all("li"):
        a = li.find("a", href=re.compile(r"/portal/bbs/([A-Z]\d+)/view\.do\?nttId=(\d+)"))
        if not a:
            continue
        m = re.search(r"/portal/bbs/([A-Z]\d+)/view\.do\?nttId=(\d+)", a["href"])
        reg = re.search(r"등록일\s*(\d{4})\.(\d{2})\.(\d{2})", li.get_text(" "))
        rows.append({
            "title": collapse(a.get_text(" ")),
            "board": m.group(1),
            "ntt_id": m.group(2),
            "registered_on": f"{reg.group(1)}-{reg.group(2)}-{reg.group(3)}" if reg else "",
        })
    return rows


_DECISION_TITLE = re.compile(r"^통화정책방향\((\d{4})\.(\d{1,2})\.(\d{1,2})\)$")
_MINUTES_TITLE = re.compile(r"^금융통화위원회 의사록\((\d{4})년도? ?제(\d+)차\)\((\d{4})\.(\d{1,2})\.(\d{1,2})\)")


def decision_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Monetary-policy press releases (not the 의결사항 or blog rows that share the title) with their meeting date."""
    out = []
    for r in rows:
        m = _DECISION_TITLE.match(r["title"])
        if m and r["board"] == PRESS_BOARD:
            out.append({**r, "meeting_date": f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"})
    return out


def minutes_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    for r in rows:
        m = _MINUTES_TITLE.match(r["title"])
        if m and r["board"] == MINUTES_BOARD:
            out.append({**r, "meeting_date": f"{m.group(3)}-{int(m.group(4)):02d}-{int(m.group(5)):02d}",
                        "session_no": int(m.group(2))})
    return out


# --------------------------------------------------------------------------
# The decision press release
# --------------------------------------------------------------------------

_RATE = re.compile(
    r"기준금리를\s*(?:현재의\s*(?P<a>\d+\.\d+)\s*%\s*수준|현\s*수준\(\s*(?P<a2>\d+\.\d+)\s*%\s*\))에서\s*"
    r"(?:(?P<b>\d+\.\d+)\s*%\s*로\s*(?P<dir>상향|하향)\s*조정|유지)")
_VOTE_ALL = re.compile(r"금융통화위원\s*(\d+)명\s*모두\s*찬성")
_VOTE_SPLIT = re.compile(r"금융통화위원\s*(\d+)명은?\s*찬성하였으며,?\s*(.+)$")
_DISSENT = re.compile(
    r"((?:[가-힣]{2,4}\s*위원(?:\s*(?:과|와|,)\s*)?)+)(?:은|는)\s*기준금리를\s*(\d+\.\d+)\s*%\s*(?:로|를)?\s*(인상|인하|유지)")


def normalize_text(text: str) -> str:
    """The pages space punctuation inconsistently ("하였다 ." on some, "하였다." on others);
    normalised so a meeting-to-meeting comparison sees wording, not spacing."""
    t = collapse(text)
    t = re.sub(r"\s+([.,;:)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    return t


def parse_vote(paragraph: str) -> dict[str, Any] | None:
    """The closing vote sentence, or None when the release has none (before 2026-02)."""
    p = normalize_text(paragraph)
    m = _VOTE_ALL.search(p)
    if m:
        return {"favor_count": int(m.group(1)), "against": [], "unanimous": True, "text": p.lstrip("□ ").strip()}
    m = _VOTE_SPLIT.search(p)
    if not m:
        return None
    against = []
    for dm in _DISSENT.finditer(m.group(2)):
        for name in re.findall(r"([가-힣]{2,4})\s*위원", dm.group(1)):
            against.append({
                "name": name,
                "preferred_rate_pct": float(dm.group(2)),
                "direction": {"인상": "higher", "인하": "lower", "유지": "hold"}[dm.group(3)],
            })
    return {"favor_count": int(m.group(1)), "against": against, "unanimous": False, "text": p.lstrip("□ ").strip()}


def parse_decision(html: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div.dbdata")
    if body is None:
        raise ValueError(f"{meeting_date}: no statement body at {source_url}")
    paras = [normalize_text(p.get_text("")) for p in body.find_all("p")]
    paras = [p for p in paras if p and p != "통화정책방향"]
    first = next((p for p in paras if "다음 통화정책방향 결정시까지" in p), None)
    if first is None:
        raise ValueError(f"{meeting_date}: no decision paragraph at {source_url}")
    m = _RATE.search(first)
    if not m:
        raise ValueError(f"{meeting_date}: no base-rate sentence at {source_url}")
    prior = float(m.group("a") or m.group("a2"))
    new = float(m.group("b")) if m.group("b") else prior
    vote_para = next((p for p in paras if "찬성하였" in p), None)
    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "prior_rate_pct": prior,
        "rate_pct": new,
        "action": "raise" if new > prior else ("lower" if new < prior else "maintain"),
        "change_bp": int(round((new - prior) * 100)),
        "vote": parse_vote(vote_para) if vote_para else None,
        "paragraphs": [p for p in paras if p is not vote_para],
    }


_OUTLOOK_HINT = re.compile(r"(?:성장률|물가)[^.]*?(?:전망치|전망)\s*\((?:각각\s*)?\d")


def outlook_sentences(paragraphs: list[str]) -> list[str]:
    """Sentences that state the Bank's new growth / inflation projection against the
    previous round ("... 지난 5월 전망치(각각 2.6%, 2.1%)를 큰 폭 상회하는 3.3% 및 2.9%를 ..."),
    present only at the four meetings that carry a new forecast (Feb/May/Aug/Nov).
    Kept verbatim: the sentences vary too much in form to turn into a table without
    guessing which number is which."""
    out = []
    for para in paragraphs:
        for s in re.split(r"(?<=다\.)\s+", para):
            if "%" in s and _OUTLOOK_HINT.search(s):
                out.append(s.lstrip("□ ").strip())
    return out


# --------------------------------------------------------------------------
# Calendar, roster, minutes
# --------------------------------------------------------------------------

def parse_schedule(html: str, year: int) -> list[str]:
    """Decision dates of one year's 통화정책방향 결정회의 ("10월 22일(목)" rows), ISO, ascending."""
    soup = BeautifulSoup(html, "html.parser")
    text = collapse(soup.get_text(" "))
    out = []
    for m in re.finditer(r"(\d{2})월\s*(\d{2})일\s*\([월화수목금토일]\)", text):
        try:
            out.append(date(year, int(m.group(1)), int(m.group(2))).isoformat())
        except ValueError:
            continue
    return sorted(set(out))


def schedule_url(year: int) -> str:
    return f"{SCHEDULE_URL}&pYear={year}"


_MEMBER = re.compile(
    r"(?P<role>의장|위원)\s+(?P<name>[가-힣]{2,4})\s+(?P<hanja>[一-鿿]{2,4})\s+임\s*기\s+"
    r"(?P<s>\d{4}\.\s*\d{2}\.\s*\d{2})\s*~\s*(?P<e>\d{4}\.\s*\d{2}\.\s*\d{2})")


def _iso_dot(text: str) -> str:
    y, m, d = re.findall(r"\d+", text)
    return f"{y}-{m}-{d}"


def parse_roster(html: str) -> list[dict[str, Any]]:
    """The seven members with their role and term, from the 금융통화위원회 page.

    The Governor chairs (의장), the Deputy Governor is the one whose 선임절차 says
    부총재(당연직); the other five are 위원.
    """
    text = collapse(BeautifulSoup(html, "html.parser").get_text(" "))
    hits = list(_MEMBER.finditer(text))
    out = []
    for i, m in enumerate(hits):
        tail = text[m.end(): hits[i + 1].start() if i + 1 < len(hits) else m.end() + 200]
        role = "의장(총재)" if m.group("role") == "의장" else ("부총재" if "부총재(당연직)" in tail[:120] else "위원")
        out.append({"name": m.group("name"), "role": role,
                    "term_start": _iso_dot(m.group("s")), "term_end": _iso_dot(m.group("e"))})
    return out


def parse_minutes_attendance(text: str) -> dict[str, list[str]]:
    """Attendees and absentees from the first page of a Board meeting's minutes.

    pdfminer prints the header with a space between every syllable ("장 용 성 위 원"),
    so the segment is unspaced before the names are read.
    """
    flat = collapse(text)
    m = re.search(r"3\.\s*출\s*석\s*위\s*원(.*?)4\.\s*결\s*석\s*위\s*원(.*?)5\.\s*참\s*여\s*자", flat)
    if not m:
        raise ValueError("no 출석위원/결석위원 block in the minutes")

    def names(segment: str) -> list[str]:
        s = re.sub(r"\s+", "", segment)
        return re.findall(r"([가-힣]{2,4}?)(?:의장|위원)(?=\(|[가-힣]{2}|$)", s)

    present = names(m.group(1))
    absent = [] if re.sub(r"\s+", "", m.group(2)) == "없음" else names(m.group(2))
    return {"present": present, "absent": absent}


def minutes_pdf_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("/fileSrc/") and a["href"].endswith(".pdf"):
            return BASE + a["href"]
    return None


def fetch_minutes_attendance(ntt_id: str) -> dict[str, Any]:
    page_url = detail_url(MINUTES_BOARD, ntt_id, MINUTES_MENU)
    pdf_url = minutes_pdf_url(fetch_text(page_url, min_size=100000))
    if not pdf_url:
        raise ValueError(f"no pdf attached to {page_url}")
    return {"page_url": page_url, "pdf_url": pdf_url,
            **parse_minutes_attendance(pdf_text(fetch_bytes(pdf_url, min_size=20000)))}


# --------------------------------------------------------------------------
# Minutes (HWP): who attended, what members said, how the vote went
# --------------------------------------------------------------------------
#
# The minutes report members only as "some members" ("일부 위원"), never by name --
# except for dissent, which the deliberation-result paragraph names ("(다만, 황건일 위원은
# ... 반대의사를 표시하고 ...)"). That is the only place the earlier meetings' votes are
# recorded (the press release carries a vote sentence only since 2026-02), so the vote is
# read from here as well.

_Q_START = re.compile(
    r"^(?:(?:이와\s*관련하여|이와\s*함께|한편|또한|아울러|이어서|특히|다만|반면)\s+)?"
    r"(?P<q>(?:또\s*다른\s+|다른\s+)?(?P<base>일부|다수의?|대부분의?|모든|몇몇|소수의?|한)\s*위원들?)(?:은|는|이|도)(?=\s|$)")
_QUANT_GROUP = {"모든": "all", "대부분": "most", "다수": "many", "일부": "some", "몇몇": "some", "소수": "few", "한": "few"}
_HEAD_AGENDA = re.compile(r"^[〈<]\s*의안\s*제\s*\d+\s*호\s*[―\-–—]+\s*통화정책방향")
_JUNK = re.compile(r"[\u0100-\u02ff\u0900-\u0dff]+")     # stray bytes some records leave at a paragraph's end


def clean_paragraphs(paragraphs: list[str]) -> list[str]:
    out = []
    for p in paragraphs:
        p = unicodedata.normalize("NFKC", p)
        p = _JUNK.sub("", p)
        p = collapse(p)
        out.append(p)
    return out


def quantifier_of(paragraph: str) -> tuple[str, str] | None:
    """('다른 일부 위원', 'some') when a paragraph opens with a member-count expression."""
    m = _Q_START.match(paragraph)
    if not m:
        return None
    return collapse(m.group("q")), _QUANT_GROUP[m.group("base").rstrip("의")]


def _stance(paragraph: str, prior: float | None) -> tuple[str | None, float | None]:
    """'raise' / 'hold' / 'lower' and the target rate a member's opening sentence names."""
    nums = [float(x) for x in re.findall(r"(\d+\.\d+)\s*%", paragraph)]
    if "동결" in paragraph or "유지" in paragraph:
        return "hold", (nums[0] if nums else prior)
    if "인상" in paragraph:
        return "raise", (nums[-1] if nums else None)
    if "인하" in paragraph:
        return "lower", (nums[-1] if nums else None)
    return None, None


def _sections(paras: list[str]) -> dict[str, tuple[int, int]]:
    """Index ranges of the monetary-policy agenda item and its numbered parts."""
    start = next((i for i, p in enumerate(paras) if _HEAD_AGENDA.match(p)), None)
    if start is None:
        raise ValueError("no 통화정책방향 agenda item in the minutes")
    end = next((i for i in range(start + 1, len(paras)) if re.match(r"^[〈<]\s*의안|^\(별첨\)", paras[i])), len(paras))
    marks: dict[str, int] = {}
    for i in range(start, end):
        m = re.match(r"^\(\s*(\d)\s*\)\s*(위원 토의내용|한국은행 기준금리 결정에 관한 위원별 의견|토의결론|심의결과)", paras[i])
        if m:
            marks[m.group(2)] = i
    keys = {"위원 토의내용": "discussion", "한국은행 기준금리 결정에 관한 위원별 의견": "opinions", "토의결론": "conclusion", "심의결과": "result"}
    order = sorted((i, keys[k]) for k, i in marks.items())
    out = {}
    for n, (i, key) in enumerate(order):
        out[key] = (i + 1, order[n + 1][0] if n + 1 < len(order) else end)
    if "opinions" not in out or "result" not in out:
        raise ValueError("minutes lack the opinion or deliberation-result part")
    return out


def _blocks(paras: list[str], lo: int, hi: int, stop_at_heading: bool = True) -> list[dict[str, Any]]:
    """Paragraphs that open with a member-count phrase, each with the paragraphs that follow
    it (a staff reply, the member's own statement) up to the next such phrase or heading."""
    blocks: list[dict[str, Any]] = []
    for i in range(lo, hi):
        p = paras[i]
        q = quantifier_of(p)
        if q:
            blocks.append({"quantifier": q[0], "group": q[1], "text": p, "followups": []})
        elif blocks and p and not (stop_at_heading and re.match(r"^\(\s*[가-힣]\s*\)\s", p)):
            blocks[-1]["followups"].append(p)
    return blocks


def parse_minutes_hwp(paragraphs: list[str], *, prior_rate: float | None, rate: float | None) -> dict[str, Any]:
    paras = clean_paragraphs(paragraphs)
    parts = _sections(paras)

    # attendance (header): "장 용 성  위 원", "권 민 수  위 원 (부총재)"
    head_end = next((i for i, p in enumerate(paras) if p.startswith("6.")), len(paras))
    attend: dict[str, list[str]] = {"present": [], "absent": []}
    bucket = None
    for p in paras[:head_end]:
        compact = re.sub(r"\s+", "", p)
        if re.match(r"^3\.출석위원", compact):
            bucket = "present"
            continue
        if re.match(r"^4\.결석위원", compact):
            bucket = "absent"
            continue
        if re.match(r"^5\.참여자", compact):
            bucket = None
        if bucket:
            m = re.match(r"^([가-힣]{2,4})(?:의장|위원)", compact)
            if m:
                attend[bucket].append(m.group(1))

    lo, hi = parts["discussion"] if "discussion" in parts else (0, 0)
    subsections = []
    cur = None
    for i in range(lo, hi):
        p = paras[i]
        if re.match(r"^\(\s*[가-힣]\s*\)\s", p):
            cur = {"title": p, "start": i + 1}
            subsections.append(cur)
    for n, sub in enumerate(subsections):
        sub_hi = subsections[n + 1]["start"] - 1 if n + 1 < len(subsections) else hi
        sub["blocks"] = _blocks(paras, sub["start"], sub_hi)
        del sub["start"]
    if not subsections and hi > lo:
        subsections = [{"title": "위원 토의내용", "blocks": _blocks(paras, lo, hi)}]

    olo, ohi = parts["opinions"]
    opinion_blocks = _blocks(paras, olo, ohi)
    distribution = None
    members = []
    for b in opinion_blocks:
        if distribution is None and "견해를 나타" in b["text"] and "국내외 금융" in b["text"]:
            distribution = b["text"]
            continue
        stance, target = _stance(b["text"], prior_rate)
        members.append({"quantifier": b["quantifier"], "group": b["group"], "stance": stance, "target_rate_pct": target,
                        "heading": b["text"], "statement": b["followups"]})

    rlo, rhi = parts["result"]
    result_paras = paras[rlo:rhi]
    conclusion = " ".join(paras[slice(*parts["conclusion"])]) if "conclusion" in parts else None
    vote = parse_minutes_vote(result_paras, present=attend["present"], prior_rate=prior_rate, rate=rate)

    return {
        **attend,
        "discussion": {"subsections": subsections},
        "opinions": {"distribution": distribution, "members": members, "conclusion": conclusion},
        "vote": vote,
    }


_DISSENT_NOTE = re.compile(r"^\(?다만,?\s*(?P<who>.+?)\s*(?:은|는)\s*한국은행\s*기준금리를\s*(?P<what>.+?)\s*(?:명백히\s*)?반대의사")
_ALT = re.compile(r"(?:(?P<bp>\d+(?:\.\d+)?)\s*%\s*(?:p|포인트)\s*(?P<dir>인상|인하)|(?P<hold>동결|유지))(?:하|할|하는|하여)?")


def parse_minutes_vote(result_paras: list[str], *, present: list[str], prior_rate: float | None, rate: float | None) -> dict[str, Any] | None:
    """The vote as the deliberation-result paragraph records it: unanimous ('위원 전원 찬성으로
    가결') or the members named in '(다만, X 위원은 ... 반대의사를 표시하고 ... 주장하였음.)'."""
    text = " ".join(result_paras)
    against: list[dict[str, Any]] = []
    note = next((p for p in result_paras if p.startswith("(다만") or "반대의사" in p), None)
    if note:
        m = re.match(r"^\(?다만,?\s*(?P<who>.+?)(?:은|는)\s*한국은행\s*기준금리", note)
        names = re.findall(r"([가-힣]{2,4})\s*위원", m.group("who") if m else note)
        alt = None
        after = note.split("기준금리", 1)[-1] if "기준금리" in note else note
        for am in _ALT.finditer(after):
            alt = am
        direction, alt_rate = None, None
        if alt and alt.group("hold"):
            # "현 수준에서 동결할 것을 주장" -- the member wanted the rate left where it was
            direction = "hold"
            alt_rate = prior_rate
        elif alt and alt.group("dir") and prior_rate is not None:
            direction = "higher" if alt.group("dir") == "인상" else "lower"
            alt_rate = round(prior_rate + (1 if direction == "higher" else -1) * float(alt.group("bp")), 2)
        against = [{"name": n, "preferred_rate_pct": alt_rate, "direction": direction} for n in names]
    elif "전원 찬성" not in text:
        return None
    favor = len(present) - len(against) if present else None
    return {"favor_count": favor, "against": against, "unanimous": not against,
            "text": (note or "위원 전원 찬성으로 가결하였음.").strip("()"), "source": "minutes"}


def hwp_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("/fileSrc/") and a["href"].endswith(".hwp"):
            return BASE + a["href"]
    return None


def fetch_minutes(ntt_id: str | None = None, *, page_url: str | None = None,
                  prior_rate: float | None = None, rate: float | None = None) -> dict[str, Any]:
    """Attendance, discussion, member opinions and the vote from a meeting's minutes (HWP).
    Falls back to the PDF's attendee list when no HWP is attached."""
    page_url = page_url or detail_url(MINUTES_BOARD, ntt_id or "", MINUTES_MENU)
    html = fetch_text(page_url, min_size=100000)
    hurl = hwp_url(html)
    pdf_url = minutes_pdf_url(html)
    if hurl:
        parsed = parse_minutes_hwp(hwp_paragraphs(fetch_bytes(hurl, min_size=20000)), prior_rate=prior_rate, rate=rate)
        return {"page_url": page_url, "pdf_url": pdf_url, "hwp_url": hurl, **parsed}
    if not pdf_url:
        raise ValueError(f"no minutes file attached to {page_url}")
    return {"page_url": page_url, "pdf_url": pdf_url,
            **parse_minutes_attendance(pdf_text(fetch_bytes(pdf_url, min_size=20000)))}


# --------------------------------------------------------------------------
# 경제전망 (the quarterly Economic Outlook) -- the numeric table
# --------------------------------------------------------------------------
#
# The 통화정책방향 text describes the new forecast in prose whose sentences vary too much to
# read numbers out of ("... 지난 5월 전망치(각각 2.6%, 2.1%)를 큰 폭 상회하는 3.3% 및 2.9%를 ...").
# The same day the Bank publishes the 경제전망 summary as a press release whose PDF carries the
# forecast tables, with the previous round's figure in brackets under each new one. Read from
# there: the label, the year and the bracket decide which number is which.

_OUTLOOK_TITLE = re.compile(r"^경제전망\((\d{4})년 (\d{1,2})월\)$")
# (id, label, unit, pattern). A pattern must be followed by a number, so the words in a chart title
# ("<국내 GDP 전망경로>") are not taken for a row.
_GROWTH_ROWS = [("gdp", "GDP 성장률", "%", r"GDP(?=\s+-?\d)"), ("consumption", "민간소비", "%", r"민간소비(?=\s+-?\d)"),
                ("goods_exports", "재화수출", "%", r"재화수출(?=\s+-?\d)"), ("construction", "건설투자", "%", r"건설투자(?=\s+-?\d)"),
                ("equipment", "설비투자", "%", r"설비투자(?=\s+-?\d)")]
_PRICE_ROWS = [("cpi", "소비자물가 상승률", "%", r"소비자물가(?:\s*상승률)?\s*(?:\(%\)\d?\)?)?(?=\s+-?\d)"),
               ("core_cpi", "근원물가 상승률", "%", r"근원물가(?:\s*상승률)?\s*(?:\(%\)\d?\)?)?(?=\s+-?\d)"),
               ("current_account", "경상수지", "억달러", r"경상수지(?:\s*\(억달러\))?(?=\s+-?\d)"),
               ("employment_change", "취업자수 증감", "만명", r"취업자수\s*증감(?:\s*\(만명\)\d?\)?)?(?=\s+-?\d)"),
               ("employment_rate", "고용률", "%", r"고용률(?:\s*\(%\)\d?\)?)?(?=\s+-?\d)")]
_PLAIN = re.compile(r"(?<![\w.\[])(-?\d[\d,]*(?:\.\d+)?)(?![\d.,]*\s*[\])])(?!\))")
_BRACKET = re.compile(r"\[\s*(-?\d[\d,]*(?:\.\d+)?)\s*\]")


def outlook_release_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Search rows that are the 경제전망 summary press release, with the meeting date they came out with."""
    out = []
    for r in rows:
        if _OUTLOOK_TITLE.match(r["title"]) and r["registered_on"]:
            out.append({**r, "meeting_date": r["registered_on"]})
    return out


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _table_rows(segment: str, spec: list[tuple[str, str, str, str]], years: list[int], forecast: list[bool]) -> list[dict[str, Any]]:
    """Rows of one summary table.

    The layout varies from round to round: the previous round's figure comes in brackets,
    either right after each new value ("3.3 [2.6] 2.9 [2.1]") or all together at the end
    ("2.0 1.0 1.8 1.9 [0.9] [1.6]"). What is constant is the count -- one plain number per
    column and a bracketed figure for the first forecast columns that existed last time, in
    column order -- so a row is read by counting, and dropped (not guessed) when the counts
    do not fit.
    """
    marks = []
    for key, label, unit, pattern in spec:
        m = re.search(pattern, segment)
        if m:
            marks.append((m.start(), m.end(), key, label, unit))
    marks.sort()
    out = []
    for n, (start, end, key, label, unit) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(segment)
        body = segment[end:stop]
        plain = [_num(x) for x in _PLAIN.findall(_BRACKET.sub(" ", body))]
        priors = [_num(x) for x in _BRACKET.findall(body)]
        if len(plain) != len(years) or len(priors) > len(years) - 1:
            continue
        vals = []
        for i, y in enumerate(years):
            prior = priors[i - 1] if 1 <= i <= len(priors) else None
            vals.append({"year": y, "value": plain[i], "prior": prior, "forecast": forecast[i]})
        out.append({"id": key, "label_ko": label, "unit": unit, "values": vals})
    return out


def parse_outlook_table(text: str) -> dict[str, Any] | None:
    """The two forecast tables of a 경제전망 summary (PDF text in row order, pypdf's reading order)."""
    flat = collapse(text)
    prior = re.search(r"\[\s*\]\s*(?:내)?는\s*(\d{2}\.\d{1,2})월\s*전망", flat)
    rows: list[dict[str, Any]] = []
    years: list[int] = []
    for title, spec in (("국내 성장률 전망", _GROWTH_ROWS), ("물가·경상수지·고용 전망", _PRICE_ROWS)):
        i = flat.find(title)
        if i < 0:
            continue
        seg = flat[i: i + 1400]
        for stop in ("주:", "자료:"):
            k = seg.find(stop)
            if k > 0:
                seg = seg[:k]
        hm = re.search(r"((?:\d{4}e?\)?\s+){2,4})", seg)
        if not hm:
            continue
        heads = re.findall(r"(\d{4})(e?)", hm.group(1))
        ys = [int(y) for y, _ in heads]
        fc = [bool(e) for _, e in heads]
        years = years or ys
        rows += _table_rows(seg[hm.end():], spec, ys, fc)
    if not rows:
        return None
    return {"prior_made_in": prior.group(1) if prior else None, "years": years, "rows": rows}


def outlook_pdf_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("/fileSrc/") and a["href"].endswith(".pdf"):
            return BASE + a["href"]
    return None


def fetch_outlook_table(ntt_id: str) -> dict[str, Any]:
    from .common import pdf_text_by_row

    page_url = detail_url("B0000502", ntt_id, PRESS_MENU)
    pdf_url = outlook_pdf_url(fetch_text(page_url, min_size=100000))
    if not pdf_url:
        raise ValueError(f"no pdf attached to {page_url}")
    table = parse_outlook_table(pdf_text_by_row(fetch_bytes(pdf_url, min_size=5000)))
    if not table:
        raise ValueError(f"no forecast table found in {pdf_url}")
    return {"source_url": page_url, "pdf_url": pdf_url, **table}

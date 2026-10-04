"""The weekly result table for the export-control catalogue.

survey.py records that a week was looked at; this module says what a person
has to read that week, as one Markdown table set that becomes the body of
the weekly survey PR:

1. deadlines  -- live rows whose `until` (or `review_valid_until`) has passed
                 or falls within DEADLINE_DAYS. A passed `until` is shown on
                 the monitor as 「기한 경과」 until someone reads the source.
2. links      -- each row's source URL fetched once. Only a 404/410 is called
                 broken; a block, a timeout or a 5xx is "자동 확인 불가",
                 because government sites refuse bots far more often than
                 they move documents.
3. candidates -- export ban / restriction / lift notices the reports pipeline
                 put on boards.export_controls in the last NOTICE_DAYS days,
                 matched to catalogue rows by issuing country and commodity:
                 an update to an existing row, or a new row with a draft.
4. open questions and coverage, carried over from survey.py.

Nothing here edits the catalogue. Drafts are low-confidence skeletons for a
person to check against the original and then paste into a module file.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTICES = HERE.parents[1] / "public" / "data" / "commodity_reports_v1.json"
REPORTS = HERE / "surveys" / "reports"

DEADLINE_DAYS = 21
NOTICE_DAYS = 8
# Measures that change what a country lets out. Sanctions, enforcement and
# dialogue notices (mostly OFAC designations of people) are not catalogue
# material.
CANDIDATE_MEASURES = {"export_ban", "export_restriction", "suspension", "list_adjustment"}
LEVEL_FROM_MEASURE = {
    "export_ban": "prohibited",
    "export_restriction": "restricted",
    "list_adjustment": "restricted",
    "suspension": "lifted",
}
MEASURE_KO = {
    "export_ban": "수출금지", "export_restriction": "수출통제", "suspension": "유예·해제",
    "list_adjustment": "목록조정",
}
# Words a translated headline or Gemini's `items` use for a catalogue slug.
ITEM_ALIASES = {
    "fuel": "petroleum_products", "fuels": "petroleum_products", "gasoline": "petroleum_products",
    "petrol": "petroleum_products", "diesel": "petroleum_products",
    "petroleum products": "petroleum_products", "motor fuel": "petroleum_products",
    "wheat flour": "wheat", "flour": "wheat", "non-basmati rice": "rice", "broken rice": "rice",
    "white rice": "rice", "rare earth": "rare_earths", "rare earths": "rare_earths",
    "palm oil": "palm_oil", "crude palm oil": "palm_oil", "cpo": "palm_oil",
    "nickel ore": "nickel", "bauxite ore": "bauxite", "sunflower oil": "sunflower_oil",
    "sunflower seeds": "sunflower_seed", "onion": "onions", "onions": "onions",
}

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# --- 1. deadlines ---------------------------------------------------------------

def deadline_flags(doc, today):
    out = []
    for row in doc.get("controls") or []:
        if row.get("level") == "lifted":
            continue
        for field, label in (("until", "조치 종료일"), ("review_valid_until", "재검토 기한")):
            day = _day(row.get(field))
            if not day:
                continue
            left = (day - today).days
            if left < 0:
                state = "지남"
            elif left <= DEADLINE_DAYS:
                state = "임박"
            else:
                continue
            out.append({"id": row.get("id"), "country": row.get("country_ko") or row.get("country"),
                        "field": field, "label": label, "date": day.isoformat(),
                        "days": left, "state": state, "url": row.get("url")})
    out.sort(key=lambda f: f["days"])
    return out


# --- 2. links ---------------------------------------------------------------------

def _fetch_status(url, timeout=20.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 -- timeouts, TLS, DNS: all "could not check"
        return None


def link_checks(doc, fetch=_fetch_status):
    out = []
    seen = {}
    for row in doc.get("controls") or []:
        url = row.get("url") or ""
        if not url:
            continue
        if url not in seen:
            seen[url] = fetch(url)
        code = seen[url]
        if code is not None and 200 <= code < 400:
            state = "ok"
        elif code in (404, 410):
            state = "깨짐"
        else:
            state = "자동 확인 불가"
        out.append({"id": row.get("id"), "url": url, "status": code, "state": state})
    return out


# --- 3. candidates -------------------------------------------------------------------

def load_notices(path=NOTICES):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    by_id = {it.get("id"): it for it in doc.get("items") or []}
    return [by_id[i] for i in (doc.get("boards") or {}).get("export_controls") or [] if i in by_id]


def _notice_day(it):
    return _day(it.get("published_at")) or _day(it.get("first_seen_at"))


def _slugs(it, known):
    """Catalogue slugs a notice names: tracked commodities, Gemini's items and
    the English headline, mapped through ITEM_ALIASES."""
    found = set(it.get("commodities") or [])
    words = [str(x).lower() for x in (it.get("control") or {}).get("items") or []]
    title = " ".join(filter(None, [(it.get("title") or {}).get("en"),
                                   (it.get("title") or {}).get("original")])).lower()
    for w in words:
        slug = ITEM_ALIASES.get(w) or w.replace(" ", "_")
        if slug in known or w in ITEM_ALIASES:
            found.add(slug)
    for phrase, slug in ITEM_ALIASES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", title):
            found.add(slug)
    for slug in known:
        if re.search(rf"\b{re.escape(slug.replace('_', ' '))}\b", title):
            found.add(slug)
    return found


def _category_of(slug, universe):
    for category, block in (universe.get("categories") or {}).items():
        for country in block.get("countries") or []:
            if slug in (country.get("commodities") or []):
                return category
    return None


def candidates(doc, notices, universe, today):
    """(candidates, skipped): skipped counts recent export-control notices
    that name no commodity -- chips, firearms, aviation licences -- which are
    the US/China technology regime, not this commodity catalogue."""
    known = set(universe.get("commodity_keys") or [])
    rows = doc.get("controls") or []
    since = today - timedelta(days=NOTICE_DAYS)
    out = []
    skipped = 0
    for it in notices:
        control = it.get("control") or {}
        if control.get("measure") not in CANDIDATE_MEASURES:
            continue
        day = _notice_day(it)
        if not day or day < since:
            continue
        iso = control.get("issuer")
        slugs = _slugs(it, known | set(ITEM_ALIASES.values()))
        if not slugs:
            skipped += 1
            continue
        matches = [r for r in rows if r.get("iso") == iso and slugs & set(r.get("commodities") or [])]
        title = it.get("title") or {}
        entry = {
            "date": day.isoformat(), "issuer": iso, "body": control.get("issuer_body_ko") or it.get("agency_ko"),
            "measure": control.get("measure"), "title_ko": title.get("ko") or title.get("original"),
            "title_original": title.get("original"), "url": it.get("url"),
            "commodities": sorted(slugs), "matches": [r.get("id") for r in matches],
        }
        if not matches:
            slug = sorted(slugs)[0] if slugs else None
            entry["draft"] = {
                "id": f"{(iso or 'xxx').lower()}-{(slug or 'tbd').replace('_', '-')}",
                "country": None, "country_ko": None, "iso": iso,
                "category": _category_of(slug, universe) if slug else None,
                "commodities": [slug] if slug else [],
                "level": LEVEL_FROM_MEASURE.get(control.get("measure")),
                "measure_type": None,
                "since": day.strftime("%Y-%m"),
                "measure_ko": title.get("ko") or "",
                "source": control.get("issuer_body") or it.get("agency"),
                "url": it.get("url"),
                "confidence": "low",
                "verified_at": None,
                "needs_reconfirm": True,
            }
        out.append(entry)
    out.sort(key=lambda c: c["date"], reverse=True)
    return out, skipped


# --- 4. render ------------------------------------------------------------------------

def _cell(text):
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def build(doc, universe, *, today, entry, notices=None, links=None):
    notices = load_notices() if notices is None else notices
    cands, skipped = candidates(doc, notices, universe, today)
    return {
        "week": entry.get("week"),
        "run_on": today.isoformat(),
        "deadlines": deadline_flags(doc, today),
        "links": links or [],
        "candidates": cands,
        "skipped_no_commodity": skipped,
        "notice_count": len(notices),
        "entry": entry,
    }


def render(rep):
    entry = rep["entry"]
    d, links, cands = rep["deadlines"], rep["links"], rep["candidates"]
    bad_links = [x for x in links if x["state"] != "ok"]
    updates = [c for c in cands if c["matches"]]
    new = [c for c in cands if not c["matches"]]
    lines = [
        f"# 수출통제 주간 점검 {rep['week']} ({rep['run_on']})",
        "",
        "| 항목 | 건수 |",
        "|---|---|",
        f"| 기한 지남·임박 | {len(d)} |",
        f"| 링크 깨짐 / 자동 확인 불가 | {sum(x['state'] == '깨짐' for x in links)} / "
        f"{sum(x['state'] == '자동 확인 불가' for x in links)} (확인 {len(links)}) |",
        f"| 이번 주 공고 → 기존 행 갱신 후보 | {len(updates)} |",
        f"| 이번 주 공고 → 신규 행 후보 | {len(new)} |",
        f"| 카탈로그 행 / 재확인 필요 | {entry.get('control_count')} / {len(entry.get('needs_reconfirm') or [])} |",
        f"| 감시 쌍: 현행 / 해제 / 미확인 | {entry['pairs']['live']} / {entry['pairs']['lifted']} / {entry['pairs']['unchecked']} |",
        "",
        "## 1. 기한",
        "",
    ]
    if d:
        lines += ["| 행 | 국가 | 구분 | 날짜 | 상태 |", "|---|---|---|---|---|"]
        for f in d:
            when = f"{-f['days']}일 지남" if f["days"] < 0 else f"{f['days']}일 남음"
            lines.append(f"| `{f['id']}` | {_cell(f['country'])} | {f['label']} | {f['date']} | **{f['state']}** ({when}) |")
    else:
        lines.append(f"{DEADLINE_DAYS}일 안에 끝나거나 이미 끝난 조치 없음.")
    lines += ["", "## 2. 원문 링크", ""]
    if not links:
        lines.append("이번 실행에서는 링크를 확인하지 않았다.")
    elif bad_links:
        lines += ["| 행 | 상태 | 응답 | 링크 |", "|---|---|---|---|"]
        for x in bad_links:
            lines.append(f"| `{x['id']}` | {x['state']} | {x['status'] or '응답 없음'} | {_cell(x['url'])} |")
        lines += ["", "「자동 확인 불가」는 사이트가 봇을 막거나 시간 초과된 것이다. 깨졌다는 뜻이 아니다."]
    else:
        lines.append(f"{len(links)}개 링크 모두 응답.")
    lines += ["", f"## 3. 최근 {NOTICE_DAYS}일 공고 → 카탈로그 후보", ""]
    if not cands:
        lines.append(f"원자재를 명시한 수출 금지·제한·해제 공고 없음 (보드 전체 {rep['notice_count']}건 중).")
    else:
        lines += ["| 날짜 | 발표국 | 조치 | 공고 | 품목 | 판단 |", "|---|---|---|---|---|---|"]
        for c in cands:
            verdict = ("갱신 후보: " + ", ".join(f"`{m}`" for m in c["matches"])) if c["matches"] else "**신규 후보**"
            title = f"[{_cell(c['title_ko'])}]({c['url']})" if c.get("url") else _cell(c["title_ko"])
            lines.append(f"| {c['date']} | {c['issuer']} | {MEASURE_KO.get(c['measure'], c['measure'])} | {title} | "
                         f"{', '.join(c['commodities']) or '—'} | {verdict} |")
        if new:
            drafts = [c["draft"] for c in new]
            lines += ["", "<details><summary>신규 후보 초안 (원문 확인 후 분류 모듈 파일에 넣을 것)</summary>", "",
                      "```json", json.dumps(drafts, ensure_ascii=False, indent=2), "```", "", "</details>"]
        lines += ["", "조치 종류·품목은 공고 제목 한 줄을 Gemini 가 읽은 값이다. 금지인지 제한인지는 원문으로 정한다."]
    if rep.get("skipped_no_commodity"):
        lines += ["", f"원자재를 명시하지 않은 수출통제 공고 {rep['skipped_no_commodity']}건(반도체·무기·항공 등 기술 통제)은 "
                      "후보에서 뺐다. 수출통제 모니터 「최근 공고」 탭에서 볼 수 있다."]
    lines += ["", "## 4. 열린 질문", ""]
    lines += [f"- {q}" for q in entry.get("open_questions") or []] or ["없음."]
    lines += ["", "---", "이 표는 카탈로그를 고치지 않는다. 행이 없다고 통제가 없는 것이 아니다."]
    return "\n".join(lines) + "\n"


def summary_counts(rep):
    return {
        "deadlines": len(rep["deadlines"]),
        "links_broken": sum(x["state"] == "깨짐" for x in rep["links"]),
        "links_unchecked": sum(x["state"] == "자동 확인 불가" for x in rep["links"]),
        "update_candidates": sum(1 for c in rep["candidates"] if c["matches"]),
        "new_candidates": sum(1 for c in rep["candidates"] if not c["matches"]),
    }


def write(rep, directory=REPORTS):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{rep['week']}.md"
    path.write_text(render(rep), encoding="utf-8")
    (directory / "latest.md").write_text(render(rep), encoding="utf-8")
    return path


def now_day():
    return datetime.now(timezone.utc).date()

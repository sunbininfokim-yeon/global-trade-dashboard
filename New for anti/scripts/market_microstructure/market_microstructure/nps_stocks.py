"""국민연금 종목별 지분 (코스피 시총 상위 N) + 공시 일정.

Two published sources, both free:

* Year-end holdings list -- fund.nps.or.kr 「국내주식 종목별 투자 현황(YYYY년 말)」 xlsx,
  every name the fund holds, with value, weight in the asset class and stake.
  Published once a year, in Q3 of the following year. The files carry names
  only (no codes), so they are matched to the KOSPI listing by name.
* 5% 대량보유 reports -- OpenDART `majorstock.json`, filtered to the filer
  국민연금공단. Filed only when the stake is ≥5% and moves ≥1%p; under the
  시행령 §154 special case the deadline is the 10th of the month after the
  change (일반투자 목적) or after the quarter (단순투자 목적).

Between two filings nothing is published: the share count of the last filing
times today's price is the only current-value estimate, and it says so.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import Any, Callable

NPS_EQUITY_PAGE = "https://fund.nps.or.kr/oprtprcn/ivsmprcn/getOHED0003M0.do"
NPS_FILE_BASE = "https://fund.nps.or.kr"
DART_MAJORSTOCK = "https://opendart.fss.or.kr/api/majorstock.json"
NPS_FILER = "국민연금공단"


# --- year-end holdings xlsx ---------------------------------------------------

def parse_holdings_links(raw_html: str) -> dict[str, str]:
    """year -> download URL from the 투자종목 list on the domestic-equity page."""
    out = {}
    for href, year in re.findall(r'href="(/fileDown\.do\?atchFileId=[\w]+&(?:amp;)?atchFileSn=\d+)"[^>]*>\s*(\d{4})\s*<', raw_html):
        out[year] = NPS_FILE_BASE + href.replace("&amp;", "&")
    return out


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace("%", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _as_pct(values: list[float | None], header: str) -> list[float | None]:
    """The files switch between fractions (0.0776), percent numbers (8.52) and
    '7.28%' strings from year to year. A column whose largest value is ≤1 and
    whose header has no (%) is a fraction."""
    fin = [v for v in values if v is not None]
    frac = bool(fin) and max(fin) <= 1.0 and "(%)" not in header
    return [None if v is None else (v * 100 if frac else v) for v in values]


def parse_holdings_xlsx(blob: bytes) -> list[dict[str, Any]]:
    import openpyxl

    ws = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
    head_i = next((i for i, r in enumerate(rows) if r and r[0] == "번호"), None)
    if head_i is None:
        raise ValueError("NPS holdings xlsx: header row not found")
    head = [str(h or "") for h in rows[head_i]]
    col = {name: next(i for i, h in enumerate(head) if h.startswith(name)) for name in ("종목명", "평가액", "자산군 내 비중", "지분율")}
    body = [r for r in rows[head_i + 1:] if isinstance(r[0], (int, float)) and r[col["종목명"]]]
    w = _as_pct([_num(r[col["자산군 내 비중"]]) for r in body], head[col["자산군 내 비중"]])
    s = _as_pct([_num(r[col["지분율"]]) for r in body], head[col["지분율"]])
    out = []
    for r, wi, si in zip(body, w, s):
        out.append({"name": str(r[col["종목명"]]).strip(), "value_eok": _num(r[col["평가액"]]),
                    "weight_pct": None if wi is None else round(wi, 4),
                    "stake_pct": None if si is None else round(si, 3)})
    if len(out) < 100:
        raise ValueError(f"NPS holdings xlsx: only {len(out)} rows")
    return out


def norm_name(s: str) -> str:
    return re.sub(r"[\s()·.]", "", str(s)).upper()


# --- DART 5% reports ------------------------------------------------------------

def nps_reports(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """국민연금공단's filings among a company's 대량보유 reports, oldest first."""
    out = []
    for r in rows or []:
        if NPS_FILER not in str(r.get("repror") or ""):
            continue
        d = str(r.get("rcept_dt") or "")
        pct = _num(r.get("stkrt"))
        if len(d) != 8 or pct is None:
            continue
        out.append({
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "kind": "dart_5pct", "stake_pct": pct,
            "chg_pp": _num(r.get("stkrt_irds")), "shares": _num(r.get("stkqy")),
            "reason": str(r.get("report_resn") or "").strip()[:80],
            "rcept_no": str(r.get("rcept_no") or ""),
        })
    return sorted(out, key=lambda x: (x["date"], x["rcept_no"]))


def fetch_dart_majorstock(corp_code: str, key: str) -> list[dict[str, Any]]:
    import requests

    r = requests.get(DART_MAJORSTOCK, params={"crtfc_key": key, "corp_code": corp_code}, timeout=30)
    r.raise_for_status()
    d = r.json()
    status = str(d.get("status"))
    if status == "013":             # 조회된 데이터가 없습니다
        return []
    if status != "000":
        raise RuntimeError(f"DART {status}: {d.get('message')}")
    return d.get("list") or []


# --- assemble -------------------------------------------------------------------

def build_nps_stocks(*, top: list[dict[str, Any]], previous: dict[str, Any] | None,
                     holdings_links: dict[str, str] | None,
                     fetch_file: Callable[[str], bytes] | None,
                     corp_index: dict[str, list[str]],
                     fetch_dart: Callable[[str], list[dict[str, Any]]] | None) -> dict[str, Any]:
    """top: [{ticker, label_ko, marcap}] in market-cap order.

    Year-end lists already parsed are kept from the previous file; a year is
    downloaded only when its link first appears (once a year). DART is asked
    every run for every name; when it fails, the stored reports stay.
    """
    prev = previous or {}
    errors: list[str] = []
    year_end: dict[str, dict[str, Any]] = dict(prev.get("year_end") or {})
    for year, url in sorted((holdings_links or {}).items()):
        if year in year_end or fetch_file is None:
            continue
        try:
            rows = parse_holdings_xlsx(fetch_file(url))
        except Exception as e:  # noqa: BLE001
            errors.append(f"NPS holdings {year}: {type(e).__name__}: {e}")
            continue
        by = {norm_name(r["name"]): r for r in rows}
        matched = {}
        for t in top:
            r = by.get(norm_name(t["label_ko"]))
            if r:
                matched[t["ticker"]] = {k: r[k] for k in ("value_eok", "weight_pct", "stake_pct")}
        total = sum(r["value_eok"] or 0 for r in rows)
        year_end[year] = {"url": url, "n_holdings": len(rows), "total_eok": round(total), "tickers": matched}

    prev_reports = {t: v.get("reports") or [] for t, v in (prev.get("by_ticker") or {}).items()}
    dart_ok = dart_rows = 0
    reporters: dict[str, int] = {}
    by_ticker: dict[str, Any] = {}
    for t in top:
        code = t["ticker"]
        reports = prev_reports.get(code, [])
        corp = (corp_index.get(code) or [None])[0]
        if fetch_dart and corp:
            try:
                raw = fetch_dart(corp)
                reports = nps_reports(raw)
                dart_ok += 1
                dart_rows += len(raw)
                for r in raw[:50]:
                    reporters[str(r.get("repror") or "")] = reporters.get(str(r.get("repror") or ""), 0) + 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"DART {code}: {type(e).__name__}: {e}")
        points = [{"date": f"{y}-12-31", "kind": "year_end", "stake_pct": v["tickers"][code]["stake_pct"],
                   "value_eok": v["tickers"][code]["value_eok"]}
                  for y, v in sorted(year_end.items()) if code in v["tickers"]]
        points += reports
        points.sort(key=lambda p: p["date"])
        if not points:
            continue
        last = points[-1]
        est = None
        if last.get("stake_pct") is not None and t.get("marcap"):
            est = round(last["stake_pct"] / 100 * t["marcap"] / 1e12, 2)
        by_ticker[code] = {"label_ko": t["label_ko"], "rank": t.get("rank"), "points": points,
                           "reports": reports, "latest": last, "est_value_jo_now": est}
    if fetch_dart and dart_ok == 0 and top:
        errors.append("DART: no company answered")
    n_nps = sum(len(v["reports"]) for v in by_ticker.values())
    if fetch_dart and dart_ok and n_nps == 0:
        # The NPS holds 5%+ of most large caps, so zero filings means the
        # filter or the payload changed, not that there is nothing to show.
        common = sorted(reporters.items(), key=lambda kv: -kv[1])[:8]
        errors.append(f"DART: {dart_ok} companies, {dart_rows} filings, none by {NPS_FILER}; "
                      f"top filers: {common}")
    return {
        "quality": "observed" if by_ticker else "missing",
        "year_end": year_end,
        "by_ticker": by_ticker,
        "dart_checked": dart_ok,
        "dart_filings_seen": dart_rows,
        "errors": errors,
        "method_ko": ("연말 전 종목 목록(국민연금, 이름으로 코스피 상장목록과 맞춤)과 DART 5% 대량보유 보고(보고자 국민연금공단)를 "
                      "날짜순으로 이은 것. 두 공시 사이의 매매는 공개되지 않습니다. '지금 추정 평가액'은 마지막 공시 지분율 × 오늘 시가총액."),
        "source": [NPS_EQUITY_PAGE, "https://opendart.fss.or.kr (majorstock.json)"],
    }


# --- disclosure calendar ----------------------------------------------------------

def _next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def schedule(today: date, *, nps_history: list[dict[str, Any]], year_end_years: list[str]) -> list[dict[str, Any]]:
    """What comes next and when. Rule-based where a rule exists; the NPS
    month-end portfolio has no published date, so its next appearance is
    estimated from the gaps between months the job has seen arrive."""
    out = [{"id": "foreign", "label_ko": "외국인 보유율 (종목별·시장)", "next": _next_business_day(today).isoformat(),
            "basis_ko": "매 거래일 19시(KST) 수집", "kind": "rule"}]
    tenth = date(today.year, today.month, 10)
    if today > tenth:
        tenth = date(today.year + (today.month == 12), today.month % 12 + 1, 10)
    out.append({"id": "dart_5pct", "label_ko": "국민연금 5% 대량보유 보고 (DART)", "next": tenth.isoformat(),
                "basis_ko": "일반투자 목적: 변동이 있던 달의 다음 달 10일까지 (단순투자는 분기 다음 달 10일). 지분 5% 이상·1%p 이상 변동만",
                "kind": "deadline"})
    months = [h for h in nps_history if h.get("kind", "month_end") == "month_end"]
    seen = [(h["month"], h.get("first_seen")) for h in months if h.get("first_seen")]
    last_month = months[-1]["month"] if months else None
    nxt = None
    if last_month:
        y, m = int(last_month[:4]), int(last_month[5:7])
        nxt = f"{y + (m == 12)}-{m % 12 + 1:02d}"
    lags = []
    for mo, fs in seen:
        y, m = int(mo[:4]), int(mo[5:7])
        end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        lags.append((date.fromisoformat(fs) - end).days)
    est = None
    if nxt and len(lags) >= 2:
        lags.sort()
        lag = lags[len(lags) // 2]
        y, m = int(nxt[:4]), int(nxt[5:7])
        end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        est = (end + timedelta(days=lag)).isoformat()
    out.append({"id": "nps_month", "label_ko": f"국민연금 월말 포트폴리오 ({nxt or '—'} 말 기준)", "next": est,
                "basis_ko": (f"공식 공개일 없음. 지금까지 본 공개 간격 중앙값 {lags[len(lags) // 2]}일로 추정" if est
                             else "공식 공개일 없음. 새 달이 올라온 날을 기록 중 — 두 달 이상 쌓이면 추정일을 표시"),
                "kind": "estimate" if est else "unknown"})
    last_year = max(year_end_years) if year_end_years else None
    ny = int(last_year) + 1 if last_year else today.year - 1
    out.append({"id": "nps_year_end", "label_ko": f"국민연금 종목별 보유 목록 ({ny}년 말 기준)", "next": f"{ny + 1}-Q3",
                "basis_ko": "기금운용지침: 전년도 말 기준 세부내역은 금년도 3분기 공시", "kind": "rule"})
    return out

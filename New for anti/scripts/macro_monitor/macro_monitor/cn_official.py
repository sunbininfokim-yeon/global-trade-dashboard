"""China, straight from the National Bureau of Statistics (keyless HTML).

The China card's real GDP growth came from the World Bank's annual series, so in November 2026 it
still showed 2025 (5.0%) while the NBS had published Q3 2026 on 2026-10-21. Every quarterly
'Preliminary Accounting Results of GDP for the ... Quarter of YYYY' release carries a full table of
year-on-year growth by quarter since 2021 ('Table 2 Year-on-Year Growth Rate of GDP'), so one page
gives the whole series.

Foreign exchange reserves come from SAFE (State Administration of Foreign Exchange). The card used the
IMF's international-liquidity series, which in November 2026 still ended in June; SAFE publishes the
month-end 'Official Reserve Assets' table within the first week of the next month, one xlsx per year.
The total (foreign currency, IMF reserve position, SDRs, gold, other) is the same concept as the IMF
series (June 2026: IMF 3,786.1, SAFE 3,786.3 bn USD), so SAFE's months replace the IMF's where SAFE has
them and the IMF keeps the older ones.
"""

from __future__ import annotations

import html as _html
import io
import re
from typing import Any, Callable
from urllib.parse import urljoin

from .us_public_series import Spec

NBS_LIST = "https://www.stats.gov.cn/english/PressRelease/"
NBS_PAGES = ["index.html", "index_1.html", "index_2.html", "index_3.html"]

GDP_SPEC = Spec(
    "gdp_yoy", "quarterly", "%", "pct1",
    "실질GDP 전년 동기 대비(분기)입니다. 중국 국가통계국(NBS) 분기 GDP 예비 집계 발표의 'Table 2 Year-on-Year Growth "
    "Rate of GDP'를 그대로 옮겼습니다(가격 불변, 원계열). 다음 분기 발표 때 이전 분기가 수정되면 그대로 따라갑니다.",
    "nbs:gdp_q_yoy", (NBS_LIST,), "quarterly", label_ko="실질GDP YoY")


SAFE_LIST = "https://www.safe.gov.cn/en/DataandStatistics/"
SAFE_PAGES = ["index.html", "index_1.html", "index_2.html", "index_3.html"]

RESERVES_SPEC = Spec(
    "fx_reserves", "monthly", "bn_usd", "bn0usd",
    "외환보유액(금 시가 포함 공식 준비자산 합계, 월말, 십억 달러)입니다. 중국 국가외환관리국(SAFE) 'Official Reserve "
    "Assets' 표의 합계(외화·IMF 포지션·SDR·금·기타)이고, SAFE 표가 없는 예전 달은 같은 개념의 IMF 국제유동성 통계입니다.",
    "safe:official_reserve_assets", (SAFE_LIST,), "monthly", label_ko="외환보유액")


def _text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t)))


def find_gdp_release(get: Callable[[str], str]) -> str:
    """URL of the newest 'Preliminary Accounting Results of GDP' release on the English list pages."""
    seen: list[str] = []
    for page in NBS_PAGES:
        try:
            raw = get(urljoin(NBS_LIST, page))
        except Exception as exc:  # noqa: BLE001 -- a missing later page just ends the walk
            seen.append(f"{page}: {exc}")
            break
        seen.append(f"{page}: {len(raw)} chars")
        m = re.search(r'href="([^"]+)"[^>]*>\s*(?:\d+\.)?\s*Preliminary Accounting Results of GDP', raw)
        if m:
            return urljoin(urljoin(NBS_LIST, page), m.group(1))
    raise ValueError(f"NBS: no 'Preliminary Accounting Results of GDP' release on the first list pages ({'; '.join(seen)})")


def parse_gdp_table(raw_html: str) -> list[tuple[str, float]]:
    """[(quarter start 'YYYY-MM-01', yoy %)] from Table 2 of a quarterly GDP release."""
    t = _text(raw_html)
    m = re.search(r"Table 2 Year-on-Year Growth Rate of GDP.*?Year Q1 Q2 Q3 Q4 (.*?)(?:Note|Table 3|$)", t)
    if not m:
        raise ValueError("NBS: 'Table 2 Year-on-Year Growth Rate of GDP' not found")
    out: list[tuple[str, float]] = []
    for y, vals in re.findall(r"\b(20\d{2})((?:\s+-?\d+(?:\.\d+)?){1,4})", m.group(1)):
        for q, v in enumerate(vals.split()):
            out.append((f"{y}-{3 * q + 1:02d}-01", float(v)))
    if len(out) < 8:
        raise ValueError(f"NBS: GDP table too short ({len(out)} quarters)")
    return sorted(out)


def fetch_gdp(get: Callable[[str], str]) -> tuple[list[tuple[str, float]], str]:
    url = find_gdp_release(get)
    return parse_gdp_table(get(url)), url


def find_reserve_files(get: Callable[[str], str], years: int = 2) -> list[tuple[int, str]]:
    """[(year, page url)] of the newest `years` 'Official Reserve Assets (YYYY)' pages, newest first."""
    found: dict[int, str] = {}
    seen: list[str] = []
    for page in SAFE_PAGES:
        try:
            raw = get(urljoin(SAFE_LIST, page))
        except Exception as exc:  # noqa: BLE001 -- a missing later page just ends the walk
            seen.append(f"{page}: {exc}")
            break
        seen.append(f"{page}: {len(raw)} chars")
        for href, y in re.findall(r'href="([^"]+)"[^>]*>\s*Official Reserve Assets\s*[(（]\s*(20\d\d)\s*[)）]', raw):
            found.setdefault(int(y), urljoin(urljoin(SAFE_LIST, page), href))
        if len(found) >= years:
            break
    if not found:
        raise ValueError(f"SAFE: no 'Official Reserve Assets (YYYY)' page on the first list pages ({'; '.join(seen)})")
    return sorted(found.items(), reverse=True)[:years]


def xlsx_link(page_html: str, page_url: str) -> str:
    m = re.search(r'href="([^"]+\.xlsx)"', page_html)
    if not m:
        raise ValueError(f"SAFE: no xlsx on {page_url}")
    return urljoin(page_url, m.group(1))


def _month_cell(c: Any) -> str | None:
    """'YYYY-MM-01' for a header cell. SAFE writes months as numbers (2026.01) except October, which
    as a number would read 2026.1 -- some years keep it as a number, some as the text '2026.10'."""
    if isinstance(c, float) and 2000 < c < 2100:
        y, m = f"{c:.2f}".split(".")
    elif isinstance(c, str) and re.fullmatch(r"\s*20\d\d\.\d{1,2}\s*", c):
        y, m = c.strip().split(".")
    else:
        return None
    return f"{y}-{int(m):02d}-01" if 1 <= int(m) <= 12 else None


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.replace("\xa0", "").replace(",", "").strip()
        return float(t) if re.fullmatch(r"-?\d+(?:\.\d+)?", t) else None
    return None


def parse_reserves_xlsx(data: bytes) -> list[tuple[str, float]]:
    """[(month 'YYYY-MM-01', total official reserve assets, bn USD)]. Each month has a USD column and
    an SDR column; the month label sits over the USD one. Months not yet published are blank."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out: dict[str, float] = {}
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        months: dict[int, str] = {}
        for r in rows:
            cols = {j: d for j, c in enumerate(r) if (d := _month_cell(c))}
            if len(cols) >= 2:
                months = cols
                break
        total = next((r for r in rows if re.search(r"合计|Total", " ".join(str(c) for c in r[:2] if c is not None))), None)
        if not months or total is None:
            continue
        for j, d in months.items():
            v = _num(total[j]) if j < len(total) else None
            if v is not None:
                out[d] = round(v / 10, 2)            # 亿美元 (100 million USD) -> bn USD
    if not out:
        raise ValueError("SAFE: no month header with a 'Total' row in the reserves xlsx")
    return sorted(out.items())


def fetch_reserves(get: Callable[[str], str], get_bytes: Callable[[str], bytes], years: int = 2
                   ) -> tuple[list[tuple[str, float]], list[str]]:
    points: dict[str, float] = {}
    urls: list[str] = []
    for _, page in find_reserve_files(get, years):
        xlsx = xlsx_link(get(page), page)
        points.update(parse_reserves_xlsx(get_bytes(xlsx)))
        urls.append(page)
    return sorted(points.items()), urls


def load_reserves_cache(path) -> tuple[list[tuple[str, float]], list[str], str] | None:
    """The last SAFE read that succeeded: GitHub's runners do not always reach safe.gov.cn, and the
    IMF step before this one rewrites the card every run, so without it a failed read would roll the
    card back to the IMF's older months."""
    import json
    from pathlib import Path

    f = Path(path)
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    return [tuple(x) for x in d["points"]], d["source_urls"], d["fetched_at"]


def save_reserves_cache(path, points: list[tuple[str, float]], urls: list[str], fetched_at: str) -> None:
    import json
    from pathlib import Path

    Path(path).write_text(json.dumps({"schema": "cn_safe_reserves_cache_v1", "fetched_at": fetched_at,
                                      "source_urls": urls, "points": [list(x) for x in points]},
                                     ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def merge_history(card: dict[str, Any], safe: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """The card's current monthly history (month-end dates, IMF) with SAFE's months laid over it."""
    hist = (card.get("history") or {}).get("10y") or {}
    by = {f"{d[:7]}-01": v for d, v in zip(hist.get("dates") or [], hist.get("values") or []) if v is not None}
    by.update(dict(safe))
    return sorted(by.items())


def http_get(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def http_get_bytes(url: str) -> bytes:
    import requests

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    return r.content


def build_reserves_patch(points: list[tuple[str, float]], urls: list[str], *, retrieved_at: str) -> dict[str, Any]:
    from . import us_public_series as ups

    patch = ups.build_patch(RESERVES_SPEC, points, retrieved_at=retrieved_at)
    patch["source_urls"] = [*urls, SAFE_LIST]
    return patch


def build_gdp_patch(points: list[tuple[str, float]], url: str, *, retrieved_at: str) -> dict[str, Any]:
    from . import us_public_series as ups
    from .za_public_series import with_gaps

    patch = ups.build_patch(GDP_SPEC, with_gaps(points, 3), retrieved_at=retrieved_at)
    patch["source_urls"] = [url, NBS_LIST]
    return patch

"""China, straight from the National Bureau of Statistics (keyless HTML).

The China card's real GDP growth came from the World Bank's annual series, so in November 2026 it
still showed 2025 (5.0%) while the NBS had published Q3 2026 on 2026-10-21. Every quarterly
'Preliminary Accounting Results of GDP for the ... Quarter of YYYY' release carries a full table of
year-on-year growth by quarter since 2021 ('Table 2 Year-on-Year Growth Rate of GDP'), so one page
gives the whole series.
"""

from __future__ import annotations

import html as _html
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


def _text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t)))


def find_gdp_release(get: Callable[[str], str]) -> str:
    """URL of the newest 'Preliminary Accounting Results of GDP' release on the English list pages."""
    for page in NBS_PAGES:
        try:
            raw = get(urljoin(NBS_LIST, page))
        except Exception:  # noqa: BLE001 -- a missing later page just ends the walk
            break
        m = re.search(r'href="([^"]+)"[^>]*>\s*(?:\d+\.)?\s*Preliminary Accounting Results of GDP', raw)
        if m:
            return urljoin(urljoin(NBS_LIST, page), m.group(1))
    raise ValueError("NBS: no 'Preliminary Accounting Results of GDP' release on the first list pages")


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


def http_get(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def build_gdp_patch(points: list[tuple[str, float]], url: str, *, retrieved_at: str) -> dict[str, Any]:
    from . import us_public_series as ups
    from .za_public_series import with_gaps

    patch = ups.build_patch(GDP_SPEC, with_gaps(points, 3), retrieved_at=retrieved_at)
    patch["source_urls"] = [url, NBS_LIST]
    return patch

"""Export amounts (not year-on-year rates) for the countries whose export card was a fixture rate.

An export card shows the amount; clicking it draws the monthly bars and, under them, the year-on-year
growth as a line (computed by the page from the same series). Where a free official source exists:

  - Singapore: non-oil domestic exports (NODX), SingStat Table Builder M451001 row 4.2, S$ thousand;
  - Israel: goods exports, US dollars, FRED XTEXVA01ILM667S (OECD main economic indicators).
    The old Israeli card was "high-tech exports"; there is no free source for that breakdown, so the
    card is now the goods total and says so.

Same contract as the other public-series modules: every value is a published observation, a series that
cannot be read leaves the previous card, nothing is estimated. Not here, and why: Taiwan, Vietnam and
Hong Kong (no keyless source found: Hong Kong's statistics API answers 403, Taiwan's customs site returns
an empty page, Vietnam publishes PDF/Excel only), and Taiwan's export *orders* (a survey rate, not an amount).
Korea's export cards are in kr_public_series.py.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

SINGSTAT = "https://tablebuilder.singstat.gov.sg/api/table/tabledata/{table}?seriesNoORrowNo={row}"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
_MONTHS = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

ups._FORMATS.update({"bn1sgd": lambda v: f"S${v:,.1f}B", "bn1usd": lambda v: f"${v:,.1f}B"})


def parse_singstat(doc: dict[str, Any], row_no: str) -> Points:
    """Monthly points of one row of a SingStat table ("2026 Aug" -> 2026-08-01); a value that is not a
    number is skipped. A row that is not in the answer raises."""
    rows = (doc.get("Data") or {}).get("row") or []
    row = next((r for r in rows if str(r.get("seriesNo")) == row_no), None)
    if row is None:
        raise ValueError(f"SingStat answer has no row {row_no!r}")
    out: Points = []
    for c in row.get("columns") or []:
        parts = str(c.get("key", "")).split()
        if len(parts) != 2 or parts[1] not in _MONTHS:
            continue
        try:
            out.append((f"{int(parts[0]):04d}-{_MONTHS[parts[1]]:02d}-01", float(str(c["value"]).replace(",", ""))))
        except (ValueError, KeyError):
            continue
    if not out:
        raise ValueError(f"SingStat row {row_no!r} has no observations")
    return sorted(out)


def fetch_singstat(table: str, row_no: str, tries: int = 3) -> tuple[Points, str | None]:
    url = SINGSTAT.format(table=urllib.parse.quote(table), row=urllib.parse.quote(row_no, safe=","))
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=90) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            row = next(r for r in doc["Data"]["row"] if str(r.get("seriesNo")) == row_no)
            return parse_singstat(doc, row_no), row.get("uoM")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, StopIteration, KeyError, ValueError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"SingStat {table}: {last}")


@dataclass(frozen=True)
class ExportSpec:
    iso3: str
    old_id: str
    new_id: str
    spec: Spec


def _spec(new_id: str, unit: str, fmt: str, note: str, source: str, urls: tuple[str, ...], label: str) -> Spec:
    return Spec(new_id, "monthly", unit, fmt, note, source, urls, "monthly", label_ko=label)


EXPORTS: list[ExportSpec] = [
    ExportSpec("SGP", "nodx_yoy", "nodx_sgd", _spec(
        "nodx_sgd", "bn_sgd", "bn1sgd", "비석유 국내수출(NODX) 월별 금액(십억 싱가포르달러)입니다. 실물 경기의 핵심 지표이며 전자·제약·화학이 중심입니다. 카드를 열면 월별 막대 아래에 전년 동월 대비 성장률 선이 함께 나옵니다. 싱가포르 통계청 Table Builder M451001(기업청 자료).",
        "singstat:M451001", ("https://tablebuilder.singstat.gov.sg/table/TS/M451001",), "NODX(비석유 국내수출)")),
    ExportSpec("ISR", "high_tech_export_yoy", "export_il", _spec(
        "export_il", "bn_usd", "bn1usd", "상품 수출 월별 금액(십억 달러)입니다. 예전 카드는 '하이테크 수출'이었지만 그 세부 분류는 무료 출처가 없어 상품 수출 총액을 싣습니다. 카드를 열면 월별 막대 아래에 전년 동월 대비 성장률 선이 함께 나옵니다. FRED XTEXVA01ILM667S(OECD).",
        "fred:XTEXVA01ILM667S", ("https://fred.stlouisfed.org/series/XTEXVA01ILM667S",), "수출(상품, 달러)")),
]


def series_for(e: ExportSpec, fred: Callable[[str], Points] = ups.fetch_fred, singstat=fetch_singstat) -> Points:
    if e.iso3 == "SGP":
        pts, unit = singstat("M451001", "4.2")
        if "thousand" not in (unit or "").lower():
            raise ValueError(f"unexpected SingStat unit {unit!r}")
        return ups.scale(pts, 1e-6)                                   # S$ thousand -> S$ billion
    if e.iso3 == "ISR":
        return ups.scale(fred("XTEXVA01ILM667S"), 1e-9)               # USD -> billion USD
    raise KeyError(e.iso3)


def build_patch(e: ExportSpec, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    patch = ups.build_patch(e.spec, points, retrieved_at=retrieved_at)
    patch["yoy_line"] = True
    return patch


def apply(country: dict[str, Any], e: ExportSpec, patch: dict[str, Any]) -> bool:
    krs.rename_indicator(country, e.old_id, e.new_id, {})
    by_id = {i["id"]: i for i in country["indicators"]}
    ind = by_id.get(e.new_id)
    if ind:
        ind.pop("analog_ko", None)     # "same slot as Korea's semiconductor exports" no longer describes the card
    changed = bool(ind) and ups.apply_patch(ind, patch)
    if changed:
        ups.sync_chips(country, by_id, {e.new_id})
    changed = krs.sync_chip_units(country, by_id, {e.new_id}) or changed
    ups.refresh_status_summary(country)
    return changed

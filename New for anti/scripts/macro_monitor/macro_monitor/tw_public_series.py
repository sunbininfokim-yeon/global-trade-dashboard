"""Taiwan: the Central Bank of the Republic of China (Taiwan)'s statistics database API. Keyless.

    https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={code}
returns a whole table as JSON: data.structure holds the column dimensions (Table1 x Table2 x ...,
row-major), data.dataSets the rows ['2026M07', v1, v2, ...] with '-' for an empty cell. The codes are
listed in the database's own API note (中央銀行統計資料庫 API 說明文件).

Cards (table / column):
  cpi_yoy          CPI, YoY                           EF07M01 / 消費者物價指數年增率     monthly
  fx_reserves      foreign exchange reserves, US$      EF07M01 / 外匯存底(百萬美元)       monthly
  cbc_discount     CBC discount rate                  EG2AM01 / 重貼現率                  monthly
  bond_10y         10-year government bond, secondary EG43M01 / 十年期政府公債次級市場利率  monthly
  m2_yoy           M2 daily average, YoY               EF01M01 / 貨幣總計數-M2|日平均|年增率  monthly
  m2_vs_2019       M2 daily average against 2019-12   EF01M01 / 貨幣總計數-M2|日平均|金額
  current_account  BOP current account, US$            BPP2Q01 / 經常帳-淨額              quarterly
  export_tw        BOP goods exports, US$              BPP2Q01 / 商品-收入                quarterly
The export card replaces 'export_yoy_tw' (a YoY rate) with an amount, like the other countries' export
cards. It is on the balance-of-payments basis and quarterly: the customs figure (monthly) is published
by the Ministry of Finance and DGBAS, whose sites sit behind a Cloudflare challenge; DGBAS's own
statistics API (nstatdb.dgbas.gov.tw, "sdmx" mode) answers metadata that stops in 2021 and returns its
HTML page for data queries. For the same reason real GDP, core CPI, export orders (MOEA) and the
current account as % of GDP are not here. PMI (CIER), foreign equity flows (TWSE), life insurers' FX
assets and hedge ratios have no source in this module. TAIEX is a Yahoo series in live_catalog.py.
"""

from __future__ import annotations

import itertools
import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

CBC_API = "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName={code}"
CBC_PAGE = "https://cpx.cbc.gov.tw/Range/RangeSelect?pxfilename={code}.px"
UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "bn1usd": lambda v: f"${v:,.1f}B",
    "bn0usd": lambda v: f"${v:,.0f}B",
})


def _tls() -> ssl.SSLContext:
    """Full certificate and hostname verification -- minus Python 3.13's new X.509 *strict* profile, which
    rejects the CBC's chain (a CA certificate without a Subject Key Identifier; curl and browsers accept it,
    and so does Python 3.12, which the refresh workflow runs)."""
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    return ctx


def fetch_table(code: str, tries: int = 3) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(CBC_API.format(code=code), headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90, context=_tls()) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            return json.loads(doc) if isinstance(doc, str) else doc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"CBC {code}: {last}")


def period_key(p: str) -> str | None:
    """'2026M07' -> 2026-07-01, '2026Q2' -> 2026-04-01; an annual '2026' -> None."""
    p = str(p).strip()
    if len(p) == 7 and p[4] == "M" and p[:4].isdigit() and p[5:].isdigit():
        return f"{p[:4]}-{p[5:]}-01"
    if len(p) == 6 and p[4] == "Q" and p[:4].isdigit() and p[5] in "1234":
        return f"{p[:4]}-{(int(p[5]) - 1) * 3 + 1:02d}-01"
    return None


def columns(doc: dict[str, Any]) -> list[str]:
    """Column labels in data order: the product of the structure's tables, joined with '|'."""
    st = doc["data"]["structure"]
    tables = [st[k] for k in sorted(st, key=lambda k: int(k.replace("Table", "")))]
    return ["|".join(x["data"].strip() for x in combo) for combo in itertools.product(*tables)]


def column(doc: dict[str, Any], label: str) -> Points:
    cols = columns(doc)
    if label not in cols:
        raise ValueError(f"CBC table has no column {label!r}")
    j = cols.index(label) + 1
    out: Points = []
    for row in doc["data"]["dataSets"]:
        d = period_key(row[0])
        if not d or j >= len(row):
            continue
        try:
            out.append((d, float(str(row[j]).replace(",", ""))))
        except ValueError:
            continue                                     # '-': no figure
    if not out:
        raise ValueError(f"CBC column {label!r} has no observations")
    return sorted(out)


@dataclass(frozen=True)
class TwSpec:
    spec: Spec
    code: str
    label: str
    scale: float = 1.0
    vs_2019: bool = False
    gap_months: int = 1


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, code: str) -> Spec:
    return Spec(id_, cadence, unit, fmt, note, f"cbc:{code}", (CBC_PAGE.format(code=code),), cadence, label_ko=label)


SPECS: dict[str, TwSpec] = {t.spec.id: t for t in [
    TwSpec(_s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
              "소비자물가지수 전년 동월 대비입니다. 대만 중앙은행 통계DB EF07M01(주계총처 자료).", "EF07M01"),
           "EF07M01", "消費者物價指數年增率"),
    TwSpec(_s("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
              "외환보유액(월말, 십억 달러)입니다. 대만 중앙은행 통계DB EF07M01.", "EF07M01"),
           "EF07M01", "外匯存底(百萬美元)", scale=1e-3),
    TwSpec(_s("cbc_discount", "monthly", "%", "pct2", "CBC 재할인율",
              "중앙은행 재할인율(정책금리)입니다. 대만 중앙은행 통계DB EG2AM01.", "EG2AM01"),
           "EG2AM01", "重貼現率"),
    TwSpec(_s("bond_10y", "monthly", "%", "pct2", "국채 10년",
              "10년 국채 유통시장 수익률(월)입니다. 대만 중앙은행 통계DB EG43M01.", "EG43M01"),
           "EG43M01", "十年期政府公債次級市場利率"),
    TwSpec(_s("m2_yoy", "monthly", "%", "pct1", "M2 전년비",
              "M2(일평균) 전년 동월 대비입니다 — 중앙은행의 M2 목표 기준. 대만 중앙은행 통계DB EF01M01.", "EF01M01"),
           "EF01M01", "貨幣總計數-M2|日平均|年增率"),
    TwSpec(_s("m2_vs_2019", "monthly", "%", "pct1", "M2 vs 2019-12",
              "M2(일평균) 2019년 12월 대비 증가율입니다. 대만 중앙은행 통계DB EF01M01.", "EF01M01"),
           "EF01M01", "貨幣總計數-M2|日平均|金額", vs_2019=True),
    TwSpec(_s("current_account", "quarterly", "bn_usd", "bn1usd", "경상수지",
              "국제수지 경상수지(분기, 십억 달러)입니다. 대만 중앙은행 통계DB BPP2Q01.", "BPP2Q01"),
           "BPP2Q01", "經常帳-淨額", scale=1e-3, gap_months=3),
    TwSpec(_s("export_tw", "quarterly", "bn_usd", "bn1usd", "상품수출(국제수지)",
              "상품 수출(국제수지 기준 '상품-수입', 분기, 십억 달러)입니다. 대만 중앙은행 통계DB BPP2Q01. 통관 기준 월별 수출은 재정부·주계총처 사이트가 봇 차단(Cloudflare) 뒤에 있어 싣지 못하고, 국제수지 기준 분기 값으로 대신합니다. 카드를 열면 막대 아래에 전년 동기 대비 성장률 선이 함께 나옵니다.", "BPP2Q01"),
           "BPP2Q01", "商品-收入", scale=1e-3, gap_months=3),
]}

RENAMES = {"export_yoy_tw": "export_tw"}
YOY_LINE_IDS = frozenset({"export_tw"})


def series_for(spec_id: str, table: Callable[[str], dict[str, Any]]) -> Points:
    t = SPECS[spec_id]
    pts = column(table(t.code), t.label)
    if t.scale != 1.0:
        pts = ups.scale(pts, t.scale)
    if t.vs_2019:
        pts = ups.vs_base(pts, "2019-12-01")
    return pts


def build_patch(spec_id: str, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    from .za_public_series import with_gaps
    t = SPECS[spec_id]
    patch = ups.build_patch(t.spec, with_gaps(points, t.gap_months), retrieved_at=retrieved_at)
    if spec_id in YOY_LINE_IDS:
        patch["yoy_line"] = True
    return patch


def apply_all(twn: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    for old, new in RENAMES.items():
        if new in patches:
            krs.rename_indicator(twn, old, new, {})
    by_id = {i["id"]: i for i in twn["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    for k in changed:
        by_id[k].pop("analog_ko", None)
    ups.sync_chips(twn, by_id, set(changed))
    units = krs.sync_chip_units(twn, by_id, {k for k in patches if k in by_id})
    before = dict(twn.get("data_status_summary") or {})
    ups.refresh_status_summary(twn)
    return {"changed": changed, "summary_changed": units or before != twn["data_status_summary"]}

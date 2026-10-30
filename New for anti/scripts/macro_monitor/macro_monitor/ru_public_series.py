"""Russia: the Bank of Russia (CBR) and the Moscow Exchange (MOEX). Keyless.

  usdrub, cnyrub      CBR official rates, daily        www.cbr.ru/scripts/XML_dynamic.asp (R01235, R01375)
  cbr_key_rate        CBR key rate, daily              DailyInfo web service, KeyRateXML
  cpi_yoy             CPI, YoY (Rosstat, as the CBR republishes it)   www.cbr.ru/hd_base/infl/
  fx_reserves_total   international reserves, US$     DailyInfo web service, mrrfXML (p1)
  m2_yoy, m2_vs_2019  money supply M2 (national definition)   www.cbr.ru/vfs/statistics/credit_statistics/monetary_agg.xlsx
  ofz_10y             10-year point of the CBR zero-coupon OFZ curve   www.cbr.ru/hd_base/zcyc_params/zcyc/
  moex_index, rtsi    IMOEX / RTS index, monthly closes   iss.moex.com (candles, interval=31)

Dates. Reserves and money supply are stocks "on the 1st" of a month; the value on 1 September is the
end of August, and is dated so. The zero-coupon curve is one date per request, so month-end values are
kept in config/ru_cbr_series_v1.json and only months not yet kept are asked for (the first run backfills).

Not here, and why: real GDP, unemployment, core CPI (Rosstat -- rosstat.gov.ru does not answer from
here, and FRED/OECD stopped Russia in 2021-22); current account (no machine-readable CBR file found);
"usable" reserves and the frozen share (analysts' estimates, not published figures); NWF liquid assets,
OFZ auction cover, Urals-Brent spread, PMIs, labour shortage index, CDS, CBR total assets.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
CBR_DYNAMIC = "https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1={d1}&date_req2={d2}&VAL_NM_RQ={code}"
CBR_SOAP = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
CBR_INFL = "https://www.cbr.ru/hd_base/infl/?UniDbQuery.Posted=True&UniDbQuery.From={d1}&UniDbQuery.To={d2}"
CBR_M2 = "https://www.cbr.ru/vfs/statistics/credit_statistics/monetary_agg.xlsx"
CBR_ZCYC = "https://www.cbr.ru/hd_base/zcyc_params/zcyc/?DateTo={d}"
MOEX_CANDLES = ("https://iss.moex.com/iss/engines/stock/markets/index/securities/{sec}/candles.json"
                "?from={d1}&interval=31&iss.meta=off&candles.columns=begin,end,close")
MOEX_DAILY = ("https://iss.moex.com/iss/history/engines/stock/markets/index/securities/{sec}.json"
              "?from={d1}&iss.meta=off&history.columns=TRADEDATE,CLOSE")
CACHE = Path(__file__).resolve().parent.parent / "config" / "ru_cbr_series_v1.json"
HISTORY_FROM = date(2016, 1, 1)

ups._FORMATS.update({
    "pct2": lambda v: f"{v:.2f}%",
    "fx2": lambda v: f"{v:,.2f}",
    "num0": lambda v: f"{v:,.0f}",
    "bn0usd": lambda v: f"${v:,.0f}B",
})


def _get(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 60,
         tries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url[:60]}: {last}")


def _num(s: str) -> float:
    return float(str(s).replace("\xa0", "").replace(" ", "").replace(",", "."))


def prev_month(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y:04d}-{m:02d}-01"


# --------------------------------------------------------------------------
# Parsers (pure)
# --------------------------------------------------------------------------

def parse_dynamic(xml: str) -> Points:
    """<Record Date="01.08.2026"><Nominal>1</Nominal><Value>79,4637</Value></Record> -> per-unit rate."""
    out: Points = []
    for d, nom, val in re.findall(r'<Record Date="(\d\d\.\d\d\.\d{4})"[^>]*>\s*<Nominal>([^<]+)</Nominal>\s*<Value>([^<]+)</Value>', xml):
        dd, mm, yy = d.split(".")
        out.append((f"{yy}-{mm}-{dd}", _num(val) / _num(nom)))
    if not out:
        raise ValueError("CBR rates answer has no records")
    return sorted(out)


def parse_keyrate(xml: str) -> Points:
    out = [(d, _num(r)) for d, r in re.findall(r"<DT>(\d{4}-\d\d-\d\d)T[^<]*</DT>\s*<Rate>([^<]+)</Rate>", xml)]
    if not out:
        raise ValueError("CBR key rate answer has no records")
    return sorted(set(out))


def parse_mrrf(xml: str, field: str = "p1") -> Points:
    """Stocks on the 1st of a month -> dated as the end of the month before."""
    out = []
    for block in re.findall(r"<mr>(.*?)</mr>", xml, re.S):
        d = re.search(r"<D0>(\d{4}-\d\d)-\d\dT", block)
        v = re.search(rf"<{field}>([^<]+)</{field}>", block)
        if d and v:
            out.append((prev_month(d.group(1) + "-01"), _num(v.group(1))))
    if not out:
        raise ValueError("CBR reserves answer has no records")
    return sorted(out)


def parse_infl(html: str) -> Points:
    """Rows |MM.YYYY| key rate | inflation YoY | target| -> monthly inflation."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 3 and re.fullmatch(r"\d\d\.\d{4}", cells[0]):
            try:
                out.append((f"{cells[0][3:]}-{cells[0][:2]}-01", _num(cells[2])))
            except ValueError:
                continue
    if not out:
        raise ValueError("CBR inflation table has no rows")
    return sorted(out)


def parse_m2(xlsx: bytes) -> dict[str, Points]:
    """{'level': ..., 'yoy': ...} for 'Денежный агрегат М2'; the 1st-of-month stocks dated a month earlier."""
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(xlsx), read_only=True, data_only=True)
    out: dict[str, Points] = {}
    for key, sheet in (("level", "Денежные агрегаты"), ("yoy", "Годовые темпы прироста")):
        rows = list(wb[sheet].iter_rows(values_only=True))
        header = rows[0]
        row = next(r for r in rows[1:] if r and str(r[0]).strip().replace("M", "М") in ("Денежный агрегат М2",))
        pts = []
        for h, v in zip(header[1:], row[1:]):
            if hasattr(h, "year") and isinstance(v, (int, float)):
                pts.append((prev_month(f"{h.year:04d}-{h.month:02d}-01"), float(v)))
        out[key] = sorted(pts)
    return out


def parse_zcyc(html: str, term: str = "10.00") -> float | None:
    """The yield at `term` years on the date asked for; None when that day has no curve ('—')."""
    rows = [[re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)]
    head = next((r for r in rows if r and "погашения" in r[0]), None)
    vals = next((r for r in rows if r and "Доходность" in r[0]), None)
    if not head or not vals or term not in head:
        return None
    try:
        return _num(vals[head.index(term)])
    except (ValueError, IndexError):
        return None


def parse_candles(doc: dict[str, Any], daily: dict[str, Any] | None = None) -> tuple[Points, str | None]:
    """Monthly closes. A monthly candle's 'end' is the end of its period, not the last trade (the running
    month's reads as a day that has not come), so the newest point and its date come from the daily
    history: the last TRADEDATE with a close."""
    by = {}
    for begin, _end, close in doc["candles"]["data"]:
        if close is not None:
            by[begin[:7] + "-01"] = float(close)
    if not by:
        raise ValueError("MOEX answer has no candles")
    last_day = None
    rows = [(d, c) for d, c in ((daily or {}).get("history") or {}).get("data", []) if c is not None]
    if rows:
        last_day, close = max(rows)
        by[last_day[:7] + "-01"] = float(close)
    return sorted(by.items()), last_day


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def _soap(method: str, d1: str, d2: str) -> str:
    body = (f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{method} xmlns="http://web.cbr.ru/"><fromDate>{d1}</fromDate><ToDate>{d2}</ToDate></{method}>'
            f'</soap:Body></soap:Envelope>')
    return _get(CBR_SOAP, data=body.encode(), headers={"Content-Type": "text/xml; charset=utf-8",
                                                          "SOAPAction": f'"http://web.cbr.ru/{method}"'}).decode("utf-8")


def fetch_fx(code: str, today: date) -> Points:
    url = CBR_DYNAMIC.format(d1=HISTORY_FROM.strftime("%d/%m/%Y"), d2=today.strftime("%d/%m/%Y"), code=code)
    return parse_dynamic(_get(url).decode("windows-1251"))


def fetch_keyrate(today: date) -> Points:
    return parse_keyrate(_soap("KeyRateXML", "2013-09-13", today.isoformat()))


def fetch_reserves(today: date) -> Points:
    return parse_mrrf(_soap("mrrfXML", HISTORY_FROM.isoformat(), today.isoformat()))


def fetch_infl(today: date) -> Points:
    return parse_infl(_get(CBR_INFL.format(d1="01.01.2013", d2=today.strftime("%d.%m.%Y"))).decode("utf-8", "replace"))


def fetch_m2() -> dict[str, Points]:
    return parse_m2(_get(CBR_M2, timeout=120))


def fetch_candles(sec: str) -> tuple[Points, str | None]:
    monthly = json.loads(_get(MOEX_CANDLES.format(sec=sec, d1=HISTORY_FROM.isoformat())).decode("utf-8"))
    recent = (date.today() - timedelta(days=14)).isoformat()
    daily = json.loads(_get(MOEX_DAILY.format(sec=sec, d1=recent)).decode("utf-8"))
    return parse_candles(monthly, daily)


def fetch_zcyc(day: date) -> float | None:
    return parse_zcyc(_get(CBR_ZCYC.format(d=day.strftime("%d.%m.%Y"))).decode("utf-8", "replace"))


def month_end_day(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def ofz_monthly(cache: dict[str, Any], today: date, fetch: Callable[[date], float | None] = fetch_zcyc,
                pause: float = 0.5) -> tuple[Points, str | None, bool]:
    """Month-end 10-year yields: kept months from the cache, the missing ones (and always the running
    month) asked for -- the last day that has a curve, looking back up to a week. Returns (points, date of
    the newest point, whether the cache changed)."""
    kept: dict[str, list] = cache.setdefault("ofz_10y", {})
    changed = False
    y, m = HISTORY_FROM.year, HISTORY_FROM.month
    while (y, m) <= (today.year, today.month):
        key = f"{y:04d}-{m:02d}-01"
        running = (y, m) == (today.year, today.month)
        if running or key not in kept:
            day = today if running else month_end_day(y, m)
            for _ in range(8):
                v = fetch(day)
                time.sleep(pause)
                if v is not None:
                    if kept.get(key) != [day.isoformat(), v]:
                        kept[key] = [day.isoformat(), v]
                        changed = True
                    break
                day -= timedelta(days=1)
                if day.month != m:
                    break
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    pts = sorted((k, v[1]) for k, v in kept.items())
    last = kept[pts[-1][0]][0] if pts else None
    return pts, last, changed


def load_cache(path: Path = CACHE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict[str, Any], retrieved_at: str, path: Path = CACHE) -> None:
    cache["source"] = "CBR zero-coupon OFZ curve, 10-year point, one date per month; see ru_public_series.py"
    cache["retrieved_at"] = retrieved_at
    cache["ofz_10y"] = dict(sorted(cache.get("ofz_10y", {}).items()))
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------

_CBR = "https://www.cbr.ru/"


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, url: str) -> Spec:
    return Spec(id_, cadence, unit, fmt, note, source, (url,), cadence, label_ko=label)


SPECS: dict[str, Spec] = {s.id: s for s in [
    _s("usdrub", "monthly", "FX", "fx2", "USD/RUB",
       "러시아은행 공식 환율(루블/달러)입니다. 차트는 월말 값, 최신 점은 최근 고시일. 2022년 이후 장외·제재 환경의 공식 고시라는 점에 유의.",
       "cbr:XML_dynamic:R01235", _CBR + "currency_base/dynamics/"),
    _s("cnyrub", "monthly", "FX", "fx2", "CNY/RUB",
       "러시아은행 공식 환율(루블/위안)입니다. MOEX 주력 · 수출입 결제 기준. 차트는 월말 값.",
       "cbr:XML_dynamic:R01375", _CBR + "currency_base/dynamics/"),
    _s("cbr_key_rate", "monthly", "%", "pct2", "CBR 기준금리",
       "러시아은행 기준금리(Key Rate)입니다. 차트는 각 달 말 적용 금리, 최신 점은 최근 일자. 러시아은행 웹서비스 KeyRate.",
       "cbr:KeyRate", _CBR + "hd_base/KeyRate/"),
    _s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
       "소비자물가 전년 동월 대비입니다(통계청 Rosstat 발표치를 러시아은행이 게시). 러시아은행 '인플레이션과 기준금리' 표.",
       "cbr:hd_base/infl", _CBR + "hd_base/infl/"),
    _s("fx_reserves_total", "monthly", "bn_usd", "bn0usd", "외환보유액(총)",
       "국제준비자산 총액(십억 달러, 월말)입니다. 러시아은행 웹서비스 mrrf. 서방에 동결된 부분을 포함한 공식 총액입니다.",
       "cbr:mrrf", _CBR + "hd_base/mrrf/mrrf_m/"),
    _s("m2_yoy", "monthly", "%", "pct1", "M2 전년비",
       "통화량 M2(국가 정의) 전년 동월 대비, 월말입니다. 러시아은행 '통화 총량' 표.",
       "cbr:monetary_agg", _CBR + "statistics/ms/"),
    _s("m2_vs_2019", "monthly", "%", "pct1", "M2 vs 2019-12",
       "통화량 M2(국가 정의) 2019년 12월 말 대비 증가율입니다. 러시아은행 '통화 총량' 표.",
       "cbr:monetary_agg", _CBR + "statistics/ms/"),
    _s("ofz_10y", "monthly", "%", "pct2", "OFZ 10년",
       "국채(OFZ) 무이표 수익률곡선의 10년 지점입니다(러시아은행 산출, 각 달 마지막 영업일). 외국인 제한 → 내수 수급.",
       "cbr:zcyc", _CBR + "hd_base/zcyc_params/zcyc/"),
    _s("moex_index", "monthly", "index", "num0", "MOEX Russia",
       "MOEX 러시아 지수(IMOEX, 루블 기준) 월말 종가입니다. 모스크바거래소 ISS.",
       "moex:IMOEX", "https://www.moex.com/en/index/IMOEX"),
    _s("rtsi", "monthly", "index", "num0", "RTS Index",
       "RTS 지수(달러 기준) 월말 종가입니다. 모스크바거래소 ISS.",
       "moex:RTSI", "https://www.moex.com/en/index/RTSI"),
]}


@dataclass
class Sources:
    today: date
    cache: dict[str, Any]
    fx: Callable[[str, date], Points] = fetch_fx
    keyrate: Callable[[date], Points] = fetch_keyrate
    reserves: Callable[[date], Points] = fetch_reserves
    infl: Callable[[date], Points] = fetch_infl
    m2: Callable[[], dict[str, Points]] = fetch_m2
    candles: Callable[[str], tuple[Points, str | None]] = fetch_candles
    zcyc: Callable[[date], float | None] = fetch_zcyc
    cache_changed: bool = False
    _m2: dict[str, Points] | None = None

    def m2_series(self) -> dict[str, Points]:
        if self._m2 is None:
            self._m2 = self.m2()
        return self._m2


def _daily_to_monthly(pts: Points) -> tuple[Points, str]:
    by: dict[str, float] = {}
    for d, v in sorted(pts):
        by[d[:7] + "-01"] = v
    return sorted(by.items()), max(pts)[0]


def series_for(spec_id: str, src: Sources) -> tuple[Points, str | None]:
    """(monthly points, the day of the newest observation when it falls inside a running month)."""
    if spec_id in ("usdrub", "cnyrub"):
        return _daily_to_monthly(src.fx("R01235" if spec_id == "usdrub" else "R01375", src.today))
    if spec_id == "cbr_key_rate":
        return _daily_to_monthly(src.keyrate(src.today))
    if spec_id == "cpi_yoy":
        return src.infl(src.today), None
    if spec_id == "fx_reserves_total":
        return ups.scale(src.reserves(src.today), 1e-3), None
    if spec_id == "m2_yoy":
        return src.m2_series()["yoy"], None
    if spec_id == "m2_vs_2019":
        return ups.vs_base(src.m2_series()["level"], "2019-12-01"), None
    if spec_id == "ofz_10y":
        pts, last, changed = ofz_monthly(src.cache, src.today, src.zcyc)
        src.cache_changed |= changed
        return pts, last
    if spec_id in ("moex_index", "rtsi"):
        return src.candles("IMOEX" if spec_id == "moex_index" else "RTSI")
    raise KeyError(spec_id)


def build_patch(spec_id: str, points: Points, last_day: str | None, *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    from .za_public_series import with_gaps
    patch = ups.build_patch(SPECS[spec_id], with_gaps(points), retrieved_at=retrieved_at,
                            asof=last_day if last_day and points and last_day[:7] == points[-1][0][:7] else None)
    if patch["asof"] != ups.month_end(points[-1][0]):
        jps.pin_last_date(patch, patch["asof"])
    return patch


def apply_all(rus: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    by_id = {i["id"]: i for i in rus["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    ups.sync_chips(rus, by_id, set(changed))
    units = krs.sync_chip_units(rus, by_id, {k for k in patches if k in by_id})
    before = dict(rus.get("data_status_summary") or {})
    ups.refresh_status_summary(rus)
    return {"changed": changed, "summary_changed": units or before != rus["data_status_summary"]}

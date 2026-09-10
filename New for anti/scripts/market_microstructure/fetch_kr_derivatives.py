"""Korea derivatives: KOSPI200 futures/options activity + investor flow.

Sources (priority):
  1) KRX OpenAPI (`KRX_API`) — drv/fut_bydd_trd, drv/opt_bydd_trd
  2) KRX public dashboard — KOSPI200 futures/options *aggregate* investor buy/sell/net
  3) Manual CSV/JSON export from data.krx 「투자자별 거래실적」 (콜/풋 각각 조회 후 저장)

The public dashboard is intentionally limited to KOSPI200 futures and options
as a whole.  It cannot identify call versus put investor flow; that detailed
table still requires an authenticated data.krx CSV export.
"""

from __future__ import annotations

import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

UA = {"User-Agent": "market-microstructure/1.0", "Accept": "application/json"}
KRX_MAIN_URL = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
KRX_MAIN_TREND_URL = (
    "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd?"
    "bld=dbms/MDC/MAIN/MDCMAIN00103"
)
KRX_MAIN_PRODUCTS = {
    "futures": "KR___FUK2I",
    "options_total": "KR___OPK2I",
}
KRX_MAIN_UNIT = 1_000_000_000  # dashboard labels investor amounts as 십억원


def _key() -> str | None:
    for n in ("KRX_API", "KRX_OPENAPI_KEY"):
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None


def _bas_dd(day: str | None = None) -> str:
    if day:
        compact = day.replace("-", "")
        if not re.fullmatch(r"\d{8}", compact):
            raise ValueError(f"basDd must be YYYYMMDD, got {day}")
        return compact
    return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")


def derivative_day_candidates(
    bas_dd: str | None = None,
    *,
    now: datetime | None = None,
    max_lookback: int = 10,
) -> list[str]:
    """Requested KRX day, or recent candidates for weekends/market holidays.

    KRX derivatives EOD normally lags the close, so the automatic run starts
    at yesterday.  On Monday that first candidate is Sunday; probing backwards
    avoids silently losing Friday's observation.  An explicit ``bas_dd`` is
    never rewritten, which keeps manual historical reruns reproducible.
    """
    if bas_dd:
        return [_bas_dd(bas_dd)]
    ref = now or datetime.now()
    return [(ref - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(1, max_lookback + 1)]


def krx_drv(endpoint: str, bas_dd: str) -> list[dict[str, Any]]:
    key = _key()
    if not key:
        raise RuntimeError("KRX_API not set")
    url = f"https://data-dbg.krx.co.kr/svc/apis/drv/{endpoint}"
    r = requests.get(
        url,
        headers={**UA, "AUTH_KEY": key},
        # KRX accepts the documented header.  Do not mirror the secret into
        # the query string: requests/exception logs would then expose it.
        params={"basDd": bas_dd},
        timeout=60,
    )
    if r.status_code == 401:
        raise RuntimeError(f"KRX 401 Unauthorized for drv/{endpoint} — check key + 이용신청")
    if r.status_code == 403:
        raise RuntimeError(f"KRX 403 Forbidden for drv/{endpoint} — mypage에서 API 이용신청 필요")
    if r.status_code == 404:
        raise RuntimeError(f"KRX 404 — endpoint drv/{endpoint} not found")
    if r.status_code >= 400:
        raise RuntimeError(f"KRX HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    block = data.get("OutBlock_1") if isinstance(data, dict) else None
    if block is None:
        raise RuntimeError(f"Unexpected payload: {str(data)[:200]}")
    return list(block)


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k not in row or row[k] in (None, ""):
            continue
        try:
            return float(str(row[k]).replace(",", ""))
        except ValueError:
            continue
    return None


def _integer(value: Any) -> int | None:
    """Parse KRX display values such as ``28,402`` without guessing units."""
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def _main_investor_kind(label: str) -> str | None:
    if label.startswith("외국인"):
        return "foreign"
    if label.startswith("기관"):
        return "institution"
    if label.startswith("개인"):
        return "retail"
    return None


def fetch_krx_public_investor_flow() -> dict[str, Any]:
    """Fetch the no-login KRX dashboard's K200 aggregate investor flow.

    The endpoint needs the same anonymous session and Referer as its public
    webpage.  Values are displayed in 십억원, so they are converted explicitly
    to KRW here.  This is a same-day observation snapshot, not an EOD history
    and not a call/put split.
    """
    session = requests.Session()
    session.headers.update({
        **UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": KRX_MAIN_URL,
    })
    landing = session.get(KRX_MAIN_URL, timeout=30)
    landing.raise_for_status()

    result: dict[str, Any] = {
        "source": "KRX 공개 대시보드 MDCMAIN00103",
        "coverage_ko": "KOSPI200 선물 및 KOSPI200 옵션 전체의 투자자별 매수·매도·순매수. 옵션 콜/풋 분리 아님.",
        "unit": "KRW",
        "futures": None,
        "options_total": None,
        "quality": "missing",
    }
    for name, product_id in KRX_MAIN_PRODUCTS.items():
        response = session.post(KRX_MAIN_TREND_URL, data={"prodId": product_id}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("output") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError(f"unexpected KRX public flow payload for {name}")
        investors: dict[str, dict[str, int | None]] = {}
        for row in rows:
            kind = _main_investor_kind(str(row.get("INVST_TP") or ""))
            if not kind:
                continue
            # ACC_BID_TRDVAL is buy and ACC_ASK_TRDVAL is sell in the KRX UI.
            buy = _integer(row.get("ACC_BID_TRDVAL"))
            sell = _integer(row.get("ACC_ASK_TRDVAL"))
            net = _integer(row.get("NETBID_TRDVAL"))
            investors[kind] = {
                "buy_krw": None if buy is None else buy * KRX_MAIN_UNIT,
                "sell_krw": None if sell is None else sell * KRX_MAIN_UNIT,
                "net_krw": None if net is None else net * KRX_MAIN_UNIT,
            }
        trade_day = next((str(r.get("TRD_DD")) for r in rows if r.get("TRD_DD")), None)
        result[name] = {
            "as_of": (
                f"{trade_day[:4]}-{trade_day[4:6]}-{trade_day[6:8]}"
                if trade_day and len(trade_day) == 8 else None
            ),
            "observed_at_krx": payload.get("CURRENT_DATETIME"),
            "investors": investors,
            "quality": "observed" if investors else "missing",
        }
    if any((result[k] or {}).get("quality") == "observed" for k in KRX_MAIN_PRODUCTS):
        result["quality"] = "partial_observed"
    return result


def _is_call(row: dict[str, Any]) -> bool | None:
    for k in ("RGHT_TP_NM", "OPTN_TP_NM", "CP_TP_NM", "ISU_NM", "ISU_ABBRV"):
        v = str(row.get(k) or "")
        if "콜" in v or "CALL" in v.upper() or re.search(r"\bC\b", v):
            return True
        if "풋" in v or "PUT" in v.upper() or re.search(r"\bP\b", v):
            return False
    # OCC-like in name
    name = str(row.get("ISU_CD") or row.get("ISU_SRT_CD") or "")
    if "C" in name and "P" not in name:
        return True
    return None


def _is_kospi200_product(row: dict[str, Any]) -> bool:
    """Include standard/weekly KOSPI200; exclude mini and KOSDAQ150."""
    product = str(row.get("PROD_NM") or "").strip()
    name = str(row.get("ISU_NM") or "").strip()
    return product.startswith("코스피200") or name.startswith("코스피200")


def aggregate_k200_options_activity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate EOD call/put trading activity, deliberately excluding OI."""
    call_vol = put_vol = call_value = put_value = 0.0
    n_call = n_put = 0
    for row in rows:
        # opt_bydd_trd contains mini-K200, KOSDAQ150 and weekly options too.
        # The board label is KOSPI200, so retain only the standard/weekly
        # KOSPI200 family and exclude 미니코스피200.
        if not _is_kospi200_product(row):
            continue
        vol = _num(row, "ACC_TRDVOL", "ACC_TRDVOL_QTY", "TRDVOL") or 0.0
        value = _num(row, "ACC_TRDVAL", "TRDVAL") or 0.0
        side = _is_call(row)
        if side is True:
            call_vol += vol
            call_value += value
            n_call += 1
        elif side is False:
            put_vol += vol
            put_value += value
            n_put += 1
    pc_vol = None if call_vol <= 0 else put_vol / call_vol
    pc_value = None if call_value <= 0 else put_value / call_value
    return {
        "call_volume": call_vol,
        "put_volume": put_vol,
        "call_trading_value_krw": call_value,
        "put_trading_value_krw": put_value,
        "put_call_volume": None if pc_vol is None else round(pc_vol, 4),
        "put_call_trading_value": None if pc_value is None else round(pc_value, 4),
        "n_call_contracts": n_call,
        "n_put_contracts": n_put,
        "quality": "observed" if (n_call + n_put) else "missing",
        "coverage_ko": "코스피200 표준·위클리 옵션 합계. 미니코스피200·코스닥150 제외.",
    }


def aggregate_k200_futures_activity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate KOSPI200 futures EOD volume/value, not open interest."""
    selected = [row for row in rows if _is_kospi200_product(row)]
    volume = sum(_num(row, "ACC_TRDVOL", "ACC_TRDVOL_QTY", "TRDVOL") or 0.0 for row in selected)
    value = sum(_num(row, "ACC_TRDVAL", "TRDVAL") or 0.0 for row in selected)
    return {
        "product": "KOSPI200_futures",
        "volume": volume,
        "trading_value_krw": value,
        "n_contracts": len(selected),
        "quality": "observed" if selected else "missing",
        "coverage_ko": "코스피200 선물 전 결제월 합계. 미니코스피200 제외.",
        "source": "KRX OpenAPI drv/fut_bydd_trd",
    }


def load_investor_csv(path: Path) -> list[dict[str, Any]]:
    """Parse data.krx CSV export (일자, 외국인 합계, ...). Unit often 백만원."""
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        # flexible headers
        date = row.get("일자") or row.get("date") or row.get("TRD_DD")
        foreign = row.get("외국인 합계") or row.get("외국인합계") or row.get("foreign_net")
        inst = row.get("기관 합계") or row.get("기관합계") or row.get("institution_net")
        retail = row.get("개인") or row.get("retail_net")
        try:
            foreign_f = float(str(foreign).replace(",", "")) if foreign not in (None, "") else None
        except ValueError:
            foreign_f = None
        rows.append(
            {
                "date": str(date).replace("/", "-") if date else None,
                "foreign_net_mn_krw": foreign_f,
                "institution_net_mn_krw": None
                if inst in (None, "")
                else float(str(inst).replace(",", "")),
                "retail_net_mn_krw": None
                if retail in (None, "")
                else float(str(retail).replace(",", "")),
            }
        )
    return rows


_DETAIL_15007_PRODUCTS = ("options_call", "options_put", "futures")
_DETAIL_15007_SOURCE = "KRX 15007 authenticated export"
_DETAIL_15007_UNIT = 1_000_000  # KRX 15007 export: 백만원


def _empty_15007_product() -> dict[str, Any]:
    """Return an explicitly missing product; never substitute zero flow."""
    return {
        "as_of": None,
        "source": _DETAIL_15007_SOURCE,
        "quality": "missing",
        "foreign": {"buy_krw": None, "sell_krw": None, "net_krw": None},
        "market_total": {"buy_krw": None, "sell_krw": None, "net_krw": None},
        "series": [],
    }


def _detail_15007_date(value: Any) -> str | None:
    text = str(value or "").strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


def _detail_15007_number(value: Any) -> int | None:
    if value is None or str(value).strip() in {"", "-", "nan", "None"}:
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None


def _read_15007_side_export(path: Path) -> dict[str, dict[str, int]]:
    """Read one 15007 BUY or SELL export keyed by date.

    KRX's downloaded XLSX has a descriptive first row and the actual header
    (일자, 기관 합계, 기타법인, 개인, 외국인 합계, 전체) on the second row.
    CSV exports vary, so locate the row containing ``일자`` rather than assuming
    a fixed number of skipped lines.  The raw values are 백만원.
    """
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - CI declares pandas
            raise RuntimeError("pandas is required to read KRX 15007 XLSX") from exc
        raw = pd.read_excel(path, header=None, dtype=str)
        rows = raw.fillna("").values.tolist()
    else:
        rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))

    header_index = next(
        (i for i, row in enumerate(rows) if any(str(cell).strip() == "일자" for cell in row)),
        None,
    )
    if header_index is None:
        raise ValueError(f"KRX 15007 header '일자' not found: {path}")
    header = [str(cell).strip() for cell in rows[header_index]]
    try:
        date_index = header.index("일자")
        foreign_index = next(i for i, name in enumerate(header) if name.replace(" ", "") in {"외국인합계", "외국인"})
        total_index = header.index("전체")
    except (StopIteration, ValueError) as exc:
        raise ValueError(f"KRX 15007 required columns missing: {path}") from exc

    observations: dict[str, dict[str, int]] = {}
    for row in rows[header_index + 1:]:
        if len(row) <= max(date_index, foreign_index, total_index):
            continue
        day = _detail_15007_date(row[date_index])
        foreign = _detail_15007_number(row[foreign_index])
        total = _detail_15007_number(row[total_index])
        # A date with a blank amount is an unavailable observation, not zero.
        if day and foreign is not None and total is not None:
            observations[day] = {"foreign_mn_krw": foreign, "total_mn_krw": total}
    return observations


def _detail_15007_leg(buy_mn: int | None, sell_mn: int | None) -> dict[str, int | None]:
    if buy_mn is None or sell_mn is None:
        return {"buy_krw": None, "sell_krw": None, "net_krw": None}
    buy = buy_mn * _DETAIL_15007_UNIT
    sell = sell_mn * _DETAIL_15007_UNIT
    net = buy - sell
    # Keep the invariant close to the data transformation.  This guards a
    # future change that might accidentally mix units or sources.
    if buy - sell != net:
        return {"buy_krw": None, "sell_krw": None, "net_krw": None}
    return {"buy_krw": buy, "sell_krw": sell, "net_krw": net}


def _detail_15007_observation(
    day: str,
    buy: dict[str, int],
    sell: dict[str, int],
) -> dict[str, Any]:
    foreign = _detail_15007_leg(buy.get("foreign_mn_krw"), sell.get("foreign_mn_krw"))
    market_total = _detail_15007_leg(buy.get("total_mn_krw"), sell.get("total_mn_krw"))
    observed = all(value is not None for leg in (foreign, market_total) for value in leg.values())
    return {
        "date": day,
        "foreign": foreign if observed else {"buy_krw": None, "sell_krw": None, "net_krw": None},
        "market_total": market_total if observed else {"buy_krw": None, "sell_krw": None, "net_krw": None},
        "source": _DETAIL_15007_SOURCE,
        "quality": "observed" if observed else "missing",
        "source_unit": "million_krw",
        "conversion_to_krw": _DETAIL_15007_UNIT,
    }


def _product_15007_from_exports(
    *, buy_path: Path | None, sell_path: Path | None, previous: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge a KRX 15007 product into an existing date-keyed series.

    Existing observations remain intact.  A re-exported date replaces that one
    date only, matching the append-only/deduped history policy.
    """
    product = _empty_15007_product()
    if isinstance(previous, dict):
        for key in ("as_of", "source", "quality", "foreign", "market_total"):
            if key in previous:
                product[key] = previous[key]
        prior_series = previous.get("series")
        if isinstance(prior_series, list):
            product["series"] = [row for row in prior_series if isinstance(row, dict) and _detail_15007_date(row.get("date"))]

    if (buy_path is None) != (sell_path is None):
        product["quality"] = "partial_observed"
        return product
    if buy_path is None or sell_path is None:
        return product
    if not buy_path.is_file() or not sell_path.is_file():
        product["quality"] = "partial_observed"
        return product

    buys = _read_15007_side_export(buy_path)
    sells = _read_15007_side_export(sell_path)
    by_date = {str(row["date"]): row for row in product["series"]}
    for day in sorted(set(buys) | set(sells)):
        if day in buys and day in sells:
            by_date[day] = _detail_15007_observation(day, buys[day], sells[day])
        else:
            # A partial re-download must overwrite an earlier same-date value
            # only when it has both sides.  Otherwise keep the prior observed
            # observation and make the product's current status explicit.
            product["quality"] = "partial_observed"

    product["series"] = [by_date[day] for day in sorted(by_date)]
    observed = [row for row in product["series"] if row.get("quality") == "observed"]
    if observed:
        latest = observed[-1]
        product.update({
            "as_of": latest["date"],
            "source": latest["source"],
            "quality": "observed" if product.get("quality") != "partial_observed" else "partial_observed",
            "foreign": latest["foreign"],
            "market_total": latest["market_total"],
        })
    return product


def build_detailed_15007(
    *,
    option_call_buy: Path | None = None,
    option_call_sell: Path | None = None,
    option_put_buy: Path | None = None,
    option_put_sell: Path | None = None,
    futures_buy: Path | None = None,
    futures_sell: Path | None = None,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create the dedicated call/put contract without touching legacy CSV flow."""
    prior_products = (previous or {}).get("products") if isinstance(previous, dict) else {}
    if not isinstance(prior_products, dict):
        prior_products = {}
    products = {
        "options_call": _product_15007_from_exports(
            buy_path=option_call_buy, sell_path=option_call_sell,
            previous=prior_products.get("options_call"),
        ),
        "options_put": _product_15007_from_exports(
            buy_path=option_put_buy, sell_path=option_put_sell,
            previous=prior_products.get("options_put"),
        ),
    }
    futures = _product_15007_from_exports(
        buy_path=futures_buy, sell_path=futures_sell,
        previous=prior_products.get("futures"),
    )
    if futures["series"]:
        products["futures"] = futures
    return {
        "schema_version": "krx-15007-call-put-v2",
        "query": {
            "market": "KOSPI200",
            "metric": "trading_value",
            "side": "buy_sell_and_net",
            "unit": "KRW",
            "source_unit": "million_krw",
            "conversion_to_krw": _DETAIL_15007_UNIT,
        },
        "products": products,
    }


def fetch_kr_derivatives_bundle(
    *,
    bas_dd: str | None = None,
    investor_opt_call_csv: Path | None = None,
    investor_opt_put_csv: Path | None = None,
    investor_fut_csv: Path | None = None,
    detailed_15007_option_call_buy: Path | None = None,
    detailed_15007_option_call_sell: Path | None = None,
    detailed_15007_option_put_buy: Path | None = None,
    detailed_15007_option_put_sell: Path | None = None,
    detailed_15007_futures_buy: Path | None = None,
    detailed_15007_futures_sell: Path | None = None,
    previous_detailed_15007: dict[str, Any] | None = None,
) -> dict[str, Any]:
    day = _bas_dd(bas_dd)
    errors: list[str] = []
    sources: list[str] = []

    futures_activity = {"quality": "missing"}
    opt_agg = {"quality": "missing"}

    if _key():
        candidates = derivative_day_candidates(bas_dd)
        for candidate in candidates:
            try:
                fut_rows = krx_drv("fut_bydd_trd", candidate)
                opt_rows = krx_drv("opt_bydd_trd", candidate)
            except Exception as e:  # noqa: BLE001
                # An auth/subscription failure will not improve on a prior day;
                # keep one actionable error instead of sending repeated calls.
                errors.append(f"derivatives:{e}")
                break
            candidate_futures = aggregate_k200_futures_activity(fut_rows)
            candidate_options = aggregate_k200_options_activity(opt_rows)
            if (
                candidate_futures.get("quality") != "observed"
                or candidate_options.get("quality") != "observed"
            ):
                continue
            day = candidate
            futures_activity = candidate_futures
            opt_agg = candidate_options
            opt_agg["source"] = "KRX OpenAPI drv/opt_bydd_trd"
            opt_agg["bas_dd"] = day
            sources.extend(("krx_fut_bydd_trd", "krx_opt_bydd_trd"))
            break
        if futures_activity.get("quality") != "observed" or opt_agg.get("quality") != "observed":
            if not errors:
                errors.append(
                    "derivatives:no usable KOSPI200 futures/options EOD rows in "
                    + ", ".join(candidates)
                )
    else:
        errors.append("KRX_API unset — KRX OpenAPI EOD futures/options activity not fetched")

    investor: dict[str, Any] = {
        "note_ko": (
            "KRX 공개 대시보드는 코스피200 선물 및 옵션 전체의 투자자별 매수·매도·순매수를 제공한다. "
            "옵션 콜/풋 분리는 인증이 필요한 data.krx 「투자자별 거래실적」 CSV를 콜·풋 각각 export해야 한다."
        ),
        "public_dashboard": None,
        "unit": "CSV 세부 순매수는 백만원; 공개 대시보드 매수·매도·순매수는 KRW",
        "futures": None,
        "options_call": None,
        "options_put": None,
        "quality": "missing",
    }
    try:
        investor["public_dashboard"] = fetch_krx_public_investor_flow()
        if investor["public_dashboard"].get("quality") == "partial_observed":
            investor["quality"] = "partial_observed"
            sources.append("krx_public_investor_dashboard")
    except Exception as e:  # noqa: BLE001
        errors.append(f"public_investor:{e}")
    if investor_fut_csv and investor_fut_csv.exists():
        investor["futures"] = load_investor_csv(investor_fut_csv)
        investor["quality"] = "observed"
        sources.append("csv_fut_investor")
    if investor_opt_call_csv and investor_opt_call_csv.exists():
        investor["options_call"] = load_investor_csv(investor_opt_call_csv)
        investor["quality"] = "observed"
        sources.append("csv_opt_call_investor")
    if investor_opt_put_csv and investor_opt_put_csv.exists():
        investor["options_put"] = load_investor_csv(investor_opt_put_csv)
        investor["quality"] = "observed"
        sources.append("csv_opt_put_investor")
    investor["detailed_15007"] = build_detailed_15007(
        option_call_buy=detailed_15007_option_call_buy,
        option_call_sell=detailed_15007_option_call_sell,
        option_put_buy=detailed_15007_option_put_buy,
        option_put_sell=detailed_15007_option_put_sell,
        futures_buy=detailed_15007_futures_buy,
        futures_sell=detailed_15007_futures_sell,
        previous=previous_detailed_15007,
    )
    if any(
        product.get("quality") in {"observed", "partial_observed"}
        for product in investor["detailed_15007"]["products"].values()
    ):
        sources.append("krx_15007_authenticated_export")

    return {
        "schema_version": "kr-derivatives-v1",
        "as_of": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kospi200_futures": futures_activity,
        "kospi200_options": opt_agg,
        "investor_nets": investor,
        "source_priority_used": sources,
        "errors": errors,
        "disclaimer_ko": "공개·신청 API / CSV. 투자 권유 아님.",
    }

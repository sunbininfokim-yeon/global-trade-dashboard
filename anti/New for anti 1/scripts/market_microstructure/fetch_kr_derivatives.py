"""Korea derivatives: KOSPI200 fut/opt OI + investor nets + equity-option OI/skew.

Sources (priority):
  1) KRX OpenAPI (`KRX_API`) — drv/fut_bydd_trd, drv/opt_bydd_trd, drv/eqsop_bydd_trd
  2) Manual CSV/JSON export from data.krx 「투자자별 거래실적」 (콜/풋 각각 조회 후 저장)
  3) Fixture seed (demo only)

data.krx web JSON requires login (LOGOUT for anonymous) — not scraped here.
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

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures"

UA = {"User-Agent": "market-microstructure/1.0", "Accept": "application/json"}


def _key() -> str | None:
    for n in ("KRX_API", "KRX_OPENAPI_KEY"):
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None


def _bas_dd(day: str | None = None) -> str:
    if day:
        return day.replace("-", "")
    return (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")


def krx_drv(endpoint: str, bas_dd: str) -> list[dict[str, Any]]:
    key = _key()
    if not key:
        raise RuntimeError("KRX_API not set")
    url = f"https://data-dbg.krx.co.kr/svc/apis/drv/{endpoint}"
    r = requests.get(
        url,
        headers={**UA, "AUTH_KEY": key},
        params={"basDd": bas_dd, "AUTH_KEY": key},
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


def aggregate_k200_options_oi(rows: list[dict[str, Any]]) -> dict[str, Any]:
    call_oi = put_oi = call_vol = put_vol = 0.0
    n_call = n_put = 0
    for row in rows:
        # Prefer KOSPI200 / 코스피200
        name = str(row.get("ISU_NM") or row.get("PROD_NM") or row.get("UNDRLYNG_NM") or "")
        if name and ("코스피200" not in name and "KOSPI200" not in name.upper() and "K200" not in name.upper()):
            # endpoint opt_bydd_trd is already non-equity; keep all
            pass
        oi = _num(row, "OPNINT_QTY", "OPN_INT_QTY", "OI", "OPNINT") or 0.0
        vol = _num(row, "ACC_TRDVOL", "ACC_TRDVOL_QTY", "TRDVOL") or 0.0
        side = _is_call(row)
        if side is True:
            call_oi += oi
            call_vol += vol
            n_call += 1
        elif side is False:
            put_oi += oi
            put_vol += vol
            n_put += 1
    pc_oi = None if call_oi <= 0 else put_oi / call_oi
    pc_vol = None if call_vol <= 0 else put_vol / call_vol
    return {
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "put_call_oi": None if pc_oi is None else round(pc_oi, 4),
        "put_call_volume": None if pc_vol is None else round(pc_vol, 4),
        "n_call_contracts": n_call,
        "n_put_contracts": n_put,
        "quality": "observed" if (n_call + n_put) else "missing",
    }


def equity_options_oi_skew(
    rows: list[dict[str, Any]],
    underlyings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Per-underlying call/put OI + crude skew from IV fields if present."""
    underlyings = underlyings or ["005930", "000660"]
    by_u: dict[str, dict[str, Any]] = {
        u: {"call_oi": 0.0, "put_oi": 0.0, "call_ivs": [], "put_ivs": []} for u in underlyings
    }
    for row in rows:
        code = None
        for k in ("UNDRLYNG_ISU_SRT_CD", "UNDRLYNG_CD", "UNDRLYNG_ISU_CD"):
            v = str(row.get(k) or "").strip()
            if len(v) >= 6 and v[-6:].isdigit():
                code = v[-6:]
                break
        name = str(row.get("ISU_NM") or "")
        if code is None:
            if "하이닉스" in name:
                code = "000660"
            elif "삼성전자" in name:
                code = "005930"
        if code not in by_u:
            continue
        oi = _num(row, "OPNINT_QTY", "OPN_INT_QTY", "OI") or 0.0
        iv = _num(row, "IMPVOL", "IV", "ATMS_IMPVOL", "IMPL_VOL")
        side = _is_call(row)
        if side is True:
            by_u[code]["call_oi"] += oi
            if iv:
                by_u[code]["call_ivs"].append(iv)
        elif side is False:
            by_u[code]["put_oi"] += oi
            if iv:
                by_u[code]["put_ivs"].append(iv)

    out = []
    for u, b in by_u.items():
        c_iv = sum(b["call_ivs"]) / len(b["call_ivs"]) if b["call_ivs"] else None
        p_iv = sum(b["put_ivs"]) / len(b["put_ivs"]) if b["put_ivs"] else None
        skew = None if c_iv is None or p_iv is None else p_iv - c_iv
        out.append(
            {
                "underlying": u,
                "call_oi": b["call_oi"],
                "put_oi": b["put_oi"],
                "put_call_oi": None
                if b["call_oi"] <= 0
                else round(b["put_oi"] / b["call_oi"], 4),
                "avg_call_iv": None if c_iv is None else round(c_iv, 6),
                "avg_put_iv": None if p_iv is None else round(p_iv, 6),
                "skew_put_minus_call_iv": None if skew is None else round(skew, 6),
                "skew_note_ko": "평균 IV(풋−콜). 행사가별 ATM 스큐 정밀화는 필드 확인 후.",
                "quality": "observed" if (b["call_oi"] + b["put_oi"]) > 0 else "missing",
            }
        )
    return out


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


def fetch_kr_derivatives_bundle(
    *,
    bas_dd: str | None = None,
    investor_opt_call_csv: Path | None = None,
    investor_opt_put_csv: Path | None = None,
    investor_fut_csv: Path | None = None,
) -> dict[str, Any]:
    day = _bas_dd(bas_dd)
    errors: list[str] = []
    sources: list[str] = []

    fut_oi = {"quality": "missing"}
    opt_agg = {"quality": "missing"}
    equity_oi: list[dict[str, Any]] = []

    if _key():
        try:
            fut_rows = krx_drv("fut_bydd_trd", day)
            # sum OI for KOSPI200 futures near month
            oi_sum = 0.0
            for row in fut_rows:
                name = str(row.get("ISU_NM") or "")
                if "코스피200" in name or "KOSPI200" in name.upper():
                    oi_sum += _num(row, "OPNINT_QTY", "OPN_INT_QTY") or 0.0
            fut_oi = {
                "product": "KOSPI200_futures",
                "open_interest_qty": oi_sum,
                "n_rows": len(fut_rows),
                "quality": "observed",
                "source": "KRX OpenAPI drv/fut_bydd_trd",
            }
            sources.append("krx_fut_bydd_trd")
        except Exception as e:  # noqa: BLE001
            errors.append(f"fut:{e}")
        try:
            opt_rows = krx_drv("opt_bydd_trd", day)
            opt_agg = aggregate_k200_options_oi(opt_rows)
            opt_agg["source"] = "KRX OpenAPI drv/opt_bydd_trd"
            opt_agg["bas_dd"] = day
            sources.append("krx_opt_bydd_trd")
        except Exception as e:  # noqa: BLE001
            errors.append(f"opt:{e}")
        try:
            eq_rows = krx_drv("eqsop_bydd_trd", day)
            equity_oi = equity_options_oi_skew(eq_rows)
            sources.append("krx_eqsop_bydd_trd")
        except Exception as e:  # noqa: BLE001
            errors.append(f"eqsop:{e}")
    else:
        errors.append("KRX_API unset — OpenAPI OI/skew not fetched")

    investor: dict[str, Any] = {
        "note_ko": (
            "외인 콜/풋 순매수는 data.krx 「투자자별 거래실적」 CSV를 콜·풋 각각 export 하거나 "
            "이용신청된 OpenAPI가 생기면 자동 수집. 웹 비로그인=LOGOUT."
        ),
        "unit": "백만원 (순매수; 음수=순매도)",
        "futures": None,
        "options_call": None,
        "options_put": None,
        "quality": "missing",
    }
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

    # seed fixture if nothing
    seed = FIXTURES / "kr_investor_derivatives.json"
    if investor["quality"] == "missing" and seed.exists():
        seeded = __import__("json").loads(seed.read_text(encoding="utf-8"))
        investor.update(seeded.get("investor") or {})
        investor["quality"] = seeded.get("quality", "demo")
        sources.append("fixture_seed")

    return {
        "schema_version": "kr-derivatives-v1",
        "as_of": f"{day[:4]}-{day[4:6]}-{day[6:8]}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "kospi200_futures_oi": fut_oi,
        "kospi200_options": opt_agg,
        "equity_options_oi_skew": equity_oi,
        "investor_nets": investor,
        "source_priority_used": sources,
        "errors": errors,
        "disclaimer_ko": "공개·신청 API / CSV. 투자 권유 아님.",
    }

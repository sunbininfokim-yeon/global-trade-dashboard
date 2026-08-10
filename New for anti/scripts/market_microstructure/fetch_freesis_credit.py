"""FreeSIS public funding / credit extension (no API key).

증시자금추이 + 신용공여 잔고 추이.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; market-microstructure/1.0)"}


def _eok(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _freesis_million_to_eok(v: Any) -> float | None:
    """FreeSIS 단위 백만원 → 억원."""
    x = _eok(v)
    if x is None:
        return None
    return round(x / 100.0, 3)


def _freesis_ymd_to_iso(raw: str) -> str | None:
    s = str(raw or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def fetch_freesis_funding_credit(
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """금투협 FreeSIS 공개 통계 (API 키 불필요).

    - 증시자금추이 STATSCU0100000060: 예탁금·미수·반대매매
    - 신용공여 잔고 추이 STATSCU0100000070: 신용거래융자·대주·예탁증권담보융자

    단위 원본=백만원 → 응답은 억원. 종목별 아님.
    """
    headers = {
        "User-Agent": UA["User-Agent"],
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
    }
    if end is None:
        end = datetime.now().strftime("%Y%m%d")
    if start is None:
        start = (datetime.now() - timedelta(days=100)).strftime("%Y%m%d")

    def _pull(obj_nm: str, service_id: str) -> list[dict[str, Any]]:
        url = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
        body = {
            "dmSearch": {
                "tmpV40": "1000000",
                "tmpV41": "1",
                "tmpV1": "D",
                "tmpV45": start,
                "tmpV46": end,
                "OBJ_NM": obj_nm,
            }
        }
        r = requests.post(
            url,
            headers={**headers, "Referer": f"https://freesis.kofia.or.kr/stat/FreeSIS.do?serviceId={service_id}"},
            json=body,
            timeout=40,
        )
        r.raise_for_status()
        return list((r.json() or {}).get("ds1") or [])

    funding_rows = _pull("STATSCU0100000060BO", "STATSCU0100000060")
    credit_rows = _pull("STATSCU0100000070BO", "STATSCU0100000070")

    by_date: dict[str, dict[str, Any]] = {}
    for row in funding_rows:
        iso = _freesis_ymd_to_iso(row.get("TMPV1"))
        if not iso:
            continue
        by_date.setdefault(iso, {"date": iso})
        by_date[iso].update(
            {
                "investor_deposit_eok": _freesis_million_to_eok(row.get("TMPV2")),
                "derivatives_margin_eok": _freesis_million_to_eok(row.get("TMPV3")),
                "customer_rp_eok": _freesis_million_to_eok(row.get("TMPV4")),
                "uncollected_eok": _freesis_million_to_eok(row.get("TMPV5")),
                "forced_sale_eok": _freesis_million_to_eok(row.get("TMPV6")),
                "forced_sale_over_uncollected_pct": _eok(row.get("TMPV7")),
            }
        )
    for row in credit_rows:
        iso = _freesis_ymd_to_iso(row.get("TMPV1"))
        if not iso:
            continue
        by_date.setdefault(iso, {"date": iso})
        loan = _freesis_million_to_eok(row.get("TMPV2"))
        coll = _freesis_million_to_eok(row.get("TMPV9"))
        short_l = _freesis_million_to_eok(row.get("TMPV5"))
        by_date[iso].update(
            {
                "credit_loan_eok": loan,
                "credit_loan_kospi_eok": _freesis_million_to_eok(row.get("TMPV3")),
                "credit_loan_kosdaq_eok": _freesis_million_to_eok(row.get("TMPV4")),
                "short_loan_eok": short_l,
                "subscription_loan_eok": _freesis_million_to_eok(row.get("TMPV8")),
                "collateral_loan_eok": coll,
            }
        )
        parts = [x for x in (loan, coll) if x is not None]
        by_date[iso]["credit_funds_eok"] = round(sum(parts), 3) if parts else None

    history = [by_date[k] for k in sorted(by_date.keys())]
    latest = history[-1] if history else None
    if not latest:
        return {"quality": "missing", "note_ko": "FreeSIS 증시자금/신용공여 조회 실패", "history": []}

    dep = latest.get("investor_deposit_eok")
    funds = latest.get("credit_funds_eok")
    loan = latest.get("credit_loan_eok")
    components = [
        {"key": "investor_deposit", "label_ko": "투자자예탁금", "value_eok": dep},
        {"key": "credit_loan", "label_ko": "신용거래융자", "value_eok": loan},
        {"key": "credit_loan_kospi", "label_ko": "신용거래융자(유가증권)", "value_eok": latest.get("credit_loan_kospi_eok")},
        {"key": "credit_loan_kosdaq", "label_ko": "신용거래융자(코스닥)", "value_eok": latest.get("credit_loan_kosdaq_eok")},
        {"key": "collateral_loan", "label_ko": "예탁증권담보융자", "value_eok": latest.get("collateral_loan_eok")},
        {"key": "short_loan", "label_ko": "신용거래대주", "value_eok": latest.get("short_loan_eok")},
        {"key": "credit_funds", "label_ko": "신용공여자금(융자+담보)", "value_eok": funds},
        {"key": "uncollected", "label_ko": "위탁매매미수금", "value_eok": latest.get("uncollected_eok")},
        {"key": "forced_sale", "label_ko": "반대매매금액(미수 대비)", "value_eok": latest.get("forced_sale_eok")},
        {"key": "forced_sale_pct", "label_ko": "미수 대비 반대매매비중(%)", "value_pct": latest.get("forced_sale_over_uncollected_pct")},
    ]
    eok = 1e8
    return {
        "as_of": latest["date"],
        "unit_native": "억원",
        "investor_deposit_eok": dep,
        "investor_deposit_krw": None if dep is None else dep * eok,
        "credit_balance_eok": loan,
        "credit_balance_krw": None if loan is None else loan * eok,
        "credit_loan_eok": loan,
        "credit_loan_kospi_eok": latest.get("credit_loan_kospi_eok"),
        "credit_loan_kosdaq_eok": latest.get("credit_loan_kosdaq_eok"),
        "collateral_loan_eok": latest.get("collateral_loan_eok"),
        "short_loan_eok": latest.get("short_loan_eok"),
        "credit_funds_eok": funds,
        "uncollected_eok": latest.get("uncollected_eok"),
        "forced_sale_eok": latest.get("forced_sale_eok"),
        "forced_sale_over_uncollected_pct": latest.get("forced_sale_over_uncollected_pct"),
        "credit_over_deposit_pct": (None if not dep or not loan or dep <= 0 else round(100.0 * loan / dep, 3)),
        "credit_funds_over_deposit_pct": (None if not dep or not funds or dep <= 0 else round(100.0 * funds / dep, 3)),
        "components": components,
        "history": history,
        "history_n": len(history),
        "quality": "observed",
        "source": [
            "https://freesis.kofia.or.kr/ (증시자금추이 STATSCU0100000060)",
            "https://freesis.kofia.or.kr/ (신용공여 잔고 추이 STATSCU0100000070)",
        ],
        "note_ko": "금투협 FreeSIS 공개 집계. 종목·증권사·계좌별 아님. 신용공여자금=신용거래융자+예탁증권담보융자. 반대매매는 시장 전체 미수 대비 금액·비중만 공개.",
    }

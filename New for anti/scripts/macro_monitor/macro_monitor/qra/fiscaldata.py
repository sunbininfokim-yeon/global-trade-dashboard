"""Fiscal Data overlays: TGA daily + MTS Customs Duties."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

UA = "Mozilla/5.0 (compatible; macro-monitor-qra/1.0; research)"
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


def _get(url: str, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_tga_recent(limit: int = 30) -> Dict[str, Any]:
    """Latest TGA closing balances (DTS operating cash). Amounts are $ millions."""
    q = urllib.parse.urlencode(
        {
            "filter": "account_type:eq:Treasury General Account (TGA) Closing Balance",
            "sort": "-record_date",
            "page[size]": str(limit),
        }
    )
    doc = _get(f"{BASE}/v1/accounting/dts/operating_cash_balance?{q}")
    series = []
    for row in doc.get("data") or []:
        # API quirk: closing balance often in open_today_bal
        raw = row.get("close_today_bal")
        if raw in (None, "null"):
            raw = row.get("open_today_bal")
        if raw in (None, "null"):
            continue
        mn = float(raw)
        series.append(
            {
                "date": row["record_date"],
                "tga_mn": mn,
                "tga_bn": round(mn / 1000.0, 3),
            }
        )
    latest = series[0] if series else None
    return {
        "source": "fiscaldata.dts.operating_cash_balance",
        "asof": latest["date"] if latest else None,
        "latest_bn": latest["tga_bn"] if latest else None,
        "series": series,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def fetch_customs_duties(limit: int = 24) -> Dict[str, Any]:
    """Monthly Customs Duties from MTS table 3 (receipts; negative ≈ net refunds)."""
    q = urllib.parse.urlencode(
        {
            "filter": "classification_desc:eq:Customs Duties",
            "sort": "-record_date",
            "page[size]": str(limit),
        }
    )
    doc = _get(f"{BASE}/v1/accounting/mts/mts_table_3?{q}")
    series = []
    for row in doc.get("data") or []:
        amt = row.get("current_month_rcpt_outly_amt")
        if amt in (None, "null"):
            continue
        dollars = float(amt)
        series.append(
            {
                "date": row["record_date"],
                "customs_duties_usd": dollars,
                "customs_duties_bn": round(dollars / 1e9, 3),
                "fytd_usd": float(row["current_fytd_rcpt_outly_amt"])
                if row.get("current_fytd_rcpt_outly_amt") not in (None, "null")
                else None,
            }
        )
    latest = series[0] if series else None
    flags = []
    if latest and latest["customs_duties_bn"] < 0:
        flags.append("customs_net_refund")
    if latest and abs(latest["customs_duties_bn"]) < 0.5:
        flags.append("customs_near_zero")
    return {
        "source": "fiscaldata.mts.mts_table_3.Customs Duties",
        "asof": latest["date"] if latest else None,
        "latest_bn": latest["customs_duties_bn"] if latest else None,
        "flags": flags,
        "series": series,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "note_ko": "음수 월 = 관세 환급이 수입을 상회(순유출).",
    }


def fetch_fiscal_overlay() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "errors": []}
    try:
        out["tga"] = fetch_tga_recent()
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["errors"].append(f"tga:{exc}")
        out["tga"] = None
    try:
        out["customs"] = fetch_customs_duties()
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["errors"].append(f"customs:{exc}")
        out["customs"] = None
    return out

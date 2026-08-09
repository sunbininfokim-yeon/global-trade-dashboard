"""Fiscal Data overlays: TGA, DTS debt transactions, MTS receipts/outlays/deficit."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

UA = "Mozilla/5.0 (compatible; macro-monitor-qra/1.0; research)"
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"


def _get(url: str, timeout: int = 45) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch_tga_recent(limit: int = 60) -> Dict[str, Any]:
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
        "url": "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance",
        "asof": latest["date"] if latest else None,
        "latest_bn": latest["tga_bn"] if latest else None,
        "series": series,
        "fetched_at": _now(),
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
        "fetched_at": _now(),
        "note_ko": "음수 월 = 관세 환급이 수입을 상회(순유출).",
    }


def fetch_public_debt_transactions(limit: int = 120) -> Dict[str, Any]:
    """DTS public debt transactions — marketable Bills/Notes/Bonds issues & redemptions ($mn)."""
    q = urllib.parse.urlencode(
        {
            "filter": "security_market:eq:Marketable",
            "sort": "-record_date",
            "page[size]": str(limit),
        }
    )
    doc = _get(f"{BASE}/v1/accounting/dts/public_debt_transactions?{q}")
    rows = doc.get("data") or []
    if not rows:
        return {"source": "fiscaldata.dts.public_debt_transactions", "asof": None, "components": [], "series": []}

    day = rows[0]["record_date"]
    agg: Dict[tuple, float] = defaultdict(float)
    for r in rows:
        if r.get("record_date") != day:
            continue
        st = r.get("security_type") or "Other"
        if st not in ("Bills", "Notes", "Bonds"):
            continue
        tt = r.get("transaction_type") or ""
        amt = float(r.get("transaction_today_amt") or 0)
        agg[(tt, st)] += amt

    def _mn(tt: str, st: str) -> float:
        return float(agg.get((tt, st), 0.0))

    components = []
    for st, label in (("Bills", "T-Bills"), ("Notes", "Notes"), ("Bonds", "Bonds")):
        issued = _mn("Issues", st)
        redeemed = _mn("Redemptions", st)
        net = issued - redeemed
        components.append(
            {
                "id": st.lower(),
                "label_ko": label,
                "kind": "bill" if st == "Bills" else "coupon",
                "issues_mn": round(issued, 1),
                "redemptions_mn": round(redeemed, 1),
                "net_mn": round(net, 1),
                "value": round(net / 1000.0, 3),  # $B for bar
                "unit": "bn_usd",
            }
        )
    net_total_bn = round(sum(c["value"] for c in components), 3)
    return {
        "source": "fiscaldata.dts.public_debt_transactions",
        "url": "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/public-debt-transactions",
        "asof": day,
        "latest_bn": net_total_bn,
        "components": components,
        "table": [
            {
                "kind": c["kind"],
                "label_ko": c["label_ko"],
                "issues_bn": round(c["issues_mn"] / 1000.0, 3),
                "redemptions_bn": round(c["redemptions_mn"] / 1000.0, 3),
                "net_bn": c["value"],
            }
            for c in components
        ],
        "note_ko": "당일 시중성(Marketable) 발행−상환 순증($B). Bills=무이표, Notes/Bonds=이표.",
        "fetched_at": _now(),
    }


def fetch_debt_to_penny() -> Dict[str, Any]:
    q = urllib.parse.urlencode({"sort": "-record_date", "page[size]": "1"})
    doc = _get(f"{BASE}/v2/accounting/od/debt_to_penny?{q}")
    row = (doc.get("data") or [None])[0]
    if not row:
        return {"source": "fiscaldata.od.debt_to_penny", "asof": None, "latest_tn": None}
    total = float(row["tot_pub_debt_out_amt"])
    public = float(row["debt_held_public_amt"])
    intra = float(row["intragov_hold_amt"])
    return {
        "source": "fiscaldata.od.debt_to_penny",
        "asof": row["record_date"],
        "latest_tn": round(total / 1e12, 3),
        "public_tn": round(public / 1e12, 3),
        "intragov_tn": round(intra / 1e12, 3),
        "components": [
            {"id": "public", "label_ko": "시중 보유", "value": round(public / 1e12, 3), "unit": "tn_usd"},
            {"id": "intragov", "label_ko": "정부내 보유", "value": round(intra / 1e12, 3), "unit": "tn_usd"},
        ],
        "fetched_at": _now(),
    }


def _mts_line(desc: str, limit: int = 24) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode(
        {
            "filter": f"classification_desc:eq:{desc}",
            "sort": "-record_date",
            "page[size]": str(limit),
        }
    )
    doc = _get(f"{BASE}/v1/accounting/mts/mts_table_2?{q}")
    out = []
    for row in doc.get("data") or []:
        amt = row.get("current_month_budget_amt")
        if amt in (None, "null"):
            continue
        out.append(
            {
                "date": row["record_date"],
                "bn": round(float(amt) / 1e9, 3),
                "usd": float(amt),
            }
        )
    return out


def fetch_mts_summary() -> Dict[str, Any]:
    """MTS Table 2: Total Receipts / Total Outlays / On-Budget Surplus(+) or Deficit(-)."""
    receipts = _mts_line("Total Receipts")
    outlays = _mts_line("Total Outlays")
    deficit = _mts_line("On-Budget Surplus (+) or Deficit (-)")
    latest_d = (deficit[0]["date"] if deficit else None) or (
        receipts[0]["date"] if receipts else None
    )
    return {
        "source": "fiscaldata.mts.mts_table_2",
        "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/summary-of-receipts-outlays-and-the-deficit-surplus-of-the-u-s-government",
        "asof": latest_d,
        "receipts_bn": receipts[0]["bn"] if receipts else None,
        "outlays_bn": outlays[0]["bn"] if outlays else None,
        "deficit_bn": deficit[0]["bn"] if deficit else None,  # negative = deficit
        "series": {
            "receipts": receipts,
            "outlays": outlays,
            "deficit": deficit,
        },
        "components": [
            {"id": "receipts", "label_ko": "세입", "value": receipts[0]["bn"], "unit": "bn_usd"}
            if receipts
            else None,
            {"id": "outlays", "label_ko": "세출", "value": outlays[0]["bn"], "unit": "bn_usd"}
            if outlays
            else None,
            {
                "id": "deficit",
                "label_ko": "흑자(+)/적자(-)",
                "value": deficit[0]["bn"],
                "unit": "bn_usd",
            }
            if deficit
            else None,
        ],
        "note_ko": "월간 On-Budget. 적자는 음수. Fiscal Data MTS Table 2.",
        "fetched_at": _now(),
    }


def fetch_fiscal_overlay() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "errors": []}
    for key, fn in (
        ("tga", fetch_tga_recent),
        ("customs", fetch_customs_duties),
        ("debt_transactions", fetch_public_debt_transactions),
        ("debt_outstanding", fetch_debt_to_penny),
        ("mts", fetch_mts_summary),
    ):
        try:
            out[key] = fn()
        except Exception as exc:  # noqa: BLE001
            out["ok"] = False
            out["errors"].append(f"{key}:{exc}")
            out[key] = None
    # drop None components in mts
    if out.get("mts") and out["mts"].get("components"):
        out["mts"]["components"] = [c for c in out["mts"]["components"] if c]
    return out

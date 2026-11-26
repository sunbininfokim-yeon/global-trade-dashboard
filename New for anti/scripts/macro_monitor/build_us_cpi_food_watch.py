#!/usr/bin/env python3
"""Refresh the USDA egg watch card for the US CPI news rail (no API keys)."""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONTRIB = ROOT.parent.parent / "public" / "data" / "us_cpi_contrib_v1.json"
USDA_URL = "https://www.ams.usda.gov/mnreports/ams_2843.pdf"
USDA_REPORT = "https://mymarketnews.ams.usda.gov/viewReport/2843"
BLS_URL = "https://www.bls.gov/news.release/cpi.t02.htm"
MIN_CENTS = 3.0
MIN_PCT = 3.0
MAX_AGE_DAYS = 6
MAX_PDF_BYTES = 4 * 1024 * 1024


def parse_usda(text: str) -> dict:
    if "Daily National Shell Egg Index Report" not in text:
        raise ValueError("wrong USDA report")
    report_date = re.search(r"Report for:\s*(\d{1,2}/\d{1,2}/\d{4})", text)
    section = re.search(r"NATIONAL SHELL EGGS[¹1]?\s*-\s*Caged\s*\n(.*?)(?=NATIONAL SHELL EGGS|\Z)",
                        text, re.DOTALL)
    if not report_date or not section:
        raise ValueError("report date or national caged section missing")
    body = section[1]
    if "Cents Per Dozen / FOB" not in body or "Wtd Avg" not in body or "Last Reported" not in body:
        raise ValueError("unexpected USDA table columns or unit")
    graded = body.partition("Graded Loose")[2].split("Gradeable Nest Run", 1)[0]
    row = re.search(
        r"(?m)^\s*(?:Graded Loose\s+)?White\s+Large\s+(\d[\d,]*)\s+"
        r"(\d+\.\d+)\s*-\s*(\d+\.\d+)\s+(\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+\.\d+)(?:\s|$)",
        graded,
    )
    dates = re.search(r"\((\d{1,2}/\d{1,2}/\d{4})\)", body)
    if not row or not dates:
        raise ValueError("comparable national white large egg quote missing")
    low, high, current, change, previous = map(float, row.groups()[1:])
    day, previous_day = (datetime.strptime(m[1], "%m/%d/%Y").date() for m in (report_date, dates))
    if not (0 < low <= current <= high and previous > 0
            and int(row[1].replace(",", "")) > 0 and 1 <= (day - previous_day).days <= 5
            and math.isclose(current - previous, change, abs_tol=0.011)):
        raise ValueError("USDA quote or previous quote failed consistency checks")
    return {
        "reference_date": day.isoformat(), "prior_reference_date": previous_day.isoformat(),
        "cents_per_dozen": current, "prior_cents_per_dozen": previous, "change_cents": change,
        "change_pct": round(change * 100 / previous, 4),
    }


def read_usda(pdf: bytes) -> dict:
    from pypdf import PdfReader

    if not pdf.startswith(b"%PDF-") or len(pdf) > MAX_PDF_BYTES:
        raise ValueError("unexpected USDA response")
    reader = PdfReader(io.BytesIO(pdf))
    if not 1 <= len(reader.pages) <= 5:
        raise ValueError("unexpected USDA report page count")
    # The quote is in a positional table. Layout extraction preserves column
    # order, and parse_usda also checks unit, price range and reported change.
    return parse_usda("\n".join(page.extract_text(extraction_mode="layout") for page in reader.pages[:2]))


def latest_egg_cpi(contrib: dict) -> dict:
    month = contrib["latest_month"]
    codes = [str(index) for index, node in enumerate(contrib["nodes"]) if node.get("code") == "SEFH"]
    if len(codes) != 1:
        raise ValueError("BLS egg component missing or ambiguous")
    month_data = contrib["baskets"]["headline"].get(month, {})
    mom = month_data.get("mom", {}).get("rows", {}).get(codes[0])
    yoy = month_data.get("yoy", {}).get("rows", {}).get(codes[0])
    return {"item_id": "eggs", "bls_item_code": "SEFH", "label_ko": "계란 CPI",
            "headline_only": True, "reference_period": month,
            "mom_pct": mom[0] if mom else None, "yoy_pct": yoy[0] if yoy else None,
            "approx_weight_pct": mom[2] if mom else None, "source_url": BLS_URL}


def build_watch(quote: dict, target: dict, *, as_of: date) -> dict:
    day = date.fromisoformat(quote["reference_date"])
    age = (as_of - day).days
    if age < 0 or age > MAX_AGE_DAYS:
        raise ValueError("USDA report date is future or stale")
    source_month = day.isoformat()[:7]
    # Once the CPI snapshot includes the USDA quote reference month, don't
    # present that quote as a new alert ahead of that month's release.
    inside_open_cpi_month = source_month > target["reference_period"]
    active = (inside_open_cpi_month and quote["change_cents"] >= MIN_CENTS and quote["change_pct"] >= MIN_PCT)
    alert = {
        "id": "usda_shell_eggs",
        "observation_id": f"usda_ams_2843:{day.isoformat()}",
        "observed_on": day.isoformat(),
        "published_at": None,
        "expires_on_us_eastern": (day + timedelta(days=MAX_AGE_DAYS)).isoformat(),
        "title_ko": f"USDA 계란 도매가 +{quote['change_pct']:.1f}% · 다음 발표에서 계란 CPI 확인",
        "watch_ko": "USDA 전국 흰색 대란 도매가가 상승. 다음 CPI에서 소매 계란 가격도 같은 방향인지 확인.",
        "interpretation": "external_price_watch_not_forecast",
        "target_item_id": target["item_id"],
        "target_cpi_reference_period": source_month,
        "source_url": USDA_REPORT,
    } if active else None
    return {
        "schema_version": "us-cpi-food-watch-v1", "country": "USA",
        "status": "watch" if active else "observed_no_alert", "alerts": [alert] if alert else [],
        "external_prices": [{
            "id": "usda_shell_eggs", "label_ko": "USDA 전국 흰색 대란 도매가",
            "source": "USDA AMS 2843", "source_url": USDA_REPORT, "latest_pdf_url": USDA_URL,
            "unit": "cents_per_dozen", "series": "National FOB, caged, graded loose, white, large, 5-day weighted",
            "target": target, "observation": quote,
        }],
        "policy": {
            "minimum_rise_pct": MIN_PCT, "minimum_rise_cents": MIN_CENTS,
            "threshold_type": "editorial_materiality_not_statistically_calibrated",
            "maximum_report_age_days": MAX_AGE_DAYS, "forecast_active": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usda-pdf", type=Path, help="optional saved USDA report for replay")
    parser.add_argument("--cpi-contrib", type=Path, default=CONTRIB)
    parser.add_argument("--as-of", type=date.fromisoformat, help="replay day in US/Eastern")
    parser.add_argument("--out", type=Path, help="write compact JSON atomically; default stdout")
    args = parser.parse_args()
    try:
        if args.usda_pdf:
            pdf = args.usda_pdf.read_bytes()
        else:
            request = Request(USDA_URL, headers={"Accept": "application/pdf"})
            with urlopen(request, timeout=30) as response:
                pdf = response.read(MAX_PDF_BYTES + 1)
        target = latest_egg_cpi(json.loads(args.cpi_contrib.read_text(encoding="utf-8")))
        quote = read_usda(pdf)
        report = build_watch(quote, target, as_of=args.as_of or datetime.now(ZoneInfo("America/New_York")).date())
        payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.out:
            if args.out.exists():
                previous_payload = args.out.read_text(encoding="utf-8")
                previous = json.loads(previous_payload)
                if previous.get("schema_version") != report["schema_version"]:
                    raise ValueError("refusing to replace a different output contract")
                if previous["external_prices"][0]["observation"]["reference_date"] > quote["reference_date"]:
                    raise ValueError("refusing to replace a newer USDA observation")
                if previous_payload == payload:
                    return 0
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.out.parent,
                                    prefix=f".{args.out.name}.", delete=False) as handle:
                temp = Path(handle.name)
                try:
                    handle.write(payload)
                    handle.close()
                    temp.replace(args.out)
                finally:
                    temp.unlink(missing_ok=True)
        else:
            print(payload, end="")
    except (ImportError, OSError, ValueError, KeyError) as exc:
        print(f"CPI food watch refresh failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

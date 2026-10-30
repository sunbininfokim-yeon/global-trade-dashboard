#!/usr/bin/env python3
"""Produce a redacted, repeatable OpenDART P1 strict-EBITDA evidence record.

The tool intentionally asks only for ``fnlttSinglAcntAll`` rows and never
writes a source payload or request URL.  ``DART_API_KEY`` is read only from
the process environment and is never included in output, exceptions, or an
evidence file.  The emitted record contains public filing metadata and the
small set of rows relevant to the strict P1 formula:

    operating income + separately reported PPE depreciation
      + separately reported intangible amortisation

This is a research/validation tool, not a production adapter.  A ``true``
eligibility result still requires a human to promote both exact concepts to
the versioned manifest with the reported evidence IDs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = ROOT / "config" / "universe_seed.json"
OPEN_DART_SINGLE_ACCOUNT_ALL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
REPORT_CODES = ("11011", "11014", "11012", "11013")
DEFAULT_COMPANIES = ("samsung_electronics", "hd_korea_shipbuilding")
FALLBACK_YEARS = (2024, 2023, 2022)


class ValidationError(RuntimeError):
    """Safe error whose text never carries a request URL or credential."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def classify_da_row(row: Mapping[str, Any]) -> tuple[str | None, bool]:
    """Classify only explicitly-labelled components; ambiguous labels stay out.

    Account names are used solely to make a review list.  This function never
    creates a manifest mapping and treats a generic ``감가상각비`` label as
    combined/ambiguous rather than assuming that it means PPE depreciation.
    """
    name = _text(row.get("account_nm")).replace(" ", "")
    if "유형자산" in name and "감가" in name:
        return "ppe_depreciation", True
    if "무형자산" in name and "상각" in name:
        return "intangible_amortization", True
    # ``상각후원가`` (amortised cost) is a financial-instrument measurement,
    # not D&A.  Require an expense/depreciation marker for the ambiguous list.
    if "감가" in name or "상각비" in name:
        return "combined_or_ambiguous", False
    return None, False


def _public_row(row: Mapping[str, Any], *, classification: str, separate_component: bool) -> dict[str, Any]:
    """Keep auditable public metadata, deliberately excluding request material."""
    return {
        "receipt_id": row.get("rcept_no"),
        "report_code": row.get("reprt_code"),
        "business_year": row.get("bsns_year"),
        "row_fs_div": row.get("fs_div"),
        "sj_div": row.get("sj_div"),
        "account_id": row.get("account_id"),
        "account_name": row.get("account_nm"),
        "currency": row.get("currency"),
        "classification": classification,
        "separate_component": separate_component,
    }


def summarize_payload(
    payload: Mapping[str, Any],
    *,
    company: Mapping[str, Any],
    year: int,
    report_code: str,
    requested_fs_div: str = "CFS",
) -> dict[str, Any]:
    """Summarise a single public OpenDART response without retaining raw rows."""
    rows = payload.get("list")
    rows = rows if isinstance(rows, list) else []
    components: list[dict[str, Any]] = []
    operating_income: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        account_id = _text(raw.get("account_id"))
        account_name = _text(raw.get("account_nm"))
        if account_id == "dart_OperatingIncomeLoss" or account_name in {"영업이익", "영업손익"}:
            operating_income.append(_public_row(raw, classification="operating_income", separate_component=True))
        classification, separate = classify_da_row(raw)
        if classification:
            components.append(_public_row(raw, classification=classification, separate_component=separate))

    receipt_ids = sorted({str(item["receipt_id"]) for item in operating_income + components if item.get("receipt_id")})
    ppe = [
        item for item in components
        if item["classification"] == "ppe_depreciation"
        and item["separate_component"]
        and item.get("sj_div") in {"IS", "CIS", "CF"}
    ]
    intangible = [
        item for item in components
        if item["classification"] == "intangible_amortization"
        and item["separate_component"]
        and item.get("sj_div") in {"IS", "CIS", "CF"}
    ]
    matching_keys = ("receipt_id", "report_code", "business_year", "row_fs_div", "currency")
    formula_available = any(
        all(operating.get(key) == component.get(key) == amortization.get(key) for key in matching_keys)
        for operating in operating_income
        for component in ppe
        for amortization in intangible
    )
    return {
        "evidence_id": f"dart-{year}-{company['id']}-{report_code}",
        "company_id": company["id"],
        "company_name_ko": company.get("name_ko"),
        "stock_code": company["stock_code"],
        "corp_code": company["corp_code"],
        "year": year,
        "report_code": report_code,
        "requested_fs_div": requested_fs_div,
        "response_status": payload.get("status"),
        "response_message": payload.get("message"),
        "row_count": len(rows),
        "row_fs_div_values": sorted({_text(row.get("fs_div")) for row in rows}),
        "receipt_ids": receipt_ids,
        "operating_income_rows": operating_income,
        "da_candidate_rows": components,
        "strict_formula_available_at_endpoint": formula_available,
        "strict_formula_reason": (
            None
            if formula_available
            else (
                "missing:separately_reported_ppe_depreciation_or_intangible_amortization"
                if not (ppe and intangible)
                else "incompatible:receipt_scope_currency_or_period"
            )
        ),
    }


def _fetch_payload(*, api_key: str, corp_code: str, year: int, report_code: str, fs_div: str) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": report_code,
            "fs_div": fs_div,
        }
    )
    request = urllib.request.Request(
        f"{OPEN_DART_SINGLE_ACCOUNT_ALL}?{query}",
        headers={"User-Agent": "kfa-p1-live-validation/1.0 (OpenDART public filings)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValidationError(f"opendart_http_status:{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValidationError("opendart_network_error") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("opendart_non_json_response") from exc
    if not isinstance(decoded, dict):
        raise ValidationError("opendart_response_not_object")
    return decoded


def _load_companies(path: Path, selected_ids: Iterable[str]) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    indexed = {
        _text(item.get("id")): dict(item)
        for item in raw.get("companies") or []
        if isinstance(item, Mapping) and item.get("id")
    }
    companies: list[dict[str, Any]] = []
    for company_id in selected_ids:
        company = indexed.get(company_id)
        if not company or not _text(company.get("stock_code")) or not _text(company.get("corp_code")):
            raise ValidationError(f"universe_company_missing_or_incomplete:{company_id}")
        companies.append(company)
    return companies


def validate_live(
    *,
    api_key: str,
    companies: Iterable[Mapping[str, Any]],
    requested_year: int,
    fallback_years: Iterable[int] = FALLBACK_YEARS,
    fs_div: str = "CFS",
) -> dict[str, Any]:
    """Validate annual-first, then the available interim endpoints for each issuer."""
    results: list[dict[str, Any]] = []
    for company_raw in companies:
        company = dict(company_raw)
        annual: dict[str, Any] | None = None
        selected_year: int | None = None
        for year in (requested_year, *tuple(fallback_years)):
            payload = _fetch_payload(api_key=api_key, corp_code=_text(company["corp_code"]), year=year, report_code="11011", fs_div=fs_div)
            annual = summarize_payload(payload, company=company, year=year, report_code="11011", requested_fs_div=fs_div)
            if annual["response_status"] in {"000", "0"}:
                selected_year = year
                break
        endpoints = [annual] if annual else []
        if selected_year is not None:
            for report_code in REPORT_CODES[1:]:
                payload = _fetch_payload(
                    api_key=api_key,
                    corp_code=_text(company["corp_code"]),
                    year=selected_year,
                    report_code=report_code,
                    fs_div=fs_div,
                )
                endpoints.append(
                    summarize_payload(
                        payload,
                        company=company,
                        year=selected_year,
                        report_code=report_code,
                        requested_fs_div=fs_div,
                    )
                )
        results.append(
            {
                "company_id": company["id"],
                "company_name_ko": company.get("name_ko"),
                "stock_code": company["stock_code"],
                "corp_code": company["corp_code"],
                "requested_annual_year": requested_year,
                "selected_year": selected_year,
                "endpoints": endpoints,
                "promotion_decision": "no_promotion"
                if not any(item.get("strict_formula_available_at_endpoint") for item in endpoints)
                else "human_review_required",
            }
        )
    return {
        "schema_version": "kfa-p1-live-dart-evidence/1",
        "provider": "OpenDART",
        "requested_fs_div": fs_div,
        "requested_annual_year": requested_year,
        "companies": results,
        "manifest_promotion": "none_automatic",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2025, help="Annual year to query first (default: 2025).")
    parser.add_argument("--company-id", action="append", dest="company_ids", help="Universe company id; repeatable.")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE, help="Local corp-code index JSON.")
    parser.add_argument("--out", type=Path, help="Optional path for the redacted public evidence JSON.")
    args = parser.parse_args(argv)
    api_key = _text(os.environ.get("DART_API_KEY"))
    if not api_key:
        print("DART_API_KEY is required in the process environment; no request was made.", file=sys.stderr)
        return 2
    try:
        companies = _load_companies(args.universe, args.company_ids or list(DEFAULT_COMPANIES))
        result = validate_live(api_key=api_key, companies=companies, requested_year=args.year)
    except ValidationError as exc:
        print(f"P1 live validation failed safely: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

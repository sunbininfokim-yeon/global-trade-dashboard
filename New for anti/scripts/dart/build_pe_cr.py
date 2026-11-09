"""Offline entry point: saved OpenDART report responses -> auditable PE/CR JSON.

Input: {entity_id, fiscal_year_end, fs_div, currency, industry,
        entity_policy, filings: {FY: {list: [...]}, Q1: ..., H1: ..., Q3: ...},
        history: [canonical-financial-facts/1 bundles]}.
No credentials, network calls, or publishing. Output goes to stdout.
"""
import argparse
import json
from pathlib import Path

from dart_kfa.canonical_facts import adapt_dart_filings, default_dart_account_specs
from dart_kfa.entity_policy import classify_entity
from dart_kfa.pe_cr import build_pe_cr


def build(payload, period="annual"):
    canonical = adapt_dart_filings(
        payload["filings"], account_specs=default_dart_account_specs(),
        fiscal_year_end=payload["fiscal_year_end"], entity_id=payload["entity_id"],
        fs_div=payload["fs_div"], currency=payload.get("currency", "KRW"),
    )
    # Caller-supplied nonfinancial flag cannot override classifier evidence.
    policy = classify_entity({**payload.get("corp", {}), "corp_code": payload["entity_id"]})
    if payload.get("entity_policy", {}).get("is_financial_entity"):
        policy = payload["entity_policy"]
    return build_pe_cr(canonical, selected_period=period, history=payload.get("history", []),
                       industry=payload.get("industry", "manufacturing"), entity_policy=policy)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--period", default="annual", choices=["annual", "Q1", "Q2", "Q3", "Q4"])
    args = parser.parse_args()
    print(json.dumps(build(json.loads(args.input.read_text()), args.period), ensure_ascii=False, allow_nan=False, indent=2))

"""Offline entry point: saved OpenDART or SEC Companyfacts -> auditable PE/CR JSON.

Input: {entity_id, fiscal_year_end, fs_div, currency, industry, corp: {induty_code},
        entity_policy, filings: {FY: {list: [...]}, Q1: ..., H1: ..., Q3: ...},
        history: [canonical-financial-facts/1 bundles], reviewed_disclosures,
        market, peer_group, peers, peer_ids, funding, segments, dart_shares, dart_bonds, ev_scenario, screen_inputs}.
Set source=SEC and supply companyfacts instead of filings for SEC. Optional
prior_reports accepts historical FY inputs in the same raw format.
An OpenDART raw report is stored as {request: {corp_code, bsns_year,
reprt_code, fs_div}, response: {status, list}} inside each filings bucket.
No credentials, network calls, or publishing. Output goes to stdout.
"""
import argparse
import json
from pathlib import Path

from dart_kfa.canonical_facts import DART_CODE_BY_BUCKET, DART_REPORTS, adapt_dart_filings, adapt_sec_companyfacts, default_dart_account_specs
from dart_kfa.entity_policy import classify_entity
from dart_kfa.pe_cr import build_pe_cr


def prepare_filings(payload):
    result = {}
    for bucket, record in payload["filings"].items():
        if not isinstance(record, dict) or not ({"request", "response"} & record.keys()):
            result[bucket] = record  # Legacy input requires fs_div on each row.
            continue
        code = bucket if bucket in DART_REPORTS else DART_CODE_BY_BUCKET.get(bucket)
        request, response = record.get("request"), record.get("response")
        expected = {"corp_code": payload["entity_id"], "bsns_year": payload["fiscal_year_end"][:4],
                    "reprt_code": code, "fs_div": payload["fs_div"]}
        if (not code or not isinstance(request, dict) or expected["fs_div"] not in {"CFS", "OFS"}
                or any(str(request.get(k) or "") != v for k, v in expected.items())):
            raise ValueError("incompatible:dart_request:" + bucket)
        if not isinstance(response, dict) or response.get("status") not in {"000", "013"}:
            raise ValueError("unavailable:dart_response:" + bucket)
        if response["status"] == "013":
            if response.get("list"):
                raise ValueError("incompatible:dart_no_data_response:" + bucket)
            result[bucket] = []
            continue
        if not isinstance(response.get("list"), list) or not response["list"]:
            raise ValueError("invalid:dart_response_rows:" + bucket)
        rows = []
        for row in response["list"]:
            if (not isinstance(row, dict) or any(str(row.get(k) or "") != expected[k] for k in ("corp_code", "bsns_year", "reprt_code"))
                    or row.get("fs_div") not in (None, "", expected["fs_div"])):
                raise ValueError("incompatible:dart_response_identity:" + bucket)
            normalized = {**row, "fs_div": expected["fs_div"], "scope_source": "opendart_request"}
            if code != "11011" and row.get("sj_div") in {"IS", "CIS"}:
                normalized["period_value_kind"] = "direct"
            rows.append(normalized)
        result[bucket] = rows
    return result


def _canonical(payload):
    source = payload.get("source", "DART")
    if source == "SEC":
        data = payload["companyfacts"]
        cik = str(payload["entity_id"])
        reported = str(data.get("cik") or "") if isinstance(data, dict) else ""
        if not cik.isascii() or not cik.isdigit() or len(cik) > 10 or not reported.isascii() or not reported.isdigit() or cik.zfill(10) != reported.zfill(10):
            raise ValueError("incompatible:sec_companyfacts_cik")
        return adapt_sec_companyfacts(data, fiscal_year_end=payload["fiscal_year_end"], entity_id=cik.zfill(10),
                                      fs_div=payload.get("fs_div", "CFS"), currency=payload.get("currency", "USD"),
                                      report_periods=payload.get("report_periods"))
    if source != "DART":
        raise ValueError("unsupported:pe_cr_filing_source")
    return adapt_dart_filings(
        prepare_filings(payload), account_specs=default_dart_account_specs(),
        fiscal_year_end=payload["fiscal_year_end"], entity_id=payload["entity_id"],
        fs_div=payload["fs_div"], currency=payload.get("currency", "KRW"), report_periods=payload.get("report_periods"),
    )


def build(payload, period="annual"):
    canonical = _canonical(payload)
    history = list(payload.get("history") or [])
    prior = payload.get("prior_reports") or []
    if not isinstance(prior, list) or len(prior) > 5:
        raise ValueError("invalid:up_to_five_prior_reports")
    for row in prior:
        if (not isinstance(row, dict) or set(row) - {"fiscal_year_end", "filings", "companyfacts", "report_periods"}
                or not isinstance(row.get("fiscal_year_end"), str) or row["fiscal_year_end"] >= canonical["fiscal_year_end"]
                or (canonical["source"] == "DART" and "filings" not in row)):
            raise ValueError("invalid:prior_report_scope_or_date")
        earlier = {k: payload[k] for k in ("source", "entity_id", "fs_div", "currency", "companyfacts") if k in payload}
        history.append(_canonical({**earlier, **row}))
    # Caller-supplied nonfinancial flag cannot override classifier evidence.
    policy = classify_entity({**(payload.get("corp") or {}), "corp_code": canonical["entity_id"], "source": canonical["source"]})
    if payload.get("entity_policy", {}).get("is_financial_entity"):
        policy = payload["entity_policy"]
    return build_pe_cr(canonical, selected_period=period, history=history,
                       industry=payload.get("industry"), corp=payload.get("corp"), entity_policy=policy,
                       reviewed_disclosures=payload.get("reviewed_disclosures"), market=payload.get("market"),
                       peer_group=payload.get("peer_group"), peers=payload.get("peers") or (),
                       funding=payload.get("funding"), segments=payload.get("segments"),
                       dart_shares=payload.get("dart_shares"), dart_bonds=payload.get("dart_bonds"), peer_ids=payload.get("peer_ids"),
                       ev_scenario=payload.get("ev_scenario"), screen_inputs=payload.get("screen_inputs"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--period", default="annual", choices=["annual", "Q1", "Q2", "Q3", "Q4"])
    args = parser.parse_args()
    print(json.dumps(build(json.loads(args.input.read_text()), args.period), ensure_ascii=False, allow_nan=False, indent=2))

#!/usr/bin/env python3
"""Build a quota-bounded monthly Comtrade panel for priority commodity reporters.

This is deliberately separate from the broad free-source monthly file.  It
collects reporter-country exports/imports to World, retains Comtrade quality
flags, and never presents the selected country panel as complete world trade.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from priority_universe import FLOW_LABELS, PRIORITY_COMMODITIES, PRIORITY_REPORTERS  # noqa: E402
from series_quality import annotate_country_series  # noqa: E402
from sources import comtrade  # noqa: E402


PUBLIC = ROOT.parents[1] / "public" / "data"
CACHE = Path("/tmp/commodity_trade_cache") / "comtrade_preview"
DEFAULT_OUT = PUBLIC / "commodity_trade_comtrade_priority_v1.json"


def _last_completed_month() -> str:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - 1
    if month == 0:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month:02d}"


def _periods_ending_at(end_month: str, count: int) -> list[str]:
    year, month = (int(value) for value in end_month.split("-"))
    periods: list[str] = []
    for _ in range(count):
        periods.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return periods  # newest first: a quota-capped run gets the most useful month


def _parse_selection(value: str, allowed: dict[str, Any], label: str) -> list[str]:
    if not value.strip() or value.strip().lower() == "all":
        return list(allowed)
    selected = [item.strip().upper() for item in value.split(",") if item.strip()]
    unknown = [item for item in selected if item not in allowed]
    if unknown:
        raise ValueError(f"unknown {label}: {', '.join(unknown)}")
    return selected


def _parse_flows(value: str) -> list[str]:
    labels_to_codes = {label: code for code, label in FLOW_LABELS.items()}
    selected: list[str] = []
    for item in value.split(","):
        normalized = item.strip().lower()
        if not normalized:
            continue
        if normalized not in labels_to_codes:
            raise ValueError("--flows must use exports and/or imports")
        selected.append(labels_to_codes[normalized])
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("--flows must contain unique exports and/or imports")
    return selected


def _load_output(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != "commodity-trade-comtrade-priority-v1":
        raise ValueError(f"unexpected priority Comtrade output format: {path}")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _series_shell(commodity_id: str) -> dict[str, Any]:
    meta = PRIORITY_COMMODITIES[commodity_id]
    return {
        "commodity_id": commodity_id,
        "sector": meta["sector"],
        "hs": meta["hs"],
        "scope_ko": meta["scope_ko"],
        "partner": "WORLD",
        "points": [],
        "latest_available_month": None,
        "status": "not_queried",
    }


def _ensure_reporter(payload: dict[str, Any], iso3: str) -> dict[str, Any]:
    reporters = payload.setdefault("reporters", {})
    reporter = reporters.setdefault(
        iso3,
        {
            "iso3": iso3,
            **PRIORITY_REPORTERS[iso3],
            "coverage_scope_ko": "해당 보고국의 World 상대 수출·수입. 세계 전체 합계가 아님.",
            "flows": {},
        },
    )
    for flow, label in FLOW_LABELS.items():
        flow_block = reporter["flows"].setdefault(label, {"flow_code": flow, "commodities": {}})
        for cid in PRIORITY_COMMODITIES:
            flow_block["commodities"].setdefault(cid, _series_shell(cid))
    return reporter


def _merge_points(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month = {point.get("month"): point for point in existing if point.get("month")}
    by_month.update({point.get("month"): point for point in incoming if point.get("month")})
    return [by_month[month] for month in sorted(by_month)]


def _annotate_reporter(payload: dict[str, Any], reference_month: str) -> None:
    for reporter in (payload.get("reporters") or {}).values():
        for flow in (reporter.get("flows") or {}).values():
            for series in (flow.get("commodities") or {}).values():
                country = {"points": series.get("points") or []}
                annotate_country_series(country, reference_month)
                series["series_quality"] = country["series_quality"]
                points = series.get("points") or []
                source_quality = [point.get("quality") or {} for point in points]
                series["comtrade_quality"] = {
                    "point_count": len(points),
                    "quantity_estimated_count": sum(bool(q.get("is_quantity_estimated")) for q in source_quality),
                    "reported_status_false_count": sum(q.get("is_reported") is False for q in source_quality),
                    "legacy_estimation_flag_count": sum(bool(q.get("legacy_estimation_flag")) for q in source_quality),
                    "note_ko": "Comtrade 원본의 추정·보고 상태 플래그를 보존하며, false가 곧 오류를 뜻하지는 않는다.",
                }
                if points:
                    series["latest_available_month"] = max(point["month"] for point in points if point.get("month"))
                    series["status"] = "available"
                elif series.get("status") == "not_queried":
                    series["status"] = "no_data_or_not_yet_queried"


def _stats(payload: dict[str, Any]) -> dict[str, Any]:
    reporters = payload.get("reporters") or {}
    series = [
        series
        for reporter in reporters.values()
        for flow in (reporter.get("flows") or {}).values()
        for series in (flow.get("commodities") or {}).values()
    ]
    return {
        "reporter_count": len(reporters),
        "series_count": len(series),
        "available_series_count": sum(bool(series.get("points")) for series in series),
        "point_count": sum(len(series.get("points") or []) for series in series),
        "latest_month": max(
            (point.get("month") for series in series for point in (series.get("points") or []) if point.get("month")),
            default=None,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporters", default="all", help="ISO3 list or all; e.g. USA,BRA,CHN")
    parser.add_argument("--flows", default="exports,imports", help="exports, imports, or both")
    parser.add_argument("--months", type=int, default=3, help="trailing completed months to request")
    parser.add_argument("--end-month", default=_last_completed_month(), help="latest completed month, YYYY-MM")
    parser.add_argument("--max-requests", type=int, default=24, help="hard cap on network Preview requests")
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=2.0,
        help="minimum pause between uncached Preview requests; protects the free endpoint",
    )
    parser.add_argument("--cache-dir", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--replace-output", action="store_true")
    parser.add_argument("--no-fetch", action="store_true", help="only inspect the current output")
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    if args.months < 1 or args.months > 12:
        parser.error("--months must be between 1 and 12")
    if args.max_requests < 0:
        parser.error("--max-requests must be non-negative")
    if args.min_interval_seconds < 0:
        parser.error("--min-interval-seconds must be non-negative")
    try:
        datetime.strptime(args.end_month, "%Y-%m")
        reporters = _parse_selection(args.reporters, PRIORITY_REPORTERS, "reporters")
        flows = _parse_flows(args.flows)
    except ValueError as exc:
        parser.error(str(exc))

    existing = {} if args.replace_output else _load_output(args.out)
    if args.no_fetch:
        if not existing:
            parser.error(f"--no-fetch requires an existing output: {args.out}")
        if args.print_stats:
            print(json.dumps(_stats(existing), ensure_ascii=False, indent=2))
        return 0

    payload = existing or {
        "schema_version": "commodity-trade-comtrade-priority-v1",
        "source": "UN Comtrade free Preview API",
        "scope_ko": "우선 보고국 패널. 국가별 World 상대 수출·수입이며 글로벌 전체 커버리지가 아님.",
        "quality_contract": "commodity-trade-quality-v1",
        "reporters": {},
        "runs": [],
    }
    periods = _periods_ending_at(args.end_month, args.months)
    hs_codes = [meta["hs"] for meta in PRIORITY_COMMODITIES.values()]
    run = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "reporters": reporters,
        "flows": [FLOW_LABELS[flow] for flow in flows],
        "periods": periods,
        "max_network_requests": args.max_requests,
        "network_requests": 0,
        "cache_hits": 0,
        "available_responses": 0,
        "failures": [],
        "quota_capped": False,
        "rate_limited": False,
    }
    last_network_request_at: float | None = None

    for iso3 in reporters:
        reporter = _ensure_reporter(payload, iso3)
        for period in periods:
            for flow in flows:
                if run["network_requests"] >= args.max_requests:
                    run["quota_capped"] = True
                    break
                if last_network_request_at is not None:
                    remaining = args.min_interval_seconds - (time.monotonic() - last_network_request_at)
                    if remaining > 0:
                        time.sleep(remaining)
                result = comtrade.fetch_preview_month(
                    hs_codes=hs_codes,
                    reporter_m49=reporter["m49"],
                    period=period,
                    flow=flow,
                    cache_dir=args.cache_dir,
                )
                cache = result.get("cache") or {}
                if cache.get("hit"):
                    run["cache_hits"] += 1
                else:
                    run["network_requests"] += 1
                    last_network_request_at = time.monotonic()
                if not result.get("available"):
                    run["failures"].append(
                        {"reporter": iso3, "flow": flow, "period": period, "reason": result.get("reason") or result.get("error") or "no data"}
                    )
                    if result.get("rate_limited"):
                        run["rate_limited"] = True
                        break
                    continue
                run["available_responses"] += 1
                commodities = reporter["flows"][FLOW_LABELS[flow]]["commodities"]
                for cid, meta in PRIORITY_COMMODITIES.items():
                    series = commodities[cid]
                    incoming = (result.get("series_by_hs") or {}).get(meta["hs"], [])
                    series["points"] = _merge_points(series.get("points") or [], incoming)
                    if not incoming and not series["points"]:
                        series["status"] = "no_data_in_preview_response"
            if run["quota_capped"] or run["rate_limited"]:
                break
        if run["quota_capped"] or run["rate_limited"]:
            break

    _annotate_reporter(payload, args.end_month)
    run["completed_at"] = datetime.now(timezone.utc).isoformat()
    payload["generated_at"] = run["completed_at"]
    payload["reference_month"] = args.end_month
    payload.setdefault("runs", []).append(run)
    payload["collection_stats"] = _stats(payload)
    _atomic_write_json(args.out, payload)
    print(f"[comtrade_priority] wrote {args.out}")
    if args.print_stats:
        print(json.dumps(payload["collection_stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build national-source monthly panels for Comtrade Preview gaps.

The output intentionally remains separate from the Comtrade Preview panel.
National sources may use a different commodity level or measure, and the later
reconciliation layer must choose a source transparently rather than merge
incompatible values.
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

from national_source_registry import NATIONAL_SOURCE_REGISTRY, automated_reporters  # noqa: E402
from priority_universe import FLOW_LABELS, PRIORITY_COMMODITIES, PRIORITY_REPORTERS  # noqa: E402
from series_quality import annotate_country_series  # noqa: E402
from sources import india_tradestat  # noqa: E402
from sources import korea_customs  # noqa: E402
from sources import mexico_inegi  # noqa: E402
from sources import norway_ssb  # noqa: E402
from sources import saudi_gastat_tableau  # noqa: E402
from sources import thailand_customs  # noqa: E402


PUBLIC = ROOT.parents[1] / "public" / "data"
CACHE = Path("/tmp/commodity_trade_cache") / "national_trade"
DEFAULT_OUT = PUBLIC / "commodity_trade_national_priority_v1.json"


def _last_completed_month() -> str:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - 1
    if month == 0:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month:02d}"


def _periods_ending_at(end_month: str, count: int) -> list[str]:
    year, month = (int(value) for value in end_month.split("-"))
    result: list[str] = []
    for _ in range(count):
        result.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return result


def _parse_reporters(value: str) -> list[str]:
    if not value.strip() or value.strip().lower() == "all":
        return automated_reporters()
    reporters = [item.strip().upper() for item in value.split(",") if item.strip()]
    unknown = [item for item in reporters if item not in PRIORITY_REPORTERS]
    unsupported = [item for item in reporters if item not in automated_reporters(include_env_key=True)]
    if unknown:
        raise ValueError(f"unknown reporters: {', '.join(unknown)}")
    if unsupported:
        raise ValueError(
            "no automated national adapter for: " + ", ".join(unsupported) + "; see national_source_registry.py"
        )
    return reporters


def _parse_flows(value: str) -> list[str]:
    lookup = {label: code for code, label in FLOW_LABELS.items()}
    selected = [lookup[item.strip().lower()] for item in value.split(",") if item.strip().lower() in lookup]
    if not selected or len(selected) != len(set(selected)) or len(selected) != len([item for item in value.split(",") if item.strip()]):
        raise ValueError("--flows must use exports and/or imports, once each")
    return selected


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if payload.get("schema_version") != "commodity-trade-national-priority-v1":
        raise ValueError(f"unexpected national priority output format: {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
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
            "coverage_scope_ko": "해당 보고국의 전체 수출·수입(상대국 World 합계). 세계 전체 합계가 아님.",
            "flows": {},
        },
    )
    for flow, label in FLOW_LABELS.items():
        flow_block = reporter["flows"].setdefault(label, {"flow_code": flow, "commodities": {}})
        for commodity_id in PRIORITY_COMMODITIES:
            flow_block["commodities"].setdefault(commodity_id, _series_shell(commodity_id))
    return reporter


def _merge(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month = {point["month"]: point for point in existing if point.get("month")}
    by_month.update({point["month"]: point for point in incoming if point.get("month")})
    return [by_month[month] for month in sorted(by_month)]


def _annotate(payload: dict[str, Any], reference_month: str) -> None:
    for reporter in (payload.get("reporters") or {}).values():
        for flow in (reporter.get("flows") or {}).values():
            for series in (flow.get("commodities") or {}).values():
                holder = {"points": series.get("points") or []}
                annotate_country_series(holder, reference_month)
                series["series_quality"] = holder["series_quality"]
                if series["points"]:
                    series["latest_available_month"] = max(point["month"] for point in series["points"])
                    series["status"] = "available"
                elif series.get("status") in {"not_queried", "not_available_at_source_hs4_level"}:
                    series["status"] = "no_data_or_not_yet_queried"


def _stats(payload: dict[str, Any]) -> dict[str, Any]:
    series = [
        item
        for reporter in (payload.get("reporters") or {}).values()
        for flow in (reporter.get("flows") or {}).values()
        for item in (flow.get("commodities") or {}).values()
    ]
    return {
        "reporter_count": len(payload.get("reporters") or {}),
        "series_count": len(series),
        "available_series_count": sum(bool(item.get("points")) for item in series),
        "point_count": sum(len(item.get("points") or []) for item in series),
        "latest_month": max(
            (point.get("month") for item in series for point in (item.get("points") or []) if point.get("month")),
            default=None,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reporters", default="all", help="automated national-source ISO3 list or all")
    parser.add_argument("--flows", default="exports,imports")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--end-month", default=_last_completed_month(), help="latest completed month, YYYY-MM")
    parser.add_argument("--max-requests", type=int, default=12, help="hard cap on uncached national-source requests")
    parser.add_argument("--min-interval-seconds", type=float, default=2.0)
    parser.add_argument("--cache-dir", type=Path, default=CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--replace-output", action="store_true")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.months <= 24:
        parser.error("--months must be between 1 and 24")
    if args.max_requests < 0 or args.min_interval_seconds < 0:
        parser.error("--max-requests and --min-interval-seconds must be non-negative")
    try:
        datetime.strptime(args.end_month, "%Y-%m")
        reporters = _parse_reporters(args.reporters)
        flows = _parse_flows(args.flows)
    except ValueError as exc:
        parser.error(str(exc))

    existing = {} if args.replace_output else _load(args.out)
    if args.no_fetch:
        if not existing:
            parser.error(f"--no-fetch requires an existing output: {args.out}")
        if args.print_stats:
            print(json.dumps(_stats(existing), ensure_ascii=False, indent=2))
        return 0
    payload = existing or {
        "schema_version": "commodity-trade-national-priority-v1",
        "source": "Official national monthly trade sources",
        "scope_ko": "국가별 공식 원천 패널. 소스별 상품 단위·측정치가 다르므로 Comtrade와 자동 합산하지 않는다.",
        "quality_contract": "commodity-trade-quality-v1",
        "source_registry": NATIONAL_SOURCE_REGISTRY,
        "reporters": {},
        "runs": [],
    }
    payload["source_registry"] = NATIONAL_SOURCE_REGISTRY
    periods = _periods_ending_at(args.end_month, args.months)
    run: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "reporters": reporters,
        "flows": [FLOW_LABELS[flow] for flow in flows],
        "periods": periods,
        "max_network_requests": args.max_requests,
        "network_requests": 0,
        "cache_hits": 0,
        "successful_responses": 0,
        "failures": [],
        "quota_capped": False,
    }
    last_request_at: float | None = None
    for iso3 in reporters:
        if iso3 not in {"IND", "KOR", "MEX", "NOR", "SAU", "THA"}:
            run["failures"].append({"reporter": iso3, "reason": "adapter not implemented"})
            continue
        reporter = _ensure_reporter(payload, iso3)
        hs4 = [meta["hs"] for meta in PRIORITY_COMMODITIES.values() if len(meta["hs"]) == 4]
        if iso3 == "SAU":
            for commodity_id, meta in PRIORITY_COMMODITIES.items():
                if len(meta["hs"]) != 4:
                    for flow in flows:
                        reporter["flows"][FLOW_LABELS[flow]]["commodities"][commodity_id]["status"] = (
                            "not_collected_by_saudi_public_hs4_adapter"
                        )
                    continue
                for flow in flows:
                    commodities = reporter["flows"][FLOW_LABELS[flow]]["commodities"]
                    if run["network_requests"] >= args.max_requests:
                        run["quota_capped"] = True
                        break
                    if last_request_at is not None:
                        pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                        if pause > 0:
                            time.sleep(pause)
                    result = saudi_gastat_tableau.fetch_monthly_hs_world(
                        periods=periods,
                        flow=flow,
                        hs_code=meta["hs"],
                        cache_dir=args.cache_dir,
                        max_requests=args.max_requests - run["network_requests"],
                        fallback_latest_months=max(12, args.months),
                    )
                    cache = result.get("cache") or {}
                    if cache.get("hit"):
                        run["cache_hits"] += 1
                    else:
                        used = int(cache.get("network_requests") or 0)
                        run["network_requests"] += used
                        if used:
                            last_request_at = time.monotonic()
                    if not result.get("available"):
                        reason = result.get("reason", "no data")
                        run["failures"].append(
                            {"reporter": iso3, "flow": flow, "hs": meta["hs"], "reason": reason}
                        )
                        if "request budget exhausted" in str(reason):
                            run["quota_capped"] = True
                            break
                        continue
                    run["successful_responses"] += 1
                    series = commodities[commodity_id]
                    incoming = (result.get("series_by_hs") or {}).get(meta["hs"], [])
                    series["points"] = _merge(series["points"], incoming)
                    if not incoming and not series["points"]:
                        series["status"] = "no_data_in_saudi_gastat_tableau_response"
                if run["quota_capped"]:
                    break
            if run["quota_capped"]:
                break
            continue
        for period in periods:
            if iso3 == "MEX":
                for flow in flows:
                    for commodity_id, meta in PRIORITY_COMMODITIES.items():
                        if len(meta["hs"]) != 4:
                            reporter["flows"][FLOW_LABELS[flow]]["commodities"][commodity_id]["status"] = (
                                "not_collected_by_mexico_hs4_adapter"
                            )
                chapters = sorted({int(meta["hs"][:2]) for meta in PRIORITY_COMMODITIES.values()})
                for chapter in chapters:
                    if run["network_requests"] >= args.max_requests:
                        run["quota_capped"] = True
                        break
                    if last_request_at is not None:
                        pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                        if pause > 0:
                            time.sleep(pause)
                    result = mexico_inegi.fetch_monthly_chapter_values(
                        period=period,
                        chapter=chapter,
                        cache_dir=args.cache_dir,
                        max_requests=args.max_requests - run["network_requests"],
                    )
                    cache = result.get("cache") or {}
                    if cache.get("hit"):
                        run["cache_hits"] += 1
                    else:
                        used = int(cache.get("network_requests") or 0)
                        run["network_requests"] += used
                        if used:
                            last_request_at = time.monotonic()
                    if not result.get("available"):
                        run["failures"].append(
                            {"reporter": iso3, "period": period, "chapter": chapter, "reason": result.get("reason", "no data")}
                        )
                        continue
                    run["successful_responses"] += 1
                    for flow in flows:
                        commodities = reporter["flows"][FLOW_LABELS[flow]]["commodities"]
                        for commodity_id, meta in PRIORITY_COMMODITIES.items():
                            if len(meta["hs"]) != 4 or int(meta["hs"][:2]) != chapter:
                                continue
                            series = commodities[commodity_id]
                            incoming = ((result.get("series_by_flow") or {}).get(flow) or {}).get(meta["hs"], [])
                            series["points"] = _merge(series["points"], incoming)
                            if not incoming and not series["points"]:
                                series["status"] = "no_data_or_confidential_in_national_source_response"
                if run["quota_capped"]:
                    break
                continue
            if iso3 == "KOR":
                for commodity_id, meta in PRIORITY_COMMODITIES.items():
                    if run["network_requests"] >= args.max_requests:
                        run["quota_capped"] = True
                        break
                    if last_request_at is not None:
                        pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                        if pause > 0:
                            time.sleep(pause)
                    result = korea_customs.fetch_monthly_hs_world(
                        period=period, hs_code=meta["hs"], cache_dir=args.cache_dir
                    )
                    cache = result.get("cache") or {}
                    if cache.get("hit"):
                        run["cache_hits"] += 1
                    else:
                        run["network_requests"] += 1
                        last_request_at = time.monotonic()
                    if not result.get("available"):
                        run["failures"].append(
                            {"reporter": iso3, "period": period, "hs": meta["hs"], "reason": result.get("reason", "no data")}
                        )
                        continue
                    run["successful_responses"] += 1
                    for flow in flows:
                        series = reporter["flows"][FLOW_LABELS[flow]]["commodities"][commodity_id]
                        incoming = (result.get("series_by_flow") or {}).get(flow, [])
                        series["points"] = _merge(series["points"], incoming)
                        if not incoming and not series["points"]:
                            series["status"] = "no_data_in_national_source_response"
                if run["quota_capped"]:
                    break
                continue
            for flow in flows:
                if run["network_requests"] >= args.max_requests:
                    run["quota_capped"] = True
                    break
                if last_request_at is not None:
                    pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                    if pause > 0:
                        time.sleep(pause)
                if iso3 == "IND":
                    result = india_tradestat.fetch_monthly_hs4_usd(period=period, flow=flow, hs_codes=hs4, cache_dir=args.cache_dir)
                elif iso3 == "NOR":
                    result = norway_ssb.fetch_monthly_hs_world(
                        period=period,
                        flow=flow,
                        hs_codes=[meta["hs"] for meta in PRIORITY_COMMODITIES.values()],
                        cache_dir=args.cache_dir,
                    )
                else:
                    result = None
                if iso3 == "THA":
                    commodities = reporter["flows"][FLOW_LABELS[flow]]["commodities"]
                    for commodity_id, meta in PRIORITY_COMMODITIES.items():
                        if run["network_requests"] >= args.max_requests:
                            run["quota_capped"] = True
                            break
                        if last_request_at is not None:
                            pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                            if pause > 0:
                                time.sleep(pause)
                        item_result = thailand_customs.fetch_monthly_hs_world(
                            period=period, flow=flow, hs_code=meta["hs"], cache_dir=args.cache_dir
                        )
                        cache = item_result.get("cache") or {}
                        if cache.get("hit"):
                            run["cache_hits"] += 1
                        else:
                            run["network_requests"] += 1
                            last_request_at = time.monotonic()
                        if not item_result.get("available"):
                            run["failures"].append(
                                {"reporter": iso3, "flow": flow, "period": period, "hs": meta["hs"], "reason": item_result.get("reason", "no data")}
                            )
                            continue
                        run["successful_responses"] += 1
                        series = commodities[commodity_id]
                        incoming = (item_result.get("series_by_hs") or {}).get(meta["hs"], [])
                        series["points"] = _merge(series["points"], incoming)
                        if not incoming and not series["points"]:
                            series["status"] = "no_data_in_national_source_response"
                    if run["quota_capped"]:
                        break
                    continue
                cache = result.get("cache") or {}
                if cache.get("hit"):
                    run["cache_hits"] += 1
                else:
                    run["network_requests"] += 1
                    last_request_at = time.monotonic()
                if not result.get("available"):
                    run["failures"].append(
                        {"reporter": iso3, "flow": flow, "period": period, "reason": result.get("reason", "no data")}
                    )
                    continue
                run["successful_responses"] += 1
                commodities = reporter["flows"][FLOW_LABELS[flow]]["commodities"]
                if iso3 != "IND":
                    for commodity_id, meta in PRIORITY_COMMODITIES.items():
                        series = commodities[commodity_id]
                        incoming = (result.get("series_by_hs") or {}).get(meta["hs"], [])
                        series["points"] = _merge(series["points"], incoming)
                        if not incoming and not series["points"]:
                            series["status"] = "no_data_in_national_source_response"
                    continue
                for commodity_id, meta in PRIORITY_COMMODITIES.items():
                    if len(meta["hs"]) != 4:
                        continue
                    series = commodities[commodity_id]
                    incoming = (result.get("series_by_hs") or {}).get(meta["hs"], [])
                    series["points"] = _merge(series["points"], incoming)
                    if not incoming and not series["points"]:
                        series["status"] = "no_data_in_national_source_response"
                for commodity_id, meta in PRIORITY_COMMODITIES.items():
                    if len(meta["hs"]) == 4:
                        continue
                    if run["network_requests"] >= args.max_requests:
                        run["quota_capped"] = True
                        break
                    if last_request_at is not None:
                        pause = args.min_interval_seconds - (time.monotonic() - last_request_at)
                        if pause > 0:
                            time.sleep(pause)
                    result = india_tradestat.fetch_monthly_specific_hs_usd(
                        period=period, flow=flow, hs_code=meta["hs"], cache_dir=args.cache_dir
                    )
                    cache = result.get("cache") or {}
                    if cache.get("hit"):
                        run["cache_hits"] += 1
                    else:
                        run["network_requests"] += 1
                        last_request_at = time.monotonic()
                    if not result.get("available"):
                        run["failures"].append(
                            {
                                "reporter": iso3,
                                "flow": flow,
                                "period": period,
                                "hs": meta["hs"],
                                "reason": result.get("reason", "no data"),
                            }
                        )
                        continue
                    run["successful_responses"] += 1
                    series = commodities[commodity_id]
                    incoming = (result.get("series_by_hs") or {}).get(meta["hs"], [])
                    series["points"] = _merge(series["points"], incoming)
                    if not incoming and not series["points"]:
                        series["status"] = result.get("empty_status") or "no_data_in_national_source_response"
                if run["quota_capped"]:
                    break
            if run["quota_capped"]:
                break
        if run["quota_capped"]:
            break
    _annotate(payload, args.end_month)
    run["completed_at"] = datetime.now(timezone.utc).isoformat()
    payload["generated_at"] = run["completed_at"]
    payload["reference_month"] = args.end_month
    payload.setdefault("runs", []).append(run)
    payload["collection_stats"] = _stats(payload)
    _write(args.out, payload)
    print(f"[national_priority] wrote {args.out}")
    if args.print_stats:
        print(json.dumps(payload["collection_stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

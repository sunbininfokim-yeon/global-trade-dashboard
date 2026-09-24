#!/usr/bin/env python3
"""Build commodity_trade_monthly_v1.json.

Priority: energy → minerals → agri.
Source order per commodity: Comtrade (if key) → domain free source (JODI/…) → null+reason.

HS hierarchy matching via hs_match.py when bridging code systems.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import math

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from hs_match import COMMODITY_HS_STEMS, hs_relation, resolve_commodity_id  # noqa: E402
from country_codes import iso2_to_iso3  # noqa: E402
from series_quality import annotate_monthly_payload  # noqa: E402
from sources import (  # noqa: E402
    abs_metal_ore,
    brazil_comexstat,
    cochilco_copper,
    comtrade,
    jodi_gas,
    jodi_oil,
    usa_ers_agri,
)
from world_link import world_rollup_policy, merge_reporters, link_country_world  # noqa: E402

PUBLIC = ROOT.parents[1] / "public" / "data"
CACHE = Path("/tmp/commodity_trade_cache")
BOARD_PATH = PUBLIC / "commodity_trade_board_v1.json"

SECTOR_ORDER = ("energy", "minerals", "agri_trade")
AGRI_IDS = {
    "wheat", "corn", "soybeans", "rice", "sunflowerseed_oil", "palm_oil",
    "sugar", "cotton", "soybean_meal", "barley", "soybean_oil",
}
MINERAL_IDS = {
    "iron_ore", "copper", "nickel", "bauxite", "aluminum", "cobalt",
    "graphite", "tungsten", "antimony", "lithium", "rare_earths",
    "gallium", "germanium",
}

def trailing_window(months_sorted: list[str], n: int = 12) -> list[str]:
    if not months_sorted:
        return []
    return months_sorted[-n:]


def latest_month(points: list[dict]) -> str | None:
    if not points:
        return None
    return max(p["month"] for p in points if p.get("month"))


def build_energy(cache: Path) -> dict:
    jodi = jodi_oil.load_export_series(cache_dir=cache, years=[2025, 2026])
    try:
        gas = jodi_gas.load_lng_export_series(cache_dir=cache)
    except Exception as exc:
        gas = {"available": False, "reason": f"JODI-Gas retrieval failed: {exc}", "series": {"lng": {}}}
    # merge gas lng series into oil bundle shape
    if gas.get("available"):
        jodi.setdefault("series", {})
        jodi["series"]["lng"] = gas.get("series", {}).get("lng") or {}
    commodities = {}
    for cid, by_ctry in (jodi.get("series") or {}).items():
        countries = {}
        all_months = set()
        for iso2, pts in by_ctry.items():
            iso3 = iso2_to_iso3(iso2)
            if not iso3:
                raise ValueError(f"JODI returned unmapped ISO2 country code: {iso2!r}")
            months = sorted({p["month"] for p in pts})
            win = trailing_window(months, 12)
            pts_win = [p for p in pts if p["month"] in win]
            if not pts_win:
                continue
            countries[iso3] = {
                "iso2": iso2,
                "iso3": iso3,
                "latest_available_month": latest_month(pts_win),
                "points": pts_win,
                "point_count": len(pts_win),
            }
            all_months.update(win)
        if not countries:
            continue
        latest = max(all_months) if all_months else None
        commodities[cid] = {
            "commodity_id": cid,
            "sector": "energy",
            "stage2_status": "monthly_available",
            "latest_available_month": latest,
            "window_rule": "latest_available_month back 12 inclusive",
            "default_month": latest,
            "source_primary": "jodi_gas" if cid == "lng" else "jodi_oil",
            "comtrade_status": "not_requested",
            "hs_stems": COMMODITY_HS_STEMS.get(cid, []),
            "code_bridge": {
                "from_system": "JODI",
                "to_system": "HS",
                "example": "CRUDEOIL → 2709",
                "relation": "alias",
                "algorithm": "hs_match.resolve_commodity_id + PRODUCT_ALIASES",
            },
            "countries": countries,
            "country_count": len(countries),
        }
    return {
        "sector": "energy",
        "source_bundle": {
            "jodi_oil": {
                "available": jodi.get("available"),
                "url": jodi.get("source_url"),
                "files": jodi.get("files"),
                "note_ko": jodi.get("note_ko"),
            },
            "jodi_gas": {
                "available": gas.get("available"),
                "url": gas.get("source_url"),
                "download": gas.get("download"),
                "note_ko": gas.get("note_ko"),
            },
        },
        "commodities": commodities,
    }



def build_minerals(cache: Path) -> dict:
    bra = brazil_comexstat.load_mineral_exports(cache_dir=cache, years=[2025, 2026])
    chl = cochilco_copper.load_copper_exports(cache_dir=cache)
    aus = abs_metal_ore.load_iron_ore_proxy(cache_dir=cache)
    # merge extra country series into bra-shaped map
    merged_series = dict(bra.get("series") or {})
    for cid, by_ctry in (chl.get("series") or {}).items():
        merged_series.setdefault(cid, {}).update(by_ctry)
    for cid, by_ctry in (aus.get("series") or {}).items():
        merged_series.setdefault(cid, {}).update(by_ctry)
    commodities = {}
    for cid, by_ctry in merged_series.items():
        if cid not in MINERAL_IDS:
            continue
        countries = {}
        all_months = set()
        for iso3, pts in by_ctry.items():
            months = sorted({p["month"] for p in pts})
            win = trailing_window(months, 12)
            pts_win = [p for p in pts if p["month"] in win]
            if not pts_win:
                continue
            countries[iso3] = {
                "iso3": iso3,
                "latest_available_month": latest_month(pts_win),
                "points": pts_win,
                "point_count": len(pts_win),
            }
            all_months.update(win)
        if not countries:
            continue
        latest = max(all_months) if all_months else None
        commodities[cid] = {
            "commodity_id": cid,
            "sector": "minerals",
            "stage2_status": "monthly_partial",
            "latest_available_month": latest,
            "window_rule": "latest_available_month back 12 inclusive",
            "default_month": latest,
            "source_primary": "national_open_data",
            "reporters": sorted(countries.keys()),
            "comtrade_status": "not_requested",
            "coverage_ko": "국가 세관/통계 공개분만 합침(BRA+CHL+AUS 해당 시). 세계 전체가 아님. 단위가 국가마다 다를 수 있음.",
            "hs_stems": COMMODITY_HS_STEMS.get(cid, []),
            "code_bridge": {
                "from_system": "NCM",
                "to_system": "HS4",
                "relation": "child → parent bucket sum",
                "algorithm": "hs_match.hs_relation + STEM_TO_COMMODITY",
            },
            "countries": countries,
            "country_count": len(countries),
        }
    return {
        "sector": "minerals",
        "source_bundle": {
            "brazil_comexstat": {
                "available": bra.get("available"),
                "url": bra.get("source_url"),
                "files": bra.get("files"),
                "note_ko": bra.get("note_ko"),
            },
            "cochilco_copper": {
                "available": chl.get("available"),
                "url": chl.get("source_url"),
                "note_ko": chl.get("note_ko"),
            },
            "abs_metal_ore": {
                "available": aus.get("available"),
                "url": aus.get("source_url"),
                "note_ko": aus.get("note_ko"),
            },
        },
        "commodities": commodities,
    }



def build_agri(cache: Path) -> dict:
    """Agri monthly: Brazil ComexStat + US ERS World-total exports; PSD annual separate."""
    bra = brazil_comexstat.load_mineral_exports(cache_dir=cache, years=[2025, 2026])
    usa = usa_ers_agri.load_us_agri_exports(cache_dir=cache)
    series = {k: v for k, v in (bra.get("series") or {}).items() if k in AGRI_IDS}
    for cid, by_ctry in (usa.get("series") or {}).items():
        series.setdefault(cid, {}).update(by_ctry)
    commodities = {}
    for cid, by_ctry in series.items():
        countries = {}
        all_months = set()
        for iso3, pts in by_ctry.items():
            months = sorted({p["month"] for p in pts})
            win = trailing_window(months, 12)
            pts_win = [p for p in pts if p["month"] in win]
            if not pts_win:
                continue
            countries[iso3] = {
                "iso3": iso3,
                "latest_available_month": latest_month(pts_win),
                "points": pts_win,
                "point_count": len(pts_win),
            }
            all_months.update(win)
        if not countries:
            continue
        latest = max(all_months) if all_months else None
        commodities[cid] = {
            "commodity_id": cid,
            "sector": "agri_trade",
            "stage2_status": "monthly_partial",
            "latest_available_month": latest,
            "window_rule": "latest_available_month back 12 inclusive",
            "default_month": latest,
            "source_primary": "brazil_comexstat",
            "reporters": sorted(countries.keys()),
            "coverage_ko": "BRA(ComexStat kg) + USA(ERS 대세계 수출 톤, 해당 품목). 단위 혼재 시 합산 금지. 세계 공급≠미국 World total.",
            "hs_stems": COMMODITY_HS_STEMS.get(cid, []),
            "code_bridge": {
                "from_system": "NCM",
                "to_system": "HS4",
                "relation": "child → parent bucket sum",
            },
            "countries": countries,
            "country_count": len(countries),
            "related_annual": ["russia_export_pulse_v1.json"] if cid in ("wheat", "sunflowerseed_oil") else [],
        }
    # country ↔ world linking algorithm (not side-by-side only)
    for cid, block in commodities.items():
        units = {
            iso: (block["countries"][iso]["points"][-1]["unit"] if block["countries"][iso]["points"] else "")
            for iso in block["countries"]
        }
        meta = merge_reporters(
            cid,
            {iso: block["countries"][iso]["points"] for iso in block["countries"]},
            units=units,
        )
        linked = link_country_world(
            cid,
            block["countries"],
            usa_is_export_to_world=("USA" in block["countries"]),
        )
        block["world_link"] = {**meta, **linked}
        if "USA" in block["countries"]:
            block["world_link"]["usa_series_mode"] = "reporter_export_to_world"

    return {
        "sector": "agri_trade",
        "source_bundle": {
            "brazil_comexstat": {
                "available": bool(series),
                "url": bra.get("source_url"),
                "note_ko": "농산물도 동일 EXP_YYYY.csv. 대두·설탕·옥수수 등 브라질 강세 품목 우선.",
            },
            "usa_ers_fatus": {
                "available": usa.get("available"),
                "url": usa.get("source_url"),
                "note_ko": usa.get("note_ko"),
                "world_semantics": usa.get("world_semantics"),
            },
            "usda_psd_annual": {
                "note_ko": "마케팅연도 정본은 russia_export_pulse / PSD. 월별과 합산 금지.",
            },
        },
        "world_link_policy": world_rollup_policy(),
        "commodities": commodities,
    }


def stub_sector(sector: str, board: dict, reason: str) -> dict:
    """Placeholders for minerals/agri until their free adapters land."""
    ids = []
    for s in board.get("sectors") or []:
        if s.get("id") == sector:
            ids = s.get("commodities") or []
    commodities = {}
    for cid in ids:
        meta = (board.get("commodities") or {}).get(cid) or {}
        commodities[cid] = {
            "commodity_id": cid,
            "sector": sector,
            "stage2_status": meta.get("stage2_data_status") or "monthly_planned",
            "latest_available_month": None,
            "countries": {},
            "country_count": 0,
            "reason_ko": reason,
            "hs_stems": COMMODITY_HS_STEMS.get(cid, meta.get("hs_hints") or []),
        }
    return {"sector": sector, "commodities": commodities, "reason_ko": reason}


def _sector_board_ids(board: dict, sector: str) -> list[str]:
    for block in board.get("sectors") or []:
        if block.get("id") == sector:
            return list(block.get("commodities") or [])
    return []


def _missing_commodity(sector: str, commodity_id: str, reason: str) -> dict[str, Any]:
    return {
        "commodity_id": commodity_id,
        "sector": sector,
        "stage2_status": "monthly_planned",
        "latest_available_month": None,
        "default_month": None,
        "countries": {},
        "country_count": 0,
        "reason_ko": reason,
        "hs_stems": COMMODITY_HS_STEMS.get(commodity_id, []),
        "comtrade_status": "not_requested",
    }


def align_sector_to_board(sector: str, payload: dict[str, Any], board: dict) -> dict[str, Any]:
    """Make missing board commodities explicit and keep non-board data auditable."""
    expected = _sector_board_ids(board, sector)
    if not expected:
        return payload
    commodities = payload.setdefault("commodities", {})
    extras = {
        cid: commodities.pop(cid)
        for cid in list(commodities)
        if cid not in expected
    }
    if extras:
        payload["supplemental_commodities"] = extras
    for cid in expected:
        commodities.setdefault(
            cid,
            _missing_commodity(
                sector,
                cid,
                "이 품목의 월별 무료 소스 어댑터가 아직 연결되지 않았습니다.",
            ),
        )
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _validate_monthly_contract(payload: dict[str, Any], board: dict) -> None:
    """Fail closed on join-breaking country codes or malformed monthly points."""
    problems: list[str] = []
    sectors = payload.get("sectors") or {}
    for sector in SECTOR_ORDER:
        expected = set(_sector_board_ids(board, sector))
        actual = set((sectors.get(sector) or {}).get("commodities") or {})
        if expected and actual != expected:
            problems.append(f"{sector}: board/output commodity mismatch")
    for sector, block in sectors.items():
        for cid, commodity in (block.get("commodities") or {}).items():
            for iso3, country in (commodity.get("countries") or {}).items():
                if len(iso3) != 3 or not iso3.isalpha() or not iso3.isupper():
                    problems.append(f"{sector}/{cid}: invalid iso3 key {iso3!r}")
                months: list[str] = []
                for point in country.get("points") or []:
                    month = point.get("month")
                    if point.get("unit") == "CONVBBL":
                        problems.append(f"{sector}/{cid}/{iso3}: CONVBBL is not trade volume")
                    if point.get("unit") == "KTONS":
                        normalized = point.get("normalized") or {}
                        try:
                            expected_kg = float(point["value"]) * 1_000_000
                            valid = normalized.get("unit") == "kg" and math.isfinite(expected_kg) and math.isclose(
                                float(normalized.get("value")), expected_kg, rel_tol=1e-12)
                        except (TypeError, ValueError, KeyError):
                            valid = False
                        if not valid:
                            problems.append(f"{sector}/{cid}/{iso3}: invalid KTONS normalization")
                    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
                        problems.append(f"{sector}/{cid}/{iso3}: invalid month {month!r}")
                    elif not point.get("unit"):
                        problems.append(f"{sector}/{cid}/{iso3}/{month}: missing unit")
                    else:
                        months.append(month)
                if len(months) != len(set(months)):
                    problems.append(f"{sector}/{cid}/{iso3}: duplicate monthly points")
    if problems:
        raise ValueError("Monthly contract validation failed: " + "; ".join(problems[:12]))


def _stats(payload: dict[str, Any]) -> dict[str, Any]:
    sectors: dict[str, Any] = {}
    for sector, block in (payload.get("sectors") or {}).items():
        commodities = block.get("commodities") or {}
        sectors[sector] = {
            "commodity_count": len(commodities),
            "with_points": sum(bool(c.get("countries")) for c in commodities.values()),
            "country_count": sum(len(c.get("countries") or {}) for c in commodities.values()),
            "point_count": sum(
                len(country.get("points") or [])
                for commodity in commodities.values()
                for country in (commodity.get("countries") or {}).values()
            ),
        }
    return {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "build_order": payload.get("build_order"),
        "sectors": sectors,
    }


def _parse_comtrade_reporters(value: str) -> dict[str, str]:
    """Parse ``USA=842,CHN=156`` without baking a country/M49 table into code."""
    reporters: dict[str, str] = {}
    if not value.strip():
        return reporters
    for item in value.split(","):
        iso3, separator, m49 = item.strip().upper().partition("=")
        if not separator or len(iso3) != 3 or not iso3.isalpha() or not m49.isdigit():
            raise ValueError("--comtrade-reporters must be comma-separated ISO3=M49 pairs")
        reporters[iso3] = m49
    return reporters


def _last_monthly_periods(end_month: str, n: int = 12) -> str:
    year, month = (int(part) for part in end_month.split("-"))
    periods: list[str] = []
    for _ in range(n):
        periods.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return ",".join(reversed(periods))


def overlay_comtrade_monthly(
    sectors: dict[str, Any], *, reporters: dict[str, str], periods: str, max_requests: int
) -> dict[str, Any]:
    """Overlay explicitly requested Comtrade reporter series, within a hard quota cap."""
    if not reporters:
        return {"enabled": False, "reason": "no reporters requested", "requests": 0, "loaded": 0}
    if max_requests < 1:
        raise ValueError("Comtrade reporters require --comtrade-max-requests >= 1")
    requests = loaded = 0
    failures: list[dict[str, str]] = []
    for block in sectors.values():
        for cid, commodity in (block.get("commodities") or {}).items():
            stems = commodity.get("hs_stems") or []
            if not stems:
                continue
            for iso3, m49 in reporters.items():
                if requests >= max_requests:
                    return {"enabled": True, "requests": requests, "loaded": loaded, "failures": failures, "quota_capped": True}
                requests += 1
                result = comtrade.fetch_monthly(hs=stems[0], reporter_m49=m49, periods=periods)
                if not result.get("available"):
                    failures.append({"commodity_id": cid, "reporter": iso3, "reason": str(result.get("reason") or "no data")})
                    continue
                points = result.get("series") or []
                commodity.setdefault("countries", {})[iso3] = {
                    "iso3": iso3,
                    "latest_available_month": latest_month(points),
                    "points": points,
                    "point_count": len(points),
                }
                commodity["country_count"] = len(commodity["countries"])
                if commodity.get("stage2_status") == "monthly_planned":
                    commodity["stage2_status"] = "monthly_partial"
                latest = max(
                    (
                        country.get("latest_available_month")
                        for country in commodity["countries"].values()
                        if country.get("latest_available_month")
                    ),
                    default=None,
                )
                commodity["latest_available_month"] = latest
                commodity["default_month"] = latest
                commodity["comtrade_status"] = "loaded_for_selected_reporters"
                loaded += 1
    return {"enabled": True, "requests": requests, "loaded": loaded, "failures": failures, "quota_capped": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sectors", default="energy,minerals,agri_trade", help="comma list order")
    ap.add_argument("--out", type=Path, default=PUBLIC / "commodity_trade_monthly_v1.json")
    ap.add_argument(
        "--replace-output",
        action="store_true",
        help="replace the output instead of preserving sectors not selected (complete build only)",
    )
    ap.add_argument(
        "--no-fetch",
        action="store_true",
        help="validate and optionally print stats from an existing output without contacting sources",
    )
    ap.add_argument("--print-stats", action="store_true", help="print standardized coverage stats as JSON")
    ap.add_argument(
        "--calendar-month",
        default=datetime.now(timezone.utc).strftime("%Y-%m"),
        help="YYYY-MM used for output metadata and the default Comtrade 12-month request window",
    )
    ap.add_argument(
        "--comtrade-reporters",
        default="",
        help="explicit monthly Comtrade reporters as ISO3=M49 pairs, e.g. USA=842,CHN=156",
    )
    ap.add_argument(
        "--comtrade-max-requests",
        type=int,
        default=0,
        help="hard maximum Comtrade requests; leave at 0 unless a quota-limited run is intended",
    )
    args = ap.parse_args()

    board = {}
    if BOARD_PATH.exists():
        board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))

    sectors_wanted = [s.strip() for s in args.sectors.split(",") if s.strip()]
    unknown = [s for s in sectors_wanted if s not in SECTOR_ORDER and s != "agri"]
    if unknown:
        ap.error(f"unknown sectors: {', '.join(unknown)}")
    sectors_wanted = ["agri_trade" if s == "agri" else s for s in sectors_wanted]
    if len(set(sectors_wanted)) != len(sectors_wanted):
        ap.error("--sectors must not contain duplicates")
    try:
        datetime.strptime(args.calendar_month, "%Y-%m")
    except ValueError:
        ap.error("--calendar-month must be YYYY-MM")

    if args.no_fetch:
        existing = _load_json(args.out)
        if not existing:
            ap.error(f"--no-fetch requires an existing output: {args.out}")
        try:
            _validate_monthly_contract(existing, board)
        except ValueError as exc:
            ap.error(str(exc))
        if args.print_stats:
            print(json.dumps(_stats(existing), ensure_ascii=False, indent=2))
        return 0

    if args.replace_output and set(sectors_wanted) != set(SECTOR_ORDER):
        ap.error("--replace-output is only allowed with all sectors to prevent accidental sector loss")

    previous = _load_json(args.out)
    sector_payload = {} if args.replace_output else dict(previous.get("sectors") or {})

    for sec in sectors_wanted:
        if sec == "energy":
            print("[build_monthly] energy via JODI…", flush=True)
            sector_payload[sec] = build_energy(CACHE)
            n = len(sector_payload[sec].get("commodities") or {})
            print(f"[build_monthly] energy commodities with data: {n}", flush=True)
        elif sec == "minerals":
            print("[build_monthly] minerals via Brazil ComexStat…", flush=True)
            sector_payload[sec] = build_minerals(CACHE)
            n = len(sector_payload[sec].get("commodities") or {})
            print(f"[build_monthly] mineral commodities with data: {n}", flush=True)
        elif sec == "agri_trade":
            print("[build_monthly] agri via Brazil ComexStat…", flush=True)
            sector_payload[sec] = build_agri(CACHE)
            n = len(sector_payload[sec].get("commodities") or {})
            print(f"[build_monthly] agri commodities with data: {n}", flush=True)

    for sec in SECTOR_ORDER:
        if sec in sector_payload:
            sector_payload[sec] = align_sector_to_board(sec, sector_payload[sec], board)

    try:
        reporters = _parse_comtrade_reporters(args.comtrade_reporters)
        comtrade_run = overlay_comtrade_monthly(
            {sec: sector_payload[sec] for sec in sectors_wanted},
            reporters=reporters,
            periods=_last_monthly_periods(args.calendar_month),
            max_requests=args.comtrade_max_requests,
        )
    except ValueError as exc:
        ap.error(str(exc))

    quality_contract = annotate_monthly_payload(sector_payload, args.calendar_month)

    # demo hs_match self-check in meta
    demos = [
        hs_relation("2709", "270900").__dict__,
        hs_relation("2709", "2710").__dict__,
        hs_relation("1001", "100199").__dict__,
    ]

    out = {
        "schema_version": "commodity-trade-monthly-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "calendar_month_now": args.calendar_month,
        "build_order": [sec for sec in SECTOR_ORDER if sec in sector_payload],
        "last_updated_sectors": sectors_wanted,
        "source_policy_ko": (
            "기본은 도메인 무료 소스(JODI 등). Comtrade 월별값은 키와 명시적 보고국이 있을 때만 "
            "선택적으로 덮어쓴다. "
            "코드 체계가 다르면 hs_match로 same/parent/child/alias 판정 후 병합. "
            "sibling은 자동 합산 금지. 숫자 발명 금지."
        ),
        "hs_match_demo": demos,
        "ui_contract": {
            "stage1": "annual or latest year rollup + export_controls color",
            "stage2": "points[] monthly trailing 12 from latest_available_month",
            "default_month": "latest_available_month",
        },
        "comtrade_run": comtrade_run,
        "quality_contract": quality_contract,
        "sectors": sector_payload,
    }

    try:
        _validate_monthly_contract(out, board)
    except ValueError as exc:
        ap.error(str(exc))
    _atomic_write_json(args.out, out)
    print(f"[build_monthly] wrote {args.out}", flush=True)

    # Never update the live board while writing an alternate output for QA.
    if BOARD_PATH.exists() and args.out.resolve() == (PUBLIC / "commodity_trade_monthly_v1.json").resolve():
        for sec_name in ("energy", "minerals", "agri_trade"):
            if sec_name not in sector_payload:
                continue
            for cid, block in (sector_payload[sec_name].get("commodities") or {}).items():
                if cid in board.get("commodities", {}):
                    st = block.get("stage2_status") or "monthly_available"
                    board["commodities"][cid]["stage2_data_status"] = st
                    board["commodities"][cid]["latest_available_month"] = block.get("latest_available_month")
        board["as_of"] = out["generated_at"][:10]
        _atomic_write_json(BOARD_PATH, board)
        print("[build_monthly] board stage2_status updated", flush=True)
    if args.print_stats:
        print(json.dumps(_stats(out), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

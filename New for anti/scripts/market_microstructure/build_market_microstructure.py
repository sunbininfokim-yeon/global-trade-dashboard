#!/usr/bin/env python3
"""Build market_microstructure_v1.json (+ TABLES.md).

Live:
  export KRX_API=...   # optional; Cloudflare secret name
  python build_market_microstructure.py --live --source auto --print-stats
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market_microstructure.ai_casino_brief import (  # noqa: E402
    build_ai_casino_brief,
    markdown_ai_casino_brief,
)
from market_microstructure.engine import build_snapshot, load_json, markdown_tables  # noqa: E402


_REUSABLE_QUALITIES = {"observed", "carried_forward"}
_PUBLIC_EXTRA_MIRRORS = (
    ("deposit_credit", "deposit_credit"),
    ("letf_category_share", "letf_category_share"),
    ("short_interest_meta", "short_interest"),
)


def _as_iso_date(value: object) -> str | None:
    """Normalize source dates without inventing an observation timestamp."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d{4})[-./](\d{2})[-./](\d{2})", value.strip())
    if not match:
        return None
    return "-".join(match.groups())


def _observed_as_of(value: dict[str, Any], fallback: str) -> str:
    """Use the source's date when it supplies one, otherwise the snapshot day."""
    for key in ("as_of", "date", "date_raw"):
        parsed = _as_iso_date(value.get(key))
        if parsed:
            return parsed
    latest = value.get("latest")
    if isinstance(latest, dict):
        for key in ("as_of", "date", "date_raw"):
            parsed = _as_iso_date(latest.get(key))
            if parsed:
                return parsed
    return fallback


def _retain_observation(
    current: Any,
    previous: Any,
    *,
    snapshot_as_of: str,
    previous_snapshot_as_of: str,
) -> Any:
    """Keep a prior observation only when this run did not observe one.

    A carried value retains the source observation date in ``as_of`` and is
    explicitly marked, so consumers cannot mistake it for today's result.
    """
    if isinstance(current, dict) and current.get("quality") == "observed":
        result = copy.deepcopy(current)
        result["as_of"] = _observed_as_of(result, snapshot_as_of)
        result.pop("carried_at", None)
        return result
    if not isinstance(previous, dict) or previous.get("quality") not in _REUSABLE_QUALITIES:
        return current
    result = copy.deepcopy(previous)
    result["as_of"] = _observed_as_of(result, previous_snapshot_as_of)
    result["quality"] = "carried_forward"
    result["carried_at"] = snapshot_as_of
    return result


def preserve_unobserved_public_observations(
    snapshot: dict[str, Any], previous: dict[str, Any] | None
) -> dict[str, Any]:
    """Carry forward failed public-source blocks, with explicit freshness data.

    ``build_snapshot`` intentionally emits missing/null blocks for unavailable
    collectors.  This function is the snapshot-level counterpart to the
    derivatives-board fallback: it preserves only a known prior observation,
    never manufactures a value when both runs are unavailable.
    """
    if not isinstance(previous, dict):
        return snapshot
    snapshot_as_of = str(snapshot.get("as_of") or "")
    previous_snapshot_as_of = str(previous.get("as_of") or "")
    if not _as_iso_date(snapshot_as_of) or not _as_iso_date(previous_snapshot_as_of):
        return snapshot

    # This ratio object is derived entirely from the FDR LETF listing.  Keep
    # it as one atomic observation so its numerator, denominator, and buckets
    # cannot drift out of sync.
    snapshot["market_letf_derivatives_ratios"] = _retain_observation(
        snapshot.get("market_letf_derivatives_ratios"),
        previous.get("market_letf_derivatives_ratios"),
        snapshot_as_of=snapshot_as_of,
        previous_snapshot_as_of=previous_snapshot_as_of,
    )

    current_public = snapshot.get("public_extras")
    previous_public = previous.get("public_extras")
    if not isinstance(current_public, dict):
        current_public = {}
    if not isinstance(previous_public, dict):
        previous_public = {}

    # Keep the top-level UI aliases and their public-extras source blocks in
    # lockstep.  This covers the FDR LETF listing plus the other independent
    # collectors in fetch_kr_public_extras.py (FreeSIS and public Naver flow).
    for snapshot_key, public_key in _PUBLIC_EXTRA_MIRRORS:
        retained = _retain_observation(
            snapshot.get(snapshot_key),
            previous.get(snapshot_key),
            snapshot_as_of=snapshot_as_of,
            previous_snapshot_as_of=previous_snapshot_as_of,
        )
        snapshot[snapshot_key] = retained
        current_public[public_key] = copy.deepcopy(retained)

    snapshot["flows_kospi_market"] = _retain_observation(
        snapshot.get("flows_kospi_market"),
        previous.get("flows_kospi_market"),
        snapshot_as_of=snapshot_as_of,
        previous_snapshot_as_of=previous_snapshot_as_of,
    )
    current_public["kospi_investor_flows"] = _retain_observation(
        current_public.get("kospi_investor_flows"),
        previous_public.get("kospi_investor_flows"),
        snapshot_as_of=snapshot_as_of,
        previous_snapshot_as_of=previous_snapshot_as_of,
    )
    snapshot["public_extras"] = current_public
    return snapshot


def _load_existing_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"previous snapshot ignored: {exc}")
        return None
    return value if isinstance(value, dict) else None


def _fetch_trading_share() -> dict:
    """FDR: cash vs levered/inverse ETF turnover shares (Amount unit=백만원 for ETF)."""
    import FinanceDataReader as fdr

    unit = 1_000_000.0
    etfs = fdr.StockListing("ETF/KR")
    kospi = fdr.StockListing("KOSPI")
    kosdaq = fdr.StockListing("KOSDAQ")
    lev = etfs[etfs["Name"].astype(str).str.contains("레버리지|인버스|곱버스", na=False)]
    ss = etfs[etfs["Name"].astype(str).str.contains("단일종목", na=False)]
    kospi_tv = float(kospi["Amount"].sum())
    kosdaq_tv = float(kosdaq["Amount"].sum())
    etf_tv = float(etfs["Amount"].sum()) * unit
    lev_tv = float(lev["Amount"].sum()) * unit
    ss_tv = float(ss["Amount"].sum()) * unit
    return {
        "kospi_jo": round(kospi_tv / 1e12, 2),
        "kosdaq_jo": round(kosdaq_tv / 1e12, 2),
        "etf_jo": round(etf_tv / 1e12, 2),
        "lev_jo": round(lev_tv / 1e12, 2),
        "ss_jo": round(ss_tv / 1e12, 2),
        "lev_of_etf_pct": round(100.0 * lev_tv / etf_tv, 1) if etf_tv else None,
        "lev_of_kospi_pct": round(100.0 * lev_tv / kospi_tv, 1) if kospi_tv else None,
        "lev_of_cash_pct": round(100.0 * lev_tv / (kospi_tv + kosdaq_tv), 1)
        if (kospi_tv + kosdaq_tv)
        else None,
        "ss_of_kospi_pct": round(100.0 * ss_tv / kospi_tv, 2) if kospi_tv else None,
        "source": "FinanceDataReader ETF/KR Amount(백만원) + KOSPI/KOSDAQ Amount",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--day",
        type=Path,
        default=ROOT / "tests/fixtures/demo_day.json",
        help="Day input JSON (fixture or live export)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Fetch KR day + HK/crypto venues, then build",
    )
    p.add_argument(
        "--source",
        choices=["auto", "krx", "fdr"],
        default="auto",
        help="KR live source: auto uses env KRX_API when present",
    )
    p.add_argument("--bas-dd", default=None, help="KRX basDd YYYYMMDD")
    p.add_argument("--fx", type=float, default=1400.0)
    p.add_argument("--usdhkd", type=float, default=7.8)
    p.add_argument(
        "--skip-external",
        action="store_true",
        help="Do not fetch HK/Yahoo + Binance venues",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "../../public/data/market_microstructure_v1.json",
    )
    p.add_argument(
        "--tables",
        type=Path,
        default=ROOT / "TABLES.md",
        help="Markdown tables path",
    )
    p.add_argument(
        "--brief",
        type=Path,
        default=ROOT / "../../public/data/ai_casino_brief_v1.json",
        help="AI Casino–style brief JSON",
    )
    p.add_argument(
        "--brief-md",
        type=Path,
        default=ROOT / "AI_CASINO_BRIEF.md",
        help="AI Casino–style brief markdown",
    )
    p.add_argument(
        "--external-snapshot-out",
        type=Path,
        default=ROOT / "../../public/data/external_venues_v1.json",
        help="dated external venue snapshot for the append-only history step",
    )
    p.add_argument(
        "--skip-extras",
        action="store_true",
        help="Skip Naver deposit/credit, KOSPI flows, LETF categories, shorts",
    )
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    if args.live:
        from fetch_kr_live import build_day

        day = build_day(
            source=args.source,
            fx_usdkrw=args.fx,
            bas_dd=args.bas_dd,
            skip_extras=args.skip_extras,
        )
        if not args.skip_external:
            from fetch_external_venues import build_external_venues

            day["external_venues"] = build_external_venues(
                usdkrw=args.fx, usdhkd=args.usdhkd
            )
            ext_path = ROOT / "tests/fixtures/external_venues.json"
            ext_path.write_text(
                json.dumps(day["external_venues"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            # Keep the source snapshot in the publish tree so the following
            # append step can run independently of this process.  The history
            # writer will preserve the Yahoo bar date and mark unstamped AUM
            # as partial; it never derives a date from fetched_at.
            args.external_snapshot_out.parent.mkdir(parents=True, exist_ok=True)
            args.external_snapshot_out.write_text(
                json.dumps(day["external_venues"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"External snapshot → {args.external_snapshot_out}")
            print(f"Fetched external venues → {ext_path}")
        try:
            day["trading_share"] = _fetch_trading_share()
        except Exception as e:  # noqa: BLE001
            print(f"trading_share skip: {e}")
        live_path = ROOT / "tests/fixtures/live_day.json"
        live_path.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Fetched live day mode={day.get('source_mode')} → {live_path}")
    else:
        day = load_json(args.day)
        # optional attach saved external fixture
        ext_path = ROOT / "tests/fixtures/external_venues.json"
        if "external_venues" not in day and ext_path.exists() and not args.skip_external:
            day["external_venues"] = load_json(ext_path)
        if "trading_share" not in day:
            try:
                day["trading_share"] = _fetch_trading_share()
            except Exception:
                pass
        if not args.skip_extras and "public_extras" not in day:
            try:
                from fetch_kr_live import _attach_public_extras

                _attach_public_extras(day)
            except Exception as e:  # noqa: BLE001
                print(f"public_extras skip: {e}")

    snap = build_snapshot(day)
    snap = preserve_unobserved_public_observations(
        snap, _load_existing_snapshot(args.out)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = markdown_tables(snap)
    args.tables.write_text(md, encoding="utf-8")

    brief = build_ai_casino_brief(snap, day=day)
    args.brief.parent.mkdir(parents=True, exist_ok=True)
    args.brief.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    brief_md = markdown_ai_casino_brief(brief)
    args.brief_md.write_text(brief_md, encoding="utf-8")

    if args.print_stats:
        print(brief_md)
        print("---")
        print(md)
    print(f"Wrote {args.out}")
    print(f"Wrote {args.tables}")
    print(f"Wrote {args.brief}")
    print(f"Wrote {args.brief_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

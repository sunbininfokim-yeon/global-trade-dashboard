#!/usr/bin/env python3
"""Build public/data/russia_export_pulse_v1.json

Official free sources only:
  - USDA PSD CSV zips (marketing-year exports)
  - IMF PortWatch Bosporus dry_bulk (exit proxy, not Russia-only)
  - Optional Comtrade monthly when COMTRADE_SUBSCRIPTION_KEY is set
  - Policy event seed file (no invented ban dates)

Does not touch shipping.js / app.js.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # New for anti/
PUBLIC = ROOT / "public" / "data" / "russia_export_pulse_v1.json"
POLICY = HERE / "config" / "policy_events.json"

# shipping_capacity on sys.path for PortWatch client
sys.path.insert(0, str(HERE.parent / "shipping_capacity"))

from comtrade_monthly import HS_SERIES, default_recent_periods, fetch_monthly_exports  # noqa: E402
from psd_exports import (  # noqa: E402
    contribution_table,
    export_series,
    load_psd_table,
    series_payload,
)


def log(msg: str) -> None:
    print(f"[russia_export_pulse] {msg}", flush=True)


def load_policy() -> list[dict[str, Any]]:
    with POLICY.open(encoding="utf-8") as fh:
        return json.load(fh)


def bosporus_proxy(fetch: bool) -> dict[str, Any]:
    base = {
        "id": "bosporus",
        "name_en": "Bosporus Strait",
        "portwatch_id": "chokepoint3",
        "role": "black_sea_exit_proxy",
        "caveat_ko": (
            "흑해 전체 통과 dry_bulk capacity. 러시아·우크라이나·루마니아·불가리아 등이 섞인다. "
            "러시아 수출량 정본이 아니다. 다크십·AIS 재밍 구간에서는 과소 관측 가능."
        ),
    }
    if not fetch:
        base["available"] = False
        base["reason"] = "run with --fetch-portwatch"
        return base
    try:
        from shipping_capacity.portwatch import PortWatchClient
        status = PortWatchClient().fetch_status("chokepoint3")
        dry = (status.get("metrics") or {}).get("dry_bulk") or {}
        tanker = (status.get("metrics") or {}).get("tanker") or {}
        base.update({
            "available": True,
            "latest_date": status.get("latest_date"),
            "quality": status.get("quality"),
            "interpretation": status.get("interpretation"),
            "metrics": {
                "dry_bulk": {
                    "change_pct_7d_vs_28d": dry.get("change_pct"),
                    "current_7d_mean_dwt": dry.get("current_7d_mean_dwt"),
                    "prior_28d_mean_dwt": dry.get("prior_28d_mean_dwt"),
                },
                "tanker": {
                    "change_pct_7d_vs_28d": tanker.get("change_pct"),
                    "current_7d_mean_dwt": tanker.get("current_7d_mean_dwt"),
                    "prior_28d_mean_dwt": tanker.get("prior_28d_mean_dwt"),
                },
            },
        })
    except Exception as exc:  # noqa: BLE001 — surface as payload failure
        base["available"] = False
        base["reason"] = str(exc)
    return base


def build_wheat(grains: Any) -> dict[str, Any]:
    ru = export_series(grains, commodity="Wheat", country="Russia")
    world = export_series(grains, commodity="Wheat", country="World")
    contrib = contribution_table(ru, world)
    latest = contrib[-1] if contrib else {}
    return {
        "commodity": "wheat",
        "label_ko": "밀",
        "label_en": "Wheat",
        "russia_exports": series_payload(
            ru,
            source_name="USDA FAS PSD grains_pulses CSV",
            source_url="https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
        ),
        "world_exports": series_payload(
            world,
            source_name="USDA FAS PSD grains_pulses CSV (country sum)",
            source_url="https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
            construction=(
                "Sum of country Exports rows excluding European Union and "
                "USSR aggregates (CSV has no World row for Exports)"
            ),
        ),
        "contribution": {
            "method": (
                "implied_world_trade_contribution_pct = "
                "100 * (RU_t - RU_{t-1}) / World_{t-1}; "
                "not a general-equilibrium trade model"
            ),
            "latest": {
                "period": latest.get("period"),
                "russia_share_of_world_pct": latest.get("russia_share_of_world_pct"),
                "russia_yoy_change_pct": latest.get("russia_yoy_change_pct"),
                "implied_world_trade_contribution_pct": latest.get(
                    "implied_world_trade_contribution_pct"
                ),
            },
            "series": contrib,
        },
    }


def build_sunflower_oil(oilseeds: Any) -> dict[str, Any] | None:
    """Oilseed export proxy — not gasoline; honest label."""
    try:
        ru = export_series(oilseeds, commodity="Oil, Sunflowerseed", country="Russia")
        world = export_series(oilseeds, commodity="Oil, Sunflowerseed", country="World")
    except KeyError as exc:
        log(f"sunflower oil skipped: {exc}")
        return None
    contrib = contribution_table(ru, world)
    latest = contrib[-1] if contrib else {}
    return {
        "commodity": "sunflowerseed_oil",
        "label_ko": "해바라기유",
        "label_en": "Oil, Sunflowerseed",
        "note_ko": "석유제품이 아님. 흑해 유지종자 수출 보조 시계열.",
        "russia_exports": series_payload(
            ru,
            source_name="USDA FAS PSD oilseeds CSV",
            source_url="https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
        ),
        "world_exports": series_payload(
            world,
            source_name="USDA FAS PSD oilseeds CSV (country sum)",
            source_url="https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
            construction=(
                "Sum of country Exports excluding EU/USSR aggregates"
            ),
        ),
        "contribution": {
            "method": (
                "implied_world_trade_contribution_pct = "
                "100 * (RU_t - RU_{t-1}) / World_{t-1}"
            ),
            "latest": {
                "period": latest.get("period"),
                "russia_share_of_world_pct": latest.get("russia_share_of_world_pct"),
                "russia_yoy_change_pct": latest.get("russia_yoy_change_pct"),
                "implied_world_trade_contribution_pct": latest.get(
                    "implied_world_trade_contribution_pct"
                ),
            },
            "series": contrib,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-portwatch", action="store_true")
    parser.add_argument("--fetch-comtrade-monthly", action="store_true")
    parser.add_argument(
        "--include-oilseeds",
        action="store_true",
        help="also download PSD oilseeds (sunflower oil); slower optional zip",
    )
    parser.add_argument("--force-psd", action="store_true", help="re-download PSD zips")
    parser.add_argument(
        "--output",
        type=Path,
        default=PUBLIC,
        help="output JSON path",
    )
    args = parser.parse_args()

    grains = load_psd_table("grains", force=args.force_psd)
    wheat = build_wheat(grains)

    commodities: dict[str, Any] = {"wheat": wheat}
    if args.include_oilseeds:
        try:
            oilseeds = load_psd_table("oilseeds", force=args.force_psd)
            sun = build_sunflower_oil(oilseeds)
            if sun:
                commodities["sunflowerseed_oil"] = sun
        except Exception as exc:  # noqa: BLE001
            log(f"oilseeds optional skip: {exc}")
    else:
        log("oilseeds skipped (pass --include-oilseeds to add sunflower oil)")

    monthly: dict[str, Any] = {"available": False, "series_by_commodity": {}}
    if args.fetch_comtrade_monthly:
        periods = default_recent_periods(24)
        for name, hs in HS_SERIES.items():
            monthly["series_by_commodity"][name] = fetch_monthly_exports(hs, periods=periods)
        monthly["available"] = any(
            v.get("available") for v in monthly["series_by_commodity"].values()
        )
        monthly["periods_requested"] = periods
    else:
        monthly["reason"] = "pass --fetch-comtrade-monthly with COMTRADE_SUBSCRIPTION_KEY"

    payload = {
        "schema_version": "russia-export-pulse-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose_ko": (
            "러시아 수출량(정본)과 세계 비중 기여분, 보스포루스 출구 프록시를 한 스냅샷에 둔다. "
            "피격·다크십은 무료 공식 데이터로 확인 불가라 제외."
        ),
        "commodities": commodities,
        "monthly_comtrade": monthly,
        "chokepoint_proxy": {
            "bosporus": bosporus_proxy(args.fetch_portwatch),
        },
        "policy_events": load_policy(),
        "out_of_scope": [
            "dark_fleet_ais",
            "vessel_strike_counts",
            "media_claims_world_wheat_minus_15pct",
            "causal_attribution_strike_to_tonnage",
        ],
        "ui_handoff_ko": (
            "Claude: shipping.js/무역 패널에서 이 JSON을 읽어 "
            "(1) 밀 수출 시계열 (2) 세계 비중·기여분 (3) 보스포루스 벌크 프록시를 나란히 표시. "
            "PortWatch만으로 러시아 수출을 단정하는 카피 금지."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log(f"wrote {args.output}")
    latest = wheat["contribution"]["latest"]
    log(
        f"wheat latest {latest.get('period')}: "
        f"share={latest.get('russia_share_of_world_pct')}% "
        f"yoy={latest.get('russia_yoy_change_pct')}% "
        f"world_contrib={latest.get('implied_world_trade_contribution_pct')}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

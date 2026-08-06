"""
Write LatAm banana dashboard payloads (DATA_LAYOUT contract).

Until models clear the skill gate, each country file is published with
``forecast_available: false`` — never invent ``point``.

Usage: python3 -m latam_banana.run_forecast
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data"))

COUNTRY_META = {
    "ecuador": {
        "file": "ecuador_yield_forecast.json",
        "country": "Ecuador",
        "title_ko": "에콰도르 바나나",
    },
    "guatemala": {
        "file": "guatemala_yield_forecast.json",
        "country": "Guatemala",
        "title_ko": "과테말라 바나나",
    },
    "costa_rica": {
        "file": "costa_rica_yield_forecast.json",
        "country": "Costa Rica",
        "title_ko": "코스타리카 바나나",
    },
    "honduras": {
        "file": "honduras_yield_forecast.json",
        "country": "Honduras",
        "title_ko": "온두라스 바나나",
    },
}

REASON = (
    "캐번디시 바나나는 블랙 시가토카·허리케인·TR4가 기상 회귀보다 지배적입니다. "
    "문헌의 고성능 모델은 농장 주간 YLWS/YLS 또는 UAV NDVI를 쓰며, "
    "공개 주(province) 라벨이 확보되고 skill gate를 통과하기 전에는 "
    "예측 point를 발행하지 않습니다."
)


def log(message: str) -> None:
    print(f"[run] {message}", flush=True)


def build_country(country: str, configs: list) -> dict:
    meta = COUNTRY_META[country]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": datetime.now(timezone.utc).year,
        "country": meta["country"],
        "title_ko": meta["title_ko"],
        "forecast_available": False,
        "panel_mode": "reference",
        "reason_ko": REASON,
        "methodology_note": (
            "Phase-1: NASA POWER Sigatoka/wind proxies + province ridge "
            "(Australia protocol). Phase-2: farm YLWS/YLS RF (Jiménez 2022) "
            "/ NDVI (Garcés-Fiallos 2025). TR4 = area quarantine layer."
        ),
        "sources": [
            {"name": "Jiménez et al. 2022 Sustainability (Panama RF)",
             "url": "https://www.mdpi.com/2071-1050/14/21/14123",
             "supports": "YLWS/YLS lead features"},
            {"name": "Garcés-Fiallos et al. 2025 Sustainability (Ecuador RF)",
             "url": "https://www.mdpi.com/2071-1050/17/22/10098",
             "supports": "NDVI + soil + phenology"},
            {"name": "FAO Banana Statistical Compendium",
             "url": "https://www.fao.org/markets-and-trade/commodities/bananas",
             "supports": "national trade cross-check only"},
        ],
        "regions": {},
    }

    any_live = False
    for cfg in configs:
        result = predict_one(cfg)
        if "error" in result:
            payload["regions"][cfg.key] = {
                "label": cfg.label,
                "label_ko": cfg.label_ko,
                "note": cfg.caveat,
                "forecast_available": False,
                "reason_ko": result.get("reason_ko", result["error"]),
                "crops": {
                    "banana": {
                        "label_ko": "바나나",
                        "unit": "kg/ha",
                    }
                },
            }
        else:
            any_live = True
            payload["regions"][cfg.key] = {
                "label": cfg.label,
                "label_ko": cfg.label_ko,
                "crops": {"banana": result},
            }

    if not any_live:
        payload["forecast_available"] = False
    return payload


def main() -> int:
    os.makedirs(PUBLIC, exist_ok=True)
    by_country: dict[str, list] = {}
    for cfg in ALL:
        by_country.setdefault(cfg.country, []).append(cfg)

    for country, configs in by_country.items():
        payload = build_country(country, configs)
        out = os.path.join(PUBLIC, COUNTRY_META[country]["file"])
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        log(f"wrote {out} (forecast_available="
            f"{payload['forecast_available']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

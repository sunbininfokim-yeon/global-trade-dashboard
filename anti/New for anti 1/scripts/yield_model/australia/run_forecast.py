"""Write the Australia dashboard forecast JSON."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .predict import predict_one
from .regions import ALL


HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data",
                                  "australia_yield_forecast.json"))


def main() -> int:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": "Australia",
        "method": (
            "log technology trend plus causal 20-season weather anomalies; "
            "forward-chaining validation"),
        "regions": {},
        "skipped": {},
    }
    for cfg in ALL:
        result = predict_one(cfg)
        if "error" in result:
            payload["skipped"][cfg.key] = result["error"]
            continue
        if result["operational_choice"] != "ridge_weather":
            pct = result["weather_effect_pct"]
            direction = ("우호" if pct >= 1.5 else
                         "불리" if pct <= -1.5 else "중립")
            payload["regions"][cfg.key] = {
                "label": cfg.label,
                "label_ko": cfg.label_ko,
                "crop": cfg.crop,
                "season": result["season"],
                "unit": result["unit"],
                "forecast_available": False,
                "panel_mode": "reference",
                "reason_ko": (
                    "전체·최근 시간순 검증에서 추세 대비 +10% 기준을 모두 "
                    "통과하지 못해 단수 전망을 발행하지 않습니다."),
                "weather_effect_pct": pct,
                "condition_signal_ko": direction,
                "last_actual": result["last_actual"],
                "season_progress": result["season_progress"],
                "features": result["features"],
                "skill": result["skill"],
                "provenance": result["provenance"],
            }
            print(f"[reference] {cfg.key}: {direction} ({pct:+.1f}%)", flush=True)
            continue
        payload["regions"][cfg.key] = {
            "label": cfg.label,
            "label_ko": cfg.label_ko,
            "crop": cfg.crop,
            **result,
        }
        print(f"[forecast] {cfg.key}: {result['point']:.0f} kg/ha", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(f"[forecast] wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Apply trained LatAm banana models (Phase-1 stub).

Until province labels unlock train, predict_one returns an error dict.
Live POWER + Open-Meteo extension can land after the first operational model.
"""

from __future__ import annotations

import json
import os

from .regions import BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")


def load_model(key: str) -> dict | None:
    path = os.path.join(MODELS, f"{key}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def predict_one(cfg, year: int | None = None) -> dict:
    """
    Return a forecast dict or ``{"error": ...}``.

    Full in-season weather path is deferred until an operational artifact
    exists (same honesty gate as train).
    """
    artifact = load_model(cfg.key)
    if artifact is None:
        return {
            "error": "no trained model",
            "reason_ko": (
                "주 단위 라벨·학습 미완료 — 주(province) 수량성 CSV와 "
                "skill gate 통과 모델이 필요합니다."
            ),
        }
    if artifact.get("operational_choice") != "ridge_weather":
        return {
            "error": "trend_only — not publishing weather point",
            "reason_ko": (
                "기상 잔차 skill이 운영 기준(10%) 미달이라 추세만 가능합니다. "
                "임의 point를 발행하지 않습니다."
            ),
            "artifact_key": cfg.key,
            "low_confidence": True,
        }
    return {
        "error": "in-season predict not wired yet",
        "reason_ko": (
            "모델 아티팩트는 있으나 시즌 중 POWER/예보 경로가 아직 "
            "연결되지 않았습니다."
        ),
        "artifact_key": cfg.key,
        "year": year,
    }


def main() -> int:
    for key, cfg in BY_KEY.items():
        result = predict_one(cfg)
        print(f"[predict] {key}: {result.get('error', 'ok')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

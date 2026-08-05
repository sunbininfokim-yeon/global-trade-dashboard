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


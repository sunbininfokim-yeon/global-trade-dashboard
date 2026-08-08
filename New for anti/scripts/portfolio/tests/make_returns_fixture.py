#!/usr/bin/env python3
"""Generate a deterministic returns fixture for portfolio tests."""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "returns_sample.json"
TICKERS = ["005930.KS", "010140.KS", "011200.KS", "000660.KS"]


def main() -> None:
    rng = random.Random(7)
    n = 252
    market = [rng.gauss(0.0005, 0.009) for _ in range(n)]
    betas = {
        "005930.KS": 1.0,
        "000660.KS": 1.3,
        "010140.KS": 0.8,
        "011200.KS": 1.1,
    }
    out = {}
    for t in TICKERS:
        out[t] = [betas[t] * m + rng.gauss(0.0001, 0.011) for m in market]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out) + "\n", encoding="utf-8")
    print("wrote", OUT, "n=", n)


if __name__ == "__main__":
    main()

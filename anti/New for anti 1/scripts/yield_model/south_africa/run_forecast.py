"""Run collection, validation/training, and current-season prediction."""

from __future__ import annotations

import argparse
from datetime import date

from .collect import build
from .challenger import evaluate as evaluate_challenger
from .predict import predict
from .train import train


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    build(refresh=args.refresh, end_year=args.year)
    train()
    evaluate_challenger()
    predict(args.year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

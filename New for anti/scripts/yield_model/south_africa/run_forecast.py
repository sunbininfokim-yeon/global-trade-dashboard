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
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    today = date.today()
    # From October the belt is planting the next harvest year; publish that
    # season's pre-season outlook instead of the harvest finished in May.
    season = args.year or (today.year + 1 if today.month >= 10 else today.year)
    build(refresh=args.refresh, end_year=min(season, today.year))
    train()
    evaluate_challenger()
    predict(season)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

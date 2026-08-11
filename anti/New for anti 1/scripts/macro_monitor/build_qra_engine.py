#!/usr/bin/env python3
"""Build QRA causal engine JSON from Treasury archives (2020+ by default).

Examples:
  python3 build_qra_engine.py --download --from-year 2020
  python3 build_qra_engine.py --no-download   # parse cache only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.qra.build import build_qra_engine, default_cache_dir, default_out_path  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Treasury QRA fetch/parse/causal engine")
    p.add_argument("--from-year", type=int, default=2020)
    p.add_argument("--to-year", type=int, default=2099)
    p.add_argument("--download", action="store_true", default=True)
    p.add_argument("--no-download", action="store_true")
    p.add_argument("--force-download", action="store_true")
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--no-fiscal", action="store_true", help="Skip Fiscal Data TGA/customs overlay")
    args = p.parse_args()

    download = not args.no_download
    build_qra_engine(
        from_year=args.from_year,
        to_year=args.to_year,
        cache_dir=args.cache_dir or default_cache_dir(),
        download=download,
        force_download=args.force_download,
        out_path=args.out or default_out_path(),
        fiscal=not args.no_fiscal,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

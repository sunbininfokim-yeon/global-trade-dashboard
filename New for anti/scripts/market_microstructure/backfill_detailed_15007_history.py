#!/usr/bin/env python3
"""Backfill KRX 15007 Call/Put foreign-flow history into the derivatives board.

Reads dated folders under a raw KRX 15007 export root and merges only complete
call/put BUY/SELL CSV sets into ``kr.investor_nets.detailed_15007``.  Incomplete
folders are skipped; missing or blank amounts are never zero-filled.  Futures
exports and unrelated board fields are left untouched.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fetch_kr_derivatives import build_detailed_15007  # noqa: E402
from validate_ui_contracts import validate_detailed_15007  # noqa: E402

DEFAULT_BOARD = ROOT / "../../public/data/derivatives_board_v1.json"
REQUIRED_FILES = (
    "options_call_buy.csv",
    "options_call_sell.csv",
    "options_put_buy.csv",
    "options_put_sell.csv",
)
_DATE_FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"date must be YYYY-MM-DD, got {value!r}"
        ) from exc


def _board_without_detailed_15007(board: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy board with ``detailed_15007`` removed for structural compare."""
    snapshot = copy.deepcopy(board)
    investor = ((snapshot.get("kr") or {}).get("investor_nets") or {})
    if isinstance(investor, dict):
        investor.pop("detailed_15007", None)
    return snapshot


def _extract_previous(board: dict[str, Any]) -> dict[str, Any] | None:
    detailed = (
        ((board.get("kr") or {}).get("investor_nets") or {}).get("detailed_15007")
    )
    return detailed if isinstance(detailed, dict) else None


def _assign_detailed_15007(board: dict[str, Any], detailed: dict[str, Any]) -> None:
    kr = board.setdefault("kr", {})
    if not isinstance(kr, dict):
        raise RuntimeError("derivatives_board.kr must be an object")
    investor = kr.setdefault("investor_nets", {})
    if not isinstance(investor, dict):
        raise RuntimeError("derivatives_board.kr.investor_nets must be an object")
    investor["detailed_15007"] = detailed


def date_folders(raw_root: Path, start: date, end: date) -> list[Path]:
    """Return chronologically sorted date folders inside [start, end]."""
    if end < start:
        raise ValueError("end must be on or after start")
    if not raw_root.is_dir():
        raise FileNotFoundError(f"raw root is not a directory: {raw_root}")

    folders: list[Path] = []
    for child in raw_root.iterdir():
        if not child.is_dir() or not _DATE_FOLDER_RE.match(child.name):
            continue
        day = date.fromisoformat(child.name)
        if start <= day <= end:
            folders.append(child)
    return sorted(folders, key=lambda path: path.name)


def missing_required_files(date_dir: Path) -> list[str]:
    return [name for name in REQUIRED_FILES if not (date_dir / name).is_file()]


def merge_date_folder(
    date_dir: Path,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge one complete date folder via the shared 15007 parser."""
    merged = build_detailed_15007(
        option_call_buy=date_dir / "options_call_buy.csv",
        option_call_sell=date_dir / "options_call_sell.csv",
        option_put_buy=date_dir / "options_put_buy.csv",
        option_put_sell=date_dir / "options_put_sell.csv",
        previous=previous,
    )
    validate_detailed_15007(merged)
    return merged


def backfill(
    raw_root: Path,
    *,
    start: date,
    end: date,
    board_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge complete date folders into the board's detailed_15007 leaf."""
    board = json.loads(board_path.read_text(encoding="utf-8"))
    if not isinstance(board, dict):
        raise RuntimeError(f"board root must be object: {board_path}")

    baseline = _board_without_detailed_15007(board)
    previous = _extract_previous(board)
    merged = 0
    skipped = 0

    for date_dir in date_folders(raw_root, start, end):
        missing = missing_required_files(date_dir)
        if missing:
            skipped += 1
            print(
                f"skip {date_dir.name}: incomplete folder, missing "
                + ", ".join(missing)
            )
            continue
        try:
            previous = merge_date_folder(date_dir, previous)
        except (OSError, ValueError, RuntimeError) as exc:
            skipped += 1
            print(f"skip {date_dir.name}: {exc}")
            continue
        merged += 1
        print(f"merged {date_dir.name}")

    if previous is None:
        previous = build_detailed_15007()
        validate_detailed_15007(previous)

    _assign_detailed_15007(board, previous)
    validate_detailed_15007(previous)

    if _board_without_detailed_15007(board) != baseline:
        raise RuntimeError(
            "board changed outside kr.investor_nets.detailed_15007; refusing write"
        )

    if dry_run:
        print(
            f"detailed_15007 backfill dry-run complete: "
            f"merged={merged} skipped={skipped} (no write)"
        )
        return board

    board_path.write_text(
        json.dumps(board, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"detailed_15007 backfill complete: "
        f"merged={merged} skipped={skipped} wrote={board_path}"
    )
    return board


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "raw_root",
        type=Path,
        help="root of dated KRX 15007 folders (…/krx_15007/YYYY-MM-DD/…)",
    )
    parser.add_argument("--start", type=_parse_day, required=True)
    parser.add_argument("--end", type=_parse_day, required=True, help="inclusive KST date")
    parser.add_argument(
        "--board",
        type=Path,
        default=DEFAULT_BOARD,
        help="path to derivatives_board_v1.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.end < args.start:
        parser.error("end must be on or after start")

    backfill(
        args.raw_root,
        start=args.start,
        end=args.end,
        board_path=args.board,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

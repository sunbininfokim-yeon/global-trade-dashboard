#!/usr/bin/env python3
"""Focused tests for the KRX 15007 Call/Put history backfill importer."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backfill_detailed_15007_history import (  # noqa: E402
    _board_without_detailed_15007,
    backfill,
)


REQUIRED = (
    "options_call_buy.csv",
    "options_call_sell.csv",
    "options_put_buy.csv",
    "options_put_sell.csv",
)


def write_export(path: Path, rows: list[tuple[str, int, int]]) -> None:
    path.write_text(
        "[15007] 투자자별 거래실적\n"
        "일자,기관 합계,기타법인,개인,외국인 합계,전체\n"
        + "".join(f"{day},0,0,0,{foreign},{total}\n" for day, foreign, total in rows),
        encoding="utf-8",
    )


def _minimal_board(*, marker: str = "untouched") -> dict:
    return {
        "schema_version": "derivatives-board-v1",
        "kr": {
            "as_of": "2026-09-03",
            "kospi200_futures": {"quality": "observed", "marker": marker},
            "kospi200_options": {"quality": "observed"},
            "investor_nets": {
                "note_ko": "fixture",
                "quality": "partial_observed",
                "public_dashboard": {"marker": marker},
                "detailed_15007": {
                    "schema_version": "krx-15007-call-put-v2",
                    "query": {
                        "market": "KOSPI200",
                        "metric": "trading_value",
                        "side": "buy_sell_and_net",
                        "unit": "KRW",
                        "source_unit": "million_krw",
                        "conversion_to_krw": 1_000_000,
                    },
                    "products": {
                        "options_call": {
                            "as_of": None,
                            "source": None,
                            "quality": "missing",
                            "foreign": {
                                "buy_krw": None,
                                "sell_krw": None,
                                "net_krw": None,
                            },
                            "market_total": {
                                "buy_krw": None,
                                "sell_krw": None,
                                "net_krw": None,
                            },
                            "series": [],
                        },
                        "options_put": {
                            "as_of": None,
                            "source": None,
                            "quality": "missing",
                            "foreign": {
                                "buy_krw": None,
                                "sell_krw": None,
                                "net_krw": None,
                            },
                            "market_total": {
                                "buy_krw": None,
                                "sell_krw": None,
                                "net_krw": None,
                            },
                            "series": [],
                        },
                    },
                },
            },
            "errors": [],
        },
        "us_oi_snap": {"as_of": "2026-09-03", "names": []},
        "us_kr_rules": {"headline_level": "watch"},
    }


def _write_complete_day(raw_root: Path, day: str, *, call_buy: int = 69111) -> Path:
    date_dir = raw_root / day
    date_dir.mkdir(parents=True, exist_ok=True)
    slash = day.replace("-", "/")
    write_export(date_dir / "options_call_buy.csv", [(slash, call_buy, 94530)])
    write_export(date_dir / "options_call_sell.csv", [(slash, 63028, 94530)])
    write_export(date_dir / "options_put_buy.csv", [(slash, 55285, 97570)])
    write_export(date_dir / "options_put_sell.csv", [(slash, 79129, 97570)])
    return date_dir


class TestBackfillDetailed15007History(unittest.TestCase):
    def test_complete_date_produces_observed_call_and_put(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            board_path = root / "board.json"
            board_path.write_text(
                json.dumps(_minimal_board(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_complete_day(raw, "2026-08-28")

            out = backfill(
                raw,
                start=date(2026, 8, 28),
                end=date(2026, 8, 28),
                board_path=board_path,
            )
            detailed = out["kr"]["investor_nets"]["detailed_15007"]
            call = detailed["products"]["options_call"]
            put = detailed["products"]["options_put"]
            self.assertEqual(call["quality"], "observed")
            self.assertEqual(put["quality"], "observed")
            self.assertEqual(len(call["series"]), 1)
            self.assertEqual(len(put["series"]), 1)
            self.assertEqual(call["series"][0]["date"], "2026-08-28")
            self.assertEqual(put["series"][0]["foreign"]["net_krw"], -23_844_000_000)

            written = json.loads(board_path.read_text(encoding="utf-8"))
            self.assertEqual(
                written["kr"]["investor_nets"]["detailed_15007"]["products"]
                ["options_call"]["series"][0]["date"],
                "2026-08-28",
            )

    def test_incomplete_folder_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            board_path = root / "board.json"
            board = _minimal_board()
            board_path.write_text(
                json.dumps(board, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            incomplete = raw / "2026-08-28"
            incomplete.mkdir(parents=True)
            for name in REQUIRED[:3]:
                (incomplete / name).write_text("placeholder\n", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                out = backfill(
                    raw,
                    start=date(2026, 8, 28),
                    end=date(2026, 8, 28),
                    board_path=board_path,
                )
            log = buf.getvalue()
            self.assertIn("skip 2026-08-28", log)
            self.assertIn("options_put_sell.csv", log)
            self.assertEqual(
                out["kr"]["investor_nets"]["detailed_15007"]["products"]
                ["options_call"]["series"],
                [],
            )

    def test_dry_run_leaves_board_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            board_path = root / "board.json"
            board_path.write_text(
                json.dumps(_minimal_board(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_complete_day(raw, "2026-08-28")
            before = board_path.read_bytes()

            backfill(
                raw,
                start=date(2026, 8, 28),
                end=date(2026, 8, 28),
                board_path=board_path,
                dry_run=True,
            )
            self.assertEqual(board_path.read_bytes(), before)

    def test_rerun_same_date_replaces_not_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            board_path = root / "board.json"
            board_path.write_text(
                json.dumps(_minimal_board(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _write_complete_day(raw, "2026-08-28", call_buy=69111)
            backfill(
                raw,
                start=date(2026, 8, 28),
                end=date(2026, 8, 28),
                board_path=board_path,
            )
            _write_complete_day(raw, "2026-08-28", call_buy=70000)
            out = backfill(
                raw,
                start=date(2026, 8, 28),
                end=date(2026, 8, 28),
                board_path=board_path,
            )
            series = out["kr"]["investor_nets"]["detailed_15007"]["products"][
                "options_call"
            ]["series"]
            self.assertEqual(len(series), 1)
            self.assertEqual(series[0]["date"], "2026-08-28")
            self.assertEqual(series[0]["foreign"]["buy_krw"], 70_000_000_000)

    def test_non_detailed_fields_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw"
            board_path = root / "board.json"
            board = _minimal_board(marker="keep-me")
            board_path.write_text(
                json.dumps(board, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            baseline = _board_without_detailed_15007(board)
            _write_complete_day(raw, "2026-08-28")

            out = backfill(
                raw,
                start=date(2026, 8, 28),
                end=date(2026, 8, 28),
                board_path=board_path,
            )
            self.assertEqual(_board_without_detailed_15007(out), baseline)
            self.assertEqual(out["kr"]["kospi200_futures"]["marker"], "keep-me")
            self.assertEqual(
                out["kr"]["investor_nets"]["public_dashboard"]["marker"],
                "keep-me",
            )


if __name__ == "__main__":
    unittest.main()

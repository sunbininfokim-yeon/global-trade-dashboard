#!/usr/bin/env python3
"""Build a per-contract-month metadata table for KOSPI200 front-month futures and options.

Reads the private krx-month-paste hive (kospi200_futures_oi from 15003,
kospi200_option_oi from 15018). Neither workbook has a 만기일 column, so
expiry_date stays null. The table records only what the workbooks show:
the first and last regular-session date each month was the front month, the
first date of the next month, and whether a missing trading day sits between.
It never derives a second-Thursday date.

  python build_kospi200_contract_meta.py --source /path/to/krx-month-paste \
      --out ../../../data/manifests/kospi200_contract_meta_v1.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATASETS = {
    "kospi200_option_oi": {"screen": "15018", "menu_id": "MDC0201050104", "product_ko": "코스피200 옵션",
                           "contract_type": "standard_monthly"},
    "kospi200_futures_oi": {"screen": "15003", "menu_id": "MDC0201050103", "product_ko": "코스피200 선물",
                            "contract_type": "standard_quarterly"},
}
NON_STANDARD = re.compile(r"위클리|미니|W\d|MINI|WEEK", re.I)
EXPIRY_REASON_KO = (
    "15003·15018 원본 엑셀에는 만기일 열이 없다(열: 일자·종목코드·종목명·시세·내재변동성·거래량·거래대금·미결제약정). "
    "종목명에는 만기월(YYYYMM)만 있다. 둘째 목요일 계산은 휴장으로 앞당겨진 만기(예: 2019-09)를 틀리게 만들므로 쓰지 않는다."
)


def read_rows(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def build_dataset(source: Path, dataset: str, calendar: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = DATASETS[dataset]
    months: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"dates": set(), "codes": set(), "names": set(), "rights": set(), "nonstandard": set(),
                 "by_date": defaultdict(lambda: {"rows": 0, "oi_null": 0, "iv_null": 0, "shas": set()})}
    )
    parts = sorted((source / "data/normalized" / dataset).glob("year=*/month=*/part.jsonl.gz"))
    part_shas = {}
    for part in parts:
        part_shas[str(part.relative_to(source))] = hashlib.sha256(part.read_bytes()).hexdigest()
        for row in read_rows(part):
            if row.get("session") != "regular":
                continue
            month = str(row.get("expiry_or_contract_month") or "")
            if not month:
                continue
            m = months[month]
            day = row["date"]
            m["dates"].add(day)
            m["codes"].add(row.get("contract_code"))
            name = str(row.get("contract_name") or "")
            if len(m["names"]) < 2:
                m["names"].add(name)
            if NON_STANDARD.search(name):
                m["nonstandard"].add(name)
            if row.get("option_type"):
                m["rights"].add(row["option_type"])
            slot = m["by_date"][day]
            slot["rows"] += 1
            slot["oi_null"] += row.get("open_interest_contracts") is None
            slot["iv_null"] += dataset == "kospi200_option_oi" and row.get("implied_volatility") is None
            slot["shas"].update((row.get("raw_shas") or {}).values())

    manifest = json.loads((source / "data/manifests" / f"{dataset}.json").read_text(encoding="utf-8"))
    observed = set().union(*(m["dates"] for m in months.values()))
    missing = [d for d in calendar if calendar[0] <= d <= max(observed) and d not in observed]
    order = sorted(months)
    out = []
    for i, month in enumerate(order):
        m = months[month]
        first, last = min(m["dates"]), max(m["dates"])
        nxt = order[i + 1] if i + 1 < len(order) else None
        nxt_first = min(months[nxt]["dates"]) if nxt else None
        gap = [d for d in missing if last < d < nxt_first] if nxt_first else None
        if nxt_first is None:
            roll = "open_latest_month"
        elif gap:
            roll = "missing_day_between"
        else:
            roll = "closed"
        last_slot = m["by_date"][last]
        codes = sorted(c for c in m["codes"] if c)
        out.append(
            {
                "dataset": dataset,
                "source_screen": info["screen"],
                "menu_id": info["menu_id"],
                "product_ko": info["product_ko"],
                "contract_type": "nonstandard_seen" if m["nonstandard"] else info["contract_type"],
                "contract_type_basis": "15003/15018 최근월물 조회 결과이고 종목명에 위클리·미니 표기가 없다",
                "expiry_or_contract_month": month,
                "contract_code": codes[0] if len(codes) == 1 else None,
                "contract_code_count": len(codes),
                "contract_code_sample": codes[:2],
                "contract_name_sample": sorted(m["names"]),
                "option_types": sorted(m["rights"]),
                "first_front_regular_date": first,
                "last_front_regular_date": last,
                "regular_dates_observed": len(m["dates"]),
                "next_contract_month": nxt,
                "next_first_front_regular_date": nxt_first,
                "missing_trading_days_before_roll": gap,
                "roll_status": roll,
                "last_date_rows": last_slot["rows"],
                "last_date_oi_null_share": round(last_slot["oi_null"] / last_slot["rows"], 4),
                "last_date_iv_null_share": (
                    round(last_slot["iv_null"] / last_slot["rows"], 4) if dataset == "kospi200_option_oi" else None
                ),
                "last_date_raw_sha256": sorted(last_slot["shas"]),
                "expiry_date": None,
                "expiry_date_status": "not_in_source",
            }
        )
    meta = {"parts": len(parts), "part_sha256": part_shas, "regular_missing_vs_calendar": missing,
            "manifest_generated_at": manifest.get("generated_at")}
    return out, meta


def build(source: Path, calendar_path: Path) -> dict[str, Any]:
    calendar = sorted(r["date"] for r in json.loads(calendar_path.read_text(encoding="utf-8"))["rows"])
    contracts, sources = [], {}
    for dataset in DATASETS:
        rows, meta = build_dataset(source, dataset, calendar)
        contracts.extend(rows)
        sources[dataset] = meta
    return {
        "schema": "kospi200-contract-meta-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_published_at": "unknown",
        "krx_requests": 0,
        "session_basis": "regular",
        "trading_calendar": {"path": str(calendar_path.name), "first": calendar[0], "last": calendar[-1],
                             "basis_ko": "공개 KOSPI200 지수 일봉의 거래일. 결측 판단은 이 달력과 hive 정규장 날짜의 차이다."},
        "expiry_date_reason_ko": EXPIRY_REASON_KO,
        "last_front_regular_date_ko": (
            "그 월물이 정규장 최근월물 조회에 마지막으로 나온 날이다. roll_status가 closed이면 다음 관측일에 바로 "
            "다음 월물로 바뀌었고 그 사이 결측 거래일이 없다. 그래도 거래소가 공시한 만기일은 아니므로 expiry_date에 넣지 않는다."
        ),
        "dedupe_note_ko": (
            "kospi200_option_oi의 중복 제거 키는 만기를 구분하지 않으므로 이 표는 별도로 두고 기존 hive에 합치지 않는다."
        ),
        "sources": sources,
        "contracts": contracts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--calendar", type=Path,
                        default=Path(__file__).resolve().parents[2] / "public/data/kospi200_index_daily_v1.json")
    args = parser.parse_args()
    doc = build(args.source, args.calendar)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    by = defaultdict(lambda: defaultdict(int))
    for c in doc["contracts"]:
        by[c["dataset"]][c["roll_status"]] += 1
    print(json.dumps({k: dict(v) for k, v in by.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

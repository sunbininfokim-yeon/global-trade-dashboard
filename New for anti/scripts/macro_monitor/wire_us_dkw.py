"""Attach Fed Board DKW 10-year yield changes to the U.S. macro pack."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import date, datetime
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo


URL = "https://www.federalreserve.gov/econres/notes/feds-notes/DKW_updates.csv"
REFERENCE_URL = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
PACK = Path(__file__).resolve().parents[2] / "public/data/macro_monitor_v1.json"
FACTORS = {
    "exp.real.short.rate.10": "기대 실질단기금리",
    "exp.inflation.10": "기대인플레이션",
    "real.term.prem.10": "실질 기간 프리미엄",
    "inflation.risk.prem.10": "인플레이션 위험 프리미엄",
}
OBSERVED = "nominal.yield.raw.10"
FITTED = "nominal.yield.fitted.10"
PANEL_ID = "dkw_yield_change"


def csv_rows(text: str, date_column: str, required_columns: tuple[str, ...]) -> csv.DictReader:
    lines = iter(text.splitlines())
    for line in lines:
        header = next(csv.reader([line]), [])
        if header and header[0] == date_column:
            if set(required_columns) - set(header):
                raise ValueError(f"Missing required columns in {date_column} CSV")
            return csv.DictReader(lines, fieldnames=header)
    raise ValueError(f"{date_column} CSV header missing")


def confirmed_month_ends(text: str, today: date) -> dict[date, date]:
    """Use the last published GSW yield date of each fully covered month."""
    by_month: dict[date, date] = {}
    for row in csv_rows(text, "Date", ("SVENY10",)):
        value = (row["SVENY10"] or "").strip()
        if not row["Date"] or value in {"", "NA", "."}:
            continue
        day = date.fromisoformat(row["Date"])
        if day > today or not isfinite(float(value)):
            continue
        month = day.replace(day=1)
        by_month[month] = max(day, by_month.get(month, day))
    if not by_month:
        raise ValueError("No valid dates in Fed nominal yield curve CSV")
    # An observation in a later month confirms the prior month in the reference
    # file has finished publishing, including short months and market holidays.
    del by_month[max(by_month)]
    return by_month


def month_end_rows(text: str, reference_text: str, today: date) -> list[tuple[date, dict[str, float]]]:
    columns = (*FACTORS, OBSERVED, FITTED)
    reference_days = set(confirmed_month_ends(reference_text, today).values())
    matched = {}
    for row in csv_rows(text, "date", columns):
        if not row["date"]:
            continue
        day = date.fromisoformat(row["date"])
        if day in reference_days:
            matched[day] = row
    observations = []
    for day in sorted(matched)[-25:]:
        row = matched[day]
        values = {key: float(row[key]) for key in columns}
        if not all(isfinite(value) for value in values.values()):
            raise ValueError(f"Missing or nonfinite DKW values for {day}")
        if abs(sum(values[key] for key in FACTORS) - values[FITTED]) > 0.001:
            raise ValueError(f"DKW factor sum differs from fitted yield for {day}")
        observations.append((day, values))
    if len(observations) < 2:
        raise ValueError("DKW requires at least two confirmed month-end observations")
    return observations


def build_panel(text: str, reference_text: str, today: date) -> dict:
    observations = month_end_rows(text, reference_text, today)
    dates, changes = [], []
    for (before, previous), (day, values) in zip(observations, observations[1:]):
        if (day.year - before.year) * 12 + day.month - before.month != 1:
            raise ValueError(f"Nonconsecutive DKW months at {day}")
        dates.append(day.strftime("%Y-%m"))
        changes.append({key: (values[key] - previous[key]) * 100 for key in values})
    last_change = changes[-1]
    last_date, last_values = observations[-1]
    drivers = [{"label": label, "change_bp": round(last_change[key], 2)} for key, label in FACTORS.items()]
    top_two = sorted(drivers, key=lambda item: abs(item["change_bp"]), reverse=True)[:2]

    def describe(bp: float) -> str:
        if not round(bp, 2):
            return "보합"
        return f"{abs(bp):.2f}bp {'상승' if bp > 0 else '하락'}"

    summary = (
        f"{last_date:%Y년 %m월} 말 미국 10년 무이표 금리는 {last_values[OBSERVED]:.2f}%였습니다. "
        f"전월 말 대비 {describe(last_change[OBSERVED])}입니다."
    )
    drivers_text = ", ".join(
        f"{item['label']}({describe(item['change_bp'])})" for item in top_two if item["change_bp"]
    )
    if drivers_text:
        summary += f" 모형에서 가장 크게 움직인 요인은 {drivers_text}입니다."
    return {
        "id": PANEL_ID,
        "label": "금리 변동 요인",
        "type": "stack",
        "unit": "bp",
        "compare_ko": "직전 월말",
        "dates": dates,
        "series": [{"label": label, "values": [round(row[key], 2) for row in changes]}
                   for key, label in FACTORS.items()],
        "line": {"label": "10년 무이표 금리 변동", "values": [round(row[OBSERVED], 2) for row in changes]},
        "asof": last_date.isoformat(),
        "source_url": URL,
        "source_name": "미 연준 이사회 DKW 연구자료",
        "latest": {
            "summary_ko": summary,
            "previous_date": observations[-2][0].isoformat(),
            "observed_pct": round(last_values[OBSERVED], 4),
            "observed_change_bp": round(last_change[OBSERVED], 2),
            "fitted_change_bp": round(last_change[FITTED], 2),
            "residual_change_bp": round(last_change[OBSERVED] - last_change[FITTED], 2),
            "drivers": drivers,
        },
        "note_ko": (
            f"{summary} 막대 네 항목의 합은 모형 금리 변동폭이며 흰 선은 "
            "같은 연구자료의 10년 무이표 금리 변동폭입니다. "
            "월말 기준 · 출처 미 연준 이사회 DKW 연구자료."
        ),
    }


def load_csv(path: Path | None, url: str) -> str:
    if path:
        return path.read_text(encoding="utf-8-sig")
    response = subprocess.run(
        ["curl", "-fsSL", "--retry", "2", "--max-time", "30", url],
        check=True, stdout=subprocess.PIPE,
    )
    return response.stdout.decode("utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="Use a saved Fed CSV for reproducibility")
    parser.add_argument("--reference-csv", type=Path, help="Use a saved Fed nominal yield curve CSV")
    parser.add_argument("--pack", type=Path, default=PACK)
    args = parser.parse_args()
    panel = build_panel(
        load_csv(args.csv, URL), load_csv(args.reference_csv, REFERENCE_URL),
        datetime.now(ZoneInfo("America/New_York")).date(),
    )
    existing = args.pack.read_text(encoding="utf-8")
    pack = json.loads(existing)
    usa = next(country for country in pack["countries"] if country["iso3"] == "USA")
    card = next(indicator for indicator in usa["indicators"] if indicator["id"] == "bond_10y")
    panels = card.get("panels", [])
    prior = next((item for item in panels if item["id"] == PANEL_ID), None)
    if prior and panel["asof"] < prior["asof"]:
        raise ValueError("Federal Reserve CSV predates the published DKW panel")
    if panel != prior:
        card["panels"] = [item for item in panels if item["id"] != PANEL_ID] + [panel]
        updated = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.pack.parent, delete=False) as temp:
            temp.write(updated)
        Path(temp.name).replace(args.pack)
    print(panel["latest"]["summary_ko"])


if __name__ == "__main__":
    main()

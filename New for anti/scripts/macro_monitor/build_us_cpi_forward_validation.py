#!/usr/bin/env python3
"""Score held-out US CPI path tests without changing public dashboard data."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

from macro_monitor.cpi.external_backtest import (
    EIA_FRED_FALLBACKS, ExternalBacktestError, fetch_fred_monthly_series,
)
from macro_monitor.cpi.forward_validation import candidate_specs, evaluate, monthly_changes, scan_lags, shift

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
PUBLIC = ROOT.parent.parent / "public" / "data"
CUTOFF = "2026-07"
JET_EIA_URL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=EER_EPJK_PF4_RGC_DPG"


class MonthlyPriceTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cell = None
        self.text = ""
        self.row = []
        self.points = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        if tag == "td":
            self.cell = dict(attrs).get("class", "").upper()
            self.text = ""

    def handle_data(self, data):
        if self.cell in {"B3", "B4"}:
            self.text += data

    def handle_endtag(self, tag):
        if tag == "td":
            if self.cell in {"B3", "B4"}:
                self.row.append(self.text.strip())
            self.cell = None
        if tag == "tr" and len(self.row) == 13 and self.row[0].isdigit() and len(self.row[0]) == 4:
            for month, value in enumerate(self.row[1:], 1):
                try:
                    self.points.append((f"{self.row[0]}-{month:02d}", float(value)))
                except ValueError:
                    continue


def fetch_jet_eia(*, opener=urlopen):
    with opener(JET_EIA_URL, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
    table = MonthlyPriceTable()
    table.feed(html)
    if not table.points:
        raise ValueError("monthly EIA table not recognized")
    return table.points


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run(history: dict, vehicle: dict, external: dict, structure: dict, *, cutoff: str,
        through: str | None, vehicle_only: bool, fetch=fetch_fred_monthly_series, fetch_jet=fetch_jet_eia) -> dict:
    local = {row["series_id"]: row["observations"] for row in history["series"]}
    start = external["sample"]["start"]
    headline = monthly_changes((r["date"], r["index"]) for r in local["CUSR0000SA0"])
    latest = max(headline)
    through = through or latest
    if not shift(cutoff, 0) < shift(through, 0) <= latest:
        raise ValueError(f"require cutoff < through <= latest observed headline CPI ({latest})")

    specs = candidate_specs(vehicle, external, structure)
    if vehicle_only:
        specs = [s for s in specs if not s["calendar_effects"]]
    definitions = {**vehicle["source"]["series"], **external["sources"]["bls"]["series"]}
    ids = {
        **definitions,
        **external["sources"]["fred"]["series"],
        **{name: EIA_FRED_FALLBACKS[series_id] for name, series_id in external["sources"]["eia"]["series"].items()},
    }
    needed = sorted({name for spec in specs for name, _ in spec["terms"] + spec["controls"]} |
                    {spec["target"] for spec in specs})
    series: dict[str, dict[str, float]] = {}
    sources = {}

    def get_source(name: str):
        series_id = ids[name]
        if name in definitions and series_id in local:
            points = [(row["date"], row["index"]) for row in local[series_id]
                      if row["data_status"] == "observed"]
            return points, {"series_id": series_id, "via": "BLS API history", "status": "available"}
        metadata = {"series_id": series_id, "via": "FRED public monthly CSV"}
        if name == "jet_fuel_us_gulf_coast_spot":
            try:
                points = fetch_jet()
                if len({month for month, _ in points if start <= month <= through}) >= 72:
                    return points, {"series_id": "EER_EPJK_PF4_RGC_DPG", "status": "available",
                                    "via": "EIA public monthly spot price table", "url": JET_EIA_URL}
                metadata["fallback_reason"] = "short_eia_history"
            except (OSError, ValueError):
                metadata["fallback_reason"] = "eia_table_unavailable"
        try:
            points = [(point.month, point.value) for point in fetch(series_id, api_key="", start=start)]
        except ExternalBacktestError:
            return [], {**metadata, "status": "unavailable", "reason": "source_request_failed"}
        return points, {**metadata, "status": "available"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, (points, metadata) in zip(needed, pool.map(get_source, needed)):
            changes = monthly_changes((month, value) for month, value in points if start <= month <= through)
            if not changes:
                metadata = {**metadata, "status": "unavailable",
                            "reason": metadata.get("reason", "no_consecutive_months")}
            series[name], sources[name] = changes, metadata

    results = []
    for spec in specs:
        result = evaluate(spec, series, cutoff=cutoff, through=through)
        result["lag_diagnostics"] = scan_lags(spec, series, cutoff=cutoff, through=through)
        results.append(result)
    return {
        "schema_version": "us-cpi-forward-validation-v1", "country": "USA",
        "training_cutoff": cutoff, "holdout_through": through,
        "bls_history_retrieved_at": history.get("retrieved_at"),
        "model": "fixed-cutoff OLS AR(1) plus controls vs same baseline plus all configured eligible source lags",
        "vintage": "latest_vintage_replay_not_real_time",
        "status": "complete" if all(r["status"] == "scored" and not r["unscored_months"] for r in results) else "partial",
        "limitations": [
            "Both models use identical complete training and holdout rows. Coefficients fit through the cutoff only.",
            "Each holdout month may use observed earlier holdout months as lagged features, not as training labels.",
            "CPI targets use SA MoM. PPI and EIA inputs are as published; external models include calendar month effects.",
            "PPI and INDPRO use at least one reference-month lag. Release-time calendars and archival vintages are not reconstructed.",
            "Same-reference-month EIA inputs are nowcast features; their as-of completeness has not been audited.",
            "Re-running can change older scores as sources revise. Small holdouts and confounding preclude promotion, causality or a live forecast.",
            "Relative RMSE change is suppressed for fewer than three matched holdout months.",
            "Single-lag diagnostics rank common pre-cutoff expanding-window folds, never the holdout. The selected lag is re-fit on its available pre-cutoff rows.",
            "Pre/post-2022 lag and rolling coefficient signs are stability diagnostics, not independent significance tests.",
            "Multivariate pathways group eligible inputs at one common lag; an EIA lag-zero model is run separately and contains only eligible lag-zero inputs.",
        ],
        "sources": sources, "relationships": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=PUBLIC / "us_cpi_api_history_v1.json")
    parser.add_argument("--cutoff", default=CUTOFF, help="last allowed month of model training")
    parser.add_argument("--through", help="last holdout month; default is latest observed headline MoM")
    parser.add_argument("--vehicle-only", action="store_true", help="offline replay using local official BLS history")
    parser.add_argument("--require-complete", action="store_true", help="do not replace output if any observations are unscored")
    parser.add_argument("--out", type=Path, help="optional private artifact path; omit for stdout")
    args = parser.parse_args()
    result = run(read_json(args.history), read_json(CONFIG / "cpi_vehicle_chain_backtest_v1.json"),
                 read_json(CONFIG / "cpi_external_backtest_v1.json"), read_json(CONFIG / "cpi_structure.map.json"),
                 cutoff=args.cutoff, through=args.through, vehicle_only=args.vehicle_only)
    output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.require_complete and result["status"] != "complete":
        print(output, file=sys.stderr, end="")
        return 2
    if args.out is None:
        print(output, end="")
    else:
        destination = args.out.resolve()
        if PUBLIC == destination or PUBLIC in destination.parents:
            parser.error("--out must be outside public/data")
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                prefix=f".{destination.name}.", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(output)
        try:
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the local ACP research model without touching deployable artifacts."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from shipping_capacity.panama_acp import (
    ACP_GATUN_DASHBOARD_PDF,
    ACP_ADVISORY_INDEX,
    attach_lagged_oni,
    build_local_acp_report,
    aggregate_daily_gatun_to_monthly,
    aggregate_daily_hydrology_proxy,
    extract_pdf_text,
    fetch_public_pdf,
    fetch_public_text,
    fetch_gatun_dashboard_snapshot,
    fetch_gpm_imerg_daily_monitor,
    fetch_monthly_operations_summaries,
    load_acp_daily_gatun_history,
    load_monthly_climate_forecast_ensemble,
    load_nasa_power_daily_meteorology,
    load_monthly_history,
    parse_booking_slot_windows,
    parse_gatun_projection_csv,
    parse_noaa_oni_text,
    summarize_projection_month,
)


def _read_pdf_or_text(location: str) -> str:
    path = Path(location)
    if not path.exists():
        raise SystemExit(f"advisory text file does not exist: {path}")
    return path.read_text(encoding="utf-8")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"monthly covariate CSV does not exist: {path}")
    import csv
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, help="Authorized local monthly ACP history CSV")
    parser.add_argument(
        "--acp-level-history",
        type=Path,
        help="Local ACP daily Gatun history CSV; requires --monthly-covariates.",
    )
    parser.add_argument(
        "--acp-nasa-proxy",
        action="store_true",
        help="Use local ACP daily levels plus local NASA POWER weather proxy for a sensitivity backtest.",
    )
    parser.add_argument("--nasa-power-daily", type=Path, help="Local NASA POWER daily JSON for --acp-nasa-proxy.")
    parser.add_argument("--oni-history", type=Path, help="Local NOAA CPC oni.ascii.txt; attached with a two-month lag.")
    parser.add_argument(
        "--climate-forecast-ensemble",
        type=Path,
        help="Local monthly C3S/NMME ensemble CSV for the month after hydrology history.",
    )
    parser.add_argument(
        "--gpm-imerg-recent-days",
        type=int,
        help="Fetch up to 31 days of local-only GPM IMERG monitoring ending on the ACP dashboard observation date.",
    )
    parser.add_argument(
        "--gpm-imerg-compare-prior-year",
        action="store_true",
        help="Fetch matching prior-year GPM days and add an observed same-calendar-day comparison.",
    )
    parser.add_argument(
        "--monthly-covariates",
        type=Path,
        help="Local monthly climate/operations CSV joined to --acp-level-history.",
    )
    parser.add_argument(
        "--advisory-text",
        action="append",
        default=[],
        help="Locally extracted ACP advisory text. May be supplied more than once.",
    )
    parser.add_argument(
        "--advisory-url",
        action="append",
        default=[],
        help="Official ACP advisory PDF URL. Fetched in memory only; raw PDF is not stored.",
    )
    parser.add_argument("--gatun-url", default=ACP_GATUN_DASHBOARD_PDF)
    parser.add_argument("--projection-url", help="Official ACP projection CSV URL, fetched in memory only.")
    parser.add_argument("--projection-month", help="YYYY-MM month to summarize from --projection-url.")
    parser.add_argument(
        "--operations-index-url",
        nargs="?",
        const=ACP_ADVISORY_INDEX,
        help="Fetch ACP monthly operations PDFs in memory from the official Advisory index.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(tempfile.gettempdir()) / "panama_acp_research_report.json",
        help="Defaults to the system temporary directory, never public/data.",
    )
    args = parser.parse_args()
    if args.history and args.acp_level_history:
        parser.error("use either --history or --acp-level-history, not both")
    if args.acp_level_history and not args.monthly_covariates and not args.acp_nasa_proxy:
        parser.error("--acp-level-history requires --monthly-covariates")
    if args.monthly_covariates and (not args.acp_level_history or args.acp_nasa_proxy):
        parser.error("--monthly-covariates requires --acp-level-history")
    if args.acp_nasa_proxy and (not args.nasa_power_daily or not args.acp_level_history):
        parser.error("--acp-nasa-proxy requires --acp-level-history and --nasa-power-daily")
    if args.nasa_power_daily and not args.acp_nasa_proxy:
        parser.error("--nasa-power-daily requires --acp-nasa-proxy")
    if bool(args.projection_url) != bool(args.projection_month):
        parser.error("--projection-url and --projection-month must be supplied together")
    if args.gpm_imerg_recent_days is not None and not 1 <= args.gpm_imerg_recent_days <= 31:
        parser.error("--gpm-imerg-recent-days must be between 1 and 31")
    if args.gpm_imerg_compare_prior_year and not args.gpm_imerg_recent_days:
        parser.error("--gpm-imerg-compare-prior-year requires --gpm-imerg-recent-days")
    dashboard = fetch_gatun_dashboard_snapshot(args.gatun_url)
    history = load_monthly_history(args.history) if args.history else []
    if args.acp_level_history:
        levels = load_acp_daily_gatun_history(args.acp_level_history)
        if args.acp_nasa_proxy:
            history = aggregate_daily_hydrology_proxy(levels, load_nasa_power_daily_meteorology(args.nasa_power_daily))
        else:
            history = aggregate_daily_gatun_to_monthly(levels, _read_csv_rows(args.monthly_covariates))
    if args.oni_history:
        history = attach_lagged_oni(history, parse_noaa_oni_text(args.oni_history.read_text(encoding="utf-8")))
    windows = []
    for filename in args.advisory_text:
        windows.extend(parse_booking_slot_windows(_read_pdf_or_text(filename), source_url=str(filename)))
    for url in args.advisory_url:
        windows.extend(parse_booking_slot_windows(extract_pdf_text(fetch_public_pdf(url)), source_url=url))
    published_projection = None
    if args.projection_url:
        published_projection = summarize_projection_month(
            parse_gatun_projection_csv(fetch_public_text(args.projection_url)), args.projection_month
        )
    monthly_operations, operations_failures = [], []
    if args.operations_index_url:
        monthly_operations, operations_failures = fetch_monthly_operations_summaries(args.operations_index_url)
    climate_forecast_members = (
        load_monthly_climate_forecast_ensemble(args.climate_forecast_ensemble)
        if args.climate_forecast_ensemble else []
    )
    satellite_precipitation = []
    previous_year_satellite_precipitation = []
    if args.gpm_imerg_recent_days:
        from datetime import datetime, timedelta

        as_of = datetime.strptime(dashboard.observation_date, "%Y-%m-%d").date()
        start = as_of - timedelta(days=args.gpm_imerg_recent_days - 1)
        satellite_precipitation = fetch_gpm_imerg_daily_monitor(start.isoformat(), as_of.isoformat())
        if args.gpm_imerg_compare_prior_year and satellite_precipitation:
            first_observed = datetime.strptime(satellite_precipitation[0].observation_date, "%Y-%m-%d").date()
            last_observed = datetime.strptime(satellite_precipitation[-1].observation_date, "%Y-%m-%d").date()
            try:
                prior_start = first_observed.replace(year=first_observed.year - 1)
                prior_end = last_observed.replace(year=last_observed.year - 1)
            except ValueError:
                parser.error("prior-year GPM comparison cannot map a leap day")
            previous_year_satellite_precipitation = fetch_gpm_imerg_daily_monitor(
                prior_start.isoformat(), prior_end.isoformat()
            )
    report = build_local_acp_report(
        dashboard,
        history=history,
        advisory_windows=windows,
        published_projection=published_projection,
        monthly_operations=monthly_operations,
        operations_failures=operations_failures,
        climate_forecast_members=climate_forecast_members,
        satellite_precipitation=satellite_precipitation,
        previous_year_satellite_precipitation=previous_year_satellite_precipitation,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()

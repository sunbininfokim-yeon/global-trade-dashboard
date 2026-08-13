"""Keyless public container context from the World Bank API."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


WORLD_BANK_API = "https://api.worldbank.org/v2/country/{countries}/indicator/IS.SHP.GOOD.TU"


def summarize_world_bank_teu(
    payload: list[Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    if len(payload) < 2 or not isinstance(payload[1], list):
        raise ValueError("unexpected World Bank container payload")
    metadata = payload[0] if isinstance(payload[0], dict) else {}
    rows = [row for row in payload[1] if isinstance(row, dict) and row.get("value") is not None]
    by_country_year = {
        (str(row.get("countryiso3code")), int(row["date"])): float(row["value"])
        for row in rows
        if row.get("countryiso3code") and str(row.get("date", "")).isdigit()
    }

    groups = []
    for group in config["country_groups"]:
        countries = group["countries"]
        candidate_years = sorted(
            {
                year
                for country, year in by_country_year
                if country in countries
            },
            reverse=True,
        )
        selected_year = None
        selected_values: dict[str, float] = {}
        for year in candidate_years:
            values = {
                country: by_country_year[(country, year)]
                for country in countries
                if (country, year) in by_country_year
            }
            if len(values) / len(countries) >= group.get("minimum_coverage_ratio", 0.7):
                selected_year = year
                selected_values = values
                break
        groups.append(
            {
                "id": group["id"],
                "name_ko": group["name_ko"],
                "year": selected_year,
                "container_port_traffic_teu": sum(selected_values.values()) if selected_values else None,
                "country_count_expected": len(countries),
                "country_count_reported": len(selected_values),
                "coverage_ratio": len(selected_values) / len(countries),
                "countries_reported": sorted(selected_values),
                "status": "observed_country_port_throughput_context" if selected_values else "no_data",
            }
        )
    return {
        "status": "observed_free_api_context_not_route_volume",
        "indicator": "IS.SHP.GOOD.TU",
        "indicator_label": "Container port traffic (TEU: 20 foot equivalent units)",
        "source_last_updated": metadata.get("lastupdated"),
        "groups": groups,
        "route_usage": "endpoint scale and plausibility check only; never used as bilateral route cargo",
        "warning_ko": "국가 항만 처리량은 수출입·환적·공컨테이너를 포함할 수 있으며 양국 간 항로 물량이 아니다.",
    }


class WorldBankContainerClient:
    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        countries = sorted(
            {
                country
                for group in config["country_groups"]
                for country in group["countries"]
            }
        )
        params = urllib.parse.urlencode(
            {
                "format": "json",
                "date": config.get("year_range", "2020:2025"),
                "per_page": 2000,
            }
        )
        url = WORLD_BANK_API.format(countries=";".join(countries)) + "?" + params
        request = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard/1.0"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        return summarize_world_bank_teu(payload, config)

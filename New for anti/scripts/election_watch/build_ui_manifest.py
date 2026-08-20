#!/usr/bin/env python3
"""Build the machine-readable election UI readiness contract.

The manifest tells the UI which screens may render from public JSON, which must
show an explicit partial state, and which must remain disabled. It intentionally
does not infer political facts or promote raw source text.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1] / "public" / "data"
BOARD_PATH = PUBLIC / "elections_board_v1.json"
CALENDAR_PATH = PUBLIC / "elections_calendar_master_v1.json"
OUTPUT_PATH = PUBLIC / "elections_ui_manifest_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def screen(status: str, paths: list[str], missing: Optional[list[str]] = None, **extra: Any) -> dict[str, Any]:
    return {
        "status": status,
        "paths": paths,
        "missing": missing or [],
        **extra,
    }


def detail_profile(country: dict[str, Any]) -> dict[str, Any]:
    iso3 = country["iso3"]
    tier = int(country.get("priority_tier") or 3)
    if iso3 == "USA":
        return {
            "id": "tier1_usa_deep",
            "max_depth": "federal_and_state_officials",
            "allow": [
                "national_executive",
                "congress_chambers",
                "federal_member_rosters",
                "state_governors",
                "state_legislature_party_seats",
                "state_federal_delegations",
                "house_factions",
            ],
            "exclude": ["county_city_local_legislator_rosters"],
        }
    if iso3 == "IRN":
        return {
            "id": "tier2_iran_china_style",
            "max_depth": "national_elected_and_appointed_power_structures",
            "allow": [
                "supreme_leader_axis",
                "elected_executive",
                "majlis_and_election_system",
                "assembly_of_experts",
                "guardian_council_and_clerical_institutions",
                "irgc_security_axis",
                "analytical_factions_with_confidence",
                "major_election_calendar",
            ],
            "exclude": [
                "subnational_rosters",
                "unverified_complete_faction_rosters",
                "invented_election_dates_or_members",
            ],
        }
    if tier == 1:
        return {
            "id": "tier1_country_specific_deep",
            "max_depth": "national_institutions_plus_selected_admin1",
            "allow": ["national_executive", "national_legislature", "country_specific_power_structure"],
            "exclude": ["local_legislator_rosters", "municipal_councillor_rosters"],
        }
    if tier == 2:
        return {
            "id": "tier2_national_core",
            "max_depth": "national_plus_selected_major_subnational_summary",
            "allow": [
                "head_of_government_or_state",
                "national_legislature_party_composition",
                "ruling_opposition_ratio",
                "major_election_calendar",
                "selected_major_subnational_summary",
            ],
            "exclude": [
                "subnational_legislator_rosters",
                "basic_local_government_officials",
                "municipal_councillor_rosters",
                "committee_member_rosters_by_default",
            ],
        }
    return {
        "id": "tier3_basic_geopolitical",
        "max_depth": "national_power_brief",
        "allow": [
            "head_of_government_or_state",
            "ruling_party",
            "national_legislature_ruling_opposition_ratio_if_available",
            "major_election_calendar",
            "country_specific_power_axis_if_geopolitically_material",
        ],
        "exclude": [
            "all_subnational_rosters",
            "local_government_detail",
            "legislative_committees",
            "party_factions_by_default",
        ],
    }


def generic_country_manifest(country: dict[str, Any]) -> dict[str, Any]:
    iso3 = country["iso3"]
    tier = int(country.get("priority_tier") or 3)
    has_map = (PUBLIC / "admin1" / f"{iso3}.json").exists()
    has_subnational = bool(country.get("subnational_live"))
    has_events = bool(country.get("events"))
    has_legislature = bool(country.get("legislature_live"))
    has_factions = bool(country.get("factions"))
    has_race = bool(country.get("race_progress"))
    has_executive = bool(country.get("executive_live"))
    has_power_structure = bool(country.get("leadership") or country.get("power") or country.get("emirates"))

    if has_map and has_subnational:
        sub_status = "partial"
        sub_missing = ["country_specific_subnational_detail_contract"]
    elif has_map:
        sub_status = "partial"
        sub_missing = ["political_overlay"]
    elif has_subnational:
        sub_status = "partial"
        sub_missing = ["admin1_geometry"]
    else:
        sub_status = "disabled"
        sub_missing = ["admin1_geometry", "political_overlay"]

    if tier >= 3:
        sub_status = "disabled"
        sub_missing = ["outside_tier_scope"]

    return {
        "iso3": iso3,
        "name_ko": country.get("name_ko"),
        "priority_tier": country.get("priority_tier"),
        "detail_profile": detail_profile(country),
        "screens": {
            "overview": screen(
                "ready" if country.get("head") else "partial",
                [f"countries[{iso3}].head", f"countries[{iso3}].parties_tracked"],
                [] if country.get("head") else ["head"],
            ),
            "calendar": screen(
                "ready" if has_events else "disabled",
                [f"countries[{iso3}].events"],
                [] if has_events else ["events"],
            ),
            "subnational_map": screen(
                sub_status,
                [f"/public/data/admin1/{iso3}.json", f"countries[{iso3}].subnational_live"],
                sub_missing,
                map_asset_exists=has_map,
                political_overlay_exists=has_subnational,
            ),
            "executive": screen(
                "ready" if has_executive else ("partial" if country.get("head") and tier == 1 else ("ready" if country.get("head") else "disabled")),
                [f"countries[{iso3}].executive_live", f"countries[{iso3}].head", f"countries[{iso3}].prime_minister"],
                [] if has_executive else (["full_executive_roster", "cabinet", "senior_staff"] if tier == 1 else []),
                display_mode=("full_executive_target" if tier == 1 else "executive_core") if has_executive else ("full_executive_target" if tier == 1 else "national_head_only"),
            ),
            "legislature": screen(
                "ready" if has_legislature else "disabled",
                [f"countries[{iso3}].legislature_live"],
                [] if has_legislature else ["live_composition"],
                display_mode="full_available_national" if tier == 1 else "party_composition_and_ruling_opposition_ratio",
            ),
            "legislature_detail": screen(
                "partial" if has_legislature and tier == 1 else "disabled",
                [f"countries[{iso3}].legislature_live"],
                ["committees", "committee_chairs", "committee_member_rosters"]
                if tier == 1
                else ["outside_tier_scope"],
            ),
            "factions": screen(
                "partial" if has_factions and tier == 1 else "disabled",
                [f"countries[{iso3}].factions"],
                ["complete_nonoverlapping_rosters"]
                if has_factions and tier == 1
                else ["outside_tier_scope" if tier > 1 else "faction_dataset"],
            ),
            "race_progress": screen(
                "ready" if has_race else "disabled",
                [f"countries[{iso3}].race_progress"],
                [] if has_race else ["active_race_progress"],
            ),
            "power_structure": screen(
                "ready" if has_power_structure else "disabled",
                [
                    f"countries[{iso3}].leadership",
                    f"countries[{iso3}].power",
                    f"countries[{iso3}].emirates",
                ],
                [] if has_power_structure else ["country_specific_power_dataset"],
                display_mode="country_specific_geopolitical_exception",
            ),
        },
    }


def apply_country_contracts(manifest: dict[str, dict[str, Any]]) -> None:
    usa = manifest.get("USA")
    if usa:
        usa["screens"].update(
            {
                "subnational_map": screen(
                    "partial",
                    [
                        "/public/data/admin1/USA.json",
                        "countries[USA].ui_ready.state_drilldown.states",
                    ],
                    [
                        "senate_term_end",
                        "all_congressional_district_geometry",
                    ],
                    map_join="state.map_feature_code ↔ feature.properties.code",
                    prejoined=True,
                    map_asset_exists=(PUBLIC / "admin1" / "USA.json").exists(),
                    political_overlay_exists=True,
                ),
                "executive": screen(
                    "ready",
                    ["countries[USA].executive_live"],
                    [],
                    display_mode="full_cabinet_plus_eop_core",
                ),
                "legislature": screen(
                    "ready",
                    ["countries[USA].ui_ready.congress"],
                    [],
                    member_rows_pre_split=True,
                    seat_count_paths={
                        "voting_party_members": "countries[USA].ui_ready.congress.summary.house_by_party",
                        "voting_members_total": "countries[USA].ui_ready.congress.summary.house_voting_members",
                        "vacancies": "countries[USA].ui_ready.congress.summary.house_vacancies",
                        "delegates_by_party": "countries[USA].ui_ready.congress.summary.house_delegates_by_party",
                    },
                    note="House list includes voting members and territorial/DC delegates; use the declared voting-seat paths for the hemicycle.",
                ),
                "legislature_detail": screen(
                    "partial",
                    ["countries[USA].ui_ready.congress"],
                    ["standing_committees", "committee_chairs", "committee_member_rosters"],
                ),
                "factions": screen(
                    "partial",
                    ["countries[USA].factions.parties"],
                    ["complete_rosters_for_all_groups"],
                    count_rule="display_count only; overlaps allowed; never sum faction counts",
                ),
            }
        )

    jpn = manifest.get("JPN")
    if jpn:
        jpn["screens"]["executive"] = screen(
            "ready",
            ["countries[JPN].executive_live"],
            [],
        )
        jpn["screens"]["subnational_map"] = screen(
            "partial",
            ["/public/data/admin1/JPN.json", "countries[JPN].subnational_live.governors"],
            ["prefectural_assembly_detail"],
            map_asset_exists=(PUBLIC / "admin1" / "JPN.json").exists(),
            political_overlay_exists=True,
        )

    kor = manifest.get("KOR")
    if kor:
        kor["screens"]["executive"] = screen(
            "partial",
            ["countries[KOR].executive_live"],
            ["cabinet_source_conflict_review"],
        )
        kor["screens"]["subnational_map"] = screen(
            "partial",
            ["/public/data/admin1/KOR.json", "countries[KOR].subnational_live"],
            ["individual_mayors_governors", "local_legislature_detail"],
            map_asset_exists=(PUBLIC / "admin1" / "KOR.json").exists(),
            political_overlay_exists=True,
        )
        kor["screens"]["factions"] = screen(
            "disabled",
            [],
            ["ppp_factions", "dpk_factions"],
        )

    chn = manifest.get("CHN")
    if chn:
        chn["navigation"] = ["party", "state_council", "military"]
        chn["hidden_navigation"] = ["national_peoples_congress"]
        chn["screens"].update(
            {
                "executive": screen(
                    "disabled",
                    [],
                    ["use_state_council_navigation_instead"],
                ),
                "party": screen(
                    "ready",
                    [
                        "countries[CHN].leadership.party_state.general_secretary",
                        "countries[CHN].leadership.party_state.politburo_standing_committee",
                        "countries[CHN].leadership.party_state.politburo",
                        "countries[CHN].leadership.party_state.central_departments",
                    ],
                    [],
                ),
                "state_council": screen(
                    "ready",
                    ["countries[CHN].leadership.party_state.state_council"],
                    [],
                ),
                "military": screen(
                    "ready",
                    [
                        "countries[CHN].leadership.cmc",
                        "countries[CHN].leadership.service_branches",
                        "countries[CHN].leadership.theater_commands",
                        "countries[CHN].leadership.security_organs",
                    ],
                    [],
                ),
                "subnational_map": screen(
                    "partial",
                    ["/public/data/admin1/CHN.json"],
                    ["provincial_party_secretaries", "provincial_governors"],
                    map_asset_exists=True,
                    political_overlay_exists=False,
                ),
            }
        )

    irn = manifest.get("IRN")
    if irn:
        irn["navigation"] = [
            "supreme_leader",
            "executive",
            "majlis",
            "assembly_of_experts",
            "clerical_institutions",
            "security_axis",
            "factions",
        ]
        irn["screens"].update(
            {
                "supreme_leader": screen(
                    "ready",
                    ["countries[IRN].leadership.supreme_leader"],
                    [],
                ),
                "executive": screen(
                    "ready",
                    ["countries[IRN].leadership.elected_executive"],
                    [],
                    display_mode="elected_executive_under_supreme_leader_axis",
                ),
                "legislature": screen(
                    "partial",
                    [
                        "countries[IRN].leadership.legislature",
                        "countries[IRN].leadership.election_system.institutions",
                    ],
                    ["majlis_party_bloc_seats", "member_roster", "committees"],
                    display_mode="managed_election_legislature",
                ),
                "experts_assembly": screen(
                    "partial",
                    ["countries[IRN].leadership.clerical_institutions.assembly_of_experts"],
                    ["member_roster", "clerical_current_counts"],
                ),
                "clerical_institutions": screen(
                    "ready",
                    [
                        "countries[IRN].leadership.clerical_institutions.guardian_council",
                        "countries[IRN].leadership.clerical_institutions.expediency_council",
                    ],
                    [],
                ),
                "security_axis": screen(
                    "partial",
                    ["countries[IRN].leadership.security_axis"],
                    ["official_current_irgc_and_quds_force_roster"],
                ),
                "factions": screen(
                    "partial",
                    ["countries[IRN].leadership.analytical_factions"],
                    ["complete_nonoverlapping_rosters", "official_party_membership"],
                    count_rule="analytical blocs overlap; never sum groups",
                ),
                "election_system": screen(
                    "ready",
                    [
                        "countries[IRN].leadership.election_system",
                        "countries[IRN].events",
                    ],
                    [],
                ),
            }
        )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    if not BOARD_PATH.exists():
        errors.append(f"missing {BOARD_PATH}")
    if not CALENDAR_PATH.exists():
        errors.append(f"missing {CALENDAR_PATH}")
    if errors:
        print("\n".join(errors))
        return 1

    board = load_json(BOARD_PATH)
    calendar = load_json(CALENDAR_PATH)
    countries = {row["iso3"]: row for row in board.get("countries", []) if row.get("iso3")}
    country_contracts = {iso3: generic_country_manifest(row) for iso3, row in countries.items()}
    apply_country_contracts(country_contracts)

    usa = countries.get("USA") or {}
    usa_states = (((usa.get("ui_ready") or {}).get("state_drilldown") or {}).get("states") or [])
    if len(usa_states) != 50:
        errors.append(f"USA ui_ready state count is {len(usa_states)}, expected 50")
    if usa_states:
        usa_map = load_json(PUBLIC / "admin1" / "USA.json")
        map_codes = {
            (feature.get("properties") or {}).get("code")
            for feature in (usa_map.get("features") or [])
        }
        missing_state_codes = sorted(
            state.get("map_feature_code")
            for state in usa_states
            if state.get("map_feature_code") not in map_codes
        )
        if missing_state_codes:
            errors.append("USA state map joins missing: " + ", ".join(missing_state_codes))
        state_house_rows = sum(
            len(((state.get("federal_delegation") or {}).get("house_members") or []))
            for state in usa_states
        )
        state_senate_rows = sum(
            len(((state.get("federal_delegation") or {}).get("senators") or []))
            for state in usa_states
        )
        territory_house_rows = sum(
            len(row.get("house_members") or [])
            for row in ((((usa.get("ui_ready") or {}).get("state_drilldown") or {}).get("territories_and_district") or []))
        )
        congress_ready = (usa.get("ui_ready") or {}).get("congress") or {}
        if state_house_rows + territory_house_rows != len(congress_ready.get("house_members") or []):
            errors.append("USA state/territory House pre-join does not match Congress House rows")
        if state_senate_rows != len(congress_ready.get("senate_members") or []):
            errors.append("USA state Senate pre-join does not match Congress Senate rows")
    usa_factions = (((usa.get("factions") or {}).get("parties") or {}))
    if sum(len(block.get("factions") or []) for block in usa_factions.values()) < 1:
        errors.append("USA factions are empty after normalization")
    jpn_factions = ((((countries.get("JPN") or {}).get("factions") or {}).get("factions") or []))
    if not jpn_factions:
        errors.append("JPN LDP factions are empty after normalization")
    if not ((countries.get("CHN") or {}).get("leadership") or {}).get("party_state"):
        errors.append("CHN leadership.party_state missing")
    irn_factions = (((countries.get("IRN") or {}).get("leadership") or {}).get("analytical_factions") or {}).get("groups")
    if not irn_factions:
        errors.append("IRN leadership.analytical_factions.groups missing")
    if not calendar.get("world_by_month"):
        errors.append("calendar.world_by_month missing")
    if len(board.get("countries") or []) < 19:
        errors.append("board contains fewer than 19 tracked countries")

    missing_spectrum = sorted(
        iso3 for iso3, row in countries.items() if not row.get("map_spectrum")
    )
    missing_admin1 = sorted(
        iso3 for iso3 in countries if not (PUBLIC / "admin1" / f"{iso3}.json").exists()
    )
    if missing_spectrum:
        warnings.append("world map has neutral/no-spectrum countries: " + ", ".join(missing_spectrum))

    ready_screens = []
    partial_screens = []
    disabled_screens = []
    for iso3, contract in country_contracts.items():
        for name, detail in contract["screens"].items():
            target = f"{iso3}.{name}"
            {"ready": ready_screens, "partial": partial_screens, "disabled": disabled_screens}[
                detail["status"]
            ].append(target)

    doc = {
        "schema_version": "elections-ui-manifest-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "board_generated_at": board.get("generated_at"),
        "calendar_generated_at": calendar.get("generated_at"),
        "claude_handoff_gate": {
            "can_start_ui": not errors,
            "rule": "Render only ready/partial screens from declared paths. Disabled screens stay disabled.",
            "no_client_modeling": True,
            "no_client_fact_invention": True,
            "no_client_data_file_creation": True,
            "errors": errors,
            "warnings": warnings,
        },
        "assets": {
            "manifest": "/public/data/elections_ui_manifest_v1.json",
            "board": "/public/data/elections_board_v1.json",
            "calendar": "/public/data/elections_calendar_master_v1.json",
            "admin1_template": "/public/data/admin1/{ISO3}.json",
        },
        "status_meanings": {
            "ready": "UI may render the declared scope directly.",
            "partial": "UI may render declared paths and must show disabled placeholders for missing fields.",
            "disabled": "Do not expose this screen as implemented.",
        },
        "scope_policy": {
            "principle_ko": "국가 중요도가 낮아질수록 지방·개별 의원보다 국가수반, 집권축, 의회 여야 구도, 핵심 선거 일정에 집중한다.",
            "tier1": "국가별 특수 권력구조까지. 미국만 주 단위 연방대표·주의회 정당 의석까지 deep.",
            "tier2": "국가 단위가 기본. 광역 수장·지방 요약은 선택적이며 지방의원 명단은 수집·표시하지 않는다. 이란·사우디는 지정학·에너지·안보 특수형으로 핵심 권력기관을 추가한다.",
            "tier3": "국가수반·집권당·국가 의회 여야 비율·핵심 일정만. UAE처럼 국가 단위 지도자 카드가 중심인 국가에 적용한다.",
            "korea_local_rule": "광역단체 요약까지만 기본 허용. 기초단체장·기초의원·광역의원 개별 명단은 기본 범위 밖.",
            "no_uniform_worldwide_depth": True,
        },
        "global_screens": {
            "home_world_map": screen(
                "partial" if missing_spectrum else "ready",
                ["board.countries[].map_spectrum", "board.countries[].head"],
                [f"map_spectrum:{iso3}" for iso3 in missing_spectrum],
                political_color_country_count=len(countries) - len(missing_spectrum),
                tracked_country_count=len(countries),
            ),
            "home_calendar": screen(
                "ready",
                ["calendar.world_by_month", "calendar.world_national_highlights"],
                [],
                board_tracked_event_rows=(calendar.get("summary") or {}).get("board_tracked_event_rows"),
            ),
            "country_navigation": {
                "status": "ready",
                "rule": "Hide the global calendar when a country opens.",
            },
        },
        "coverage": {
            "tracked_countries": len(countries),
            "countries_with_spectrum": len(countries) - len(missing_spectrum),
            "countries_with_admin1_geometry": len(countries) - len(missing_admin1),
            "missing_spectrum": missing_spectrum,
            "missing_admin1_geometry": missing_admin1,
            "screen_counts": {
                "ready": len(ready_screens),
                "partial": len(partial_screens),
                "disabled": len(disabled_screens),
            },
        },
        "countries": country_contracts,
    }
    OUTPUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUTPUT_PATH), **doc["coverage"], "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

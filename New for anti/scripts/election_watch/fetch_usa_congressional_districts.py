#!/usr/bin/env python3
"""Build UI-ready U.S. congressional-district geometry from Census TIGERweb.

The Census endpoint supplies only official boundary geometry.  This builder
pre-joins the already-published board's House member/party fields before the
browser reads the asset, so the UI never creates political joins client-side.

Source: U.S. Census Bureau, TIGERweb Legislative MapServer, layer 4
        119th Congressional Districts, January 1 2025 vintage.

Usage:
    python3 fetch_usa_congressional_districts.py --all
    python3 fetch_usa_congressional_districts.py --state CA
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(os.path.join(HERE, "..", ".."))
BOARD = os.path.join(APP, "public", "data", "elections_board_v1.json")
OUT_DIR = os.path.join(APP, "public", "data", "congressional_districts", "USA")
ENDPOINT = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer/4/query"
SOURCE = "U.S. Census Bureau TIGERweb · 119th Congressional Districts · 2025-01-01 vintage"

FIPS_BY_STATE = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22",
    "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40",
    "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56", "DC": "11",
}


def load_usa():
    with open(BOARD, encoding="utf-8") as handle:
        board = json.load(handle)
    return next(country for country in board["countries"] if country["iso3"] == "USA")


def district_key(value):
    if value is None:
        return "00"
    return str(value).zfill(2)


def members_by_state(usa):
    output = {}
    for state in usa.get("ui_ready", {}).get("state_drilldown", {}).get("states", []):
        rows = {}
        for member in state.get("federal_delegation", {}).get("house_members", []):
            rows[district_key(member.get("district"))] = {
                "member_name": member.get("name", "불명"),
                "party_abbr": member.get("abbr", "불명"),
                "bioguide_id": member.get("bioguideId", "불명"),
            }
        output[state["id"]] = rows
    return output


def fetch_geojson(state_fips):
    query = urllib.parse.urlencode({
        "where": f"STATE='{state_fips}'",
        "outFields": "STATE,CD119,GEOID,NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    request = urllib.request.Request(f"{ENDPOINT}?{query}", headers={"User-Agent": "GlobalTradeElectionWatch/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        document = json.load(response)
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise RuntimeError(f"Census returned no district features for FIPS {state_fips}")
    return document


def build_state(state_id, fips, members):
    source = fetch_geojson(fips)
    features = []
    for feature in source["features"]:
        props = feature.get("properties") or {}
        district = district_key(props.get("CD119"))
        member = members.get(state_id, {}).get(district, {})
        features.append({
            "type": "Feature",
            "properties": {
                "state_id": state_id,
                "district": district,
                "member_name": member.get("member_name", "불명"),
                "party_abbr": member.get("party_abbr", "불명"),
                "bioguide_id": member.get("bioguide_id", "불명"),
            },
            "geometry": feature["geometry"],
        })
    return {
        "type": "FeatureCollection",
        "source": SOURCE,
        "retrieved": str(date.today()),
        "board_generated_at": load_usa().get("generated_at", "불명"),
        "features": features,
    }


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--state", choices=sorted(FIPS_BY_STATE))
    parser.add_argument("--refresh", action="store_true", help="이미 만든 주 GeoJSON도 공식 소스로 다시 받기")
    args = parser.parse_args()
    usa = load_usa()
    members = members_by_state(usa)
    wanted = sorted(FIPS_BY_STATE) if args.all else [args.state]
    os.makedirs(OUT_DIR, exist_ok=True)
    for state_id in wanted:
        path = os.path.join(OUT_DIR, f"{state_id}.json")
        if not args.refresh and os.path.exists(path) and os.path.getsize(path) > 200:
            print(f"{state_id}: 기존 자산 유지 → {os.path.relpath(path, APP)}", flush=True)
            continue
        document = build_state(state_id, FIPS_BY_STATE[state_id], members)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        print(f"{state_id}: {len(document['features'])} districts → {os.path.relpath(path, APP)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

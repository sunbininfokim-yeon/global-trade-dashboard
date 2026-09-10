#!/usr/bin/env python3
"""One-off probe: does TIGERweb/Legislative serve a 120th Congress layer yet,
and if so does it already carry the 2025 mid-decade redistricting for the 8
states we need? Prints JSON; makes no changes to the repo."""
import json
import urllib.parse
import urllib.request

BASE = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Legislative/MapServer"
UA = {"User-Agent": "GlobalTradeElectionWatch-probe/1.0"}
NEEDED = {"TX": "48", "NC": "37", "MO": "29", "OH": "39", "UT": "49", "CA": "06", "AL": "01", "TN": "47"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    root = get(f"{BASE}?f=json")
    layers = [{"id": l["id"], "name": l["name"]} for l in root.get("layers", [])]
    print("ALL_LAYERS", json.dumps(layers, ensure_ascii=False))

    cd_layers = [l for l in layers if "congressional" in l["name"].lower()]
    print("CONGRESSIONAL_LAYERS", json.dumps(cd_layers, ensure_ascii=False))

    target = next((l for l in cd_layers if "120" in l["name"]), None)
    print("LAYER_120TH_FOUND", json.dumps(target, ensure_ascii=False))
    if not target:
        print("RESULT", json.dumps({"has_120th_layer": False}))
        return

    layer_id = target["id"]
    # Sample-check: any redistricted state whose district count now differs
    # from its pre-2025 count would prove this layer already reflects the
    # 2025-2026 mid-decade maps rather than a stale January-2025 snapshot.
    counts = {}
    for state, fips in NEEDED.items():
        query = urllib.parse.urlencode({
            "where": f"STATE='{fips}'",
            "outFields": "STATE",
            "returnGeometry": "false",
            "f": "json",
        })
        doc = get(f"{BASE}/{layer_id}/query?{query}")
        counts[state] = len(doc.get("features", []))
    print("STATE_FEATURE_COUNTS", json.dumps(counts, ensure_ascii=False))
    print("RESULT", json.dumps({"has_120th_layer": True, "layer_id": layer_id, "layer_name": target["name"]}))


if __name__ == "__main__":
    main()

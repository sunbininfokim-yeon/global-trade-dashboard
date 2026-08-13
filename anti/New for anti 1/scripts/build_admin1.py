#!/usr/bin/env python3
"""Split Natural Earth admin-1 into one small file per country.

Why not fetch it in the browser
-------------------------------
The climate country view needs internal borders -- "Mato Grosso" or "Punjab"
does not read as a place without them. Natural Earth's 50m admin-1 file is small
but only covers nine countries, so Argentina, Ghana, Côte d'Ivoire, Vietnam,
Ukraine, Thailand and every country still in training came back empty. The 10m
file covers all 253, and is 39 MB.

Nobody should download 39 MB to look at one country. This cuts it per country at
build time, so the browser fetches roughly a hundred kilobytes for the country it
is actually showing. Adding a country to the registry adds its file here -- no UI
change, same as the manifest.

Coordinates are rounded to three decimals (~100 m). The country view tops out
around zoom 5, where that is well under one pixel.

Usage:
    python3 build_admin1.py            # every country in the registry
    python3 build_admin1.py ARG GHA    # only these ISO3 codes
"""

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
YIELD_MODEL = os.path.join(HERE, "yield_model")
OUT_DIR = os.path.abspath(os.path.join(HERE, "..", "public", "data", "admin1"))
CACHE = os.path.join(HERE, "cache", "ne_10m_admin_1.geojson")

SOURCE = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
          "/master/geojson/ne_10m_admin_1_states_provinces.geojson")

PRECISION = 3


def fetch_source():
    """Download once into the gitignored cache; reuse after that."""
    if os.path.exists(CACHE) and os.path.getsize(CACHE) > 1_000_000:
        print(f"  캐시 사용: {os.path.relpath(CACHE, HERE)}")
    else:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        print(f"  내려받는 중 (39MB, 최초 1회): {SOURCE}")
        urllib.request.urlretrieve(SOURCE, CACHE)
    with open(CACHE, encoding="utf-8") as fh:
        return json.load(fh)


def round_coords(node):
    """Round in place and drop points that collapse onto their neighbour."""
    if isinstance(node, (int, float)):
        return round(node, PRECISION)
    if not isinstance(node, list):
        return node
    if node and isinstance(node[0], (int, float)):
        return [round(v, PRECISION) for v in node]

    out = [round_coords(child) for child in node]
    # A ring of rounded points often repeats; collapse runs but keep it closed.
    if out and isinstance(out[0], list) and out[0] and isinstance(out[0][0], float):
        deduped = [out[0]]
        for pt in out[1:]:
            if pt != deduped[-1]:
                deduped.append(pt)
        if len(deduped) >= 4 and deduped[0] != deduped[-1]:
            deduped.append(deduped[0])
        return deduped if len(deduped) >= 4 else out
    return out


def registry_isos():
    """ISO3 codes from the country manifests, so this tracks the registry."""
    isos = []
    if not os.path.isdir(YIELD_MODEL):
        return isos
    for folder in sorted(os.listdir(YIELD_MODEL)):
        path = os.path.join(YIELD_MODEL, folder, "model.yaml")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("iso:"):
                    isos.append(line.split(":", 1)[1].strip())
                    break
    return isos


def main():
    wanted = [a.upper() for a in sys.argv[1:]] or registry_isos()
    if not wanted:
        print("대상 국가 없음 — model.yaml 이 있어야 한다", file=sys.stderr)
        return 1
    print(f"대상 {len(wanted)}개국: {', '.join(wanted)}")

    doc = fetch_source()
    by_iso = {}
    for feat in doc.get("features", []):
        props = feat.get("properties") or {}
        iso = str(props.get("adm0_a3") or props.get("iso_a3") or "").upper()
        if iso not in wanted:
            continue
        by_iso.setdefault(iso, []).append({
            "type": "Feature",
            # Only what the map draws or labels. The source carries 80+ fields
            # per feature and they would dominate the file size.
            "properties": {
                "name": props.get("name"),
                "type": props.get("type_en") or props.get("type"),
                "code": props.get("iso_3166_2"),
            },
            "geometry": {
                "type": feat["geometry"]["type"],
                "coordinates": round_coords(feat["geometry"]["coordinates"]),
            },
        })

    os.makedirs(OUT_DIR, exist_ok=True)
    total = 0
    for iso in wanted:
        feats = by_iso.get(iso, [])
        path = os.path.join(OUT_DIR, f"{iso}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats},
                      fh, ensure_ascii=False, separators=(",", ":"))
        size = os.path.getsize(path)
        total += size
        flag = "" if feats else "   ← 원본에 이 국가 행정구역 없음"
        print(f"  {iso}  {len(feats):>3}개  {size/1024:>7.1f} KB{flag}")
    print(f"총 {total/1024:.0f} KB → {os.path.relpath(OUT_DIR, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Draft a country's model.yaml from what its pipeline already produced.

Why this exists
---------------
A country only reaches the screen once scripts/yield_model/{country}/model.yaml
exists. Russia and Vietnam had trained models and published forecast JSON for
weeks and appeared nowhere, because nobody wrote that one file. That is a
coordination failure, not a modelling one, and it will repeat for Canada,
Ukraine, Thailand, MENA and the Central American set unless adding a country is
something a terminal can finish by itself.

So: run this, review the draft, commit. Everything it can read from the
pipeline it fills in; everything it cannot it marks TODO rather than guessing,
because a wrong coordinate or a wrong label is worse than an obvious blank.

  region keys, labels, units   <- public/data/{country}_yield_forecast.json
  coordinates                  <- {country}/regions.py station lists, averaged
  model_status                 <- measured skill in the forecast JSON
  iso, label_ko, sources       <- TODO for a human

Usage:
    python3 scaffold_manifest.py russia
    python3 scaffold_manifest.py russia --force    # overwrite an existing draft
"""

import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DATA = os.path.abspath(os.path.join(HERE, "..", "..", "public", "data"))


def forecast_path(country):
    """The dashboard reads {country}_yield_forecast.json; the US predates that."""
    for name in (f"{country}_yield_forecast.json", "yield_forecast.json"):
        p = os.path.join(PUBLIC_DATA, name)
        if os.path.exists(p):
            return p, name
    return None, None


def station_points(country):
    """Station coordinates per region group, read out of regions.py.

    The file is Python, not data, so this parses literals rather than importing
    -- importing would run collect-time code and need the science dependencies
    installed just to write a config file.
    """
    path = os.path.join(HERE, country, "regions.py")
    if not os.path.exists(path):
        return {}
    src = open(path, encoding="utf-8").read()

    groups = {}
    # Station dicts are written inline: {"name": ..., "lat": ..., "lon": ...}
    for m in re.finditer(r"^([A-Z_][A-Z0-9_]*)\s*=\s*\[", src, re.M):
        var = m.group(1)
        start = m.end() - 1
        depth, i = 0, start
        while i < len(src):
            if src[i] == "[":
                depth += 1
            elif src[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = src[start:i + 1]
        pts = [(float(a), float(b)) for a, b in
               re.findall(r'"lat"\s*:\s*(-?[\d.]+)\s*,\s*"lon"\s*:\s*(-?[\d.]+)', block)]
        if pts:
            groups[var] = pts
    return groups


def centroid(pts):
    return [round(sum(p[1] for p in pts) / len(pts), 2),
            round(sum(p[0] for p in pts) / len(pts), 2)]


def match_group(region_key, groups):
    """Pick the station list whose variable name best matches a region key.

    Deliberately conservative: a single clear winner or nothing. A near-miss
    would place a producing region in the wrong part of the country, and a TODO
    is easier to catch in review than a plausible wrong number.
    """
    tokens = [t for t in re.split(r"[_\W]+", region_key.lower()) if len(t) > 2]
    best, score = None, 0
    for var, pts in groups.items():
        v = var.lower()
        s = sum(1 for t in tokens if t in v)
        if s > score:
            best, score = pts, s
    return centroid(best) if best and score else None


def grade(doc):
    """model_status from measured skill, using the same rule as build_registry."""
    passed = failed = 0

    def walk(n):
        nonlocal passed, failed
        if isinstance(n, dict):
            sk = n.get("skill")
            if isinstance(sk, dict):
                v = sk.get("beats_trend")
                if v is None:
                    for k in ("skill_vs_trend_only", "skill_vs_trend", "weather_skill"):
                        if isinstance(sk.get(k), (int, float)):
                            v = sk[k] > 0
                            break
                if v is True:
                    passed += 1
                elif v is False:
                    failed += 1
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(doc)
    skipped = len(doc.get("skipped") or {})
    total = passed + failed
    ratio = passed / total if total else 0
    if passed and ratio >= 0.7 and not skipped:
        return "validated", None, (passed, failed, skipped)
    if passed:
        note = (f"산지 {passed}곳 검증 통과"
                + (f" / {failed}곳은 추세를 이기지 못함" if failed else "")
                + (f" / {skipped}곳 피처 부족" if skipped else "") + ".")
        return "provisional", note, (passed, failed, skipped)
    return "training", (f"추세를 이긴 산지가 없다 (실패 {failed} · 스킵 {skipped}). 학습 진행 중."), (passed, failed, skipped)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    country = args[0]
    force = "--force" in sys.argv

    out = os.path.join(HERE, country, "model.yaml")
    if os.path.exists(out) and not force:
        print(f"이미 있음: {os.path.relpath(out, HERE)}  (--force 로 덮어쓰기)")
        return 1

    fpath, fname = forecast_path(country)
    if not fpath:
        print(f"예측 JSON 없음: public/data/{country}_yield_forecast.json\n"
              f"  predict.py 를 먼저 돌리세요.", file=sys.stderr)
        return 1

    doc = json.load(open(fpath, encoding="utf-8"))
    regions = doc.get("regions") or {}
    skipped = doc.get("skipped") or {}
    groups = station_points(country)
    status, note, (p, f, s) = grade(doc)

    lines = [
        f"# {country} — 국가 모델 매니페스트 (scaffold_manifest.py 생성)",
        "# 규격: ../MODEL_MANIFEST.md",
        "#",
        "# TODO 로 표시된 항목은 사람이 채워야 합니다. 추정으로 채우면 화면에",
        "# 그럴듯한 오류가 남으므로 비워 둡니다.",
        "",
        f"country: {country}",
        "iso: TODO            # ISO 3166-1 alpha-3",
        "label_ko: TODO",
        f"label_en: TODO       # 월드 GeoJSON 의 properties.name 과 일치해야 함",
        "panel_mode: forecast",
        f"data_file: {fname}",
        f"model_status: {status}",
    ]
    if note:
        lines.append(f'status_note_ko: "{note}"')
    lines += [
        "",
        "view:                # 국가 클릭 시 카메라",
        "  longitude: TODO",
        "  latitude: TODO",
        "  zoom: 3.6",
        "",
        "regions:",
    ]

    todo_coords = []
    for key, r in list(regions.items()) + [(k, {"label": v}) for k, v in skipped.items()]:
        label = str(r.get("label") or key)
        coords = match_group(key, groups)
        lines.append(f"  - key: {key}")
        lines.append(f'    label_ko: "{label}"')
        lines.append(f"    ui_name: {key}")
        if coords:
            lines.append(f"    coordinates: [{coords[0]}, {coords[1]}]")
        else:
            lines.append("    coordinates: [TODO, TODO]   # [경도, 위도]")
            todo_coords.append(key)
        lines.append(f"    crops_region_keys: [{key}]")

    lines += [
        "",
        "sources:",
        "  labels:",
        '    name: "TODO"      # 자국 공식 통계 기관',
        "    url: TODO",
        '    updated: "TODO"   # 데이터 자체의 최신 시점 (YYYY-MM-DD)',
        "  climate:",
        "    name: NASA POWER (daily)",
        "    url: https://power.larc.nasa.gov/",
        f'    updated: "TODO"',
        "",
        "trade_policy:",
        "  restricted: false",
        "  prohibited_crops: []",
        '  note_ko: "TODO"',
        "",
    ]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(lines))

    print(f"→ {os.path.relpath(out, HERE)}")
    print(f"   산지 {len(regions)}개 + 스킵 {len(skipped)}개 · "
          f"skill 통과 {p} / 실패 {f} / 스킵 {s} → model_status: {status}")
    print(f"   좌표 자동: {len(regions) + len(skipped) - len(todo_coords)}개"
          + (f" · 수동 필요: {', '.join(todo_coords)}" if todo_coords else ""))
    print("   TODO 를 채운 뒤 build_registry.py --check 로 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

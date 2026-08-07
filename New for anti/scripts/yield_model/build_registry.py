#!/usr/bin/env python3
"""Build the climate registry the dashboard reads, from each country's model.yaml.

Why this exists
---------------
The country list used to be a literal inside app.js. Two terminals adding two
countries edited the same object, so every parallel country task collided on one
file. Now a country lives entirely in scripts/yield_model/{country}/model.yaml
and this script collects those into one JSON the UI fetches at startup.

Adding a country therefore touches no UI code at all.

Validation is not optional here. A manifest that declares a forecast whose JSON
is missing produces an empty panel on the live site -- which is exactly what
India shipped as until 2026-08-06 -- so that case fails the build instead.

Usage:
    python3 build_registry.py            # write registry, exit non-zero on error
    python3 build_registry.py --check    # validate only, write nothing
"""

import json
import os
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DATA = os.path.abspath(os.path.join(HERE, "..", "..", "public", "data"))
OUT = os.path.join(PUBLIC_DATA, "climate_registry_v1.json")

REQUIRED = ("country", "iso", "label_ko", "label_en", "panel_mode", "data_file",
            "view", "regions", "model_status")
PANEL_MODES = ("forecast", "reference")

# How finished the model is, separate from whether a panel exists.
#
# panel_mode says what the screen shows; model_status says how much the numbers
# on it have earned. China publishes three regions that all score worse than a
# trend-only baseline (-0.57 to -1.60) and India publishes one that scores
# 0.009, which is zero in practice. Both were indistinguishable from Argentina's
# validated set until this field existed.
MODEL_STATUSES = ("validated", "provisional", "training")


def load_yaml(path):
    """Parse model.yaml.

    PyYAML is not a dependency of this repo's CI (the forecast workflows install
    only pandas/numpy/scipy/scikit-learn), and adding one for a config file this
    small is not worth it. The subset parsed here is the subset MODEL_MANIFEST.md
    documents: nested maps, lists of maps, scalars, and inline [a, b] lists.
    """
    try:
        import yaml  # noqa: F401
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except ImportError:
        pass

    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    def scalar(tok):
        tok = tok.strip()
        if not tok:
            return None
        if tok.startswith("[") and tok.endswith("]"):
            inner = tok[1:-1].strip()
            return [scalar(x) for x in inner.split(",")] if inner else []
        if tok[0] in "'\"" and tok[-1] == tok[0]:
            return tok[1:-1]
        low = tok.lower()
        if low in ("true", "false"):
            return low == "true"
        if low in ("null", "~", ""):
            return None
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            pass
        return tok

    def parse(idx, indent):
        """Return (value, next_index) for the block starting at `idx`."""
        # A block is a list if its first content line starts with "- ".
        i = idx
        while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
            i += 1
        if i >= len(lines):
            return None, i
        is_list = lines[i].lstrip().startswith("- ")

        if is_list:
            out = []
            while i < len(lines):
                raw = lines[i]
                if not raw.strip() or raw.lstrip().startswith("#"):
                    i += 1
                    continue
                ind = len(raw) - len(raw.lstrip())
                if ind < indent or not raw.lstrip().startswith("- "):
                    break
                rest = raw.lstrip()[2:].rstrip("\n")
                if ":" in rest and not rest.strip().startswith("["):
                    # Inline first key of a mapping item; re-feed it as a block.
                    item_lines = [" " * (ind + 2) + rest + "\n"]
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j]
                        if nxt.strip() and not nxt.lstrip().startswith("#"):
                            nind = len(nxt) - len(nxt.lstrip())
                            if nind <= ind:
                                break
                        item_lines.append(nxt)
                        j += 1
                    saved, globals()["_LINES"] = lines[:], None
                    out.append(_parse_lines(item_lines))
                    i = j
                else:
                    out.append(scalar(rest))
                    i += 1
            return out, i

        out = {}
        while i < len(lines):
            raw = lines[i]
            if not raw.strip() or raw.lstrip().startswith("#"):
                i += 1
                continue
            ind = len(raw) - len(raw.lstrip())
            if ind < indent:
                break
            line = raw.strip()
            if ":" not in line:
                break
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val and not val.startswith("#"):
                out[key] = scalar(val.split("  #")[0])
                i += 1
            else:
                child, i = parse(i + 1, ind + 1)
                out[key] = child
        return out, i

    def _parse_lines(sub):
        nonlocal lines
        keep = lines
        lines = sub
        try:
            v, _ = parse(0, 0)
            return v
        finally:
            lines = keep

    value, _ = parse(0, 0)
    return value


def validate(m, folder, errors):
    """Collect every problem rather than stopping at the first."""
    tag = folder

    for field in REQUIRED:
        # A reference country publishes no model, so grading one is meaningless.
        if field == "model_status" and m.get("panel_mode") == "reference":
            continue
        if m.get(field) in (None, "", [], {}):
            errors.append(f"{tag}: 필수 항목 누락 — {field}")

    if m.get("country") and m["country"] != folder:
        errors.append(f"{tag}: country='{m['country']}' 가 폴더명과 다름")

    mode = m.get("panel_mode")
    if mode and mode not in PANEL_MODES:
        errors.append(f"{tag}: panel_mode='{mode}' (허용: {', '.join(PANEL_MODES)})")

    status = m.get("model_status")
    if status and status not in MODEL_STATUSES:
        errors.append(f"{tag}: model_status='{status}' (허용: {', '.join(MODEL_STATUSES)})")
    if status in ("provisional", "training") and not m.get("status_note_ko"):
        errors.append(
            f"{tag}: model_status={status} 이면 status_note_ko 가 필요하다 — "
            f"무엇이 안 끝났는지 화면에 적어야 한다."
        )

    data_file = m.get("data_file")
    if mode == "forecast" and data_file:
        path = os.path.join(PUBLIC_DATA, data_file)
        if not os.path.exists(path):
            errors.append(
                f"{tag}: panel_mode=forecast 인데 public/data/{data_file} 이 없음. "
                f"화면에 빈 패널이 뜬다 — 예측을 생성하거나 panel_mode 를 reference 로."
            )
        else:
            status = m.get("model_status")
            ev = forecast_skill(path)
            if ev and ev.get("unknown"):
                errors.append(
                    f"{tag}: skill 형식을 읽지 못한 산지 {ev['unknown']}건. "
                    f"근거 없이 등급을 매기지 않는다 — forecast JSON 의 skill 스키마를 확인할 것."
                )
            elif ev and status:
                total = ev["passed"] + ev["failed"]
                ratio = (ev["passed"] / total) if total else 0
                summary = (f"통과 {ev['passed']} / 실패 {ev['failed']} / 스킵 {ev['skipped']}")
                if status == "validated" and (ev["passed"] == 0 or ratio < 0.7):
                    errors.append(
                        f"{tag}: model_status=validated 인데 근거가 부족하다 ({summary}). "
                        f"검증 통과 비율 {ratio:.0%} — provisional 또는 training 으로."
                    )
                elif status == "provisional" and ev["passed"] == 0:
                    errors.append(
                        f"{tag}: model_status=provisional 인데 추세를 이긴 산지가 없다 ({summary}). "
                        f"training 으로 두고 화면에 학습 중임을 알려야 한다."
                    )
            keys = declared_region_keys(m)
            have = forecast_region_keys(path)
            missing = [k for k in keys if k not in have]
            if have and missing:
                errors.append(
                    f"{tag}: forecast JSON 에 없는 region key — {', '.join(missing)}"
                )

    view = m.get("view") or {}
    for axis, lo, hi in (("longitude", -180, 180), ("latitude", -90, 90), ("zoom", 0, 12)):
        v = view.get(axis)
        if v is None or not isinstance(v, (int, float)) or not (lo <= v <= hi):
            errors.append(f"{tag}: view.{axis} 값이 이상함 — {v!r}")

    for r in m.get("regions") or []:
        key = r.get("key") or "?"
        c = r.get("coordinates")
        if not (isinstance(c, list) and len(c) == 2
                and all(isinstance(x, (int, float)) for x in c)):
            errors.append(f"{tag}/{key}: coordinates 는 [경도, 위도] 여야 함 — {c!r}")
        elif not (-180 <= c[0] <= 180 and -90 <= c[1] <= 90):
            errors.append(f"{tag}/{key}: coordinates 범위 초과 — {c!r}")

    for kind, src in (m.get("sources") or {}).items():
        updated = (src or {}).get("updated")
        if not updated:
            errors.append(f"{tag}: sources.{kind}.updated 없음 — 데이터 신선도를 화면에 못 띄운다")
            continue
        try:
            d = datetime.strptime(str(updated), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{tag}: sources.{kind}.updated 가 YYYY-MM-DD 형식이 아님 — {updated!r}")
            continue
        if d > date.today():
            errors.append(f"{tag}: sources.{kind}.updated 가 미래 — {updated}")


def declared_region_keys(m):
    out = []
    for r in m.get("regions") or []:
        out.extend(r.get("crops_region_keys") or ([r["key"]] if r.get("key") else []))
    return out


def forecast_skill(path):
    """Count regions that beat a trend-only baseline, from the forecast JSON.

    A manifest cannot be trusted to grade itself -- the whole point of the field
    is to stop a half-trained country from looking finished -- so the claim is
    checked against what the pipeline actually measured.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        return None
    passed = failed = 0

    unknown = 0

    def grade(sk):
        """Did this region beat a trend-only baseline?

        Country pipelines report skill under different keys -- India and China
        write `beats_trend`, the US writes `skill_vs_trend_only`, Australia
        writes `skill_vs_trend`, Indonesia nests per target under `yield`.
        Reading only one of them scored three working countries as zero and
        would have labelled them "training" on no evidence at all.
        """
        if not isinstance(sk, dict):
            return None
        if "beats_trend" in sk:
            return bool(sk["beats_trend"])
        for key in ("skill_vs_trend_only", "skill_vs_trend", "weather_skill"):
            if isinstance(sk.get(key), (int, float)):
                return sk[key] > 0
        nested = sk.get("yield")
        if isinstance(nested, dict):
            return grade(nested)
        return None

    def walk(node):
        nonlocal passed, failed, unknown
        if isinstance(node, dict):
            if isinstance(node.get("skill"), dict):
                verdict = grade(node["skill"])
                if verdict is True:
                    passed += 1
                elif verdict is False:
                    failed += 1
                else:
                    unknown += 1
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    skipped = len(doc.get("skipped") or {})
    return {"passed": passed, "failed": failed, "skipped": skipped, "unknown": unknown}


def forecast_region_keys(path):
    """Region keys present in a forecast JSON, across the shapes in use."""
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        return set()
    keys = set()
    for container in ("regions", "skipped"):
        node = doc.get(container)
        if isinstance(node, dict):
            keys |= set(node)
            for v in node.values():
                if isinstance(v, dict) and isinstance(v.get("crops"), dict):
                    keys |= set(v["crops"])
    return keys


def main():
    check_only = "--check" in sys.argv
    countries, errors = {}, []

    for folder in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, folder, "model.yaml")
        if not os.path.isfile(path):
            continue
        try:
            m = load_yaml(path)
        except Exception as exc:
            errors.append(f"{folder}: model.yaml 파싱 실패 — {exc}")
            continue
        if not isinstance(m, dict):
            errors.append(f"{folder}: model.yaml 이 맵이 아님")
            continue
        validate(m, folder, errors)
        countries[m.get("label_en") or folder] = m

    if not countries:
        errors.append("model.yaml 을 가진 국가 폴더가 하나도 없음")

    # A trained country that nobody wrote a manifest for is invisible on the
    # site, and nothing announces it. Russia and Vietnam sat like that for
    # weeks with finished models and published forecasts. Fail the build
    # instead, and say exactly which command fixes it.
    declared = {m.get("data_file") for m in countries.values()}
    for fname in sorted(os.listdir(PUBLIC_DATA)):
        if not fname.endswith("_yield_forecast.json"):
            continue
        if fname in declared:
            continue
        country = fname[: -len("_yield_forecast.json")]
        errors.append(
            f"{country}: 예측 JSON 이 있는데 매니페스트가 없다 (public/data/{fname}). "
            f"화면에 뜨지 않는다 — `python3 scaffold_manifest.py {country}` 로 초안을 만든 뒤 "
            f"TODO 를 채우세요."
        )

    if errors:
        print("레지스트리 검증 실패:\n", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print(f"\n{len(errors)}건. 규격은 MODEL_MANIFEST.md 참고.", file=sys.stderr)
        return 1

    if check_only:
        print(f"✓ {len(countries)}개국 검증 통과")
        return 0

    doc = {
        "schema_version": "climate-registry-v1",
        "generated_at": datetime.now().astimezone().isoformat(),
        "note": "Generated from scripts/yield_model/*/model.yaml. Do not edit by hand.",
        "countries": countries,
    }
    os.makedirs(PUBLIC_DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"✓ {len(countries)}개국 → {os.path.relpath(OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

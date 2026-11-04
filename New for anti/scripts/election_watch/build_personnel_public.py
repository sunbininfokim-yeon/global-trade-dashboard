#!/usr/bin/env python3
"""Publish config/<iso3>_personnel_<date>.json files for the country screens.

Each country's newest file is copied to public/data/personnel/<ISO3>.json and
listed in public/data/personnel/index.json.  Checks before publishing:

* schema is ``<iso3>_personnel_v1`` and ``country`` matches the file name;
* ``as_of`` is present;
* every URL field is http(s).

    python3 build_personnel_public.py          # write
    python3 build_personnel_public.py --check  # fail if the published files differ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
TARGET = ROOT.parents[1] / "public" / "data" / "personnel"
NAME = re.compile(r"^([a-z]{3})_personnel_(\d{4}-\d{2}-\d{2})\.json$")


def _urls(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if (key == "url" or key.endswith("_url")) and isinstance(value, str):
                yield f"{path}.{key}", value
            else:
                yield from _urls(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _urls(value, f"{path}[{i}]")


def validate(iso: str, data: dict) -> list[str]:
    errors = []
    if data.get("schema") != f"{iso}_personnel_v1":
        errors.append(f"{iso}: schema {data.get('schema')!r}")
    if data.get("country") != iso.upper():
        errors.append(f"{iso}: country {data.get('country')!r}")
    if not data.get("as_of"):
        errors.append(f"{iso}: as_of missing")
    for path, url in _urls(data):
        if not url.startswith(("http://", "https://")):
            errors.append(f"{iso}{path}: not an http(s) URL: {url!r}")
    return errors


def latest_sources() -> dict[str, Path]:
    found: dict[str, tuple[str, Path]] = {}
    for path in sorted(CONFIG.glob("*_personnel_*.json")):
        match = NAME.match(path.name)
        if not match:
            continue
        iso, day = match.groups()
        if iso not in found or day > found[iso][0]:
            found[iso] = (day, path)
    return {iso: path for iso, (_, path) in sorted(found.items())}


def render(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def build() -> tuple[dict[str, str], list[str]]:
    outputs: dict[str, str] = {}
    errors: list[str] = []
    index = {"schema": "personnel_index_v1", "countries": {}}
    for iso, path in latest_sources().items():
        data = json.loads(path.read_text(encoding="utf-8"))
        errors += validate(iso, data)
        outputs[f"{iso.upper()}.json"] = render(data)
        index["countries"][iso.upper()] = {"as_of": data.get("as_of"), "source": path.name}
    outputs["index.json"] = render(index)
    return outputs, errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs, errors = build()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.check:
        stale = [name for name, text in outputs.items()
                 if not (TARGET / name).exists() or (TARGET / name).read_text(encoding="utf-8") != text]
        if stale:
            print(f"stale personnel files: {', '.join(stale)}; run build_personnel_public.py", file=sys.stderr)
            return 1
        print(f"ok ({len(outputs) - 1} countries)")
        return 0
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        (TARGET / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(outputs) - 1} countries to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build a daily snapshot of trade flows so the dashboard paints instantly.

Why this exists
---------------
The dashboard used to call /api/comtrade on every visit. The Worker's KV cache
already stopped that from hitting UN Comtrade repeatedly, but the browser still
downloaded ~220KB of raw Comtrade rows per commodity per page entry and
re-aggregated them in JS before a single arc appeared.

Trade data on an annual period changes at most once a year, so paying that cost
per visit buys nothing. This script does the fetch-and-aggregate once a day in
CI and commits the result as a static asset, which Cloudflare serves from its
edge and the browser caches. First paint becomes one small file read.

Drift safety
------------
The M49 code -> country mapping and the HS code per commodity are not restated
here; they are parsed out of ``data.js``. If the dashboard's mapping changes,
this snapshot follows it automatically instead of silently disagreeing.

Output: ``New for anti/public/data/trade_flows_v1.json``, storing compact
``[sourceName, targetName, volumeUsdMillions, netWeightMt]`` tuples. Coordinates,
colours and percentages are all recomputed in the browser from the same tables
it already ships, so nothing is duplicated into the payload.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_JS = REPO_ROOT / "New for anti" / "data.js"
OUT_PATH = REPO_ROOT / "New for anti" / "public" / "data" / "trade_flows_v1.json"

DEFAULT_ORIGIN = "https://global-trade-dashboard.sunbin-info-kim.workers.dev"
PERIOD = "2023"
SCHEMA = "trade_flows_v1"
REQUEST_GAP_SECONDS = 1.5


def _block(source: str, name: str) -> str:
    """Return the text of a top-level ``const <name> = { ... };`` object."""
    start = source.index(f"const {name} = {{")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise ValueError(f"unterminated object literal for {name}")


def _strip_comments(text: str) -> str:
    return re.sub(r"//[^\n]*", "", text)


def load_dashboard_tables() -> tuple[dict[int, str], set[str], dict[str, str]]:
    """Parse M49 codes, known country names and HS codes out of data.js."""
    source = DATA_JS.read_text(encoding="utf-8")

    m49_text = _strip_comments(_block(source, "M49_MAP"))
    m49 = {int(code): name for code, name in re.findall(r"(\d+)\s*:\s*\"([^\"]+)\"", m49_text)}

    countries_text = _strip_comments(_block(source, "COUNTRIES"))
    countries = set(re.findall(r"\"([^\"]+)\"\s*:\s*\[", countries_text))

    config_text = _strip_comments(_block(source, "COMMODITY_API_CONFIG"))
    hs_codes = dict(re.findall(r"(\w+)\s*:\s*\{\s*hsCode:\s*\"(\d+)\"", config_text))

    if not m49 or not countries or not hs_codes:
        raise SystemExit("failed to parse data.js tables (M49_MAP / COUNTRIES / COMMODITY_API_CONFIG)")
    return m49, countries, hs_codes


def fetch_rows(origin: str, hs_code: str, timeout: int) -> list[dict[str, Any]]:
    url = f"{origin}/api/comtrade?hs={hs_code}&period={PERIOD}"
    # Cloudflare's bot protection answers urllib's default User-Agent with 403,
    # so identify as a normal client the way a browser visit would.
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        payload = json.load(res)
    rows = payload.get("data")
    return rows if isinstance(rows, list) else []


def aggregate(rows: list[dict[str, Any]], m49: dict[int, str], countries: set[str]) -> list[list[Any]]:
    """Collapse Comtrade's mirrored export/import rows into one row per route.

    Both partners report the same trade, so a route can arrive twice with
    slightly different values. Keeping the larger of the two mirrors is what
    data.js has always done -- reproduced here so the snapshot and the live
    fallback agree.
    """
    best: dict[tuple[str, str], tuple[float, float]] = {}

    for row in rows:
        source = m49.get(row.get("reporterCode"))
        partner = m49.get(row.get("partnerCode"))
        if not source or not partner or source == partner:
            continue
        if source not in countries or partner not in countries:
            continue

        usd = row.get("primaryValue") or 0
        if usd <= 0:
            continue
        net_weight_kg = row.get("netWgt") or 0

        if row.get("flowCode") == "M":
            source, partner = partner, source

        key = (source, partner)
        if key not in best or best[key][0] < usd:
            best[key] = (usd, net_weight_kg)

    flows = [
        [source, target, round(usd / 1_000_000), round(kg / 1_000_000_000, 2)]
        for (source, target), (usd, kg) in best.items()
    ]
    flows.sort(key=lambda f: f[2], reverse=True)
    return flows


def build(origin: str, only: list[str] | None, timeout: int) -> dict[str, Any]:
    m49, countries, hs_codes = load_dashboard_tables()
    targets = {k: v for k, v in hs_codes.items() if not only or k in only}
    if not targets:
        raise SystemExit(f"no matching commodities; known: {', '.join(sorted(hs_codes))}")

    previous: dict[str, Any] = {}
    if OUT_PATH.exists():
        try:
            previous = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("commodities", {})
        except (json.JSONDecodeError, OSError):
            previous = {}

    commodities: dict[str, Any] = {}
    failures: list[str] = []

    for i, (key, hs_code) in enumerate(sorted(targets.items())):
        if i:
            time.sleep(REQUEST_GAP_SECONDS)
        try:
            flows = aggregate(fetch_rows(origin, hs_code, timeout), m49, countries)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
            print(f"  {key:<13} FAILED ({type(err).__name__}: {err})", file=sys.stderr)
            failures.append(key)
            flows = []

        if not flows:
            # A transient upstream failure must not blank out a commodity that
            # was fine yesterday -- the stale entry is far better than an
            # empty map, and the browser can still fall back to /api.
            kept = previous.get(key)
            if kept and kept.get("flows"):
                commodities[key] = kept
                print(f"  {key:<13} kept previous ({len(kept['flows'])} routes)")
            continue

        commodities[key] = {"hs_code": hs_code, "period": PERIOD, "flows": flows}
        print(f"  {key:<13} {len(flows):>4} routes")

    # Everything failed and there was nothing to fall back on: refuse to write a
    # snapshot the dashboard would read as "no trade exists".
    if not commodities:
        raise SystemExit("all commodities failed; leaving existing snapshot untouched")
    if failures:
        print(f"warning: {len(failures)} commodity fetch(es) failed: {', '.join(failures)}", file=sys.stderr)

    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "period": PERIOD,
        "source": "UN Comtrade (comtradeapi.un.org) via Cloudflare Worker proxy",
        "note": "flows: [sourceName, targetName, volumeUsdMillions, netWeightMt]",
        "commodities": commodities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Worker origin serving /api/comtrade")
    parser.add_argument("--only", nargs="*", help="limit to these commodity keys")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    print(f"[snapshot] building from {args.origin} (period {PERIOD})")
    doc = build(args.origin, args.only, args.timeout)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    total = sum(len(c["flows"]) for c in doc["commodities"].values())
    size_kb = args.out.stat().st_size / 1024
    print(f"[snapshot] wrote {args.out.name}: {len(doc['commodities'])} commodities, {total} routes, {size_kb:.0f}KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

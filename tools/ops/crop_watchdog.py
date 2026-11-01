#!/usr/bin/env python3
"""
Crop-monitor freshness check: is every country forecast still being refreshed,
and is the weather inside it still arriving?

Usage: python3 tools/ops/crop_watchdog.py [--today YYYY-MM-DD]

The commit-time watchdog (data_freshness_watchdog.yml) only notices a job that
stopped committing. The crop pipelines fail more quietly: the job keeps
running and committing while an upstream feed has stopped, so the forecast is
regenerated every week on the same old weather. Or a region drops out of the
payload and the map just shows one fewer dot. This reads the published JSON
itself, for every country in scripts/yield_model/*/model.yaml with
`panel_mode: forecast`:

  stale forecast  generated_at older than the country's cadence + grace
  stale weather   the newest weather_through more than WEATHER_LAG_DAYS
                  behind generated_at (the run happened, the feed did not)
  dropped region  a region listed in the payload's `skipped` (warning only:
                  some are seasonal, e.g. a crop between harvest and sowing)
  future weather  weather_through after generated_at, i.e. forecast days
                  counted as observed (warning)

Errors exit 1 so the scheduled run fails and GitHub emails the owner; warnings
are printed and written to the job summary.
"""

import argparse
import glob
import json
import os
import sys
from datetime import date, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP = os.path.join(ROOT, "New for anti")
MODELS = os.path.join(APP, "scripts", "yield_model")
DATA = os.path.join(APP, "public", "data")

# Weekly unless listed. Grace covers one missed schedule plus a slow run.
DEFAULT_MAX_AGE_DAYS = 9
MAX_AGE_DAYS = {
    "canada": 35,          # canada_yield_forecast.yml runs monthly
}
# POWER lags real time by 2-7 days and the forecast runs weekly.
WEATHER_LAG_DAYS = 16
WEATHER_KEYS = ("weather_through",)


def load_yaml(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect(obj, keys, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and len(v) >= 10:
                try:
                    out.append(date.fromisoformat(v[:10]))
                except ValueError:
                    pass
            collect(v, keys, out)
    elif isinstance(obj, list):
        for v in obj:
            collect(v, keys, out)
    return out


def check(today):
    errors, warnings = [], []
    for path in sorted(glob.glob(os.path.join(MODELS, "*", "model.yaml"))):
        m = load_yaml(path)
        country = m.get("country") or os.path.basename(os.path.dirname(path))
        if m.get("panel_mode") != "forecast" or not m.get("data_file"):
            continue
        tag = f"{country} ({m['data_file']})"
        data_path = os.path.join(DATA, m["data_file"])
        try:
            with open(data_path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            errors.append(f"{tag}: cannot read forecast ({e})")
            continue

        try:
            generated = datetime.fromisoformat(payload["generated_at"]).date()
        except (KeyError, TypeError, ValueError):
            errors.append(f"{tag}: no usable generated_at")
            continue
        age = (today - generated).days
        limit = MAX_AGE_DAYS.get(country, DEFAULT_MAX_AGE_DAYS)
        if age > limit:
            errors.append(f"{tag}: forecast generated {generated} is {age} days old "
                          f"(limit {limit})")

        through = collect(payload.get("regions", {}), WEATHER_KEYS, [])
        if through:
            newest = max(through)
            lag = (generated - newest).days
            if lag > WEATHER_LAG_DAYS:
                errors.append(f"{tag}: weather stops at {newest}, {lag} days before the "
                              f"run on {generated} -- the feed has stopped")
            elif newest > generated:
                warnings.append(f"{tag}: weather_through {newest} is after the run on "
                                f"{generated} (forecast days reported as observed)")

        skipped = payload.get("skipped")
        if isinstance(skipped, dict) and skipped:
            for key, why in skipped.items():
                warnings.append(f"{tag}: region {key} not published -- {why}")
        elif isinstance(skipped, list) and skipped:
            warnings.append(f"{tag}: regions not published -- {', '.join(map(str, skipped))}")
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    errors, warnings = check(args.today)
    lines = [f"::error::{e}" for e in errors] + [f"::warning::{w}" for w in warnings]
    print("\n".join(lines) if lines else "All crop forecasts are fresh.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Crop forecasts\n\n")
            f.write("\n".join(f"- ❌ {e}" for e in errors) + "\n" if errors else "")
            f.write("\n".join(f"- ⚠️ {w}" for w in warnings) + "\n" if warnings else "")
            if not lines:
                f.write("All fresh.\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

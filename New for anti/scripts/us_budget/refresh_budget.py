"""Collect and validate the US budget into one atomic annual/monthly bundle.

Run from any directory: python refresh_budget.py --output-dir /tmp/budget
The workflow stages these files before publishing. No secrets or DB are used.
"""
from datetime import datetime, timezone
from decimal import Decimal
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import annual
import treasury

DATA = Path(__file__).resolve().parents[2] / "public/data/us_budget"
BUNDLE = "budget_live_v1.json"
STATUS = "collection_status_v1.json"


def encode(data):
    def convert(value):
        if isinstance(value, Decimal):
            return float(value)
        raise TypeError(f"Unsupported JSON type {type(value)}")
    return (json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False, default=convert) + "\n").encode()


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            name = handle.name
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def compatible_mts(feed):
    ytd = dict(feed["fiscal_ytd"])
    ytd["complete"] = ytd.pop("complete_fy")
    return dict(schema_version=1, source="Treasury MTS Tables 1, 3, 6", unit="USD",
                mts_record_date=feed["publication_date"], months=feed["monthly"], fytd=ytd,
                checked_at=feed["checked_at"], sources=feed["sources"],
                note="record_date is the accounting period end, not the day the report was published.")


def assemble(get=treasury.request):
    # A single run must not observe two versions of the same source response.
    cache = {}
    def cached(url):
        if url not in cache:
            cache[url] = get(url)
        return cache[url]
    feed = treasury.collect(cached)
    end = feed["publication_date"]
    year = int(end[:4]) - (int(end[5:7]) < 9)
    completed = feed if end[5:] == "09-30" else treasury.collect(cached, f"{year}-09-30")
    manifest = annual.discover(cached)
    tables, sources = annual.load(manifest, cached)
    rebuilt = annual.build(tables, manifest, sources, completed, feed["monthly"])
    return dict(schema_version=1, annual=rebuilt, live=compatible_mts(feed))


def revisions(previous, current):
    """Keep a bounded audit of real amount changes; do not discard revisions."""
    if not previous:
        return []
    before = {r["month"]: r for r in previous["live"]["months"]}
    out = []
    for row in current["live"]["months"]:
        old = before.get(row["month"])
        if old:
            for key in ("receipts", "outlays", "deficit"):
                if abs(Decimal(str(row[key])) - Decimal(str(old[key]))) > Decimal("0.05"):
                    out.append(dict(month=row["month"], metric=key, before=old[key], after=row[key],
                                    old_vintage=old["vintage"], new_vintage=row["vintage"]))
    return out


def run(output, published=DATA, get=treasury.request, now=None):
    now = now or datetime.now(timezone.utc).isoformat()
    previous = read(published / BUNDLE)
    previous_status = read(published / STATUS) or {}
    try:
        result = assemble(get)
        if previous:
            if result["live"]["mts_record_date"] < previous["live"]["mts_record_date"]:
                raise ValueError("Treasury accounting period regressed")
            if (result["annual"]["proposal_fy"], result["annual"]["publication"]) < (previous["annual"]["proposal_fy"], previous["annual"]["publication"]):
                raise ValueError("OMB publication regressed")
        delta = revisions(previous, result)
        result["recent_revisions"] = (previous.get("recent_revisions", []) if previous else [])[-100:]
        if delta:
            result["recent_revisions"] = (result["recent_revisions"] + [dict(checked_at=now, changes=delta)])[-100:]
        result["dataset_id"] = hashlib.sha256(encode(result)).hexdigest()
        result["checked_at"] = now
        status = dict(schema_version=1, state="ok", last_checked_at=now, last_success_at=now,
                      dataset_id=result["dataset_id"], mts_record_date=result["live"]["mts_record_date"],
                      omb_publication=result["annual"]["publication"], revision_count=len(delta))
        # Both datasets and their provenance are in one validated atomic file.
        atomic(output / BUNDLE, encode(result))
        atomic(output / STATUS, encode(status))
        print(f"Validated MTS {status['mts_record_date']}, OMB FY{result['annual']['proposal_fy']}, {len(delta)} amount revisions")
        return 0
    except Exception as err:
        # Publish an error receipt, never a replacement monetary dataset.
        status = dict(previous_status, schema_version=1, state="failed", last_checked_at=now,
                      last_success_at=previous_status.get("last_success_at"), error_code="budget_collection_failed",
                      message="공식 자료 수집 또는 기간·금액 검증에 실패했습니다. 마지막 정상 자료를 유지합니다.")
        atomic(output / STATUS, encode(status))
        print(f"::error::Budget collection failed; previous monetary data preserved: {err}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--published-dir", type=Path, default=DATA)
    args = parser.parse_args()
    return run(args.output_dir, args.published_dir)


if __name__ == "__main__":
    sys.exit(main())

"""Run after the monthly BLS history refresh, without external inputs or movers."""
import argparse
import json
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

from macro_monitor.cpi.internal_watch import assess
from macro_monitor.cpi.monthly import shift

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT.parents[1] / "public" / "data" / "us_cpi_api_history_v1.json"
MAP = ROOT / "config" / "cpi_structure.map.json"
SCHEMA = "us-cpi-internal-watch-v1"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_report(history, mapping, month=None):
    if (history.get("schema_version") != "us-cpi-api-history-v1"
            or history.get("source", {}).get("data_status") != "official_observed"):
        raise ValueError("expected official BLS CPI history")
    headline = [r for r in history["series"] if r["id"] == "all_items" and r["series_id"] == "CUSR0000SA0"]
    if len(headline) != 1:
        raise ValueError("BLS seasonally adjusted headline missing or ambiguous")
    available = {shift(o["date"], 0) for o in headline[0]["observations"]
                 if o["data_status"] == "observed" and o["index"] is not None
                 and isfinite(o["index"]) and o["index"] > 0}
    if not available or (month is not None and month not in available):
        raise ValueError("no observed headline CPI for requested month")
    month = month or max(available)
    return {"schema_version": SCHEMA, "source": "BLS",
            "source_url": "https://www.bls.gov/cpi/",
            **assess(history, mapping, month)}


def publish(report, out):
    if out.exists():
        old = read_json(out)
        if old.get("schema_version") != SCHEMA:
            raise ValueError("refusing to replace another JSON contract")
        if old["reference_period"] > report["reference_period"]:
            raise ValueError("refusing to replace a newer CPI reference month")
        if old == report:
            return False
    with NamedTemporaryFile("w", dir=out.parent, encoding="utf-8", delete=False) as tmp:
        path = Path(tmp.name)
        try:
            json.dump(report, tmp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            tmp.write("\n")
            tmp.close()
            path.replace(out)
        finally:
            path.unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", help="inspect an earlier reference month (latest available vintage)")
    parser.add_argument("--history", type=Path, default=HISTORY, help="normalized BLS history input")
    parser.add_argument("--out", type=Path, help="atomically write a current release snapshot")
    args = parser.parse_args()
    if args.month and args.out:
        parser.error("--month is for inspection; publishing requires the latest BLS release")
    try:
        report = make_report(read_json(args.history), read_json(MAP), args.month)
        if args.out:
            changed = publish(report, args.out)
            print(f"{report['reference_period']}: {'updated' if changed else 'unchanged'}")
        else:
            print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"CPI internal watch failed: {exc}\n")


if __name__ == "__main__":
    main()

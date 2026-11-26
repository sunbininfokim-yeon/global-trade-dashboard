"""Run after the monthly BLS history refresh, without external inputs or movers."""
import argparse
import json

from build_us_cpi_forward_validation import CONFIG, PUBLIC, read_json
from macro_monitor.cpi.internal_watch import assess
from macro_monitor.cpi.forward_validation import shift


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", help="inspect an earlier reference month (latest available vintage)")
    args = parser.parse_args()
    history = read_json(PUBLIC / "us_cpi_api_history_v1.json")
    headline = next(row for row in history["series"] if row["id"] == "all_items")
    available = {o["date"] for o in headline["observations"] if o["data_status"] == "observed"}
    month = shift(args.month or max(available), 0)
    if month not in available:
        parser.error("no observed headline CPI for requested month")
    print(json.dumps(assess(history, read_json(CONFIG / "cpi_structure.map.json"), month),
                     ensure_ascii=False, allow_nan=False))

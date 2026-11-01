"""Apply a staged, validated budget or just its failure receipt. No git/network."""
import argparse
import hashlib
from pathlib import Path

from refresh_budget import BUNDLE, STATUS, DATA, atomic, encode, read


def publish(staged, output, outcome):
    if outcome not in ("success", "failure"):
        raise ValueError("Unknown collection outcome")
    status = read(staged / STATUS)
    if not status or status.get("schema_version") != 1:
        raise ValueError("Missing collection receipt")
    old_status = read(output / STATUS) or {}
    if status.get("last_checked_at", "") < old_status.get("last_checked_at", ""):
        raise ValueError("Refusing an older collection receipt")
    previous = read(output / BUNDLE)
    if outcome == "failure":
        if status.get("state") != "failed":
            raise ValueError("A failure run must carry a failure receipt")
        # Retain the successful dataset and its own success time.
        status["dataset_id"] = previous.get("dataset_id") if previous else None
        status["last_success_at"] = old_status.get("last_success_at")
        atomic(output / STATUS, encode(status))
        return
    bundle = read(staged / BUNDLE)
    if status.get("state") != "ok" or not bundle or status.get("dataset_id") != bundle.get("dataset_id"):
        raise ValueError("Successful receipt does not match the dataset")
    payload = {k: v for k, v in bundle.items() if k not in ("dataset_id", "checked_at")}
    if hashlib.sha256(encode(payload)).hexdigest() != bundle["dataset_id"]:
        raise ValueError("Staged dataset hash mismatch")
    if previous:
        if bundle["live"]["mts_record_date"] < previous["live"]["mts_record_date"]:
            raise ValueError("Staged MTS period is older than published data")
        if (bundle["annual"]["proposal_fy"], bundle["annual"]["publication"]) < (previous["annual"]["proposal_fy"], previous["annual"]["publication"]):
            raise ValueError("Staged OMB publication is older than published data")
    atomic(output / BUNDLE, encode(bundle))
    atomic(output / STATUS, encode(status))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DATA)
    parser.add_argument("--outcome", choices=["success", "failure"], required=True)
    args = parser.parse_args()
    publish(args.staged_dir, args.output_dir, args.outcome)

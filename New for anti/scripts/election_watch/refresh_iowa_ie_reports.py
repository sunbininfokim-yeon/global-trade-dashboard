#!/usr/bin/env python3
"""Refresh a bounded Iowa public IE report index, preserving last valid on failure."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
from election_watch.iowa_ie_reports import collect
from election_watch.polls import atomic

ROOT = Path(__file__).resolve().parent


def refresh(public, checked_at, collector=collect):
    target = public/'usa_governor_ie_report_indexes/2026/IA.json'
    health = public/'usa_governor_ie_report_index_status/2026/IA.json'
    try:
        payload = collector(checked_at)
        atomic(target, payload)
        atomic(health, {'state': 'IA', 'checked_at': checked_at, 'status': 'ok',
                       'cycle_discovery_complete': payload['cycle_discovery_complete']})
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        atomic(health, {'state': 'IA', 'checked_at': checked_at,
                       'status': 'error_last_valid_preserved', 'error_type': type(error).__name__})
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent/'public/data')
    args = parser.parse_args()
    return refresh(args.public, datetime.now(timezone.utc).isoformat())


if __name__ == '__main__':
    raise SystemExit(main())

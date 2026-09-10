#!/usr/bin/env python3
"""Scheduled backend entry point; collect sources, preserve failures, build map assets."""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from build_superpac import PUBLIC, ROOT, atomic_json
from build_superpac_map import build
from election_watch.superpac import now
from election_watch.superpac_schedule import collection_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cadence', choices=['daily', 'weekly'], default='daily')
    parser.add_argument('--cycle', type=int, help='Explicit historical cycle; otherwise date-driven')
    parser.add_argument('--force', action='store_true', help='Ignore weekday gate for a manual run')
    parser.add_argument('--plan', action='store_true', help='Print the plan without keys or network requests')
    parser.add_argument('--date', type=date.fromisoformat, help='Planning tests only; requires --plan')
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    if args.date and not args.plan:
        parser.error('--date is only valid with --plan')
    day = args.date or datetime.now(timezone.utc).date()
    cycles = collection_plan(day, args.cadence, args.force, args.cycle)
    if args.plan or not cycles:
        print(json.dumps({'date': str(day), 'cadence': args.cadence, 'cycles': cycles, 'due': bool(cycles)}))
        return 0
    started = now()
    results = []
    for cycle in cycles:
        for name, script in [('federal', 'build_superpac.py'), ('WA_governor', 'build_governor_finance.py'), ('CA_governor', 'build_governor_finance.py')]:
            # The key is inherited from the runner environment, never written to arguments or outputs.
            command = [sys.executable, str(ROOT / script), '--cycle', str(cycle), '--public', str(args.public)]
            if name.endswith('_governor'):
                command.extend(['--state', name[:2]])
            try:
                process = subprocess.run(command, timeout=4 * 3600, check=False)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
            results.append({'cycle': cycle, 'source': name, 'status': 'success' if code == 0 else 'failed', 'exit_code': code})
    # Source failures leave their last good files intact. Healthy sources still advance.
    try:
        build(args.public, cadence=args.cadence)
        map_status = 'success'
    except (ValueError, OSError, KeyError, AssertionError, TypeError):
        map_status = 'failed'
    failed = map_status == 'failed' or any(r['status'] == 'failed' for r in results)
    atomic_json(args.public / 'usa_election_finance_refresh_status_v1.json', {
        'schema': 'usa_election_finance_refresh_status_v1', 'started_at': started, 'finished_at': now(),
        'status': 'failed' if failed else 'success', 'cadence': args.cadence,
        'expected_interval_hours': 24 if args.cadence == 'daily' else 168,
        'stale_after_hours': 72 if args.cadence == 'daily' else 240,
        'sources': results, 'map_build': map_status})
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())

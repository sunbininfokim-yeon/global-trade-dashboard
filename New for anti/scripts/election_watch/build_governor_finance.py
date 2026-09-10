#!/usr/bin/env python3
"""Collect implemented state sources without requiring a federal API key."""
import argparse
import json
from pathlib import Path
from build_superpac import PUBLIC, ROOT, atomic_json
from election_watch.governor_wa import collect as collect_wa
from election_watch.governor_ca import collect as collect_ca
from election_watch.superpac import SourceError
from election_watch.superpac_schedule import reporting_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=reporting_cycle())
    parser.add_argument('--state', choices=['WA','CA'], default='WA')
    parser.add_argument('--ca-local-tables', type=Path, help='Reviewed local official tables; offline verification only')
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    if args.cycle < 2010 or args.cycle % 2:
        parser.error('even reporting cycle >= 2010 required')
    try:
        roster_path = ROOT / 'config/governor_candidates' / str(args.cycle) / 'CA.json'
        roster = json.loads(roster_path.read_text())['candidates'] if roster_path.exists() else []
        payload = collect_wa(args.cycle) if args.state == 'WA' else collect_ca(args.cycle, roster, args.ca_local_tables)
        atomic_json(args.public / 'usa_governor_finance' / str(args.cycle) / (args.state + '.json'), payload)
        print(json.dumps({'cycle': args.cycle, 'state': args.state, 'quality': payload['quality']}))
    except SourceError as exc:
        print(str(exc))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect implemented state sources without requiring a federal API key."""
import argparse
import json
from pathlib import Path
from build_superpac import PUBLIC, atomic_json
from election_watch.governor_wa import collect
from election_watch.superpac import SourceError
from election_watch.superpac_schedule import reporting_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=reporting_cycle())
    parser.add_argument('--public', type=Path, default=PUBLIC)
    args = parser.parse_args()
    if args.cycle < 2010 or args.cycle % 2:
        parser.error('even reporting cycle >= 2010 required')
    try:
        payload = collect(args.cycle)
        atomic_json(args.public / 'usa_governor_finance' / str(args.cycle) / 'WA.json', payload)
        print(json.dumps({'cycle': args.cycle, 'state': 'WA', 'quality': payload['quality']}))
    except SourceError as exc:
        print(str(exc))
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

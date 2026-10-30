#!/usr/bin/env python3
"""Build reviewed polling data. Does not fetch, estimate, or edit election UI."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, build

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'config/usa_polls/2026.json')
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent / 'public/data')
    parser.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--monitor-report', type=Path)
    args = parser.parse_args()
    result = build(read(args.input), args.public, args.as_of,
                   read(args.monitor_report) if args.monitor_report else None)
    print({k: result[k] for k in ('cycle', 'race_count', 'covered_race_count',
                                'observation_count', 'independent_survey_count')})

if __name__ == '__main__':
    main()

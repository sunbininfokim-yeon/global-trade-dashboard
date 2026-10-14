#!/usr/bin/env python3
"""Publish the 50-state candidate display audit from existing data."""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from election_watch.candidate_coverage import candidate_coverage
from election_watch.polls import atomic, read

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parent.parent / 'public/data'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board', type=Path, default=PUBLIC / 'elections_board_v1.json')
    p.add_argument('--polls', type=Path, default=PUBLIC / 'usa_election_live_polls_v1.json')
    p.add_argument('--catalog', type=Path, default=ROOT / 'config/usa_polls/targets_2026.json')
    p.add_argument('--output', type=Path, default=PUBLIC / 'usa_candidate_coverage_v1.json')
    p.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    args = p.parse_args()
    audit = candidate_coverage(read(args.board), read(args.polls), read(args.catalog), args.as_of)
    atomic(args.output, audit)
    print(audit['totals'])

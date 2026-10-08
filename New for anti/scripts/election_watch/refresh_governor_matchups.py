#!/usr/bin/env python3
"""Refresh governor identities from the reviewed NGA general-candidate sections."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.governor_matchups import collect, apply_ballot_reviews

ROOT = Path(__file__).resolve().parent
ROSTERS = ROOT / 'config/governor_matchups/2026.json'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ratings', type=Path, default=ROOT.parent.parent/'public/data/usa_election_ratings_review_v1.json')
    p.add_argument('--output', type=Path, default=ROSTERS)
    p.add_argument('--ballot-reviews', type=Path, default=ROOT/'config/governor_matchups/2026_ballot_reviews.json')
    args = p.parse_args()
    ratings = read(args.ratings)
    cycle = ratings['cycle']
    registries = {f.stem: read(f)['candidates'] for f in (ROOT/'config/governor_candidates'/str(cycle)).glob('*.json')}
    snapshot = collect(cycle, [r['state'] for r in ratings['offices']['governor']['races']],
                       datetime.now(timezone.utc).date().isoformat(), registries)
    if args.ballot_reviews.exists():
        snapshot = apply_ballot_reviews(snapshot, read(args.ballot_reviews), snapshot['reviewed_on'])
    atomic(args.output, snapshot)
    print(snapshot['coverage'])


if __name__ == '__main__':
    main()

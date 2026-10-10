#!/usr/bin/env python3
"""Review and publish a complete nationwide display candidate snapshot.

No API key. The explicit review flag is separate from polling approval. Failed
sources or an incomplete universe leave the last valid snapshot untouched.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

from election_watch.house_rosters import merge_national_house, attach_reviewed_poll_aliases, merge_official_house_reviews, attach_verified_finance_ids, apply_reviewed_aliases
from election_watch.federal_matchups import merge_ballot_reviews
from election_watch.polls import atomic, read

ROOT = Path(__file__).resolve().parent


def refresh(snapshot_path, catalog_path, ballot_reviews_path, output, reviewed_on, source_dir=None, polls_path=None, agency_path=None, finance_dir=None, aliases_path=None):
    catalog = read(catalog_path)
    def document(state):
        if source_dir is not None:
            return state, (Path(source_dir) / f'{state}.html').read_text(encoding='utf-8')
        req = urllib.request.Request(f'https://www.thegreenpapers.com/G26/{state}',
            headers={'User-Agent': 'US election public candidate research'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return state, response.read().decode('utf-8')
    with ThreadPoolExecutor(max_workers=5) as executor:
        documents = dict(executor.map(document, sorted(catalog['states'])))
    # Reviewed agency rosters take priority over secondary reports.
    baseline = merge_ballot_reviews(read(snapshot_path), read(ballot_reviews_path), reviewed_on)
    result = merge_national_house(baseline, catalog, documents, reviewed_on)
    if agency_path is not None:
        result = merge_official_house_reviews(result, read(agency_path), reviewed_on)
    if aliases_path is not None:
        result = apply_reviewed_aliases(result, read(aliases_path), reviewed_on)
    if polls_path is not None:
        result = attach_reviewed_poll_aliases(result, read(polls_path))
    if finance_dir is not None:
        result = attach_verified_finance_ids(result, (read(path) for path in Path(finance_dir).glob('*-house-*.json')))
    atomic(output, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'config/federal_matchups/2026.json')
    parser.add_argument('--catalog', type=Path, default=ROOT / 'config/usa_polls/targets_2026.json')
    parser.add_argument('--ballot-reviews', type=Path, default=ROOT / 'config/usa_polls/ballot_reviews_2026.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'config/federal_matchups/2026.json')
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--polls', type=Path, default=ROOT.parent.parent / 'public/data/usa_election_live_polls_v1.json')
    parser.add_argument('--agency-reviews', type=Path, default=ROOT / 'config/federal_matchups/2026_official_house_reviews.json')
    parser.add_argument('--finance-dir', type=Path, default=ROOT.parent.parent / 'public/data/usa_election_finance/2026/races')
    parser.add_argument('--identity-aliases', type=Path, default=ROOT / 'config/federal_matchups/2026_identity_aliases.json')
    parser.add_argument('--reviewed-on', default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument('--review-public-sources', action='store_true', required=True,
                        help='Explicit display-roster review, never polling admission approval')
    args = parser.parse_args()
    snapshot = refresh(args.snapshot, args.catalog, args.ballot_reviews, args.output, args.reviewed_on, args.source_dir, args.polls,
                       args.agency_reviews if args.agency_reviews.exists() else None, args.finance_dir,
                       args.identity_aliases if args.identity_aliases.exists() else None)
    print(f"Reviewed {sum(r['office'] == 'house' for r in snapshot['races'].values())} House races across 50 states")

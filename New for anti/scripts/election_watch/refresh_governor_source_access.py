#!/usr/bin/env python3
"""Retry reviewed public governor portals without modifying financial observations."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read
from election_watch.governor_source_access import publish_access

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', choices=['GA','MI','OH','IA','WI','AZ','NV','CT','NM'], required=True)
    parser.add_argument('--cycle', type=int, default=2026)
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent/'public/data')
    args = parser.parse_args()
    checked = datetime.now(timezone.utc).isoformat()
    path = args.public/'usa_governor_source_access'/str(args.cycle)/f'{args.state}.json'
    try:
        directory = read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')
        previous = read(path) if path.exists() else None
        payload = publish_access(path, args.state, args.cycle, directory['states'][args.state], checked, previous)
        print({'state': args.state, 'status': payload['status'], 'checked_at': checked,
               'candidate_amounts_available': False})
        return int(payload['status'] != 'public_endpoint_reachable_mapping_required')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print({'state': args.state, 'status': 'error_last_access_receipt_preserved',
               'error_type': type(error).__name__})
        return 1


if __name__ == '__main__': raise SystemExit(main())

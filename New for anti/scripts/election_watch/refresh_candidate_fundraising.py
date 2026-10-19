#!/usr/bin/env python3
"""Refresh FEC campaign summaries without an API key; preserve last good data."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from election_watch.polls import read, atomic
from election_watch.candidate_fundraising import collect, preserve_previous

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=2026)
    parser.add_argument('--public', type=Path, default=ROOT.parents[1]/'public/data')
    args = parser.parse_args(); stamp = datetime.now(timezone.utc).isoformat()
    folder = args.public/'usa_election_finance'/str(args.cycle)
    output = folder/'candidate_fundraising_v1.json'
    try:
        doc = collect(args.cycle, stamp[:10], stamp, read(ROOT/'config/usa_polls/targets_2026.json'))
        # Never replace a newer successful capture with an older replay.
        if output.exists():
            doc = preserve_previous(doc, read(output))
        atomic(output, doc)
        health = {'status': 'success', 'captured_at': stamp, 'candidate_count': doc['candidate_count']}
        code = 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        health = {'status': 'failed_last_good_preserved', 'attempted_at': stamp,
                  'error_type': type(exc).__name__, 'last_good_exists': output.exists()}
        code = 1
    atomic(folder/'candidate_fundraising_status_v1.json', health)
    print(health)
    return code


if __name__ == '__main__':
    raise SystemExit(main())

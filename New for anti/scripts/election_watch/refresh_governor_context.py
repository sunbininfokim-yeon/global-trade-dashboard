#!/usr/bin/env python3
"""Recheck the exact governor context; changed eligibility waits for review."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from election_watch.polls import read, atomic, require
from election_watch.governor_context import parse_nga

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=2026)
    parser.add_argument('--public', type=Path, default=ROOT.parents[1]/'public/data')
    args = parser.parse_args(); stamp = datetime.now(timezone.utc).isoformat()
    output = args.public/'usa_election_finance'/str(args.cycle)/'governor_context_inputs_v1.json'
    try:
        inputs = read(ROOT/'config/usa_polls/governor_context_2026.json')
        require(args.cycle == inputs['cycle'], 'unsupported governor context cycle')
        url = inputs['source']['url']
        with urlopen(Request(url, headers={'User-Agent': 'ElectionEvidenceReview/1.0'}), timeout=30) as response:
            require(response.url == url, 'unexpected NGA context redirect')
            body = response.read(3_000_001); require(len(body) <= 3_000_000, 'oversized NGA context')
        result = parse_nga(body.decode('utf-8'), inputs, read(ROOT/'config/usa_polls/targets_2026.json'), stamp)
        atomic(output, result)
        health = {'status': 'success', 'captured_at': stamp, 'reviewed_on': inputs['reviewed_on']}; code = 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        health = {'status': 'failed_last_good_preserved', 'attempted_at': stamp,
                  'error_type': type(exc).__name__, 'last_good_exists': output.exists()}; code = 1
    atomic(output.with_name('governor_context_status_v1.json'), health)
    print(health)
    return code


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build state read models from reviewed inputs and the published national polls."""
import argparse
from pathlib import Path
import subprocess
import sys
from election_watch.polls import read
from election_watch.state_inputs import packets
from publish_federal_matchups import publish

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent/'public/data')
    args = parser.parse_args()
    board = read(args.public/'usa_election_live_polls_v1.json')
    for packet in packets():
        state = packet['state']
        day = next(r.get('as_of', board['as_of']) for r in board['races'].values() if r['state'] == state)
        publish(ROOT/'config/federal_matchups/2026.json', args.public/'elections_board_v1.json', day,
                ROOT/'config/usa_polls/ballot_reviews_2026.json', state)
        subprocess.run([sys.executable, str(ROOT/'refresh_state_evidence.py'), '--state', state,
                        '--as-of', day, '--public', str(args.public), '--polls',
                        str(args.public/'usa_election_live_polls_v1.json')], check=True)


if __name__ == '__main__': main()

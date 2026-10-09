#!/usr/bin/env python3
"""CI-only bounded push retry: regenerate on latest main, never merge generated JSON."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PUBLIC = 'New for anti/public/data/'


def git(*args, check=True):
    return subprocess.run(['git', *args], check=check)


def stage_paths():
    # State snapshots are immutable; the regenerated index points to the new
    # content. Other finance, workflow and source files cannot enter this commit.
    from election_watch.state_inputs import packets
    paths = [PUBLIC+f for f in ('usa_election_live_polls_v1.json',
        'usa_election_live_polls_status_v1.json', 'usa_election_poll_history_2026.json',
        'usa_midterms_forecast_v1.json', 'elections_board_v1.json',
        'usa_election_state_evidence_index_v1.json')]
    index = __import__('json').loads(Path(PUBLIC+'usa_election_state_evidence_index_v1.json').read_text())
    paths += [PUBLIC+index['states'][p['state']]['data_file'] for p in packets()]
    return paths


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--checkpoint', type=Path, required=True)
    args = p.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Publication is restricted to the main Actions runner')
    for attempt in range(3):
        if attempt:
            git('fetch', 'origin', 'main')
            # This is the disposable Actions checkout; the collected inputs and
            # failed publication remain in the uploaded checkpoint/artifact.
            git('reset', '--hard', 'origin/main')
            subprocess.run([sys.executable, str(ROOT/'publish_packet_projections.py')], check=True)
            subprocess.run([sys.executable, str(ROOT/'refresh_live_polls.py'), '--retry-capture', str(args.checkpoint)], check=True)
        subprocess.run([sys.executable, str(ROOT/'publish_packet_projections.py')], check=True)
        git('add', '--', *stage_paths())
        if git('diff', '--cached', '--quiet', check=False).returncode == 0: return
        git('commit', '-m', 'chore: publish US election inputs and generated read models')
        if git('push', 'origin', 'HEAD:main', check=False).returncode == 0: return
    raise SystemExit('Main advanced repeatedly; original collection artifact retained for retry')


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""State input PRs must not also write shared catalogs or generated boards."""
import argparse
import subprocess
from election_watch.state_inputs import CATALOGS, CONFIG, packets
from election_watch.polls import read

PREFIX = 'New for anti/'
PACKETS = PREFIX + 'scripts/election_watch/config/state_evidence/2026/'
SHARED = {PREFIX + 'scripts/election_watch/config/' + f for f in CATALOGS}
SHARED.update(PREFIX + 'public/data/' + f for f in (
    'elections_board_v1.json', 'usa_election_live_polls_v1.json', 'usa_election_live_polls_status_v1.json',
    'usa_election_poll_history_2026.json', 'usa_midterms_forecast_v1.json',
    'usa_election_state_evidence_index_v1.json', 'usa_election_state_poll_status_v1.json'))
SHARED.update(PREFIX + 'scripts/election_watch/' + f for f in (
    'refresh_live_polls.py', 'refresh_state_polls.py', 'publish_state_packets.py',
    'publish_packet_projections.py', 'publish_polling_run.py', 'freeze_state_inputs.py',
    'check_state_packet_changes.py', 'election_watch/live_polls.py',
    'election_watch/poll_primary_supplements.py', 'election_watch/poll_quality.py',
    'election_watch/state_inputs.py', 'election_watch/poll_refresh_provenance.py'))
SHARED.update({'docs/ops/TASKS.md', '.github/workflows/us_election_polls_refresh.yml'})
INTEGRATION = 'codex/election-state-integration-20261010'


def violations(changed, branch):
    if branch == INTEGRATION:
        return []  # One explicitly authorized platform integration, not a state task.
    packet_changes = [f for f in changed if f.startswith(PACKETS) and f.endswith('.json')]
    state_task = bool(packet_changes) or bool(__import__('re').search(r'codex/[a-z]{2}-(?:state-)?evidence-', branch))
    return sorted(f for f in set(changed) if f in SHARED or
                  f.startswith(PREFIX+'public/data/usa_election_state_evidence/')) if state_task else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--head-ref', default='HEAD')
    parser.add_argument('--branch', required=True)
    args = parser.parse_args()
    packets()
    for file in CATALOGS:
        read(CONFIG/file)  # Also check preconditions against the current baseline.
    changed = subprocess.check_output(['git', 'diff', '--name-only',
        f'{args.base_ref}...{args.head_ref}'], text=True).splitlines()
    bad = violations(changed, args.branch)
    if bad:
        raise SystemExit('State PR edits shared generated/config files; freeze inputs into its state packet:\n' + '\n'.join(bad))
    print('State packet scope valid')


if __name__ == '__main__':
    main()

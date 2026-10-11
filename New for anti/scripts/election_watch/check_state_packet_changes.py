#!/usr/bin/env python3
"""Keep each state's research separate from shared code and publication."""
import argparse
import re
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
SHARED.update({'AGENTS.md', 'CLAUDE.md', 'docs/ops/US_ELECTION_STATE_INPUTS.md',
               'docs/ops/START_PROMPTS.md', 'docs/ops/README.md', 'docs/ops/OWNERS.md'})
STATES = frozenset('AK AL AR AZ CA CO CT DE FL GA HI IA ID IL IN KS KY LA MA MD ME MI MN MS MO MT NC ND NE NH NJ NM NV NY OH OK OR PA RI SC SD TN TX UT VA VT WA WI WV WY'.split())
CONFIG_PREFIX = PREFIX + 'scripts/election_watch/config/'
PUBLIC_PREFIX = PREFIX + 'public/data/'
REVIEW_DIRS = frozenset((
    'usa_election_poll_release_reviews', 'usa_governor_finance_audits',
    'usa_governor_finance_audit_status', 'usa_governor_source_access',
    'usa_governor_ie_report_indexes', 'usa_governor_ie_report_index_status',
    'usa_governor_ie_report_reviews',
))


def input_state(file):
    """Recognize state research even on a branch with an arbitrary name."""
    if file.startswith(CONFIG_PREFIX):
        name = file.removeprefix(CONFIG_PREFIX)
        directory = name.split('/')[0]
        if directory not in {'state_evidence', 'governor_finance', 'governor_candidates', 'governor_ie_filers'}:
            return None
    elif file.startswith(PUBLIC_PREFIX):
        name = file.removeprefix(PUBLIC_PREFIX)
        if name.split('/')[0] not in REVIEW_DIRS:
            return None
    else:
        return None
    match = re.match(r'([A-Z]{2})(?:[_.-]|$)', name.rsplit('/', 1)[-1])
    return match[1] if match and match[1] in STATES else None


def branch_state(branch):
    match = re.fullmatch(r'(?:codex|claude|cursor)/([a-z]{2})-(?:state-)?evidence-.+', branch)
    return match[1].upper() if match and match[1].upper() in STATES else None


def research_states(changed, branch):
    return {s for s in [branch_state(branch), *(input_state(f) for f in changed)] if s}


def named_states(file):
    """State-named tests, adapters and handoffs may not leak into another PR."""
    if file.startswith(PREFIX + 'scripts/election_watch/') and file.endswith('.py'):
        name = file.rsplit('/', 1)[-1].removesuffix('.py')
        # Match state tokens only in the state adapter/test naming convention.
        match = re.match(r'(?:governor_|ballot_|test_(?:poll_|superpac_)(?:governor_)?)([a-z]{2})(?:_|$)', name)
        return {match[1].upper()} & STATES if match else set()
    if file.startswith('docs/ops/handoff/'):
        return set(re.split(r'[-_.]', file.rsplit('/', 1)[-1])) & STATES
    return set()


def unmerged_base_inputs(base_ref, main_ref='origin/main', cwd=None):
    """A shared foundation is allowed; an unmerged state research base is not."""
    changed = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames',
        f'{main_ref}...{base_ref}'], text=True, cwd=cwd).splitlines()
    return sorted(f for f in changed if input_state(f))


def violations(changed, branch):
    states = research_states(changed, branch)
    if not states:
        return []
    def common_code(file):
        if not file.startswith(PREFIX+'scripts/election_watch/') or not file.endswith('.py') or '/tests/' in file:
            return False
        # State-owned adapters may change; common collectors/builders may not.
        return not any(re.search(rf'(^|_){s.lower()}(_|\.py$)', file.rsplit('/',1)[-1]) for s in states)
    bad = {f for f in changed if f in SHARED or common_code(f) or
           f.startswith('.github/workflows/') or
           (f.startswith(PREFIX+'js/elections/') and '/tests/' not in f) or
           (f.startswith(CONFIG_PREFIX) and input_state(f) not in states) or
           (f.startswith(PUBLIC_PREFIX) and input_state(f) not in states) or
           bool(named_states(f) - states)}
    if len(states) > 1:
        bad.update(f for f in changed if input_state(f) or named_states(f))
    return sorted(bad)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--head-ref', default='HEAD')
    parser.add_argument('--branch', required=True)
    parser.add_argument('--main-ref', default='origin/main', help='Fetch main before running the scope check')
    args = parser.parse_args()
    packets()
    for file in CATALOGS:
        read(CONFIG/file)  # Also check preconditions against the current baseline.
    changed = subprocess.check_output(['git', 'diff', '--name-only', '--no-renames',
        f'{args.base_ref}...{args.head_ref}'], text=True).splitlines()
    bad = violations(changed, args.branch)
    if bad:
        raise SystemExit('State PR edits shared files or another state; isolate reviewed inputs:\n' + '\n'.join(bad))
    if research_states(changed, args.branch):
        try:
            inherited = unmerged_base_inputs(args.base_ref, args.main_ref)
        except subprocess.CalledProcessError as error:
            raise SystemExit('Cannot verify state PR base; fetch origin main and retry') from error
        if inherited:
            raise SystemExit('State PR is stacked on unmerged state inputs; use main or a shared foundation:\n' + '\n'.join(inherited))
    print('State packet scope valid')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Join one state, one ten-state group, or all 50 states in A–E order.

Uses reviewed public inputs. This does not collect FEC/state sources or install
an Actions schedule. Collection receipts never update another source's date.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from election_watch.polls import read
from election_watch.state_evidence import ordered_states, build_state, load_finance, publish_states

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parent.parent / 'public/data'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    select = p.add_mutually_exclusive_group(required=True)
    select.add_argument('--state'); select.add_argument('--group', choices=list('ABCDE'))
    select.add_argument('--all', action='store_true')
    p.add_argument('--plan', type=Path, default=ROOT/'config/usa_polls/state_evidence_plan_2026.json')
    p.add_argument('--public', type=Path, default=PUBLIC)
    p.add_argument('--polls', type=Path, default=PUBLIC/'usa_election_live_polls_v1.json')
    p.add_argument('--as-of', default=datetime.now(timezone.utc).date().isoformat())
    args = p.parse_args(); plan = read(args.plan); order = ordered_states(plan, args.as_of)
    selected = [(g, s) for g, s in order if args.all or args.state == s or args.group == g]
    if not selected: p.error('state must be one of the fifty states')
    catalog = read(ROOT/'config/usa_polls/targets_2026.json')
    from election_watch.federal_matchups import validate_snapshot
    federal = read(ROOT/'config/federal_matchups/2026.json'); validate_snapshot(federal, args.as_of)
    governors = read(ROOT/'config/governor_matchups/2026.json')
    from election_watch.governor_matchups import validate_snapshot as validate_governors
    validate_governors(governors, 2026, args.as_of)
    polls = read(args.polls); finance = load_finance(args.public/'usa_election_finance_index_v1.json', 2026)
    directory = read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')
    audits = {}
    for _,state in selected:
        path=args.public/'usa_governor_finance_audits'/'2026'/f'{state}.json'
        if path.exists():
            audits[state]={**read(path),'data_file':path.relative_to(args.public).as_posix()}
    identities = read(ROOT/'config/usa_polls/state_finance_identities_2026.json')
    if identities.get('schema') != 'usa_state_finance_identities_v1' or identities.get('cycle') != 2026:
        p.error('unreviewed finance identity snapshot')
    def builder(state, group):
        payload = build_state(state, group, plan, catalog, federal, governors, polls,
                              finance, directory, args.as_of, identities, audits)
        return payload
    result = publish_states(args.public, plan, selected, builder, datetime.now(timezone.utc).isoformat())
    print({'processed_states': result['processed_state_count'], 'last_state': result['last_processed_state'],
           'errors': result['errors'], 'deep_source_review_remaining': len(result['deep_source_review_remaining'])})
    return int(bool(result['errors']))


if __name__ == '__main__': raise SystemExit(main())

#!/usr/bin/env python3
"""Rebuild reviewed state captures with the current collector, without refetching.

Original receipt dates are preserved. This is an explicit integration/replay,
never a claim of a new API/document/finance collection.
"""
import argparse
from copy import deepcopy
from pathlib import Path
from election_watch.polls import read, atomic, require
from election_watch.state_inputs import packets, digest
from election_watch.live_polls import apply_watchlist, build_live, poll_history
from election_watch.poll_priorities import apply_priorities, attach_coverage, load_finance_links
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_gaps import attach_gaps
from election_watch.state_poll_capture import merge_capture

ROOT = Path(__file__).resolve().parent


def rebuild(previous, history, selected, public):
    board = deepcopy(previous); archive = deepcopy(history)
    config = ROOT/'config/usa_polls'
    finance = load_finance_links(public/'usa_election_finance_index_v1.json', 2026)
    for packet in selected:
        state = packet['state']; saved = packet['capture']; receipt = saved['receipt']
        old = board.get('state_captures', {}).get(state, {})
        require(not old.get('captured_at') or old['captured_at'] <= saved['fetched_at'],
                'newer state capture already published; replay held')
        policy = apply_priorities(apply_watchlist(read(config/'live_2026.json'), read(config/'watchlist_2026.json')),
            read(config/'priorities_2026.json'), public/'congressional_districts/USA', saved['as_of'])
        policy = apply_matchups(policy, read(ROOT/'config/governor_matchups/2026.json'), saved['as_of'])
        ballots = read(config/'ballot_reviews_2026.json')
        policy = apply_targets(policy, read(config/'targets_2026.json'), ballots, saved['as_of'])
        policy['quality_reviews'] = read(config/'quality_reviews_2026.json')['reviews']
        policy['races'] = {rid: r for rid, r in policy['races'].items() if r['state'] == state}
        policy['states'] = [state]
        provider = deepcopy(saved['provider_records']); rows = deepcopy(provider)
        for raw in saved['primary_records']:
            capture = raw['primary_source_capture']
            # Remove only exact IDs already verified as duplicate/replaced in
            # that original collection, retaining its reviewed raw snapshot.
            replaced = set(capture.get('provider_duplicate_ids', []) + capture.get('reviewed_replaced_provider_ids', []))
            rows = [r for r in rows if r['id'] not in replaced]
            rows.append(deepcopy(raw))
        capture = build_live(rows, policy, read(config/'results_2026.json'), saved['as_of'],
                             saved['fetched_at'], receipt['source_url'])
        attach_coverage(capture, provider, policy, finance); attach_gaps(capture, finance)
        board = merge_capture(board, capture, state, receipt)
        board['target_catalog']['ballot_review_count'] = len(ballots['races'])
        newer = poll_history(rows, policy, saved['as_of'])
        archive['races'] = {rid: r for rid, r in archive['races'].items() if rid not in capture['races']}
        archive['races'].update({rid: {**r, 'as_of': saved['as_of'], 'fetched_at': saved['fetched_at']}
                                 for rid, r in newer['races'].items()})
        board.setdefault('state_packet_replays', {})[state] = {
            'packet_sha256': digest(packet), 'original_captured_at': saved['fetched_at'],
            'new_collection': False, 'source_commit': packet.get('source_commit')}
    archive['race_count'] = len(archive['races'])
    archive['observation_count'] = sum(len(r['observations']) for r in archive['races'].values())
    return board, archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--states', nargs='+')
    parser.add_argument('--pending', action='store_true', help='Bootstrap unimported packets before live collection')
    parser.add_argument('--public', type=Path, default=ROOT.parent.parent/'public/data')
    args = parser.parse_args()
    target = args.public/'usa_election_live_polls_v1.json'
    history = args.public/'usa_election_poll_history_2026.json'
    previous = read(target)
    require(bool(args.states) != args.pending, 'select states or pending')
    selected = [p for p in packets() if (args.pending and previous.get('state_packet_replays', {}).get(p['state'], {}).get('packet_sha256') != digest(p)) or args.states and p['state'] in args.states]
    if args.states:
        require(len(selected) == len(set(args.states)), 'missing/duplicate state packet')
    # All captures must validate before either national artifact is written.
    board, archive = rebuild(previous, read(history), selected, args.public)
    atomic(target, board); atomic(history, archive)
    print({'rebuilt_states': [p['state'] for p in selected], 'observations': board['coverage']['displayed_observations'],
           'new_collection': False})


if __name__ == '__main__':
    main()

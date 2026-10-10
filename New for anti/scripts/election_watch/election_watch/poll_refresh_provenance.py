"""Retain state-scoped evidence receipts when rebuilding the national board.

The new board's dates describe the actual national fetch. Earlier state receipts
remain historical provenance, never proof that an old release was fetched today.
"""
from copy import deepcopy
from .polls import require


def retain_state_provenance(board, history, previous, state_packets=()):
    if not previous:
        return
    require(previous['schema'] == board['schema'] == 'usa_live_polls_v1'
            and previous['cycle'] == board['cycle'] == history['cycle'],
            'previous polling provenance schema/cycle')
    if previous.get('state_captures'):
        board['state_captures'] = deepcopy(previous['state_captures'])
        history['state_captures'] = deepcopy(previous['state_captures'])
    if previous.get('state_packet_replays'):
        board['state_packet_replays'] = deepcopy(previous['state_packet_replays'])
    for rid, old in previous.get('races', {}).items():
        if rid not in board['races']:
            continue
        provenance = deepcopy(old.get('state_capture_provenance'))
        if old.get('fetched_at') and old.get('source_url'):
            provenance = {key: deepcopy(old[key]) for key in
                          ('as_of', 'fetched_at', 'source_status', 'source_url') if key in old}
        if provenance:
            board['races'][rid]['state_capture_provenance'] = provenance
            if rid in history['races']:
                history['races'][rid]['state_capture_provenance'] = deepcopy(provenance)
    # Import historical review receipts only after a successful fresh build.
    # Never bootstrap old packet observations over a newer last-good board
    # before a network request that may fail.
    from .state_inputs import digest
    for packet in state_packets:
        state = packet['state']; saved = packet['capture']
        old = board.setdefault('state_captures', {}).get(state, {})
        if not old.get('captured_at') or old['captured_at'] <= saved['fetched_at']:
            board['state_captures'][state] = deepcopy(saved['receipt'])
        board.setdefault('state_packet_replays', {})[state] = {
            'packet_sha256': digest(packet), 'original_captured_at': saved['fetched_at'],
            'new_collection': False, 'receipt_import_only': True,
            'source_commit': packet.get('source_commit')}
    if board.get('state_captures'):
        history['state_captures'] = deepcopy(board['state_captures'])

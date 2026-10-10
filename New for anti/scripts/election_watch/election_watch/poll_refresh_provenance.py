"""Retain state-scoped evidence receipts when rebuilding the national board.

The new board's dates describe the actual national fetch. Earlier state receipts
remain historical provenance, never proof that an old release was fetched today.
"""
from copy import deepcopy
from .polls import require


def retain_state_provenance(board, history, previous):
    if not previous:
        return
    require(previous['schema'] == board['schema'] == 'usa_live_polls_v1'
            and previous['cycle'] == board['cycle'] == history['cycle'],
            'previous polling provenance schema/cycle')
    if previous.get('state_captures'):
        board['state_captures'] = deepcopy(previous['state_captures'])
        history['state_captures'] = deepcopy(previous['state_captures'])
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

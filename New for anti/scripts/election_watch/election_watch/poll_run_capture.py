"""Replay an actual collection on a newer main without changing collection time."""
from copy import deepcopy
from datetime import date, datetime
from .polls import digest, require


def validate_capture(payload):
    require(payload['schema'] == 'usa_poll_run_capture_v1', 'poll run capture schema')
    checked = datetime.fromisoformat(payload['captured_at'].replace('Z', '+00:00'))
    require(date.fromisoformat(payload['as_of']) <= checked.date(), 'future poll run capture')
    require(payload['source_url'].startswith('https://api.votehub.com/polls?'), 'poll run capture source')
    fields = ('as_of', 'captured_at', 'source_url', 'provider_rows', 'rows', 'primary_receipts',
              'ballot_capture', 'ballot_health')
    require(payload['sha256'] == digest({k:payload[k] for k in fields}), 'poll run capture changed')
    require(isinstance(payload['rows'], list) and isinstance(payload['provider_rows'], list)
            and payload['provider_rows'], 'poll run capture records')
    return payload


def make_capture(rows, provider_rows, source_url, as_of, captured_at, primary_receipts=None,
                 ballot_capture=None, ballot_health=None):
    data = {'as_of':as_of, 'captured_at':captured_at, 'source_url':source_url,
            'provider_rows':provider_rows, 'rows':rows, 'primary_receipts':primary_receipts or [],
            'ballot_capture':ballot_capture or {}, 'ballot_health':ballot_health or {'status':'not_configured'}}
    return validate_capture({'schema':'usa_poll_run_capture_v1', **data, 'sha256':digest(data)})


def restore_ballots(ballots, captured):
    """Retain the exact official refresh unless main has a conflicting review."""
    result = deepcopy(ballots)
    for rid, saved in captured.items():
        require(rid.startswith('USA:FL:') and saved['value']['state']=='FL', 'captured ballot state')
        current = result['races'].get(rid)
        require(current == saved['value'] or digest(current) == saved['before_sha256'],
                'captured ballot conflicts with newer main review')
        result['races'][rid] = deepcopy(saved['value'])
    return result

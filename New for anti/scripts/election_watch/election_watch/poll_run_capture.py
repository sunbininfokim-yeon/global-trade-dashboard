"""Replay an actual collection on a newer main without changing collection time."""
from datetime import date, datetime
from .polls import digest, require


def validate_capture(payload):
    require(payload['schema'] == 'usa_poll_run_capture_v1', 'poll run capture schema')
    checked = datetime.fromisoformat(payload['captured_at'].replace('Z', '+00:00'))
    require(date.fromisoformat(payload['as_of']) <= checked.date(), 'future poll run capture')
    require(payload['source_url'].startswith('https://api.votehub.com/polls?'), 'poll run capture source')
    fields = ('as_of', 'captured_at', 'source_url', 'provider_rows', 'rows', 'primary_receipts')
    require(payload['sha256'] == digest({k:payload[k] for k in fields}), 'poll run capture changed')
    require(isinstance(payload['rows'], list) and isinstance(payload['provider_rows'], list)
            and payload['provider_rows'], 'poll run capture records')
    return payload


def make_capture(rows, provider_rows, source_url, as_of, captured_at, primary_receipts=None):
    data = {'as_of':as_of, 'captured_at':captured_at, 'source_url':source_url,
            'provider_rows':provider_rows, 'rows':rows, 'primary_receipts':primary_receipts or []}
    return validate_capture({'schema':'usa_poll_run_capture_v1', **data, 'sha256':digest(data)})

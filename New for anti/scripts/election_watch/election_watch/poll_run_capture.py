"""Replay an actual collection on a newer main without changing collection time."""
from copy import deepcopy
from datetime import date, datetime
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from .polls import digest, require


def collection_failure(exc, stage):
    """Log actionable diagnostics without copying arbitrary exception text/URLs."""
    known = {
        'quality review schema/cycle': 'quality_review_schema_cycle',
        'primary_and_provider_wave_conflict': 'primary_and_provider_wave_conflict',
        'empty or changed API schema': 'provider_schema_changed',
        'pagination needs adapter update': 'provider_pagination_changed',
        'unexpected API redirect': 'provider_redirect_changed',
        'oversized response': 'provider_response_too_large',
        'poll run capture changed': 'capture_digest_mismatch',
        'captured ballot conflicts with newer main review': 'ballot_review_conflict',
    }
    if isinstance(exc, HTTPError):
        code = f'http_{exc.code}' if type(exc.code) is int and 100 <= exc.code <= 599 else 'http_error'
    elif isinstance(exc, URLError):
        code = 'network_error'
    elif isinstance(exc, TimeoutError):
        code = 'network_timeout'
    elif isinstance(exc, JSONDecodeError):
        code = 'invalid_json'
    elif isinstance(exc, ValueError):
        code = known.get(str(exc), 'validation_failed')
    elif isinstance(exc, OSError):
        code = 'file_io_failed'
    elif isinstance(exc, (KeyError, TypeError, IndexError)):
        code = 'schema_mismatch'
    else:
        code = 'unexpected_error'
    return {'stage': stage, 'error_type': type(exc).__name__, 'error_code': code}


def primary_capture_health(receipts):
    """Summarize both finite-document and HTML routes; no receipt means unobserved."""
    conflicts, references, unavailable, documents = set(), set(), set(), set()
    unknown = 0
    for receipt in receipts:
        status = receipt.get('status')
        rid = receipt.get('id')
        capture = receipt.get('record', {}).get('primary_source_capture', receipt)
        if (status in ('primary_provider_conflict_reference_only', 'provider_wave_conflict_reference_only')
                or capture.get('conflict_reason') == 'primary_and_provider_wave_conflict'):
            conflicts.add(rid)
            references.add(rid)
        elif status == 'carried_forward_reference_only':
            references.add(rid)
        elif status == 'unavailable_no_previous_data':
            unavailable.add(receipt.get('contract_id'))
        elif status != 'primary_documents_rechecked':
            unknown += 1
        if any(d.get('status') != 'unchanged' for d in capture.get('documents', [])):
            documents.add(rid)
    issue = bool(references or unavailable or documents or unknown)
    return {'status': 'review_required' if issue else 'ok' if receipts else 'not_observed',
            'receipt_count': len(receipts), 'unknown_receipt_count': unknown,
            'conflict_release_ids': sorted(r for r in conflicts if r),
            'reference_only_release_ids': sorted(r for r in references if r),
            'unavailable_contract_ids': sorted(r for r in unavailable if r),
            'document_problem_release_ids': sorted(r for r in documents if r)}


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

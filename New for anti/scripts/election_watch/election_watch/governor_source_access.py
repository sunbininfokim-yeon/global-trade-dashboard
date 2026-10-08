"""Check reviewed public governor portals; reachability is never financial coverage."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .polls import atomic, require

BLOCKED = ('the request is blocked', 'access denied', 'service unavailable', 'request unsuccessful. incapsula incident id:')


def probe(url, opener=urlopen):
    request = Request(url, headers={'User-Agent': 'ElectionWatch/1.0 public-source-review'})
    try:
        with opener(request, timeout=25) as response:
            body = response.read(262144)
            code = response.status
            resolved = response.geturl()
        text = body.decode('utf-8', errors='replace').casefold()
        same_host = urlparse(resolved).hostname == urlparse(url).hostname
        status = ('public_endpoint_reachable' if code == 200 and same_host and
                  not any(marker in text for marker in BLOCKED) else 'source_access_blocked'
                  if any(marker in text for marker in BLOCKED) else 'source_response_review_required')
        return {'url': url, 'status': status, 'http_status': code,
                'same_host': same_host, 'body_prefix_sha256': hashlib.sha256(body).hexdigest()}
    except HTTPError as error:
        status = ('source_access_blocked' if error.code in (401, 403) else
                  'source_unavailable' if error.code == 429 or error.code >= 500 else
                  'source_response_review_required')
        return {'url': url, 'status': status, 'http_status': error.code,
                'error_type': 'HTTPError'}
    except (OSError, URLError) as error:
        return {'url': url, 'status': 'source_unavailable', 'http_status': None,
                'error_type': type(error).__name__}


def collect_access(state, cycle, agency, checked_at, previous=None, opener=urlopen):
    review = agency['public_source_review']
    require(cycle == 2026 and review['cycle'] == cycle and
            date.fromisoformat(review['reviewed_on']) <= date.fromisoformat(checked_at[:10]),
            'unreviewed governor portal')
    endpoints = review['endpoints']
    require(endpoints and sum(e['role'] == 'current_public_portal' for e in endpoints) == 1,
            'ambiguous current governor portal')
    for endpoint in endpoints:
        parsed = urlparse(endpoint['url'])
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
                'invalid governor portal URL')
        require(endpoint['role'] in ('current_public_portal', 'current_public_export', 'legacy_search', 'legacy_independent_registry'),
                'unreviewed governor portal role')
    if previous:
        validate_access(previous, state, cycle, checked_at[:10])
    results = [{**probe(e['url'], opener), 'role': e['role']} for e in endpoints]
    current = next(e for e in results if e['role'] == 'current_public_portal')
    accessible = current['status'] == 'public_endpoint_reachable'
    # A reachable legacy endpoint must never make the current source healthy.
    return {'schema': 'usa_governor_source_access_v1', 'state': state, 'cycle': cycle,
        'checked_at': checked_at,
        'status': 'public_endpoint_reachable_mapping_required' if accessible else current['status'],
        'last_current_endpoint_accessible_at': checked_at if accessible else
            (previous or {}).get('last_current_endpoint_accessible_at'),
        'financial_data_collected': False, 'candidate_amounts_available': False,
        'current_portal_url': current['url'], 'source_review': deepcopy(review), 'endpoints': results,
        'note_ko': '공개 사이트 접근 검사만 수행. 후보별 독립지출 수집·금액·최신 공시일 확인과 다릅니다. 접근 실패는0달러가 아닙니다. 기존 유효 금융 파일/원래 기준일은 변경하지 않습니다.'}


def validate_access(payload, state, cycle, as_of):
    require(payload['schema'] == 'usa_governor_source_access_v1' and
            payload['state'] == state and payload['cycle'] == cycle and
            date.fromisoformat(payload['checked_at'][:10]) <= date.fromisoformat(as_of),
            'governor source access scope/date mismatch')
    require(payload['status'] in ('public_endpoint_reachable_mapping_required', 'source_access_blocked',
                                 'source_response_review_required', 'source_unavailable') and
            payload['financial_data_collected'] is False and payload['candidate_amounts_available'] is False,
            'governor source access cannot assert financial coverage')
    current = [e for e in payload['endpoints'] if e['role'] == 'current_public_portal']
    require(len(current) == 1 and current[0]['url'] == payload['current_portal_url'] and
            (payload['status'] == 'public_endpoint_reachable_mapping_required'
             if current[0]['status'] == 'public_endpoint_reachable' else payload['status'] == current[0]['status']),
            'governor source access status mismatch')
    last = payload.get('last_current_endpoint_accessible_at')
    require(not last or datetime.fromisoformat(last.replace('Z', '+00:00')) <=
            datetime.fromisoformat(payload['checked_at'].replace('Z', '+00:00')), 'future governor portal access')
    return payload


def publish_access(path, state, cycle, agency, checked_at, previous=None, opener=urlopen):
    # Validation/config failures do not overwrite the last valid health receipt.
    payload = collect_access(state, cycle, agency, checked_at, previous, opener)
    validate_access(payload, state, cycle, checked_at[:10])
    atomic(path, payload)
    return payload

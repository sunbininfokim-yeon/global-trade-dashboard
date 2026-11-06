"""Observe a deployed first forecast; keep publication evidence separate from generation."""
import argparse
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

from option_direction_model import digest, read
from run_us_kr_preopen import display_payload, timing
from us_kr_direction_engine import TICKERS, write_immutable
from research_stock_open_close_direction import TARGETS

VERSION = 'us-kr-publication-observation-v1'
DEFAULT_URL = 'https://global-trade-dashboard.sunbin-info-kim.workers.dev/public/data/us_kr_direction_v1.json'


def timestamp(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('timezone-aware observation timestamp required')
    return t


def public_identity(payload):
    """Ignore refresh metadata and additive display fields, but require every primary score."""
    result = {k: payload[k] for k in ['schema_version', 'status', 'target_date', 'generated_at',
              'KR_source_date', 'US_source_date', 'forecast_cutoff_KST', 'model_id', 'trained_through', 'research_only']}
    cards = payload['cards']
    if len(cards) != len(TICKERS) or {c['ticker'] for c in cards} != set(TICKERS):
        raise ValueError('all three distinct primary cards required')
    result['cards'] = {}
    for card in cards:
        scores = card['scores']
        if set(scores) != set(TARGETS):
            raise ValueError('all four primary event scores required')
        result['cards'][card['ticker']] = {}
        for target in TARGETS:
            score = {k: scores[target][k] for k in ['probability', 'score_0_100', 'direction', 'information_state']}
            p = score['probability']
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError('invalid public probability')
            if target in ('opening_up', 'closing_up'):
                for key, expected in [('up_probability', p), ('down_probability', 1-p)]:
                    if key in scores[target] and scores[target][key] != expected:
                        raise ValueError('public UP/DOWN complement differs from the primary probability')
            result['cards'][card['ticker']][target] = score
    return result


def validate_observation(receipt, forecast):
    """Recheck saved evidence against the immutable first forecast, never a revision."""
    if (forecast.get('record_role') != 'first_preopen_forecast' or
            forecast.get('status') != 'research_preopen_forecast' or
            forecast.get('eligible_for_primary_evaluation') is not True or
            forecast.get('eligible_for_prospective_evaluation') is not True):
        raise ValueError('eligible first pre-open forecast required')
    if receipt.get('schema_version') != VERSION:
        raise ValueError('unknown publication receipt version')
    if (receipt.get('target_date') != forecast['target_date'] or
            receipt.get('model_id') != forecast['model_id'] or
            receipt.get('forecast_sha256') != digest(forecast)):
        raise ValueError('publication receipt is for a different forecast')
    if receipt.get('http_status') != 200 or urlparse(receipt.get('url', '')).scheme != 'https':
        raise ValueError('successful HTTPS observation required')
    observed = timestamp(receipt['observed_at'])
    if observed < timestamp(forecast['generated_at']):
        raise ValueError('observation precedes forecast generation')
    gate = timing(forecast['target_date'], observed.to_pydatetime())
    if gate['reasons'] or observed >= timestamp(gate['cutoff']):
        raise ValueError('public payload not observed before the pre-open cutoff')
    if (forecast['KR_source_date'] != gate['source'] or forecast['required_US_session'] != gate['us_source'] or
            timestamp(forecast['forecast_cutoff_KST']) != timestamp(gate['cutoff'])):
        raise ValueError('forecast source session mismatch')
    payload = receipt['payload']
    if receipt.get('payload_sha256') != digest(payload):
        raise ValueError('publication payload hash mismatch')
    if public_identity(payload) != public_identity(display_payload(forecast)):
        raise ValueError('deployed payload differs from the first forecast')
    return observed


def observe(forecast, url=DEFAULT_URL, clock=None, get=None):
    """Timestamp AFTER the HTTP response. A late successful deploy is still late."""
    if urlparse(url).scheme != 'https':
        raise ValueError('publication URL must use HTTPS')
    clock = clock or (lambda: datetime.now(timezone.utc))
    get = get or requests.get
    receipt = {'schema_version': VERSION, 'target_date': forecast['target_date'],
               'model_id': forecast['model_id'], 'forecast_sha256': digest(forecast), 'url': url,
               'workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
               'workflow_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'checkout_commit': os.environ.get('GITHUB_SHA'),
               'status': 'publication_unverified', 'eligible_for_publication_evaluation': False,
               'evidence': 'HTTP payload observed by this runner; not the first publication time or an independent clock'}
    try:
        response = get(url, headers={'Cache-Control': 'no-cache', 'Accept': 'application/json'}, timeout=20)
        receipt['http_status'] = response.status_code
        response.raise_for_status()
        receipt['payload'] = response.json()
        receipt['payload_sha256'] = digest(receipt['payload'])
    except (requests.RequestException, ValueError) as e:
        receipt['reason'] = type(e).__name__ + ': ' + str(e)
    receipt['observed_at'] = timestamp(clock()).isoformat()
    if 'reason' not in receipt:
        try:
            validate_observation(receipt, forecast)
        except (KeyError, TypeError, ValueError) as e:
            receipt['reason'] = type(e).__name__ + ': ' + str(e)
        else:
            receipt.update(status='verified_preopen_publication', eligible_for_publication_evaluation=True)
    return receipt


def publication_evidence(directory, forecast, now):
    """Missing or invalid observations never silently become verified publication."""
    paths = sorted((Path(directory)/'publications').glob('*.json'))
    valid = []; reasons = []
    for path in paths:
        try:
            receipt = read(path)
            observed = validate_observation(receipt, forecast)
            if (receipt.get('status') != 'verified_preopen_publication' or
                    receipt.get('eligible_for_publication_evaluation') is not True):
                raise ValueError('receipt does not claim verified publication')
            if observed > timestamp(now):
                raise ValueError('observation is after evaluation time')
            valid.append((observed, path, receipt))
        except (OSError, KeyError, TypeError, ValueError) as e:
            reasons.append({'file': path.name, 'reason': str(e)})
    if not valid:
        return {'status': 'unverified', 'reason': 'no_publication_observation' if not paths else 'no_valid_publication_observation',
                'invalid_observations': reasons}
    observed, path, receipt = min(valid, key=lambda r: r[0])
    return {'status': 'verified', 'first_observed_at': observed.isoformat(), 'receipt': path.name,
            'url': receipt['url'], 'receipt_sha256': digest(receipt), 'invalid_observations': reasons}


def save_observation(archive_dir, forecast, receipt):
    stamp = timestamp(receipt['observed_at']).tz_convert('UTC').strftime('%Y%m%dT%H%M%S%fZ')
    path = (Path(archive_dir)/forecast['target_date']/forecast['model_id'][:16]/'publications'/
            (stamp+'-'+digest(receipt)[:12]+'.json'))
    write_immutable(path, receipt)
    return path


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive-dir', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--url', default=DEFAULT_URL)
    args = p.parse_args()
    # Import here so the evaluation module can reuse publication_evidence.
    from evaluate_us_kr_forward import validate_first
    from us_kr_direction_engine import validate_model
    primary = read(args.model); validate_model(primary)
    first = args.archive_dir/args.target/primary['model_id'][:16]/'first.json'
    if not first.exists():
        p.error('no immutable first forecast exists for this target and model')
    forecast = read(first)
    validate_first(forecast, primary, args.target, timestamp(datetime.now(timezone.utc)))
    receipt = observe(forecast, args.url)
    path = save_observation(args.archive_dir, forecast, receipt)
    print({'status': receipt['status'], 'receipt': str(path), 'reason': receipt.get('reason')})
    raise SystemExit(0 if receipt['eligible_for_publication_evaluation'] else 2)

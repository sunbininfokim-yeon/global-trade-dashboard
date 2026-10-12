"""Check collection attempts independently of publication lag and source coverage."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = 'https://global-trade-dashboard.sunbin-info-kim.workers.dev'


def check_status(status, now=None):
    now = now or datetime.now(timezone.utc)
    errors = []
    try:
        attempted = datetime.fromisoformat(status['last_attempt_at'])
        if attempted.tzinfo is None:
            raise ValueError('missing timezone')
        days = (now-attempted).total_seconds()/86400
        if days > 35 or days < -1:
            errors.append('collection_attempt_stale_or_invalid')
    except (KeyError, ValueError, TypeError):
        errors.append('collection_attempt_missing')
    if status.get('execution_status', status.get('status')) != 'completed':
        errors.append('collection_partial_or_failed')
    if status.get('scope') != 'scheduled':
        errors.append('no_full_scheduled_collection')
    if status.get('run_kind') == 'resume':
        try:
            full = datetime.fromisoformat(status['last_full_attempt_at'])
            if full.tzinfo is None or not -1 <= (now-full).total_seconds()/86400 <= 35:
                raise ValueError('invalid full attempt')
        except (KeyError, ValueError, TypeError):
            errors.append('full_collection_attempt_stale_or_missing')
        if status.get('last_full_execution_status') != 'completed':
            errors.append('last_full_collection_failed_or_missing')
    return errors


def observation_warnings(status, now=None):
    now = now or datetime.now(timezone.utc)
    warnings = []
    for key, queue in status.get('queues', {}).items():
        if queue.get('pending_jobs') or queue.get('empty_jobs') or queue.get('deferred_error_jobs'):
            warnings.append({'series':key,'issue':'acquisition_gaps',**queue})
        try:
            resumed = datetime.fromisoformat(queue['last_resume_at'])
            if resumed.tzinfo is None or (now-resumed).total_seconds()/86400 > 7:
                warnings.append({'series':key,'issue':'queue_not_resumed_within_7_days'})
        except (KeyError,ValueError,TypeError):
            warnings.append({'series':key,'issue':'queue_resume_time_missing'})
    for product in status.get('observations', {}).get('products', []):
        for source in product.get('world_sources', []):
            for issue, field in (('publication_hold','publication_held_months'),
                                 ('observed_history_gaps','observed_history_gaps')):
                if source.get(field):
                    warnings.append({k:product[k] for k in ('reporter','hs','flow')} | {
                        'issue':issue, 'source':source.get('source'), 'unit':source.get('unit'),
                        'months':source[field]})
        for field in ('world_latest_period', 'bilateral_latest_period'):
            period = product.get(field)
            try:
                observed = datetime.strptime(period, '%Y%m')
                lag = (now.year-observed.year)*12+now.month-observed.month
            except (ValueError, TypeError):
                lag = None
            if period is None or lag is None or lag > 6 or lag < 0:
                warnings.append({k:product[k] for k in ('reporter','hs','flow')} | {
                    'series':field, 'latest_period':period, 'lag_months':lag,
                    'issue':'not_acquired' if period is None else 'stale_or_invalid_observation'})
        if product.get('world_latest_period') and product.get('bilateral_latest_period') and not product.get('same_period_latest'):
            warnings.append({k:product[k] for k in ('reporter','hs','flow')} | {
                'issue':'latest_period_mismatch', 'latest_common_period':product.get('latest_common_period')})
    for iso, country in status.get('observations', {}).get('countries', {}).items():
        for field in ('world_latest_period', 'bilateral_latest_period'):
            period = country.get(field)
            if period is None:
                warnings.append({'reporter': iso, 'series': field, 'issue': 'not_acquired'})
                continue
            try:
                observed = datetime.strptime(period, '%Y%m')
                lag = (now.year-observed.year)*12+now.month-observed.month
            except (ValueError, TypeError):
                lag = None
            if lag is None or lag > 6 or lag < 0:
                warnings.append({'reporter': iso, 'series': field, 'latest_period': period,
                                 'lag_months': lag, 'issue': 'stale_or_invalid_observation'})
    return warnings


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default=BASE)
    parser.add_argument('--status-file',type=Path,help='validate local/artifact execution separately from deployment')
    args=parser.parse_args()
    try:
        limit=4*1024*1024
        if args.status_file:
            with args.status_file.open('rb') as response:
                body=response.read(limit+1)
        else:
            req=Request(args.base+'/public/data/commodity_trade_refresh_status_v1.json',headers={
                'Accept':'application/json', 'User-Agent':'CommodityTradeFreshnessMonitor/1.0'})
            with urlopen(req,timeout=30) as response:
                body=response.read(limit+1)
        if len(body)>limit:
            raise ValueError('size limit')
        status=json.loads(body)
        if not isinstance(status,dict):
            raise ValueError('invalid status document')
        errors=check_status(status)
        warnings=observation_warnings(status)
    except Exception:
        errors=['published_refresh_status_unavailable']
        warnings=[]
    print(json.dumps({'status':'fail' if errors else 'pass','issues':errors,'coverage_warnings':warnings,
                      'evidence_scope':'local_execution' if args.status_file else 'published_deployment'}))
    return bool(errors)


if __name__=='__main__':
    raise SystemExit(main())

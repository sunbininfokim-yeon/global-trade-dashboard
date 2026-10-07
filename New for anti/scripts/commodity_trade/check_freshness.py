"""Check collection attempts independently of publication lag and source coverage."""
import argparse
import json
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
    if status.get('status') != 'completed':
        errors.append('collection_partial_or_failed')
    if status.get('scope') != 'scheduled':
        errors.append('no_full_scheduled_collection')
    return errors


def observation_warnings(status, now=None):
    now = now or datetime.now(timezone.utc)
    warnings = []
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
    args=parser.parse_args()
    try:
        req=Request(args.base+'/public/data/commodity_trade_refresh_status_v1.json',headers={'Accept':'application/json'})
        with urlopen(req,timeout=30) as response:
            body=response.read(1024*1024+1)
        if len(body)>1024*1024:
            raise ValueError('size limit')
        status=json.loads(body)
        errors=check_status(status)
        warnings=observation_warnings(status)
    except Exception:
        errors=['published_refresh_status_unavailable']
        warnings=[]
    print(json.dumps({'status':'fail' if errors else 'pass','issues':errors,'coverage_warnings':warnings}))
    return bool(errors)


if __name__=='__main__':
    raise SystemExit(main())

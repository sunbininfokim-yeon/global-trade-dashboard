"""Scheduled collection: bounded country batches, retained data, explicit run status."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from priority_universe import PRIORITY_REPORTERS
from national_source_registry import automated_reporters
from pipeline_store import atomic_json

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1] / 'public/data'


def run_stage(name, argv, status, timeout=1800):
    # No raw stdout/exception URLs in public records (may contain provider credentials).
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run([sys.executable, '-B', str(ROOT/argv[0]), *argv[1:]],
                                capture_output=True, timeout=timeout)
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = 124
    stage = dict(stage=name, started_at=started, exit_code=code,
        status='completed' if code == 0 else 'failed', completed_at=datetime.now(timezone.utc).isoformat())
    if code == 0 and (name.startswith('preview_') or name.startswith('national_')):
        filename = 'commodity_trade_comtrade_priority_v1.json' if name.startswith('preview_') else 'commodity_trade_national_priority_v1.json'
        panel = json.loads((PUBLIC/filename).read_text())
        run = (panel.get('runs') or [{}])[-1]
        # A successful empty Preview response is a release gap, not API failure.
        stage['empty_responses'] = sum(f.get('reason') == 'no data' for f in run.get('failures', []))
        stage['source_failures'] = len(run.get('failures', [])) - stage['empty_responses']
        stage['request_budget_exhausted'] = run.get('quota_capped', False)
        stage['network_requests'] = run.get('network_requests', 0)
        if stage['source_failures'] or stage['request_budget_exhausted']:
            stage['status']='partial'
    if code == 0 and name == 'global_sources':
        panel = json.loads((PUBLIC/'commodity_trade_monthly_v1.json').read_text())
        stage['retained_previous_reporters'] = len(panel.get('retained_previous_reporters', []))
        if stage['retained_previous_reporters']:
            stage['status'] = 'partial'
    if name.startswith('bilateral') and code != 124:
        # Copy only known non-secret numeric/status fields, never stdout text.
        try:
            summary = json.loads(result.stdout.decode().splitlines()[-1])
            for key in ('planned_jobs', 'network_requests', 'unfinished_jobs'):
                if type(summary.get(key)) is int:
                    stage[key] = summary[key]
            if summary.get('stop_reason') in ('rate_limited', 'auth_required', 'network_error'):
                stage['stop_reason'] = summary['stop_reason']
            if code == 0 and stage.get('unfinished_jobs', 0):
                stage['status'] = 'partial'
        except (ValueError, IndexError, UnicodeError):
            stage['status'] = 'failed'
    status['stages'].append(stage)
    print(f'{name}: exit={code}', flush=True)
    return code == 0


def observation_health(data_dir=PUBLIC):
    """Generated time is never substituted for an observed reporting month."""
    coverage = json.loads((data_dir/'commodity_trade_coverage_v1.json').read_text())
    assets = {}
    def observed_months(node):
        if isinstance(node, dict):
            for point in node.get('points', []):
                if isinstance(point.get('month'), str):
                    yield point['month']
            for key, value in node.items():
                if key != 'points':
                    yield from observed_months(value)
        elif isinstance(node, list):
            for value in node:
                yield from observed_months(value)
    for name in ('monthly', 'comtrade_priority', 'national_priority', 'saudi_bulletin'):
        panel = json.loads((data_dir/f'commodity_trade_{name}_v1.json').read_text())
        assets[name] = {'generated_at': panel.get('generated_at'),
                        'latest_observed_month': max(observed_months(panel), default=None)}
    countries = {iso: {k: c.get(k) for k in ('world_latest_period', 'bilateral_latest_period')}
                 for iso, c in coverage.get('countries', {}).items()}
    return {'assets': assets, 'countries': countries,
            'scope': 'priority_panels_and_bilateral; raw observed months, not display eligibility'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=int, choices=range(3), required=True)
    parser.add_argument('--skip-global', action='store_true', help='targeted smoke run only')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    status_path = PUBLIC/'commodity_trade_refresh_status_v1.json'
    previous = json.loads(status_path.read_text()) if status_path.exists() else {}
    status = dict(schema_version='commodity-trade-refresh-status-v1', last_attempt_at=now.isoformat(),
                  last_success_at=previous.get('last_success_at'), batch=args.batch, stages=[],
                  scope='smoke' if args.skip_global else 'scheduled', auth={}, status='running')
    atomic_json(status_path, status)
    gateway = bool(os.getenv('TRADE_GATEWAY_URL') and os.getenv('TRADE_PIPELINE_TOKEN'))
    korea = bool(os.getenv('KOREA_CUSTOMS_SERVICE_KEY')) or gateway
    status['auth'] = {'comtrade_direct_key_present':bool(os.getenv('COMTRADE_API_KEY')),
                      'korea_direct_key_present':bool(os.getenv('KOREA_CUSTOMS_SERVICE_KEY')),
                      'gateway_configured':gateway}
    try:
        if not args.skip_global:
            run_stage('global_sources', ['build_monthly.py'], status, 3600)
        reporters = list(PRIORITY_REPORTERS)[args.batch*9:(args.batch+1)*9]
        for iso in reporters:
            run_stage('preview_'+iso, ['build_comtrade_priority_monthly.py','--reporters',iso,
                '--months','6','--max-requests','12','--min-interval-seconds','3'],status)
        for iso in automated_reporters() + (['KOR'] if korea else []):
            run_stage('national_'+iso,['build_national_priority_monthly.py','--reporters',iso,
                '--months','3','--max-requests','72','--min-interval-seconds','3'],status)
        if not korea:
            status['stages'].append({'stage':'national_KOR','status':'auth_required','exit_code':None})
        run_stage('saudi_bulletin',['build_saudi_bulletin.py'],status)
        mode = 'gateway' if gateway else 'direct' if os.getenv('COMTRADE_API_KEY') else 'preview'
        checkpoint = Path(os.environ.get('TRADE_CHECKPOINT', '/tmp/commodity-trade-checkpoint.json'))
        run_stage('bilateral',['build_bilateral.py','--fetch','--mode',mode,'--reporters',','.join(reporters),
            '--hs','all','--period-strategy','observed','--months','1','--max-requests','60',
            '--interval','3','--checkpoint',str(checkpoint)],status)
        if korea:
            run_stage('bilateral_KOR',['build_bilateral.py','--fetch','--mode','gateway' if gateway else 'direct',
                '--source','korea_customs','--reporters','KOR','--hs','all','--hs-version','HSK',
                '--months','3','--max-requests','60','--interval','3','--checkpoint',str(checkpoint)],status)
        run_stage('coverage',['monthly_coverage.py'],status)
        valid = run_stage('release_gate',['validate_release.py'],status)
        status['status'] = 'completed' if valid and all(s['status']=='completed' for s in status['stages']) else 'partial'
        if status['status']=='completed' and not args.skip_global:
            status['last_success_at'] = datetime.now(timezone.utc).isoformat()
        return 0 if valid else 1
    finally:
        status['completed_at'] = datetime.now(timezone.utc).isoformat()
        if status['status']=='running':
            status['status']='failed'
        try:
            status['observations'] = observation_health()
        except (OSError, ValueError, KeyError, TypeError):
            status['observation_health_unavailable'] = True
        atomic_json(status_path,status)


if __name__ == '__main__':
    raise SystemExit(main())

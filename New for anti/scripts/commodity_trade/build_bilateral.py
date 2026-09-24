"""Collect resumable bilateral partitions and publish versioned data + manifest.

No fetch unless --fetch is passed. A manifest is switched only after immutable
content-addressed parts are written, so interrupted publication stays consistent.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from bilateral import ContractError, build_partition, period_key
from bilateral_jobs import make_job, execute_plan
from bilateral_provider import Provider, KOREA_PARTNERS
from pipeline_store import atomic_json, read_json, single_writer
from priority_universe import PRIORITY_REPORTERS, PRIORITY_COMMODITIES
from export_control_screen import screen, coverage, with_documents
from monthly_coverage import observed_targets, PANEL_NAMES

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parent.parent / 'public/data'
ISO_BY_CODE = {str(int(v['m49'])): k for k, v in PRIORITY_REPORTERS.items()}
ISO_BY_CODE.update({'180': 'COD', '894': 'ZMB', '716': 'ZWE', '508': 'MOZ'})


def months_back(end, count):
    period_key(end, 'M')
    n = int(end[:4]) * 12 + int(end[4:]) - 1
    return [f'{(n-i)//12:04d}{(n-i)%12+1:02d}' for i in range(count)]


def plan_jobs(reporters, hs_codes, periods, *, source='comtrade', frequency='M', hs_version='H6', partners=None):
    jobs = []
    # Breadth first: recent month, product, country, both directions.
    for period in periods:
        for hs in hs_codes:
            for iso in reporters:
                reporter = str(int(PRIORITY_REPORTERS[iso]['m49']))
                scopes = [partners or ['*']]
                if source == 'korea_customs':
                    if iso != 'KOR' or frequency != 'M':
                        raise ContractError('Korea source requires KOR monthly')
                    scopes = [[p] for p in (partners or ['0'] + sorted(KOREA_PARTNERS)) if p != '410']
                for flow in ('X', 'M'):
                    for selected in scopes:
                        meta = dict(source=source, reporter=reporter, reporter_iso3=iso, hs=hs,
                                    hs_version=f'HSK{period[:4]}' if source == 'korea_customs' and hs_version == 'HSK' else hs_version,
                                    period=period, frequency=frequency,
                                    requested_flows=[flow], value_basis='FOB' if flow == 'X' else 'CIF',
                                    scope_id='partner2_0_customs_C00_mot_0' if source == 'comtrade' else 'korea_item_country_net_trade',
                                    all_partners_verified=False, partners_disjoint=False)
                        jobs.append(make_job(meta, selected))
    return jobs


def public_parts(state, catalogue, *, as_of, monitor=None):
    groups = {}
    for jid, partition in state.get('data', {}).items():
        meta = partition['meta']
        status = state['jobs'][jid]
        # Never mix denominator and partner refresh vintages. Korea's one-cell
        # jobs combine only when all statistical fields AND refresh cycle match.
        key = tuple(meta[k] for k in ('source', 'reporter', 'hs', 'hs_version', 'frequency', 'period', 'scope_id', 'value_basis')) + (status['last_success_cycle'],)
        group = groups.setdefault(key, {'meta': dict(meta), 'rows': [], 'acquisition': []})
        group['acquisition'].append({'job_id': jid, **status, 'retrieved_at': meta.get('retrieved_at')})
        for flow, block in partition['flows'].items():
            group['rows'].extend({'partner': r['partner'], 'flow': flow, 'period': meta['period'],
                                  'metrics': r['metrics'], 'quality': r['quality']} for r in block['rows'])
            world = {k: v['world_total'] for k, v in block['metrics'].items()}
            if any(v is not None for v in world.values()):
                quality = next((v['world_quality'] for v in block['metrics'].values() if v['world_quality'] is not None), {})
                group['rows'].append({'partner': '0', 'flow': flow, 'period': meta['period'], 'metrics': world, 'quality': quality})
    parts = []
    for group in groups.values():
        p = build_partition(group['meta'], group['rows'])
        p['acquisition'] = group['acquisition']
        p['latest_success_cycle'] = group['acquisition'][0]['last_success_cycle']
        for block in p['flows'].values():
            for r in block['rows']:
                r['exporter_iso3'] = ISO_BY_CODE.get(r['exporter'])
                r['importer_iso3'] = ISO_BY_CODE.get(r['importer'])
                r['partner_iso3'] = ISO_BY_CODE.get(r['partner'])
                # This is the exporter's restriction even in an import view.
                r['export_control'] = screen(exporter_iso3=r['exporter_iso3'], importer_iso3=r['importer_iso3'],
                                              hs=p['meta']['hs'], period=p['meta']['period'], frequency=p['meta']['frequency'],
                                              catalogue=catalogue, as_of=as_of, monitor=monitor)
        parts.append(p)
    return parts


def publish(state, out_dir, catalogue, *, as_of, monitor=None):
    out_dir = Path(out_dir)
    if not state.get('data') and (out_dir / 'index.json').exists():
        raise ContractError('cannot replace a published feed with empty state')
    entries = []
    for part in public_parts(state, catalogue, as_of=as_of, monitor=monitor):
        content = json.dumps(part, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        digest = sha256(content).hexdigest()
        name = 'parts/' + digest + '.json'
        if not (out_dir / name).exists():
            atomic_json(out_dir / name, part)
        meta = part['meta']
        counterparties = sorted({r['partner'] for b in part['flows'].values() for r in b['rows']}, key=int)
        entries.append({**{k: meta[k] for k in ('source', 'reporter', 'hs', 'hs_version', 'period', 'frequency', 'value_basis')},
                        'reporter_iso3': ISO_BY_CODE.get(meta['reporter']), 'partners': counterparties,
                        'flows': meta.get('requested_flows'), 'path': name,
                        'latest_success_cycle': part['latest_success_cycle'],
                        'retained_after_failure': any(a['status'] != 'ok' for a in part['acquisition'])})
    product_screens = {}
    for j in state.get('jobs', {}).values():
        m = j.get('query_meta', {})
        if 'X' not in m.get('requested_flows', []):
            continue
        key = (m['reporter'], m['hs'], m['period'], m['frequency'])
        product_screens[key] = {'reporter': m['reporter'], 'reporter_iso3': ISO_BY_CODE.get(m['reporter']),
                               'hs': m['hs'], 'period': m['period'], 'frequency': m['frequency'],
                               'export_control': screen(exporter_iso3=ISO_BY_CODE.get(m['reporter']), importer_iso3=None,
                                   hs=m['hs'], period=m['period'], frequency=m['frequency'], catalogue=catalogue,
                                   as_of=as_of, monitor=monitor)}
    manifest = {'schema': 'commodity-trade-bilateral-index-v1', 'generated_at': datetime.now(timezone.utc).isoformat(),
                'coverage': 'observed_partitions_only', 'entries': entries,
                'jobs': state.get('jobs', {}), 'export_control_coverage': coverage(catalogue),
                'policy_source_checks': monitor or {'status': 'not_checked'},
                'product_policy_screens': list(product_screens.values()),
                'note_ko': '연도·월, 직접 신고·상대국 신고, 물량·금액의 기준을 합치지 않습니다. 미확보는 0이 아닙니다.'}
    atomic_json(out_dir / 'index.json', manifest)
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--mode', choices=['preview', 'direct', 'gateway'], default='preview')
    p.add_argument('--source', choices=['comtrade', 'korea_customs'], default='comtrade')
    p.add_argument('--reporters', default='CHL,BRA,USA')
    p.add_argument('--hs', default='2603,7403,2709')
    p.add_argument('--hs-version', default='H6')
    p.add_argument('--partners', help='Comtrade codes, e.g. 0,682; omitted = all available partners')
    p.add_argument('--frequency', choices=['M', 'A'], default='M')
    today = date.today()
    prev = date(today.year, today.month, 1).toordinal() - 1
    p.add_argument('--end-period', default=date.fromordinal(prev).strftime('%Y%m'))
    p.add_argument('--months', type=int, default=3)
    p.add_argument('--period-strategy', choices=['calendar', 'observed'], default='calendar',
                   help='observed: query newest recorded panel months, not an inferred latest release')
    p.add_argument('--panel', type=Path, action='append',
                   help='observed strategy inputs; defaults to Comtrade and national priority panels')
    p.add_argument('--cycle', default=today.strftime('%Y-%m'))
    p.add_argument('--max-requests', type=int, default=12)
    p.add_argument('--interval', type=float, default=3)
    p.add_argument('--checkpoint', type=Path, required=True, help='persist outside public; restore across CI runs')
    p.add_argument('--out-dir', type=Path, default=PUBLIC / 'commodity_trade_bilateral_v1')
    p.add_argument('--controls', type=Path, default=PUBLIC / 'export_controls_v1.json')
    p.add_argument('--policy-monitor', type=Path)
    p.add_argument('--checkpoint-seed-out', type=Path, help='optional non-secret handoff state; never under public/')
    p.add_argument('--plan-only', action='store_true')
    args = p.parse_args(argv)
    if 'public' in args.checkpoint.resolve().parts:
        p.error('checkpoint must not live under public/')
    if args.checkpoint_seed_out and 'public' in args.checkpoint_seed_out.resolve().parts:
        p.error('handoff checkpoint must not live under public/')
    if not 1 <= args.months <= 24 or not 0 <= args.max_requests <= 1000 or not 0 <= args.interval <= 30:
        p.error('invalid month/request/interval bound')
    reporters = list(PRIORITY_REPORTERS) if args.reporters == 'all' else args.reporters.split(',')
    if any(r not in PRIORITY_REPORTERS for r in reporters):
        p.error('unknown reporter; use ISO3')
    hs_codes = sorted({m['hs'] for m in PRIORITY_COMMODITIES.values()} | {'2604', '2607', '2608', '7403'}) if args.hs == 'all' else args.hs.split(',')
    periods = months_back(args.end_period, args.months) if args.frequency == 'M' else [period_key(args.end_period, 'A')]
    jobs = plan_jobs(reporters, hs_codes, periods, source=args.source, frequency=args.frequency,
                     hs_version=args.hs_version, partners=args.partners.split(',') if args.partners else None)
    if args.period_strategy == 'observed':
        if args.source != 'comtrade' or args.frequency != 'M':
            p.error('observed panel dates are Comtrade monthly query hints only')
        panels = [read_json(path) for path in (args.panel or [PUBLIC / name for name in PANEL_NAMES])]
        targets = observed_targets(panels, reporters, hs_codes, end_period=args.end_period, month_count=args.months)
        jobs = []
        for iso, hs, flow, period in targets:
            jobs.extend(j for j in plan_jobs([iso], [hs], [period], hs_version=args.hs_version,
                        partners=args.partners.split(',') if args.partners else None)
                        if j['meta']['requested_flows'] == [flow])
        periods = sorted({j['meta']['period'] for j in jobs}, reverse=True)
    if args.plan_only:
        print(json.dumps({'jobs': len(jobs), 'max_requests_this_run': args.max_requests, 'periods': periods,
                          'period_strategy': args.period_strategy,
                          'reporters_with_jobs': sorted({j['meta']['reporter_iso3'] for j in jobs})}))
        return 0
    with single_writer(str(args.checkpoint) + '.lock'):
        state = read_json(args.checkpoint, {'schema': 'bilateral-checkpoint-v1', 'jobs': {}, 'data': {}})
        if not args.checkpoint.exists() and (args.out_dir / 'index.json').exists():
            raise ContractError('published feed exists; restore checkpoint before refreshing')
        # Older local checkpoints omitted query metadata which existed in the
        # published index. Restore metadata only after validating job identity;
        # never import observations/status/last_success_cycle from a public file.
        prior = read_json(args.out_dir / 'index.json', {}).get('jobs', {})
        for jid, status in state.get('jobs', {}).items():
            old = prior.get(jid, {})
            if not old.get('query_meta') and jid in state.get('data', {}):
                meta = state['data'][jid]['meta']
                # Only recover a wildcard scope if its full identity matches.
                if make_job(meta, ['*'])['id'] == jid:
                    old = {'query_meta': meta, 'partners': ['*']}
            if not status.get('query_meta') and old.get('query_meta') and old.get('partners'):
                if make_job(old['query_meta'], old['partners'])['id'] == jid:
                    status['query_meta'], status['partners'] = old['query_meta'], old['partners']
        provider = Provider(args.mode, interval=args.interval)
        stop_reason = None
        if args.fetch:
            r = execute_plan(jobs, state, cycle=args.cycle, max_requests=args.max_requests, provider=provider,
                             checkpoint=lambda s: atomic_json(args.checkpoint, s))
            state = r['state']
            stop_reason = r['stop_reason']
        # Metadata-only migration for prior checkpoints; never fabricates jobs
        # or observations that were not attempted.
        for j in jobs:
            if j['id'] in state['jobs']:
                state['jobs'][j['id']].setdefault('query_meta', j['meta'])
                state['jobs'][j['id']].setdefault('partners', j['partners'])
        atomic_json(args.checkpoint, state)
        catalogue = read_json(args.controls)
        if not isinstance(catalogue, dict) or not isinstance(catalogue.get('controls'), list):
            raise ContractError('export-control catalogue missing or invalid; publication stopped')
        catalogue = with_documents(catalogue, read_json(ROOT / 'config/export_policy_documents.json', {'documents': []}))
        manifest = publish(state, args.out_dir, catalogue, as_of=today.isoformat(),
                           monitor=read_json(args.policy_monitor) if args.policy_monitor else None)
        if args.checkpoint_seed_out:
            atomic_json(args.checkpoint_seed_out, state)
        counts = {}
        for v in state['jobs'].values():
            counts[v['status']] = counts.get(v['status'], 0) + 1
        print(json.dumps({'planned_jobs': len(jobs), 'network_requests': provider.calls,
                          'published_parts': len(manifest['entries']), 'statuses': counts,
                          'stop_reason': stop_reason}, ensure_ascii=False))
        return 3 if stop_reason == 'rate_limited' else 2 if stop_reason else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError):
        print('{"status":"pipeline_error","detail":"validation_or_storage_failure; existing manifest retained"}')
        raise SystemExit(1)

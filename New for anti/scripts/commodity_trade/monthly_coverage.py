"""Auditable priority-panel coverage and source-month query hints.

National and Comtrade totals remain separate. Hints select requests only: they
never supply bilateral observations, World denominators or HS revision evidence.
The broader JODI/proxy bundle is deliberately outside this priority-panel count.
"""
from datetime import datetime, timezone
import argparse
import math
from pathlib import Path
import re

from bilateral import ContractError, period_key
from pipeline_store import atomic_json, read_json
from priority_universe import PRIORITY_REPORTERS

PUBLIC = Path(__file__).resolve().parents[2] / 'public/data'
PANEL_NAMES = ('commodity_trade_comtrade_priority_v1.json',
               'commodity_trade_national_priority_v1.json')


def observed_cells(panels):
    """Numeric zero counts; null, bool, invalid month and non-HS cells do not."""
    for panel in panels:
        if not isinstance(panel, dict) or panel.get('schema_version') not in {
                'commodity-trade-comtrade-priority-v1', 'commodity-trade-national-priority-v1'}:
            raise ContractError('unknown priority panel schema')
        for iso, reporter in panel.get('reporters', {}).items():
            if iso not in PRIORITY_REPORTERS:
                continue
            for direction, block in reporter.get('flows', {}).items():
                if direction not in {'exports', 'imports'}:
                    continue
                for commodity, series in block.get('commodities', {}).items():
                    hs = series.get('hs')
                    if not isinstance(hs, str) or not re.fullmatch(r'\d{4}|\d{6}', hs):
                        continue
                    for point in series.get('points', []):
                        value, month = point.get('value'), point.get('month')
                        if (isinstance(value, bool) or not isinstance(value, (int, float))
                                or not math.isfinite(value) or value < 0
                                or not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month)):
                            continue
                        try:
                            period = period_key(month.replace('-', ''), 'M')
                        except ContractError:
                            continue
                        yield {'reporter_iso3': iso, 'hs': hs, 'commodity_id': commodity,
                               'flow': 'X' if direction == 'exports' else 'M', 'period': period,
                               'source': point.get('source') or panel.get('source'),
                               'unit': point.get('unit'), 'panel_schema': panel['schema_version']}


def observed_targets(panels, reporters, hs_codes, *, end_period, month_count):
    """Breadth-first country round-robin, then requested HS/flow, then history.

Months are the newest *observed* months at/before end_period, not a calendar
window. National-source dates are only Comtrade query candidates, not proof of
Comtrade availability. No omitted direction is fabricated.
"""
    period_key(end_period, 'M')
    grouped = {}
    for c in observed_cells(panels):
        if c['reporter_iso3'] in reporters and c['hs'] in hs_codes and c['period'] <= end_period:
            key = c['reporter_iso3'], c['hs'], c['flow']
            grouped.setdefault(key, set()).add(c['period'])
    buckets = {}
    for iso in reporters:
        series = []
        for hs in hs_codes:
            for flow in ('X', 'M'):
                periods = sorted(grouped.get((iso, hs, flow), ()), reverse=True)[:month_count]
                series.append([(iso, hs, flow, period) for period in periods])
        buckets[iso] = [s[depth] for depth in range(month_count) for s in series if depth < len(s)]
    return [buckets[iso][i] for i in range(max(map(len, buckets.values()), default=0))
            for iso in reporters if i < len(buckets[iso])]


def coverage_report(panels, index):
    countries = {iso: {'name_ko': m['name_ko'], 'world_total_series': [],
                       'bilateral_series': [], 'bilateral_attempt_statuses': {}}
                 for iso, m in PRIORITY_REPORTERS.items()}
    groups = {}
    for c in observed_cells(panels):
        key = tuple(c[k] for k in ('reporter_iso3', 'panel_schema', 'source', 'hs', 'flow', 'unit'))
        groups.setdefault(key, set()).add(c['period'])
    for (iso, schema, source, hs, flow, unit), periods in groups.items():
        countries[iso]['world_total_series'].append({'panel_schema': schema, 'source': source,
            'hs': hs, 'flow': flow, 'unit': unit, 'months': sorted(periods), 'latest_period': max(periods)})
    for entry in index.get('entries', []):
        iso = entry.get('reporter_iso3')
        if iso not in countries or entry.get('frequency') != 'M' or not entry.get('partners'):
            continue
        countries[iso]['bilateral_series'].append({k: entry.get(k) for k in (
            'source', 'hs', 'hs_version', 'period', 'flows', 'value_basis', 'path', 'retained_after_failure')})
    for j in index.get('jobs', {}).values():
        m = j.get('query_meta', {})
        iso = m.get('reporter_iso3')
        if iso in countries and m.get('frequency') == 'M':
            counts = countries[iso]['bilateral_attempt_statuses']
            counts[j['status']] = counts.get(j['status'], 0) + 1
    for c in countries.values():
        c['world_total_available'] = bool(c['world_total_series'])
        c['bilateral_available'] = bool(c['bilateral_series'])
        c['bilateral_coverage'] = 'partial_observed' if c['bilateral_available'] else 'not_acquired'
        c['next_step'] = ('expand_product_month_flow_coverage' if c['bilateral_available'] else
                          'acquire_reporter_bilateral' if c['world_total_available'] else 'verify_source_availability')
        c['world_latest_period'] = max((s['latest_period'] for s in c['world_total_series']), default=None)
        c['bilateral_latest_period'] = max((s['period'] for s in c['bilateral_series']), default=None)
    return {'schema': 'commodity-trade-priority-coverage-v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'scope': 'priority_panels_and_monthly_bilateral_only; excludes_JODI_and_proxies',
            'inputs': {'panels_generated_at': [p.get('generated_at') for p in panels],
                       'bilateral_generated_at': index.get('generated_at')},
            'counts': {'target_reporters': len(countries),
                       'world_total_reporters': sum(c['world_total_available'] for c in countries.values()),
                       'bilateral_reporters': sum(c['bilateral_available'] for c in countries.values()),
                       'any_monthly_reporters': sum(c['world_total_available'] or c['bilateral_available'] for c in countries.values())},
            'countries': countries,
            'note_ko': '국가 수는 하나 이상의 수치가 있는 범위입니다. 모든 상품·월·방향 확보 또는 운영 배포를 뜻하지 않습니다. 총량을 상대국별 수치로 추정하지 않습니다.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=PUBLIC)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    panels = [read_json(args.data_dir / name) for name in PANEL_NAMES]
    index = read_json(args.data_dir / 'commodity_trade_bilateral_v1/index.json')
    report = coverage_report(panels, index)
    atomic_json(args.out or args.data_dir / 'commodity_trade_coverage_v1.json', report)
    import json
    print(json.dumps(report['counts']))


if __name__ == '__main__':
    main()

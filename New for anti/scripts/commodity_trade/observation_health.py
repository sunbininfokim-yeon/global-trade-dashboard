"""Product/flow freshness without mixing sources, units or reporting periods."""
from priority_universe import PRIORITY_COMMODITIES


def history_gaps(months):
    """Absent observations, not proof of nonzero trade or failed reporting."""
    if not months:
        return []
    start, end = min(months), max(months)
    lo = int(start[:4])*12 + int(start[4:])-1
    hi = int(end[:4])*12 + int(end[4:])-1
    return [f'{i//12:04d}{i%12+1:02d}' for i in range(lo,hi+1)
            if f'{i//12:04d}{i%12+1:02d}' not in months]


def product_health(coverage):
    expected_hs = sorted({m['hs'] for m in PRIORITY_COMMODITIES.values()} | {'2604', '2607', '2608', '7403'})
    result = []
    for iso, country in coverage.get('countries', {}).items():
        worlds = country.get('world_total_series', [])
        bilateral = country.get('bilateral_series', [])
        hs_codes = sorted(set(expected_hs) | {s['hs'] for s in worlds + bilateral})
        for hs in hs_codes:
            for flow in ('X', 'M'):
                w = [s for s in worlds if s['hs'] == hs and s['flow'] == flow]
                b = [s for s in bilateral if s['hs'] == hs and flow in (s.get('flows') or [])]
                wm = {m for s in w for m in s.get('months', [])}
                bm = {s['period'] for s in b}
                result.append(dict(reporter=iso, hs=hs, flow=flow,
                    world_latest_period=max(wm, default=None),
                    bilateral_latest_period=max(bm, default=None),
                    latest_common_period=max(wm & bm, default=None),
                    world_sources=[{k: s.get(k) for k in (
                        'source', 'panel_schema', 'unit', 'latest_period', 'latest_eligible_period',
                        'publication_unreviewed_months', 'publication_held_months')} | {
                            'observed_history_gaps':history_gaps(s.get('months',[]))} for s in w],
                    bilateral_sources=[{k: s.get(k) for k in (
                        'source', 'hs_version', 'value_basis', 'period', 'retained_after_failure')} for s in b],
                    # Common date alone is not evidence of matching units/revisions.
                    comparison_status='date_alignment_only_not_a_denominator',
                    same_period_latest=bool(wm and bm and max(wm) == max(bm))))
    return result

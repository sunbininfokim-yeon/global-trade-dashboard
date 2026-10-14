"""A failed/partial source refresh cannot erase known-good reporter months."""
from copy import deepcopy
from world_link import link_country_world, merge_reporters


def preserve_monthly(previous, refreshed):
    retained = []
    for sector, old in previous.items():
        if sector not in refreshed:
            continue
        for cid, old_c in old.get('commodities', {}).items():
            c = refreshed[sector].setdefault('commodities', {}).setdefault(cid, deepcopy(old_c))
            for iso, old_country in old_c.get('countries', {}).items():
                incoming = c.setdefault('countries', {}).get(iso)
                if not incoming or not incoming.get('points'):
                    c['countries'][iso] = deepcopy(old_country)
                    c['countries'][iso]['refresh_status'] = 'retained_previous_no_new_observations'
                    retained.append([sector,cid,iso])
                else:
                    by_month = {p['month']: p for p in old_country.get('points', [])}
                    by_month.update({p['month']: p for p in incoming['points']})
                    incoming['points'] = [by_month[m] for m in sorted(by_month)[-12:]]
                country = c['countries'][iso]
                country['latest_available_month'] = max((p['month'] for p in country.get('points', [])), default=None)
            points = [p for r in c.get('countries', {}).values() for p in r.get('points', [])]
            c['country_count'] = len(c.get('countries', {}))
            if points:
                c['latest_available_month'] = max(p['month'] for p in points)
                c['stage2_status'] = 'monthly_available'
                if sector == 'agri_trade':
                    countries = c['countries']
                    c['world_link'] = {**merge_reporters(cid, {i:r['points'] for i,r in countries.items()},
                        units={i:r['points'][-1]['unit'] for i,r in countries.items() if r.get('points')}),
                        **link_country_world(cid,countries,usa_is_export_to_world='USA' in countries)}
                    if 'USA' in countries:
                        c['world_link']['usa_series_mode'] = 'reporter_export_to_world'
    return retained

"""Offline, reversible repair of legacy JODI observations; never a fresh fetch.

Default is dry-run. --write requires a separate backup location and refuses to
overwrite that backup. Conversion factors are archived as metadata, not zeros.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from build_monthly import PUBLIC, BOARD_PATH, _atomic_write_json, _validate_monthly_contract
from series_quality import annotate_monthly_payload, annotate_country_series
from world_link import link_country_world, merge_reporters


def repair(payload):
    result = copy.deepcopy(payload)
    removed = corrected = 0
    for sector in result['sectors'].values():
        for group in ('commodities', 'supplemental_commodities'):
            for cid, block in sector.get(group, {}).items():
                countries = block.get('countries', {})
                for country in countries.values():
                    points = []
                    for p in country.get('points', []):
                        if p.get('unit') == 'CONVBBL':
                            archived = copy.deepcopy(p)
                            archived.pop('normalized', None)
                            archived['exclusion_reason'] = 'conversion_factor_not_trade_volume'
                            country.setdefault('excluded_conversion_factors', []).append(archived)
                            removed += 1
                        else:
                            if p.get('unit') == 'KTONS' and p.get('normalized', {}).get('value') != p['value'] * 1_000_000:
                                corrected += 1
                            points.append(p)
                    country['points'] = points
                    country['point_count'] = len(points)
                    country['latest_available_month'] = max((p['month'] for p in points), default=None)
                    annotate_country_series(country, result['calendar_month_now'])
                # Keep unavailable reporters explicitly outside the available set.
                for iso in list(countries):
                    if not countries[iso].get('points'):
                        block.setdefault('unavailable_countries', {})[iso] = countries.pop(iso)
                        block['unavailable_countries'][iso]['status'] = 'no_valid_trade_observations'
                block['country_count'] = len(countries)
                block['latest_available_month'] = max((c['latest_available_month'] for c in countries.values()), default=None)
                block['default_month'] = block['latest_available_month']
                if not countries and block.get('stage2_status') != 'monthly_planned':
                    block['stage2_status'] = 'monthly_planned'
                if 'world_link' in block:
                    usa = block['world_link'].get('usa_series_mode') == 'reporter_export_to_world'
                    units = {iso: c['points'][-1]['unit'] for iso, c in countries.items()}
                    block['world_link'] = {
                        **merge_reporters(cid, {i:c['points'] for i,c in countries.items()}, units=units),
                        **link_country_world(cid, countries, usa_is_export_to_world=usa),
                    }
                    if usa:
                        block['world_link']['usa_series_mode'] = 'reporter_export_to_world'
    # Preserve acquisition timestamps: this operation does not refresh data.
    result['quality_contract'] = annotate_monthly_payload(result['sectors'], result['calendar_month_now'])
    for sector in result['sectors'].values():
        if sector.get('supplemental_commodities'):
            annotate_monthly_payload({'extra': {'commodities': sector['supplemental_commodities']}}, result['calendar_month_now'])
    if removed or corrected:
        result['unit_repair'] = {
            'version': 'jodi-units-v1', 'is_source_refresh': False,
            'conversion_factors_excluded': removed, 'ktons_normalizations_corrected': corrected,
            'note': 'Original values retained; excluded factors archived in country metadata. No replacement volumes inferred.',
        }
    return result, {'conversion_factors_excluded': removed, 'ktons_normalizations_corrected': corrected}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=PUBLIC / 'commodity_trade_monthly_v1.json')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--backup', type=Path)
    args = ap.parse_args()
    raw = args.input.read_bytes()
    old = json.loads(raw)
    new, stats = repair(old)
    _validate_monthly_contract(new, json.loads(BOARD_PATH.read_text()))
    print(json.dumps({**stats, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'changed': old != new}))
    if args.write and new != old:
        if not args.backup or args.backup.resolve() == args.input.resolve():
            ap.error('--write requires a distinct --backup path')
        with args.backup.open('xb') as stream:
            stream.write(raw)
        _atomic_write_json(args.input, new)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

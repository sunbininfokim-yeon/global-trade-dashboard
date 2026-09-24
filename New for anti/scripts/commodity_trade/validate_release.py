"""Offline release gate: actual generated assets, not just unit tests."""
import argparse
import json
import math
from copy import deepcopy
from pathlib import Path

from build_monthly import PUBLIC, _validate_monthly_contract
from validate_bilateral_public import validate as validate_bilateral
from monthly_coverage import coverage_report
from world_link import to_kg
from preview_quality import annotate_preview_series


def validate_preview_publication(payload):
    held = 0
    for reporter in payload.get('reporters', {}).values():
        for flow in reporter.get('flows', {}).values():
            for series in flow.get('commodities', {}).values():
                expected = deepcopy(series)
                annotate_preview_series(expected)
                if (series.get('publication_summary') != expected['publication_summary']
                        or series.get('series_quality', {}).get('flags') != expected['series_quality']['flags']
                        or any(p.get('publication') != q.get('publication')
                               for p, q in zip(series.get('points', []), expected.get('points', [])))):
                    raise ValueError('Preview publication metadata missing or stale; run --annotate-only')
                held += len(expected['publication_summary']['held_months'])
    return held


def validate_bulletin(data):
    required = {'schema_version':'commodity-trade-saudi-bulletin-v1', 'reporter_iso3':'SAU',
                'series_id':'oil_exports_aggregate_value', 'flow':'X', 'partner':'WORLD'}
    if any(data.get(k) != v for k,v in required.items()):
        raise ValueError('Saudi bulletin identity mismatch')
    if data.get('hs') is not None or data.get('bilateral_available') is not False or data.get('quantity_available') is not False:
        raise ValueError('Saudi bulletin must not imply crude quantities or partners')
    months = []
    for point in data.get('points', []):
        oil, total = point.get('value'), point.get('total_goods_exports_sar_million')
        if point.get('unit') != 'SAR_million' or not all(type(v) in (int,float) and math.isfinite(v) and v >= 0 for v in (oil,total)) or oil > total:
            raise ValueError('invalid bulletin monetary value')
        share = point.get('share_of_total_goods_export_value')
        if (total == 0 and share is not None) or (total > 0 and (not isinstance(share,(int,float)) or not math.isclose(share,oil/total))):
            raise ValueError('bulletin oil-value share mismatch')
        months.append(point['month'])
    if not months or months != sorted(set(months)) or max(months) != data.get('latest_available_month'):
        raise ValueError('invalid bulletin month coverage')


def validate(data_dir):
    data_dir = Path(data_dir)
    def read(name):
        return json.loads((data_dir/name).read_text())
    monthly = read('commodity_trade_monthly_v1.json')
    _validate_monthly_contract(monthly, read('commodity_trade_board_v1.json'))
    factors = bad_mass = 0
    def walk(obj):
        nonlocal factors, bad_mass
        if isinstance(obj,dict):
            # Archived excluded factors are metadata, not published observations.
            for point in obj.get('points', []):
                factors += point.get('unit') == 'CONVBBL'
                expected = to_kg(point.get('value'), point.get('unit'))
                if expected is not None:
                    normalized = point.get('normalized') or {}
                    value = normalized.get('value')
                    bad_mass += (normalized.get('unit') != 'kg' or not isinstance(value,(int,float))
                                 or not math.isfinite(value) or not math.isclose(value,expected,rel_tol=1e-12))
            for key,value in obj.items():
                if key != 'excluded_conversion_factors':
                    walk(value)
        elif isinstance(obj,list):
            for item in obj:
                walk(item)
    walk(monthly)
    if factors or bad_mass:
        raise ValueError(f'legacy monthly invalid: factors={factors}, bad_mass={bad_mass}')
    bulletin = read('commodity_trade_saudi_bulletin_v1.json')
    validate_bulletin(bulletin)
    national = read('commodity_trade_national_priority_v1.json')
    comtrade = read('commodity_trade_comtrade_priority_v1.json')
    preview_held = validate_preview_publication(comtrade)
    index = read('commodity_trade_bilateral_v1/index.json')
    bilateral = validate_bilateral(data_dir/'commodity_trade_bilateral_v1')
    coverage = coverage_report([comtrade,national], index)
    saved = read('commodity_trade_coverage_v1.json')
    if saved['counts'] != coverage['counts'] or saved['countries'] != coverage['countries']:
        raise ValueError('coverage asset is stale')
    crude = national['reporters']['SAU']['flows']['exports']['commodities']['crude_oil']
    return {'status':'pass', 'monthly_invalid_conversion_factors':factors, 'monthly_bad_mass_normalization':bad_mass,
            'priority_coverage':coverage['counts'], 'bilateral':bilateral,
            'preview_held_months':preview_held,
            'saudi': {'bulletin_oil_value_latest':bulletin['latest_available_month'],
                      'hs2709_world_latest':crude['latest_available_month'],
                      'hs2709_bilateral_available':any(e.get('reporter_iso3')=='SAU' and e.get('hs')=='2709' and e.get('partners') for e in index['entries'])}}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir',type=Path,default=PUBLIC)
    args = ap.parse_args()
    print(json.dumps(validate(args.data_dir),ensure_ascii=False,indent=2))

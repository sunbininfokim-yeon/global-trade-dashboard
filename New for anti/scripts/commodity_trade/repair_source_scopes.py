"""Offline B02/B07 reclassification, not acquisition or numerical imputation.

Dry-run by default. --write requires a new backup path. Exact source product
codes move observations to their proper supplemental bucket; values, units,
months and acquisition timestamps stay unchanged. Ambiguous values are never
split into guessed components.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from build_monthly import PUBLIC, BOARD_PATH, _atomic_write_json, _validate_monthly_contract
from series_quality import annotate_monthly_payload
from sources.jodi_oil import PRODUCT_TO_COMMODITY, product_scope
from world_link import link_country_world, merge_reporters

LABELS = {
    'gasoil_diesel': '가스·디젤유 (JODI GASDIES)',
    'motor_gasoline': '자동차 휘발유 (JODI MOTORGAS)',
    'jet_kerosene': '등유·항공유 (JODI JETKERO)',
    'residual_fuel_oil': '잔사 연료유 (JODI RESFUEL)',
    'lpg': 'LPG (JODI LPG)',
    'crude_ngl_other': '원유·NGL·기타 합계 (JODI TOTCRUDE)',
}


def refresh_block(cid, block):
    countries = block.get('countries', {})
    for iso in list(countries):
        country = countries[iso]
        pts = country.get('points') or []
        country['point_count'] = len(pts)
        country['latest_available_month'] = max((p['month'] for p in pts), default=None)
        if not pts:
            archived = block.setdefault('unavailable_countries', {})
            if iso in archived and archived[iso] != country:
                raise ValueError('conflicting unavailable country metadata')
            archived[iso] = countries.pop(iso)
            archived[iso]['status'] = 'no_exact_source_product_observations'
    block['country_count'] = len(countries)
    block['latest_available_month'] = max((c['latest_available_month'] for c in countries.values()),default=None)
    block['default_month'] = block['latest_available_month']
    if not countries:
        block['stage2_status'] = 'monthly_planned'
    if 'world_link' in block:
        usa = block['world_link'].get('usa_series_mode') == 'reporter_export_to_world'
        block['world_link'] = {
            **merge_reporters(cid,{i:c['points'] for i,c in countries.items()},
                              units={i:c['points'][-1]['unit'] for i,c in countries.items()}),
            **link_country_world(cid,countries,usa_is_export_to_world=usa),
        }
        if usa:
            block['world_link']['usa_series_mode'] = 'reporter_export_to_world'


def repair(payload):
    result = copy.deepcopy(payload)
    moved = Counter()
    for sector_name, sector in result['sectors'].items():
        moves = []
        for group in ('commodities','supplemental_commodities'):
            for cid, block in list(sector.get(group,{}).items()):
                for iso, country in list(block.get('countries',{}).items()):
                    kept = []
                    for p in country.get('points') or []:
                        if p.get('source') == 'cochilco_bulletin' and p.get('unit') == 'kMT_cu_content':
                            p.update({'hs_bridge':None,'hs_relation':'source_product_not_hs_equivalent',
                                      'measurement_basis':'contained_copper_mass',
                                      'comparison_scope':'COCHILCO:copper_total_shipments:contained_copper_mass'})
                        product = p.get('product_code')
                        expected = PRODUCT_TO_COMMODITY.get(product)
                        if p.get('source') != 'jodi_oil':
                            kept.append(p)
                            continue
                        if expected is None:
                            raise ValueError(f'unknown JODI product {product!r}; raw source recheck required')
                        # Scope annotations only; no value/unit/month edits.
                        p.update(product_scope(product))
                        if expected != cid:
                            moves.append((expected,iso,country,p))
                            moved[product] += 1
                        else:
                            kept.append(p)
                    country['points'] = kept
                if cid == 'petroleum_products' and any(p.get('source') == 'jodi_oil'
                        for c in block.get('countries',{}).values() for p in c.get('points',[])):
                    block['hs_stems'] = []
                    block['source_product_scope'] = ['TOTPRODS']
        for cid,iso,country,p in moves:
            supplements = sector.setdefault('supplemental_commodities',{})
            target = supplements.setdefault(cid,{
                'commodity_id':cid,'sector':sector_name,'label_ko':LABELS.get(cid,cid),
                'stage2_status':'monthly_partial','source_primary':'jodi_oil',
                'hs_stems':[],'source_product_scope':[p['product_code']],
                'scope_note':'Exact JODI source product, not an HS aggregate. Reclassified, not freshly collected.',
                'countries':{},
            })
            dest = target['countries'].setdefault(iso,{
                **{k:copy.deepcopy(v) for k,v in country.items() if k not in {'points','series_quality'}},
                'points':[],
            })
            key = (p['month'],p.get('source'),p.get('product_code'),p.get('unit'))
            duplicate = next((q for q in dest['points'] if
                (q['month'],q.get('source'),q.get('product_code'),q.get('unit')) == key),None)
            if duplicate is not None:
                if duplicate.get('value') != p.get('value'):
                    raise ValueError('conflicting reclassified observation; refusing overwrite')
            else:
                dest['points'].append(p)
                dest['points'].sort(key=lambda q:q['month'])
        for group in ('commodities','supplemental_commodities'):
            for cid, block in sector.get(group,{}).items():
                refresh_block(cid,block)
    ref = result['calendar_month_now']
    result['quality_contract'] = annotate_monthly_payload(result['sectors'],ref)
    for sector in result['sectors'].values():
        annotate_monthly_payload({'extra':{'commodities':sector.get('supplemental_commodities',{})}},ref)
    if moved:
        result['source_scope_repair'] = {
            'version':'source-scopes-602-v1','is_source_refresh':False,
            'reclassified_by_product':dict(sorted(moved.items())),
            'note':'Raw values/units/months/acquisition dates retained; no inferred petroleum total.',
        }
    return result, {'reclassified_by_product':dict(sorted(moved.items())), 'reclassified_points':sum(moved.values())}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,default=PUBLIC/'commodity_trade_monthly_v1.json')
    ap.add_argument('--board',type=Path,default=BOARD_PATH)
    ap.add_argument('--write',action='store_true')
    ap.add_argument('--backup',type=Path)
    args=ap.parse_args()
    raw=args.input.read_bytes()
    before=json.loads(raw)
    after,stats=repair(before)
    _validate_monthly_contract(after,json.loads(args.board.read_text()))
    print(json.dumps({**stats,'changed':before!=after,'source_sha256':hashlib.sha256(raw).hexdigest()},ensure_ascii=False))
    if args.write and before!=after:
        if not args.backup or args.backup.resolve()==args.input.resolve():
            ap.error('--write requires a distinct new --backup path')
        with args.backup.open('xb') as stream:
            stream.write(raw)
        _atomic_write_json(args.input,after)
    return 0


if __name__=='__main__':
    raise SystemExit(main())

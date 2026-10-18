"""Bounded, offline native-value reconciliation against preserved source files.

No credentials, fetching, publication writes, unit guessing or revised-value
replacement. Source-value differences require revision review; no overlap is
unverified, never a zero. Re-run with separately acquired official snapshots.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook
from country_codes import iso2_to_iso3
from sources.jodi_oil import PRODUCT_TO_COMMODITY, _parse_value
from sources.usa_ers_agri import _parse_sheet


def observations(payload):
    for sector in payload.get('sectors',{}).values():
        for group in ('commodities','supplemental_commodities'):
            for cid,block in sector.get(group,{}).items():
                for iso,country in block.get('countries',{}).items():
                    for point in country.get('points',[]):
                        yield cid,iso,point


def fingerprint(path):
    return {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}


def reconcile(payload, *, jodi_files=(), ers_workbook=None):
    raw_jodi={}
    ambiguous=set()
    for file in jodi_files:
        with Path(file).open(newline='',encoding='utf-8-sig') as stream:
            for row in csv.DictReader(stream):
                if row.get('FLOW_BREAKDOWN')!='TOTEXPSB':
                    continue
                iso=iso2_to_iso3(row.get('REF_AREA') or '')
                if not iso:
                    continue
                key=(iso,row.get('TIME_PERIOD'),row.get('ENERGY_PRODUCT'),row.get('UNIT_MEASURE'))
                value=_parse_value(row.get('OBS_VALUE'))
                if value is None:
                    continue
                if key in raw_jodi and raw_jodi[key]!=value:
                    ambiguous.add(key)
                raw_jodi[key]=value
    raw_ers={}
    if ers_workbook:
        wb=load_workbook(ers_workbook,read_only=True,data_only=True)
        try:
            for ws in wb.worksheets:
                for p in _parse_sheet(ws):
                    raw_ers[(p['product_code'],p['month'])]=p['value']
        finally:
            wb.close()
    outcomes=[]
    counts=Counter()
    for cid,iso,p in observations(payload):
        source=p.get('source')
        if source not in {'jodi_oil','ers_fatus_top10_world_total'}:
            continue
        status='source_not_supplied'
        expected=None
        expected_cid=None
        if source=='jodi_oil' and jodi_files:
            key=(iso,p.get('month'),p.get('product_code'),p.get('unit'))
            expected=raw_jodi.get(key)
            expected_cid=PRODUCT_TO_COMMODITY.get(p.get('product_code'))
            status='source_key_ambiguous' if key in ambiguous else 'source_observation_not_present'
        elif source=='ers_fatus_top10_world_total' and ers_workbook:
            # This adapter's observations are USA export-to-World metric tons.
            if iso=='USA' and p.get('unit')=='metric_tons':
                expected=raw_ers.get((cid,p.get('month')))
                status='source_month_not_in_current_workbook'
            else:
                status='measurement_scope_mismatch'
        if expected is not None and status!='source_key_ambiguous':
            value=p.get('value')
            if type(value) not in (int,float) or not math.isfinite(value):
                status='invalid_published_value'
            elif not math.isclose(value,expected,rel_tol=1e-12,abs_tol=1e-8):
                status='source_value_changed_requires_revision_review'
            else:
                status='native_value_matches'
        classification_error=source=='jodi_oil' and expected_cid is not None and expected_cid!=cid
        counts[f'{source}:{status}']+=1
        if classification_error:
            counts['jodi_oil:classification_mismatch']+=1
        if status!='native_value_matches' or classification_error:
            outcomes.append({'source':source,'commodity_id':cid,'iso3':iso,'month':p.get('month'),
                             'product_code':p.get('product_code'),'unit':p.get('unit'),
                             'published_value':p.get('value'),'current_source_value':expected,
                             'status':status,'classification_mismatch':classification_error,
                             'expected_commodity_id':expected_cid})
    return {'counts':dict(sorted(counts.items())),'review_items':outcomes,
            'source_rows_indexed':{'jodi_oil':len(raw_jodi),'ers_world_total':len(raw_ers)},
            'ambiguous_jodi_keys':len(ambiguous),
            'scope_note':'Same source/product/reporter/month/native unit only. Current-source differences are not automatically historical parser errors.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--published',type=Path,required=True)
    ap.add_argument('--jodi-csv',type=Path,nargs='*',default=[])
    ap.add_argument('--ers-workbook',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if any('.partial' in path.name or '.tmp' in path.name for path in args.jodi_csv):
        ap.error('incomplete transport snapshots must not be reconciliation inputs')
    if args.output.resolve()==args.published.resolve():
        ap.error('reconciliation output must not overwrite published observations')
    data=json.loads(args.published.read_text())
    report=reconcile(data,jodi_files=args.jodi_csv,ers_workbook=args.ers_workbook)
    report.update({'schema_version':'commodity-source-reconciliation-v1',
        'checked_at':datetime.now(timezone.utc).isoformat(),'source_fetch_performed_by_this_command':False,
        'published_input':fingerprint(args.published),
        'source_files':[fingerprint(p) for p in [*args.jodi_csv,*([args.ers_workbook] if args.ers_workbook else [])]]})
    # Explicitly refuse overwriting an earlier audit record.
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'counts':report['counts'],'review_items':len(report['review_items']),
                      'source_rows_indexed':report['source_rows_indexed']},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())

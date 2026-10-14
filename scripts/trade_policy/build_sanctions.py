"""Bounded public CSL snapshot -> selected legal entities. No fuzzy legal conclusions."""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
URL = 'https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv'
REQUIRED = {'_id', 'name', 'source', 'alt_names', 'addresses', 'start_date', 'end_date', 'source_list_url', 'source_information_url'}
REQUIRED_LISTS = ('Specially Designated Nationals (SDN)', 'Entity List (EL)', 'Non-SDN Chinese Military-Industrial Complex Companies List (CMIC)', 'Capta List (CAP)')
KINDS = {'Specially Designated Nationals (SDN)': ('blocking', ''), 'Sectoral Sanctions Identifications List (SSI)': ('sectoral', ''), 'Non-SDN Chinese Military-Industrial Complex Companies List (CMIC)': ('securities', ''), 'Capta List (CAP)': ('bank_account', ''), 'Entity List (EL)': ('export_license', ''), 'Unverified List (UVL)': ('verification', ''), 'Denied Persons List (DPL)': ('export_denial', ''), 'Military End User (MEU) List': ('military_end_use', ''), 'Non-SDN Menu-Based Sanctions List (NS-MBS List)': ('menu_based', '')}

def normalize(value):
    # Keep corporate words and parentheses; never substring-match a group to subsidiaries.
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()

def validity(row, as_of):
    for field in ('start_date', 'end_date'):
        if row.get(field):
            try: date.fromisoformat(row[field])
            except ValueError: return 'date_review'
    if row.get('start_date') and row['start_date'] > as_of: return 'future'
    if row.get('end_date') and row['end_date'] <= as_of: return 'expired_or_ends_today'
    return 'listed_active_or_undated'

def screen(company, rows, as_of):
    names = {normalize(n) for n in company['screen_names']}
    hits, candidates = [], []
    for row in rows:
        matched = next((n for n in [row['name'], *row['alt_names'].split(';')] if normalize(n) in names), None)
        if not matched: continue
        # Address is a location signal, not nationality. Roster country is kept separately.
        country_ok = re.search(r'(?:^|[,;]\s*)' + re.escape(company['address_country']) + r'(?:\s*;|\s*$)', row['addresses']) is not None
        record = {k: row.get(k, '') for k in ('name','source','programs','start_date','end_date','license_requirement','license_policy','source_list_url','source_information_url')}
        record.update(source_id=row['_id'], entity_number=row.get('entity_number',''), matched_name=matched,
                      restriction_kind=KINDS.get(row['source'].split(' - ')[0], ('other',''))[0], validity=validity(row, as_of))
        (hits if country_ok else candidates).append(record)
    hits = list({(r['source'],r['source_id']):r for r in hits}.values())
    return {**company, 'screened_on': as_of, 'status': 'listed_in_snapshot' if hits else ('identity_review' if candidates else 'no_exact_match'),
            'matches': hits, 'identity_candidates': candidates}

def build(raw, as_of, roster, measures):
    date.fromisoformat(as_of)
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
    if not REQUIRED <= set(reader.fieldnames or []): raise ValueError('Incomplete CSL columns; preserve previous output')
    rows = list(reader)
    if len(rows) < 1000: raise ValueError('Incomplete CSL universe; preserve previous output')
    sources = Counter(r['source'] for r in rows)
    if any(not any(k.startswith(name+' - ') for k in sources) for name in REQUIRED_LISTS):
        raise ValueError('Missing required CSL lists; preserve previous output')
    if any(not r['_id'] or not r['name'] for r in rows): raise ValueError('Missing stable CSL identity')
    if len({c['id'] for c in roster}) != len(roster): raise ValueError('Duplicate roster IDs')
    companies = [screen(c, rows, as_of) for c in roster]
    return {'schema_version':1,'checked_on':as_of,'coverage':'curated_pilot','selection_ko':'4개국 10개 법인씩 은행·산업 대표성을 고려한 시범 목록. 100대 기업 순위 및 국가 전체 제재 목록이 아닙니다.',
            'screening_scope_ko':'공식 CSL 스냅샷의 법인명·입력 별칭 정확 일치와 주소 국가를 대조했습니다. 원기관 명단·소유구조·거래별 허가까지 판정하지 않습니다.',
            'receipt':{'source_url':URL,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'row_count':len(rows),'source_counts':dict(sources),'screened_on':as_of},
            'countries':{iso:{'name_ko':name,'program_scope_ko':scope} for iso,name,scope in [
                ('RUS','러시아','러시아 관련 제재·은행·산업·물품 제한 중 선택 검토본'),('CHN','중국','지정 기업·증권·최종용도별 제한 중 선택 검토본'),
                ('KOR','한국','이 시범본에 한국 전체를 대상으로 한 OFAC 국가 제재는 미수록. 개별 지정과 대외 거래 위험은 별도 확인'),
                ('JPN','일본','이 시범본에 일본 전체를 대상으로 한 OFAC 국가 제재는 미수록. 개별 지정과 대외 거래 위험은 별도 확인')]},
            'measures':measures,'companies':companies}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path);p.add_argument('--download',action='store_true');p.add_argument('--as-of',required=True)
    p.add_argument('--output',type=Path,default=ROOT/'New for anti/public/data/trade_policy/us_sanctions_v1.json')
    args=p.parse_args()
    if bool(args.input)==bool(args.download):p.error('choose exactly one of --input or --download')
    if args.download:
        with urlopen(Request(URL,headers={'User-Agent':'ChokeMonitor-public-research/1.0', 'Accept-Encoding':'identity'}),timeout=60) as response:
            expected = response.headers.get('Content-Length')
            raw=response.read(40_000_001)
            if expected and len(raw) != int(expected): raise ValueError('Incomplete HTTP body; preserve previous output')
        if len(raw)>40_000_000:raise ValueError('CSL too large; preserve previous output')
    else:raw=args.input.read_bytes()
    base=Path(__file__).parent
    out=build(raw,args.as_of,json.loads((base/'sanctions_roster.json').read_text()),json.loads((base/'sanctions_measures.json').read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix('.json.tmp');temp.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');temp.replace(args.output)
    print(json.dumps({'companies':len(out['companies']),'status_counts':dict(Counter(c['status'] for c in out['companies'])),'source_rows':out['receipt']['row_count']}))
if __name__=='__main__':main()

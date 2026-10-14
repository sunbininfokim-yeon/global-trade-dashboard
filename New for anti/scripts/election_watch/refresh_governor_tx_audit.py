#!/usr/bin/env python3
"""Collect official Texas CAND as an audit; never publish candidate support/oppose."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from election_watch.polls import read,atomic
from election_watch.governor_tx import collect
from election_watch.superpac import SourceError
ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public',type=Path,default=ROOT.parent.parent/'public/data');p.add_argument('--cycle',type=int,default=2026);args=p.parse_args()
 target=args.public/'usa_governor_finance_audits'/str(args.cycle)/'TX.json';health=args.public/'usa_governor_finance_audit_status'/str(args.cycle)/'TX.json'
 try:
  roster=read(ROOT/'config/governor_matchups'/f'{args.cycle}.json')['contests']['TX']['candidates'];raw=collect(args.cycle,roster=roster)
  if raw['schema']!='usa_governor_audit_v1' or raw['state']!='TX' or raw['cycle']!=args.cycle or raw['spending'] or any(x['direction'] is not None for x in raw['unclassified_spending']):raise SourceError('TX direction audit contract changed')
  out={'schema':'usa_governor_finance_audit_v1','state':'TX','cycle':args.cycle,'captured_at':raw['generated_at'],'status':'collected_normalization_held','source_url':raw['source_url'],'candidate_amounts_available':False,'support_cents':None,'oppose_cents':None,'financial_data_collected':True,'raw_audit':raw,'note_ko':'공식 CAND 실수집. 지지/반대 미확인·신고 이름 불일치는 후보별 금액으로 발행하지 않음.'}
  atomic(target,out);atomic(health,{'state':'TX','status':'collected_normalization_held','checked_at':raw['generated_at'],'candidate_amounts_available':False});print({'state':'TX','status':out['status'],'candidate_amounts_available':False,'input_records':raw['quality']['input_records']});return 0
 except (OSError,ValueError,KeyError,TypeError,SourceError) as error:
  atomic(health,{'state':'TX','status':'error_last_valid_preserved','checked_at':datetime.now(timezone.utc).isoformat(),'error_type':type(error).__name__});print({'state':'TX','status':'error_last_valid_preserved','error_type':type(error).__name__});return 1
if __name__=='__main__':raise SystemExit(main())

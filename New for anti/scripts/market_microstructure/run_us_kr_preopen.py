"""Collect exact-session inputs, run a frozen model, and preserve forecast records."""
import argparse
import copy
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import exchange_calendars as xc
import pandas as pd

from backfill_detailed_15007_history import merge_date_folder, missing_required_files, REQUIRED_FILES
from build_kospi200_price_panel import fetch_naver_chart, NAVER_CHART
from option_direction_model import PUBLIC, calendar, digest, read, unique, window, write
from research_direction_diagnostics import ReviewedCalendar
from research_short_horizon_flow import components
from research_us_lag1_direction import SYMBOLS, previous_us_session
from us_kr_direction_engine import predict, validate_model, write_immutable
from us_kr_comparison import DEFAULT_MODEL as COMPARISON_MODEL, predict as comparison_predict
from us_kr_factors import DEFAULT_MODEL as FACTOR_MODEL, factor_payload

LABELS={'005930':'삼성전자','000660':'SK하이닉스','KOSPI':'KOSPI'}
PROBABILITY_CONTRACT={
    'basis':'conditional on nonflat opening and closing directions, matching the frozen training cohort',
    'opening_up':{'positive':'next open > previous KR close','negative':'next open < previous KR close'},
    'closing_up':{'positive':'next close > previous KR close','negative':'next close < previous KR close'},
    'direction_persists':{'positive':'opening and closing directions agree','negative':'opening and closing directions differ'},
    'opening_extends':{'positive':'open-to-close direction extends the opening direction',
                       'negative':'opening direction does not extend'},
    'flat_probability':'not estimated; do not interpret binary complements as a three-class forecast',
    'reference_only':'recent base rate only; probabilities are not a model direction signal'}


def timing(target,now,replay=False):
    base=calendar();cal=ReviewedCalendar(base)
    if not cal.is_session(target):raise ValueError('target is not a reviewed KRX session')
    i=cal.sessions.get_loc(target);source=cal.sessions[i-1].strftime('%Y-%m-%d')
    usday,usclose,cutoff=previous_us_session(xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31'),target)
    reasons=[]
    if pd.Timestamp(now)<base.session_close(source):reasons.append('KR source session not closed')
    if pd.Timestamp(now)<pd.Timestamp(usclose):reasons.append('US source session not closed')
    if not replay and pd.Timestamp(now)>pd.Timestamp(cutoff):reasons.append('forecast cutoff passed')
    return {'source':source,'us_source':usday,'cutoff':cutoff,'reasons':reasons}


def board_with_raw(board,raw_root,source):
    result=copy.deepcopy(board)
    if raw_root is None:return result,{'status':'provided_board_only'}
    previous=result['kr']['investor_nets']['detailed_15007']
    products=previous.get('products',{})
    present={s:{r['date'] for r in products.get('options_'+s,{}).get('series',[])
                if components(r) is not None} for s in ['call','put']}
    days=window(ReviewedCalendar(calendar()),source,60);merged=[];receipts={}
    for day in days:
        if day!=source and all(day in present[s] for s in present):continue
        folder=Path(raw_root)/day
        if missing_required_files(folder):continue
        previous=merge_date_folder(folder,previous);merged.append(day)
        receipts[day]={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in REQUIRED_FILES}
    result['kr']['investor_nets']['detailed_15007']=previous
    missing=missing_required_files(Path(raw_root)/source)
    status='expected_folder_incomplete' if missing else ('merged_expected_source_only' if merged==[source] else 'merged_expected_source_and_missing_history')
    return result,{'status':status,'date':source,'missing':missing,'merged_dates':merged,'raw_sha256':receipts}


def collect_kr_prices(source,now):
    cal=ReviewedCalendar(calendar());days=window(cal,source,20)
    if len(days)!=21:raise ValueError('missing KR calendar history')
    candidates=[]
    for ticker in LABELS:
        raw=fetch_naver_chart(ticker,days[0].replace('-',''),source.replace('-',''))
        if any(d not in raw for d in days):raise ValueError('missing KR price sessions: '+ticker)
        rows=[dict(date=d,quality='observed',**raw[d]) for d in days]
        if any(not math.isfinite(r[k]) or r[k]<=0 for r in rows for k in ['open','high','low','close']):
            raise ValueError('invalid KR OHLC: '+ticker)
        candidates.append({'ticker':ticker,'rows':rows,'source':'Naver chart',
            'source_url':NAVER_CHART.format(symbol=ticker,start=days[0].replace('-',''),end=source.replace('-','')),
            'price_adjustment':'provider chart basis, same source as research; not independently verified'})
    metadata={'collected_at':datetime.now(timezone.utc).isoformat(),'provider_published_at':'unknown',
        'window_policy':'replace entire exact 21-session window; never mix providers or fill missing sessions'}
    return ({**metadata,'candidates':[c for c in candidates if c['ticker']!='KOSPI']},
            {**metadata,'candidates':[c for c in candidates if c['ticker']=='KOSPI']})


def collect_us_prices(target,now):
    import yfinance as yf
    cal=xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31')
    day,closed,_=previous_us_session(cal,target);previous=cal.previous_session(day).strftime('%Y-%m-%d')
    end=(datetime.fromisoformat(day)+timedelta(days=1)).strftime('%Y-%m-%d')
    frame=yf.download(SYMBOLS,start=previous,end=end,interval='1d',group_by='ticker',
                      auto_adjust=True,progress=False,threads=False)
    out={}
    for sym in SYMBOLS:
        sub=frame[sym];bars={}
        for date,row in sub.iterrows():
            d=date.strftime('%Y-%m-%d')
            if d in [previous,day]:bars[d]={'date':d,'close':float(row['Close'])}
        if any(d not in bars or not math.isfinite(bars[d]['close']) or bars[d]['close']<=0 for d in [previous,day]):
            raise ValueError('missing expected US price pair: '+sym)
        out[sym]=[bars[previous],bars[day]]
    return {'source':'yfinance Yahoo daily auto_adjust=True','collected_at':datetime.now(timezone.utc).isoformat(),
            'provider_published_at':'unknown','session_timezone':'America/New_York','symbols':out,
            'expected_US_source':day,'calendar_close_UTC':closed,
            'window_policy':'both required sessions fetched together, no stale fallback'}


def provenance_revisions(old,new):
    oldrows={c['ticker']:unique(c['rows']) for c in old.get('candidates',[])};changed=[]
    for c in new.get('candidates',[]):
        for r in c['rows']:
            prev=oldrows.get(c['ticker'],{}).get(r['date'])
            if prev:
                fields=[k for k in ['open','high','low','close','volume'] if prev.get(k)!=r.get(k)]
                if fields:changed.append({'ticker':c['ticker'],'date':r['date'],'changed_fields':fields})
    return changed


def archive_forecast(forecast,root):
    result=copy.deepcopy(forecast)
    if forecast['status']!='research_preopen_forecast':
        result['eligible_for_primary_evaluation']=False
        return result,None
    directory=Path(root)/forecast['target_date']/forecast['model_id'][:16];directory.mkdir(parents=True,exist_ok=True)
    first=directory/'first.json'
    if first.exists():
        old=read(first)
        if (old['input_hashes']==forecast['input_hashes'] and old['results']==forecast['results']
                and old.get('comparisons')==forecast.get('comparisons')):
            return old,first
        stamp=datetime.fromisoformat(forecast['generated_at']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        result.update(record_role='revision',eligible_for_primary_evaluation=False)
        path=directory/'revisions'/(stamp+'.json')
    else:
        result.update(record_role='first_preopen_forecast',eligible_for_primary_evaluation=True)
        path=first
    write_immutable(path,result)
    return result,path


def record_attempt(forecast,root):
    """Keep failures as well as successes; replay never counts as a live attempt."""
    if forecast['status']=='retrospective_replay':return None
    receipt={k:copy.deepcopy(forecast.get(k)) for k in
             ['target_date','model_id','generated_at','status','reasons','input_errors','input_hashes']}
    receipt['schema_version']='us-kr-preopen-attempt-v1'
    receipt['comparison_status']=forecast.get('comparisons',{}).get('status','not_requested')
    stamp=datetime.fromisoformat(forecast['generated_at']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path=Path(root)/forecast['target_date']/forecast['model_id'][:16]/'attempts'/(stamp+'-'+digest(receipt)[:12]+'.json')
    write_immutable(path,receipt)
    return path


def display_payload(forecast,previous=None,factors=None):
    status=forecast['status'];target=forecast['target_date']
    if status=='unavailable' and previous and previous.get('target_date')==target and previous.get('status')=='research_preopen_forecast':
        out=copy.deepcopy(previous)
        out['refresh']={'status':'unavailable','checked_at':forecast['generated_at'],'reasons':forecast['reasons']}
        if factors is not None:out['factors']=factors
        return out
    cards=[]
    if status!='unavailable':
        for ticker,result in forecast['results'].items():
            scores={k:{f:r[f] for f in ['probability','score_0_100','direction','information_state']}
                    for k,r in result['scores'].items()}
            for name in ['opening_up','closing_up']:
                if name in scores:
                    p=scores[name]['probability']
                    if isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
                        raise ValueError('invalid display probability')
                    scores[name].update(up_probability=p,down_probability=1-p)
            cards.append({'ticker':ticker,'label_ko':LABELS[ticker],'scores':scores})
    out={'schema_version':'us-kr-direction-display-v1','status':status,'target_date':target,
         'generated_at':forecast['generated_at'],'KR_source_date':forecast['KR_source_date'],
         'US_source_date':forecast['required_US_session'],'forecast_cutoff_KST':forecast['forecast_cutoff_KST'],
         'model_id':forecast['model_id'],'trained_through':forecast['trained_through'],'research_only':True,
         'probability_contract':copy.deepcopy(PROBABILITY_CONTRACT),
         'cards':cards,'refresh':{'status':status,'checked_at':forecast['generated_at'],'reasons':forecast['reasons']}}
    if status=='unavailable' and previous:
        out['last_available']={k:previous.get(k) for k in ['target_date','generated_at','status']}
    if factors is not None:out['factors']=factors
    return out


def atomic_json(path,result):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as f:
        tmp=Path(f.name)
        f.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    os.replace(tmp,path)


def run(args,now=None,clock=None):
    if args.replay and args.public_output:raise ValueError('replay must not publish a live display payload')
    if args.public_output and Path(args.public_output).name!='us_kr_direction_v1.json':
        raise ValueError('public output must be named us_kr_direction_v1.json')
    clock=clock or (lambda:datetime.now(timezone.utc))
    started=now or clock()
    artifact=read(args.model);validate_model(artifact)
    timing_info=timing(args.target,started,args.replay)
    root=Path(args.run_dir)
    if root.exists() and any(root.iterdir()):raise ValueError('new run directory required')
    root.mkdir(parents=True,exist_ok=True)
    stocks=read(args.stocks) if args.stocks else {'candidates':[]}
    kospi=read(args.kospi) if args.kospi else {'candidates':[]}
    us=read(args.us) if args.us else {'symbols':{}}
    board=read(args.board);report={'target':args.target,'timing':timing_info,'started_at':started.isoformat(),'errors':[]}
    if not timing_info['reasons']:
        try:
            board,report['KRX_raw']=board_with_raw(board,args.krx_root,timing_info['source'])
            if args.refresh_prices:
                new_stocks,new_kospi=collect_kr_prices(timing_info['source'],started)
                report['provider_revisions']=provenance_revisions(stocks,new_stocks)+provenance_revisions(kospi,new_kospi)
                stocks,kospi=new_stocks,new_kospi
                us=collect_us_prices(args.target,started)
        except Exception as e:
            report['errors'].append(type(e).__name__+': '+str(e))
    inputs=root/'inputs';inputs.mkdir(exist_ok=True)
    for name,value in [('board',board),('stocks',stocks),('kospi',kospi),('us',us)]:write(inputs/(name+'.json'),value)
    prices={'candidates':stocks['candidates']+kospi['candidates']}
    generated=now or clock()
    forecast=predict(artifact,board,prices,us,args.target,now=generated,replay=args.replay)
    if report['errors']:
        forecast.update(status='unavailable',results={},eligible_for_prospective_evaluation=False)
        forecast['reasons']+=['collection failed: '+e for e in report['errors']]
    comparison_model=getattr(args,'comparison_model',None)
    if comparison_model and forecast['status'] in ('research_preopen_forecast','retrospective_replay'):
        try:
            forecast['comparisons']=comparison_predict(read(comparison_model),artifact,forecast)
        except (OSError,ValueError,KeyError,TypeError) as e:
            forecast['comparisons']={'status':'unavailable','reason':type(e).__name__+': '+str(e)}
            print({'comparison_unavailable':forecast['comparisons']['reason']})
    attempt=record_attempt(forecast,args.archive_dir) if not args.replay else None
    forecast,archive=archive_forecast(forecast,args.archive_dir)
    write_immutable(root/'forecast.json',forecast)
    previous=read(args.public_output) if args.public_output and Path(args.public_output).exists() else None
    factors=None
    if factor_model:=getattr(args,'factor_model',None):
        try:
            factors=factor_payload(
                read(factor_model),board,us,target=args.target,now=now or clock(),replay=args.replay,
                krx_root=args.krx_root,flow_root=getattr(args,'stock_flow_root',None),
                clock=clock if now is None else None,
            )
        except (OSError,ValueError,KeyError,TypeError) as exc:
            report['factor_error']=type(exc).__name__+': '+str(exc)
            print({'factor_unavailable':report['factor_error']})
    display=display_payload(forecast,previous,factors)
    write(root/'display_payload.json',display)
    if args.public_output:atomic_json(args.public_output,display)
    report.update(forecast_status=forecast['status'],archive_record=str(archive) if archive else None,
                  attempt_record=str(attempt) if attempt else None,comparison_status=forecast.get('comparisons',{}).get('status','not_requested'))
    write(root/'run_report.json',report)
    print({'status':forecast['status'],'target':args.target,'run_dir':str(root),'reasons':forecast['reasons']})
    return 2 if forecast['status']=='unavailable' else 0


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--comparison-model',type=Path,default=COMPARISON_MODEL,
                   help='frozen comparison artifact; primary model is unchanged')
    p.add_argument('--factor-model',type=Path,default=FACTOR_MODEL)
    p.add_argument('--stock-flow-root',type=Path,help='optional normalized KRX 12009 directory')
    p.add_argument('--board',type=Path,default=PUBLIC/'derivatives_board_v1.json')
    p.add_argument('--stocks',type=Path);p.add_argument('--kospi',type=Path);p.add_argument('--us',type=Path)
    p.add_argument('--krx-root',type=Path);p.add_argument('--refresh-prices',action='store_true')
    p.add_argument('--replay',action='store_true');p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--archive-dir',type=Path,required=True);p.add_argument('--public-output',type=Path)
    args=p.parse_args()
    if not args.refresh_prices and not all([args.stocks,args.kospi,args.us]):p.error('offline mode requires --stocks --kospi --us')
    if args.public_output and args.public_output.name!='us_kr_direction_v1.json':p.error('public output must be named us_kr_direction_v1.json')
    if args.replay and args.public_output:p.error('replay must not publish a live display payload')
    if args.public_output and args.public_output.resolve() in {x.resolve() for x in [args.board,args.model,args.factor_model,args.stocks,args.kospi,args.us] if x}:
        p.error('public output would overwrite an input')
    raise SystemExit(run(args))

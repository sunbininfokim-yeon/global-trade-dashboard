"""Fixed previous-US-session signals for KR next-open/close direction. No costs/PnL."""
import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

import pandas as pd
import exchange_calendars as xc

from option_direction_model import PUBLIC, read, unique, write
from research_direction_diagnostics import directional_scores
from research_mixed_option_activity import build
from research_option_dynamics import evaluate
from research_short_horizon_prediction import paired_loss, holm
from research_stock_open_close_direction import TARGETS, path_labels

FAMILIES=['price','existing','mixed','us_market','us_semis','us_all','mixed_us_all']
SYMBOLS=['QQQ','SPY','SMH','MU','NVDA','AMD','^VIX']


def previous_us_session(cal,target):
    cutoff=pd.Timestamp(target,tz='Asia/Seoul')+pd.Timedelta(hours=8,minutes=30)
    days=cal.sessions[cal.sessions.strftime('%Y-%m-%d')<target]
    if not len(days):raise ValueError('US calendar history missing')
    day=days[-1];close=cal.session_close(day)
    if close>=cutoff:raise ValueError('US source closes after forecast cutoff')
    return day.strftime('%Y-%m-%d'),close.isoformat(),cutoff.isoformat()


def us_vector(data,cal,target):
    day,closed,cutoff=previous_us_session(cal,target)
    prev=cal.previous_session(day).strftime('%Y-%m-%d')
    changes={}
    for s in SYMBOLS:
        a=data[s].get(day,{}).get('close');b=data[s].get(prev,{}).get('close')
        if any(v is None or not math.isfinite(v) or v<=0 for v in (a,b)):
            return None,{'reason':'missing_expected_US_session','symbol':s,'day':day,'previous':prev}
        changes[s]=a/b-1
    market=[changes[s] for s in ['QQQ','SPY','^VIX']]+[math.log(data['^VIX'][day]['close'])]
    semis=[changes[s] for s in ['SMH','MU','NVDA','AMD']]
    return (market,semis),{'US_session':day,'US_close_UTC':closed,'forecast_cutoff_KST':cutoff}


def assemble(board,prices,chain,us,ticker):
    base,chain_exclusions=build(board,prices,chain,ticker=ticker)
    bars=unique(next(c['rows'] for c in prices['candidates'] if c['ticker']==ticker))
    cal=xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31')
    data={s:unique(us['symbols'][s]) for s in SYMBOLS};rows=[];exclusions=Counter();alignment={}
    for r in base:
        labels=path_labels(bars[r['date']]['close'],bars[r['target_date']]['open'],bars[r['target_date']]['close'])
        if any(labels[t] is None for t in TARGETS):exclusions['flat_boundary']+=1;continue
        v,meta=us_vector(data,cal,r['target_date'])
        if v is None:exclusions['missing_expected_US_session']+=1;continue
        market,semis=v
        rows.append({**r,**labels,'us_market':r['existing']+market,'us_semis':r['existing']+semis,
                     'us_all':r['existing']+market+semis,'mixed_us_all':r['mixed']+market+semis})
        alignment[r['date']]={'KR_source_date':r['date'],'KR_target_date':r['target_date'],**meta}
    return rows,dict(exclusions),chain_exclusions,alignment


def analyze(board,prices,chain,us,ticker):
    rows,excluded,chain_excluded,alignment=assemble(board,prices,chain,us,ticker)
    output={};comparisons={}
    for target in TARGETS:
        prepared=[{**r,'y':r[target]} for r in rows]
        preds,folds=evaluate(prepared,FAMILIES)
        if not folds:raise ValueError('insufficient temporal folds')
        for candidate in ['us_market','us_semis','us_all','mixed_us_all']:
            baseline='mixed_calibrated' if candidate=='mixed_us_all' else 'existing_calibrated'
            for b in [baseline,'prior_recent']:
                comparisons[target+':'+candidate+'_vs_'+b]=paired_loss(preds[candidate+'_calibrated'],preds[b])
        output[target]={'scores':{k:directional_scores(v) for k,v in preds.items()},'folds':folds,
            'predictions':{k:[{f:r[f] for f in ['date','target_date','y','p']} for r in v] for k,v in preds.items()}}
    return {'ticker':ticker,'n_complete_rows':len(rows),'exclusions':excluded,'chain_exclusions':chain_excluded,
             'alignment':alignment,'targets':output,'comparisons':comparisons}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--us',type=Path,required=True);p.add_argument('--stocks',type=Path,required=True)
    p.add_argument('--kospi',type=Path,required=True);p.add_argument('--chain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    board=read(PUBLIC/'derivatives_board_v1.json');us=read(args.us);chain=read(args.chain)
    prices={'candidates':read(args.stocks)['candidates']+read(args.kospi)['candidates']}
    results={}
    for ticker in ['005930','000660','KOSPI']:
        results[ticker]=analyze(board,prices,chain,us,ticker);print('analyzed',ticker,flush=True)
    comparisons={t+':'+k:v for t,r in results.items() for k,v in r['comparisons'].items()};holm(comparisons)
    result={'status':'retrospective_research_only','lag':'fixed previous US trading session -> following KR session',
        'forecast_time':'KR target date 08:30 KST','US_input_symbols':SYMBOLS,'results':results,
        'input_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in
            [args.us,args.stocks,args.kospi,args.chain,PUBLIC/'derivatives_board_v1.json']},
        'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limitations':['No lag search, no costs/PnL. Current-snapshot historical prices, not verified point-in-time data',
            'US regular close precedes KR cutoff; source publication lag not independently verified',
            'One KR target row per session; holiday multiple-US-day signals reduced to most recent session only',
            'Missing expected US calendar session pair is excluded, never silently replaced with an older row',
            'Same nonflat KR outcome cohort for all families; not unconditional live probabilities',
            'US features are available next KR morning, not at prior KR close',
            '96 Brier comparisons Holm-adjusted; explored history, no prospective validation',
            'US option history and KR whole-market spot flows not included',
            'Separate heads are not a joint distribution; zero-slope calibration means recent base rate only']}
    write(args.output,result);print('wrote',args.output,flush=True)

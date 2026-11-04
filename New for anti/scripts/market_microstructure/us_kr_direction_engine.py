"""Versioned pre-open US→KR research inference. Training is always explicit."""
import argparse
import hashlib
import math
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import exchange_calendars as xc
import pandas as pd
from scipy.special import expit

from option_direction_model import (PUBLIC, calendar, digest, fit, option_features, price_data,
                                    probability, read, unique, window, write)
from research_direction_diagnostics import ReviewedCalendar, richer_price_features
from research_option_dynamics import logit, sigmoid_calibration
from research_short_horizon_flow import components
from research_stock_open_close_direction import TARGETS
from research_us_lag1_direction import SYMBOLS, assemble, previous_us_session, us_vector

VERSION='us-kr-preopen-direction-research-v1'
TICKERS=['005930','000660','KOSPI']
FEATURES=['momentum5','volatility20','today_return','today_gap','today_intraday','momentum20',
          'call_rank60','put_rank60','call_mean5','put_mean5','QQQ_return1','SPY_return1',
          'VIX_return1','log_VIX','SMH_return1','MU_return1','NVDA_return1','AMD_return1']
PACKAGES=['exchange-calendars','numpy','pandas','scipy','scikit-learn']


def code_hashes():
    names=['us_kr_direction_engine.py','option_direction_model.py','research_direction_diagnostics.py',
           'research_option_dynamics.py','research_pr791_evaluation.py','research_short_horizon_flow.py',
           'research_short_horizon_prediction.py','research_mixed_option_activity.py',
           'research_stock_open_close_direction.py','research_us_lag1_direction.py']
    return {n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in names}


def train(board,prices,chain,us,cutoff):
    cal=ReviewedCalendar(calendar())
    if not cal.is_session(cutoff):raise ValueError('training cutoff must be a KRX session')
    start=(pd.Timestamp(cutoff)+pd.Timedelta(days=1)-pd.DateOffset(months=6)).strftime('%Y-%m-%d')
    models={}
    for ticker in TICKERS:
        rows,_,_,_=assemble(board,prices,chain,us,ticker)
        rows=[r for r in rows if r['target_date']<=cutoff]
        if not rows or max(r['target_date'] for r in rows)!=cutoff:
            raise ValueError('cutoff lacks complete outcomes: '+ticker)
        base=[r for r in rows if r['target_date']<start]
        calrows=[r for r in rows if r['date']>=start]
        if len(calrows)<60 or not base:raise ValueError('insufficient independent calibration')
        if max(r['target_date'] for r in base)>=min(r['date'] for r in calrows):
            raise ValueError('train/calibration overlap')
        heads={}
        for target in TARGETS:
            model=fit([{**r,'y':r[target]} for r in base],'us_all')
            c=sigmoid_calibration([logit(probability(model,r['us_all'])) for r in calrows],
                                  [r[target] for r in calrows])
            heads[target]={'model':model,'calibrator':c}
        models[ticker]={'heads':heads,'n_base':len(base),'n_calibration':len(calrows),
            'last_base_target':max(r['target_date'] for r in base),
            'first_calibration_source':min(r['date'] for r in calrows),
            'last_calibration_target':max(r['target_date'] for r in calrows)}
    artifact={'schema_version':VERSION,'features':FEATURES,'tickers':TICKERS,'targets':TARGETS,
        'family':'us_all; fixed domestic price/options + US market/semiconductors',
        'trained_through':cutoff,'models':models,'created_at':datetime.now(timezone.utc).isoformat(),
        'implementation_sha256':code_hashes(),'runtime_versions':{p:version(p) for p in PACKAGES},
        'input_hashes':{'board':digest(board),'prices':digest(prices),'chain':digest(chain),'us':digest(us)},
        'validation':'retrospective research only; nonflat training cohort; prospective validation pending',
        'decision_contract':'latest completed US regular session, KR target day before 08:30 KST',
        'target_contract':{'opening_up':'next open > previous KR close','closing_up':'next close > previous KR close',
            'direction_persists':'open and close on same side of previous KR close',
            'opening_extends':'close-open direction equals open-previous_close direction'},
        'limitations':['No US option chain, KR whole-market spot flow, stock-specific option/cash flow or cost inputs',
            'Separate heads are not a coherent joint distribution',
            'Reference only; no causal or validated live accuracy claim']}
    artifact['model_id']=digest(artifact)
    return artifact


def validate_model(artifact):
    if digest({k:v for k,v in artifact.items() if k!='model_id'})!=artifact.get('model_id'):
        raise ValueError('model integrity check failed')
    if artifact.get('schema_version')!=VERSION or artifact.get('features')!=FEATURES:
        raise ValueError('model feature schema changed')
    if artifact.get('implementation_sha256')!=code_hashes():
        raise ValueError('frozen implementation changed; new reviewed model version required')
    if artifact.get('runtime_versions')!={p:version(p) for p in PACKAGES}:
        raise ValueError('frozen research runtime version changed')


def feature_vector(board,prices,us,ticker,source,target):
    cal=ReviewedCalendar(calendar());days=window(cal,source,60)
    if len(days)!=61:raise ValueError('insufficient KRX history')
    products=board['kr']['investor_nets']['detailed_15007']['products']
    for side in ['call','put']:
        rows=unique(products['options_'+side]['series'])
        if any(d not in rows or components(rows[d]) is None for d in days):
            raise ValueError('missing/invalid observed '+side+' on exact 61-session window')
    opt=option_features(board,cal).get(source)
    bars=unique(next(c['rows'] for c in prices['candidates'] if c['ticker']==ticker))
    short=window(cal,source,20)
    if len(short)!=21 or any(d not in bars for d in short):raise ValueError('missing exact 21-session prices: '+ticker)
    for d in short:
        row=bars[d]
        if row.get('quality') not in (None,'observed'):raise ValueError('nonobserved price: '+ticker)
        if any(row.get(k) is None or not math.isfinite(row[k]) or row[k]<=0 for k in ['open','high','low','close']):
            raise ValueError('invalid OHLC: '+ticker)
    p,_=price_data(prices,cal,ticker=ticker)
    if opt is None or source not in p:raise ValueError('missing current source features')
    rich=richer_price_features([{'date':source,'price_only':p[source],'option_only':opt}],bars,cal)
    data={s:unique(us['symbols'][s]) for s in SYMBOLS}
    v,meta=us_vector(data,xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31'),target)
    if v is None:raise ValueError('missing US session pair: '+str(meta))
    x=rich[0]['price_only']+opt+v[0]+v[1]
    if len(x)!=len(FEATURES) or not all(math.isfinite(v) for v in x):raise ValueError('invalid feature vector')
    return x,meta


def interpret(p,target,base_only):
    if base_only:return 'REFERENCE_ONLY'
    if p==.5:return 'NEUTRAL'
    if target in ['opening_up','closing_up']:return 'UP' if p>.5 else 'DOWN'
    if target=='direction_persists':return 'MAINTAIN' if p>.5 else 'REVERSE'
    return 'EXTEND' if p>.5 else 'NO_EXTENSION'


def predict(artifact,board,prices,us,target,now=None,replay=False):
    validate_model(artifact)
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('timezone-aware generation timestamp required')
    if now<datetime.fromisoformat(artifact['created_at']):raise ValueError('cannot backdate before model creation')
    base_cal=calendar();cal=ReviewedCalendar(base_cal)
    if not cal.is_session(target):raise ValueError('target must be a reviewed KRX session')
    index=cal.sessions.get_loc(target);source=cal.sessions[index-1].strftime('%Y-%m-%d')
    cutoff=pd.Timestamp(target,tz='Asia/Seoul')+pd.Timedelta(hours=8,minutes=30)
    usday,usclosed,_=previous_us_session(xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31'),target)
    out={'schema_version':VERSION,'model_id':artifact['model_id'],'trained_through':artifact['trained_through'],
         'generated_at':now.isoformat(),'target_date':target,'KR_source_date':source,
         'forecast_cutoff_KST':cutoff.isoformat(),'target_open_UTC':base_cal.session_open(target).isoformat(),
         'required_US_session':usday,'required_US_close_UTC':usclosed,'status':'unavailable',
         'input_hashes':{'board':digest(board),'prices':digest(prices),'us':digest(us)},
         'results':{},'reasons':[],'validation':artifact['validation'],
         'timing_evidence':'local generation time; provider first publication time unverified'}
    if target<=artifact['trained_through']:out['reasons'].append('target not after training outcomes')
    if not replay and now>cutoff:out['reasons'].append('forecast cutoff passed; explicit retrospective replay required')
    if pd.Timestamp(now)<base_cal.session_close(source):out['reasons'].append('KR source session not closed')
    if pd.Timestamp(now)<pd.Timestamp(usclosed):out['reasons'].append('required US session not closed')
    if out['reasons']:return out
    errors={};vectors={}
    for ticker in TICKERS:
        try:vectors[ticker]=feature_vector(board,prices,us,ticker,source,target)
        except (ValueError,KeyError,StopIteration) as e:errors[ticker]=str(e)
    if errors:
        out['reasons'].append('missing or invalid required source data');out['input_errors']=errors
        return out
    for ticker,(x,meta) in vectors.items():
        scores={}
        for target_name,head in artifact['models'][ticker]['heads'].items():
            raw=probability(head['model'],x);c=head['calibrator']
            p=float(expit(c['slope']*logit(raw)+c['intercept']))
            base_only=c['at_zero_slope']
            scores[target_name]={'probability':p,'score_0_100':100*p,'raw_probability':raw,
                'direction':interpret(p,target_name,base_only),
                'information_state':'recent_base_rate_only' if base_only else 'model_score_with_calibration',
                'calibration_slope':c['slope']}
        out['results'][ticker]={'scores':scores,'feature_values':dict(zip(FEATURES,x)),'alignment':meta}
    out['status']='retrospective_replay' if replay else 'research_preopen_forecast'
    out['eligible_for_prospective_evaluation']=not replay
    return out


def write_immutable(path,result):
    path=Path(path)
    if path.exists():
        old=read(path)
        if {k:v for k,v in old.items() if k!='generated_at'}=={k:v for k,v in result.items() if k!='generated_at'}:
            return 'unchanged'
        raise ValueError('output changed; preserve original and use a revision path')
    write(path,result);return 'written'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['train','predict'])
    p.add_argument('--board',type=Path,default=PUBLIC/'derivatives_board_v1.json')
    p.add_argument('--stocks',type=Path,required=True);p.add_argument('--kospi',type=Path,required=True)
    p.add_argument('--us',type=Path,required=True);p.add_argument('--chain',type=Path)
    p.add_argument('--cutoff');p.add_argument('--target');p.add_argument('--model',type=Path)
    p.add_argument('--replay',action='store_true');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();inputs=[args.board,args.stocks,args.kospi,args.us]+[x for x in [args.chain,args.model] if x]
    if args.output.resolve() in {x.resolve() for x in inputs}:p.error('output would overwrite an input')
    board=read(args.board);us=read(args.us)
    prices={'candidates':read(args.stocks)['candidates']+read(args.kospi)['candidates']}
    if args.command=='train':
        if not args.cutoff or not args.chain:p.error('train requires --cutoff and --chain')
        if args.output.exists():p.error('new model version path required')
        result=train(board,prices,read(args.chain),us,args.cutoff)
        write(args.output,result)
    else:
        if not args.model or not args.target:p.error('predict requires --model and --target')
        result=predict(read(args.model),board,prices,us,args.target,replay=args.replay)
        print(write_immutable(args.output,result))
    print({k:result.get(k) for k in ['status','model_id','trained_through','target_date','reasons']})

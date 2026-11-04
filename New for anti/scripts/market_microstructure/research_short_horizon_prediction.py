"""Fixed short-horizon comparisons; retrospective research, no live signal update."""
import argparse
import hashlib
from pathlib import Path

import numpy as np

from option_direction_model import PUBLIC, calendar, option_features, price_data, read, unique, window, write
from research_direction_diagnostics import ReviewedCalendar, richer_price_features, directional_scores
from research_option_dynamics import evaluate
from research_short_horizon_flow import components

FAMILIES = ['price', 'existing', 'flow1', 'split1', 'split_change', 'split2', 'split3', 'split5']
BANDS = [0., .025, .05, .10]


def signal(p, band=0.):
    if not 0 <= p <= 1 or not 0 <= band < .5:
        raise ValueError('invalid probability or band')
    return 1 if p > .5+band else -1 if p < .5-band else 0


def assemble(board, etfs, ticker='069500'):
    cal=ReviewedCalendar(calendar())
    prices=unique(next(c['rows'] for c in etfs['candidates'] if c['ticker']==ticker))
    options=option_features(board,cal);price_features,labels=price_data(etfs,cal,ticker=ticker)
    base=[{'date':d,**labels[d],'option_only':options[d],'price_only':price_features[d],
           'combined':price_features[d]+options[d]}
          for d in sorted(set(options)&set(price_features)&set(labels))]
    base=richer_price_features(base,prices,cal)
    products=board['kr']['investor_nets']['detailed_15007']['products']
    vals={side:{d:components(r) for d,r in unique(products['options_'+side]['series']).items()}
          for side in ('call','put')}
    rows=[]
    for r in base:
        days=window(cal,r['date'],4)
        if len(days)!=5 or any(vals[s].get(d) is None for s in vals for d in days):
            continue
        def split(d):
            return [vals[s][d][f] for s in ('call','put') for f in ('imbalance','participation')]
        current=np.array(split(days[-1])); prev=np.array(split(days[-2]))
        price=r['price_only']
        q={k:r[k] for k in ('date','target_date','y','return')}
        q.update(feature_source_date=r['date'],price=price,existing=price+r['option_only'],
                 flow1=price+[vals[s][r['date']]['net_share'] for s in ('call','put')],
                 split1=price+current.tolist(), split_change=price+current.tolist()+(current-prev).tolist())
        for n in (2,3,5):
            q['split'+str(n)]=price+np.mean([split(d) for d in days[-n:]],axis=0).tolist()
        rows.append(q)
    return rows


def policy(records, band, gate_base_rate=False):
    p=np.array([r['p'] for r in records]);r=np.array([r['return'] for r in records])
    positions=np.array([0 if gate_base_rate and r.get('information_state')=='recent_base_rate_only'
                        else signal(r['p'],band) for r in records]); active=positions!=0
    out={'n':len(r),'buy':int((positions==1).sum()),'sell':int((positions==-1).sum()),
         'neutral':int((positions==0).sum()),'coverage':float(active.mean()),
         'direction_hit_active':float(((positions[active]*r[active])>0).mean()) if active.any() else None,
         'cost_scenarios':{}}
    for bp in (0,5,10):
        pnl=positions*r-active*bp/10000
        wealth=np.cumprod(1+pnl); peak=np.maximum.accumulate(np.r_[1.,wealth])[1:]
        out['cost_scenarios'][str(bp)]={'mean_per_active_pct':float(pnl.sum()/active.sum()*100) if active.any() else None,
             'mean_per_session_pct':float(pnl.mean()*100),'compounded_return_pct':float((wealth[-1]-1)*100),
             'max_drawdown_pct':float((wealth/peak-1).min()*100)}
    return out


def paired_loss(a,b):
    if [(r['date'],r['target_date'],r['y']) for r in a]!=[(r['date'],r['target_date'],r['y']) for r in b]:
        raise ValueError('unpaired evaluation')
    delta=np.array([(x['p']-x['y'])**2-(y['p']-y['y'])**2 for x,y in zip(a,b)])
    rng=np.random.default_rng(42);blocks=np.lib.stride_tricks.sliding_window_view(delta,5)
    means=np.array([blocks[rng.integers(len(blocks),size=int(np.ceil(len(delta)/5)))].ravel()[:len(delta)].mean()
                    for _ in range(2000)])
    observed=float(delta.mean())
    p=(1+int((np.abs(means-observed)>=abs(observed)).sum()))/(len(means)+1)
    return {'brier_delta':observed,'block95':np.quantile(means,[.025,.975]).tolist(),
            'two_sided_centered_block_p':p}


def holm(comparisons):
    ordered=sorted(comparisons,key=lambda k:comparisons[k]['two_sided_centered_block_p'])
    running=0.
    for i,k in enumerate(ordered):
        running=max(running,min(1.,(len(ordered)-i)*comparisons[k]['two_sided_centered_block_p']))
        comparisons[k]['holm_adjusted_p']=running


def run(board,etfs):
    rows=assemble(board,etfs)
    predictions,folds=evaluate(rows,FAMILIES)
    if not folds: raise ValueError('no evaluable folds')
    for family in FAMILIES:
        for r in predictions[family+'_calibrated']:
            fold=next(f for f in reversed(folds) if f['test_start']<=r['date'])
            r['information_state']='recent_base_rate_only' if fold['calibrators'][family]['at_zero_slope'] else 'model_score_with_calibration'
    predictions['always_up']=[{**r,'p':1.} for r in predictions['prior_recent']]
    comparisons={}
    for family in FAMILIES[1:]:
        for baseline in ('price_calibrated','prior_recent'):
            comparisons[family+'_vs_'+baseline]=paired_loss(predictions[family+'_calibrated'],predictions[baseline])
    holm(comparisons)
    scores={k:{'probability':directional_scores(v),
               'signal_policies':{str(b):policy(v,b) for b in BANDS},
               'base_rate_gated_policies':{str(b):policy(v,b,True) for b in BANDS} if k.endswith('_calibrated') else None}
            for k,v in predictions.items()}
    yearly={str(y):{k:directional_scores([r for r in v if r['date'].startswith(str(y))])
                    for k,v in predictions.items()} for y in range(2022,2027)}
    return {'status':'retrospective_research_only','target':'069500 next KRX session close/open > 0; flat is non-up',
         'display_contract':{'probability_score':'100*p_up; 50 is equal probability',
              'signed_score':'200*(p_up-.5); zero is equal probability',
              'strict_rule':'p>.5 BUY, p<.5 SELL, p=.5 NEUTRAL',
              'neutral_band_candidates':BANDS,'decision_subject':'underlying ETF direction, not call/put option trade',
              'caveat':'50% is not expected-return break-even; returns, costs and short implementation differ'},
         'common_training_rows':len(rows),'first_source':rows[0]['date'],'last_source':rows[-1]['date'],
         'folds':folds,'scores':scores,'yearly':yearly,'comparisons':comparisons,'predictions':predictions,
         'limitations':['All families use identical dates and six price controls; raw/calibrated scores both disclosed',
           'Historical interval already explored, no untouched holdout or live promotion',
           'Transaction-cost figures are round-trip bps per active session, illustrative long/short exposure only',
           'Borrow, financing, futures basis and actual execution are not modeled',
           'Pre-open availability and adjusted OHLC execution equivalence unverified',
           'Band/candidate with best historical result must not be selected without new prospective validation',
           'Holm adjusts 14 primary calibrated Brier comparisons; raw scores and policy returns are exploratory',
           'Zero calibration slope means recent base rate only; it is not option-responsive probability']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board',type=Path,default=PUBLIC/'derivatives_board_v1.json')
    p.add_argument('--prices',type=Path,default=PUBLIC/'kospi200_etf_candidates_daily_v1.json')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=run(read(args.board),read(args.prices))
    result['input_sha256']={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (args.board,args.prices)}
    result['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write(args.output,result)
    print({'evaluation_n':result['scores']['prior_recent']['probability']['n'],'output':str(args.output)})

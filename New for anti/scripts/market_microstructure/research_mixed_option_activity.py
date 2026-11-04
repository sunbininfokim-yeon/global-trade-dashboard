"""Mixed money/contract activity research using a pinned existing private chain."""
import argparse
import base64
import gzip
import hashlib
import json
import math
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

from option_direction_model import PUBLIC, calendar, read, unique, window, write
from research_direction_diagnostics import ReviewedCalendar
from research_option_dynamics import evaluate, splits
from research_short_horizon_prediction import assemble, paired_loss, holm, policy

FAMILIES=['price','existing','money','interaction','volume','mixed']


def aggregate(rows):
    selected={};conflicts=set()
    fields=('volume_contracts','trading_value_krw','open_interest_contracts','implied_volatility')
    for r in rows:
        if r.get('quality')!='observed' or r.get('session')!='regular': continue
        key=(str(r.get('expiry_or_contract_month')),r.get('option_type'),r.get('strike'))
        if key[1] not in ('call','put') or key[2] is None: continue
        prev=selected.get(key);stamp=str(r.get('collected_at') or '')
        if prev and stamp==str(prev.get('collected_at') or '') and any(prev.get(k)!=r.get(k) for k in fields):
            conflicts.add(key)
        if prev is None or stamp>str(prev.get('collected_at') or ''):selected[key]=r
    if conflicts:return {'status':'missing','reason':'conflicting_duplicate'}
    expiries={k[0] for k in selected}
    if len(expiries)!=1 or expiries & {'None',''}:return {'status':'missing','reason':'multiple_or_missing_expiries'}
    out={'status':'observed_subset','expiry':next(iter(expiries))}
    for side in ('call','put'):
        group=[r for k,r in selected.items() if k[1]==side]
        if not group:return {'status':'missing','reason':'missing_side'}
        out[side+'_n']=len(group)
        for field in fields[:3]:
            vals=[r.get(field) for r in group]
            if any(v is None or not math.isfinite(v) or v<0 for v in vals):
                return {'status':'missing','reason':'invalid_'+field}
            out[side+'_'+field]=sum(vals)
        iv=[(r.get('implied_volatility'),r.get('open_interest_contracts')) for r in group]
        iv=[(v,w) for v,w in iv if v is not None and math.isfinite(v) and 1<=v<=150 and w>0]
        out[side+'_iv_oi_weighted']=sum(v*w for v,w in iv)/sum(w for v,w in iv) if iv else None
    return out


def extract(manifest, gh):
    cache=Path('/tmp/krx-mixed-activity-derived-v1');cache.mkdir(exist_ok=True)
    def part(receipt):
        cached=cache/(receipt['git_blob']+'.json')
        if cached.exists():return read(cached)
        for attempt in range(3):
            try:
                raw=json.loads(subprocess.check_output([gh,'api','repos/sunbininfokim-yeon/krx-month-paste/git/blobs/'+receipt['git_blob']],timeout=40))
                break
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
                if attempt==2:raise
                time.sleep(1+attempt)
        zipped=base64.b64decode(raw['content'])
        if hashlib.sha256(zipped).hexdigest()!=receipt['sha256']:raise ValueError('source checksum mismatch')
        groups=defaultdict(list)
        for line in gzip.decompress(zipped).splitlines():
            r=json.loads(line)
            if r.get('session')=='regular':groups[r['date']].append(r)
        result={d:aggregate(rs) for d,rs in groups.items()}
        write(cached,result)
        return result
    points={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,p in enumerate(pool.map(part,manifest['receipts']),1):
            if set(points)&set(p):raise ValueError('overlapping date partitions')
            points.update(p)
            if i%12==0:print('existing private parts',i,flush=True)
    return {'source':manifest['private_source'],'scope':'regular observed chain subset; completeness unverified',
            'receipts':manifest['receipts'],'points':dict(sorted(points.items()))}


def build(board,etfs,chain,ticker='069500'):
    cal=ReviewedCalendar(calendar());base=assemble(board,etfs,ticker=ticker)
    products=board['kr']['investor_nets']['detailed_15007']['products']
    market={s:unique(products['options_'+s]['series']) for s in ('call','put')}
    prices=unique(next(c['rows'] for c in etfs['candidates'] if c['ticker']==ticker))
    out=[];excluded=defaultdict(int)
    for r in base:
        day=r['date'];days=window(cal,day,20)
        if len(days)!=21 or any(d not in market[s] for s in market for d in days):continue
        amounts=np.array([[market[s][d]['market_total']['buy_krw'] for s in ('call','put')] for d in days])
        if not np.isfinite(amounts).all() or (amounts<=0).any():continue
        # Past 20 sessions only define typical market activity, including across expiry rolls.
        shock=np.log(amounts[-1]/amounts[:-1].mean(axis=0)).tolist()
        money=shock+[math.log(amounts[-1,1]/amounts[-1,0])]
        # Contemporary net-flow × activity and cross-call/put interactions are hypotheses, not inferred positions.
        direction=r['flow1'][-2:];ip=r['split1'][-4:]
        inter=[direction[0]*shock[0],direction[1]*shock[1],ip[0]*ip[2],ip[1]*ip[3]]
        q={**r,'money':r['existing']+money+ip,
           'interaction':r['existing']+money+ip+inter}
        p=chain['points'].get(day,{});prev=chain['points'].get(days[-2],{})
        if p.get('status')!='observed_subset' or prev.get('status')!='observed_subset':
            excluded['missing_chain_pair']+=1;continue
        if p['expiry']!=prev['expiry']:
            excluded['roll']+=1;continue
        vs=[p[s+'_volume_contracts'] for s in ('call','put')]
        os=[p[s+'_open_interest_contracts'] for s in ('call','put')]
        previous_volume=sum(prev[s+'_volume_contracts'] for s in ('call','put'))
        if min(vs+os+[previous_volume])<=0:
            excluded['zero_volume_or_oi']+=1;continue
        iv=[p[s+'_iv_oi_weighted'] for s in ('call','put')]
        if any(v is None for v in iv):excluded['missing_iv']+=1;continue
        volume=[math.log(sum(vs)),math.log(vs[1]/vs[0]),math.log(sum(vs)/previous_volume),
                sum(vs)/sum(os),math.log(os[1]/os[0]),sum(iv)/200,(iv[1]-iv[0])/100]
        q['volume']=q['interaction']+volume[:4]
        q['mixed']=q['interaction']+volume
        target=prices[r['target_date']]
        if not target.get('high') or not target.get('low') or target['low']<=0:continue
        q['abs_return']=abs(q['return']);q['range']=math.log(target['high']/target['low'])
        out.append(q)
    return out,dict(excluded)


def magnitude(rows,target):
    preds={k:[] for k in FAMILIES+['recent_mean']}
    for start,train,cal,test in splits(rows):
        history=train+cal
        for family in preds:
            if family=='recent_mean':values=np.repeat(np.mean([r[target] for r in cal]),len(test))
            else:
                x=np.array([r[family] for r in history]);m=x.mean(axis=0);s=x.std(axis=0);s[s==0]=1
                model=Ridge(alpha=10).fit((x-m)/s,np.log([r[target]+1e-5 for r in history]))
                # Fixed log transform; no test-window bias correction or tuning.
                values=np.maximum(0,np.exp(model.predict((np.array([r[family] for r in test])-m)/s))-1e-5)
            preds[family]+=[{'date':r['date'],'actual':r[target],'estimate':float(v)} for r,v in zip(test,values)]
    scores={}
    for k,rs in preds.items():
        actual=np.array([r['actual'] for r in rs]);estimated=np.array([r['estimate'] for r in rs])
        scores[k]={'n':len(rs),'mae':float(abs(actual-estimated).mean()),
                   'spearman':float(spearmanr(actual,estimated).statistic)}
    comparisons={}
    for family in FAMILIES[1:]:
        for baseline in ('price','recent_mean'):
            a,b=preds[family],preds[baseline]
            if [r['date'] for r in a]!=[r['date'] for r in b]:raise ValueError('magnitude unpaired')
            delta=np.array([abs(r['actual']-r['estimate'])-abs(s['actual']-s['estimate']) for r,s in zip(a,b)])
            rng=np.random.default_rng(42);blocks=np.lib.stride_tricks.sliding_window_view(delta,5)
            means=np.array([blocks[rng.integers(len(blocks),size=int(np.ceil(len(delta)/5)))].ravel()[:len(delta)].mean() for _ in range(2000)])
            observed=float(delta.mean())
            comparisons[family+'_vs_'+baseline]={'mae_delta':observed,'block95':np.quantile(means,[.025,.975]).tolist(),
                'two_sided_centered_block_p':(1+int((np.abs(means-observed)>=abs(observed)).sum()))/(len(means)+1)}
    return {'scores':scores,'predictions':preds,'comparisons':comparisons,
            'note':'Magnitude diagnostics exploratory; no variance-risk-premium or option-return claim'}


def run(board,etfs,chain):
    rows,excluded=build(board,etfs,chain);preds,folds=evaluate(rows,FAMILIES)
    comparisons={}
    for f in FAMILIES[2:]:
        for b in ('price_calibrated','existing_calibrated','prior_recent'):
            comparisons[f+'_vs_'+b]=paired_loss(preds[f+'_calibrated'],preds[b])
    comparisons['volume_vs_interaction']=paired_loss(preds['volume_calibrated'],preds['interaction_calibrated'])
    comparisons['mixed_vs_volume']=paired_loss(preds['mixed_calibrated'],preds['volume_calibrated'])
    holm(comparisons)
    from research_direction_diagnostics import directional_scores
    magnitudes={t:magnitude(rows,t) for t in ('abs_return','range')}
    magnitude_comparisons={t+':'+k:v for t,m in magnitudes.items() for k,v in m['comparisons'].items()}
    holm(magnitude_comparisons)
    return {'status':'retrospective_research_only','common_rows':len(rows),'exclusions':excluded,
            'first_source':rows[0]['date'],'last_source':rows[-1]['date'],'folds':folds,
            'direction_scores':{k:directional_scores(v) for k,v in preds.items()},
            'direction_policies':{k:{str(b):policy(v,b) for b in (0.,.025,.05)} for k,v in preds.items()},
            'comparisons':comparisons,'direction_predictions':preds,
            'magnitude':magnitudes,
            'feature_groups':{'money':['call/put market amount vs past20 mean','log put/call market amount','call/put foreign imbalance and participation'],
                'interaction':['netflow*activity shocks','call/put imbalance product','call/put participation product'],
                'mixed':['money+interaction','log observed chain volume','log put/call volume','same-expiry volume change','volume/OI','log put/call OI','OI-weighted IV level and difference']},
            'limitations':['Chain volume is observed standard-front-chain subset, not all-market volume; missing strikes and DTE composition may confound sums',
                '15007 market amounts and regular-chain volume have different scopes; not substituted or reconciled as identical totals',
                'No new KRX queries; pinned preexisting private records. Historical availability and OHLC execution equivalence unverified',
                'Same-date paired comparisons only; no untouched holdout, no live update',
                'Calibration may collapse to recent base rate; high accuracy alone does not prove option information',
                'Magnitude is movement size, not profitability of long/short volatility. IV and realized horizon differ',
                '14 calibrated Brier comparisons Holm adjusted; 20 exploratory magnitude MAE comparisons Holm adjusted separately',
                'Magnitude uncertainty checks added after inspecting aggregate MAE; not a preregistered confirmation']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chain',type=Path,required=True);p.add_argument('--extract',action='store_true')
    p.add_argument('--manifest',type=Path,default=Path('data/manifests/option_surface_source_manifest_20261102.json'))
    p.add_argument('--gh',default='gh');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.extract:write(args.chain,extract(read(args.manifest),args.gh))
    board=PUBLIC/'derivatives_board_v1.json';etfs=PUBLIC/'kospi200_etf_candidates_daily_v1.json'
    result=run(read(board),read(etfs),read(args.chain))
    result['input_sha256']={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (board,etfs,args.chain)}
    result['implementation_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    write(args.output,result);print('wrote',args.output,flush=True)

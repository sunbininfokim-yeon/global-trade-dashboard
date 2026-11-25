import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import logit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression, QuantileRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SYMBOLS={'KOSPI':'kospi','005930':'samsung','000660':'hynix'}
US=('spy','nasdaq','sox')
FLOWS=('call_net','put_net')
SIZE=('gap_abs20','gap_abs1','kr_vol20','kr_return1','kr_return5')
PRE=(*SIZE,*US,'lag_reversal')
TEST_START='2016-01-01'
FEE_BPS=20
CONFIDENCE=.80


def read(path):
    return json.loads(path.read_text())


def daily(root, key):
    c=read(root/f'codex_regime_{key}_1d.json')['chart']['result'][0]
    time=pd.to_datetime(c['timestamp'],unit='s',utc=True).tz_convert(c['meta']['exchangeTimezoneName']).tz_localize(None).normalize()
    out=pd.DataFrame(c['indicators']['quote'][0],index=time)[['open','close']]
    if key=='spy':
        out['close']=c['indicators']['adjclose'][0]['adjclose']
    assert time.is_unique and time.is_monotonic_increasing
    return out.where(out.gt(0))


def panel(root, opening_file):
    kr={key:daily(root,ticker) for key,ticker in SYMBOLS.items()}
    index=kr['KOSPI'].index
    us_close=pd.concat({key:daily(root,key).close for key in US},axis=1)
    assert us_close.notna().all().all()
    us=us_close.pct_change(fill_method=None)
    source=pd.Series(us.index,index=us.index).reindex(index-pd.Timedelta(days=1),method='ffill').set_axis(index)
    assert (source.dropna().to_numpy() < source.dropna().index.to_numpy()).all()
    aligned=us.reindex(source).set_axis(index).where(source.ne(source.shift()),axis=0)
    for key in US:
        aligned[key+'_abs']=aligned[key].abs()
    flow=read(root/'codex_regime_15007_board.json')['kr']['investor_nets']['detailed_15007']['products']
    flow_cols={}
    for side in ('call','put'):
        rows=[]
        for row in flow['options_'+side]['series']:
            if row['quality']=='observed' and row['market_total']['buy_krw']>0:
                rows.append((pd.Timestamp(row['date']),row['foreign']['net_krw']/row['market_total']['buy_krw']))
        column=pd.Series(dict(rows),name=side+'_net')
        assert len(column)==len(rows)
        flow_cols[side+'_net']=column
    flow_frame=pd.DataFrame(flow_cols).reindex(index).shift()
    first=pd.DataFrame(read(opening_file)['rows'])
    first['date']=pd.to_datetime(first.date)
    first['open_to_15']=first.close_15m/first.session_open-1
    first['open_vs_prior_15']=first.close_15m/first.previous_close-1
    assert not first.duplicated(['symbol','date']).any()
    for code, p in kr.items():
        p=p.reindex(index)
        close=p.close.where(p.open.notna())
        gap=p.open/close.shift()-1
        ending=close/close.shift()-1
        reversal=(np.sign(gap)!=np.sign(ending)).astype(float).where(gap.abs().gt(1e-10)&ending.abs().gt(1e-10))
        ret=close.pct_change(fill_method=None)
        f=pd.DataFrame({
            'gap':gap,'abs_gap':gap.abs(),'gap_abs20':gap.abs().rolling(20).mean().shift(),
            'gap_abs1':gap.abs().shift(),'kr_vol20':ret.rolling(20).std().shift(),
            'kr_return1':ret.shift(),'kr_return5':close.pct_change(5,fill_method=None).shift(),
            'lag_reversal':reversal.shift(),'reversal':reversal,'open_to_close':close/p.open-1,
        }).join(aligned).join(flow_frame)
        f=f.join(first.loc[first.symbol==code].set_index('date')[['open_to_15','open_vs_prior_15']])
        yield code,f


def model(family):
    if family=='median':
        return make_pipeline(StandardScaler(),QuantileRegressor(quantile=.5,alpha=.01,solver='highs'))
    return make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=500))


def predict(train,test,y,cols,family):
    if not cols:
        return np.full(len(test),train[y].mean())
    m=model(family)
    if family=='median':
        return m.fit(train[list(cols)],train[y]*10000).predict(test[list(cols)]).clip(min=0)/10000
    return m.fit(train[list(cols)],train[y]).predict_proba(test[list(cols)])[:,1]


def walk(data,y,base,full,family,start=TEST_START,short=False):
    data=data[list(dict.fromkeys([y,*base,*full]))].dropna().sort_index()
    if short:
        folds=[(data.iloc[:30],data.iloc[30:])]
    else:
        test=data.loc[start:]
        folds=[(data.loc[:q.start_time-pd.Timedelta(days=1)],d) for q,d in test.groupby(test.index.to_period('Q'))]
    out=[]
    for tr,te in folds:
        if len(tr)<(30 if short else 120) or te.empty or (family!='median' and tr[y].nunique()!=2):
            continue
        assert tr.index.max()<te.index.min()
        out.append(pd.DataFrame({'y':te[y],'base':predict(tr,te,y,base,family),
                                 'candidate':predict(tr,te,y,full,family)},index=te.index))
    return pd.concat(out) if out else pd.DataFrame(columns=['y','base','candidate'],index=pd.DatetimeIndex([]))


def nw(series):
    x=np.asarray(series,dtype=float)
    if len(x)<10:
        return dict(delta=float(x.mean()) if len(x) else None,p=None,ci95=None,t=None)
    c=x-x.mean()
    variance=np.dot(c,c)/len(x)
    for lag in range(1,6):
        variance+=2*(1-lag/6)*np.dot(c[lag:],c[:-lag])/len(x)
    se=np.sqrt(max(0,variance)/len(x))
    t=x.mean()/se if se else None
    return dict(delta=float(x.mean()),t=float(t) if t is not None else None,
                p=float(norm.sf(t)) if t is not None else None,
                ci95=[float(x.mean()-1.96*se),float(x.mean()+1.96*se)] if se else None)


def comparison(frame,absolute=False):
    before=(frame.base-frame.y).abs() if absolute else (frame.base-frame.y)**2
    after=(frame.candidate-frame.y).abs() if absolute else (frame.candidate-frame.y)**2
    if frame.empty:
        return {'n':0,'p':None}
    out=dict(n=len(frame),start=str(frame.index.min().date()),end=str(frame.index.max().date()),
             base=float(before.mean()),candidate=float(after.mean()),**nw(before-after))
    if not absolute:
        out['events']=int(frame.y.sum())
        out['event_recall']=float((frame.loc[frame.y.eq(1),'candidate']>=.5).mean()) if out['events'] else None
    return out


def calibration(frame):
    frame=frame[['y','US3']].rename(columns={'US3':'base'}).sort_index().copy()
    frame['raw_logit']=logit(frame.base.clip(.0001,.9999))
    parts=[]
    for q,sub in frame.groupby(frame.index.to_period('Q')):
        tr=frame[frame.index<q.start_time]
        if len(tr)<250:
            continue
        parts.append(sub.assign(candidate=predict(tr,sub,'y',('raw_logit',),'binary')))
    return pd.concat(parts)


def reliability(frame):
    bins=[]
    for low,high in zip((50,60,70,80,90),(60,70,80,90,101)):
        p=frame.base
        confidence=np.maximum(p,1-p)
        window=(confidence>=low/100)&(confidence<high/100)
        if window.any():
            bins.append({'low':low,'high':min(100,high),'n':int(window.sum()),'confidence':float(confidence[window].mean()),
                         'hit':float(((p[window]>=.5)==frame.y[window]).mean())})
    return bins


def trade(frame,pred,fee):
    x=frame[['open_to_close']].join(pred[['US3']],how='inner').dropna()
    signed=np.where(x.US3>=CONFIDENCE,1,np.where(x.US3<=1-CONFIDENCE,-1,0))
    returns=np.where(signed!=0,10000*signed*x.open_to_close-fee,0)
    return pd.DataFrame({'n_trades':np.abs(signed),'net_bps':returns,'gross_bps':np.where(signed!=0,returns+fee,0)},index=x.index)


def source_history(path):
    rows=read(path)['rows']
    out={}
    for kind,subset in [('all',rows),('non_replay',[r for r in rows if r.get('kind')!='replay'])]:
        targets=[]
        for row in subset:
            for code in SYMBOLS:
                v=row.get('v1',{}).get(code,{})
                a=row.get('actual',{}).get(code,{})
                if isinstance(v.get('opening_up'),(int,float)) and isinstance(a.get('open_ret'),(int,float)):
                    targets.append((abs(v['opening_up']-.5),abs(a['open_ret'])))
        out[kind]={'days':len(subset),'rows':len(targets),'opening_confidence_abs_gap_corr':float(np.corrcoef(np.asarray(targets).T)[0,1]) if len(targets)>2 else None}
    return out


def main():
    ap=argparse.ArgumentParser(description='Evaluate frozen opening magnitude and reversal hypotheses on existing prices.')
    ap.add_argument('--snapshots',type=Path,required=True)
    ap.add_argument('--opening-labels',type=Path,required=True)
    ap.add_argument('--direction-predictions',type=Path,required=True)
    ap.add_argument('--display-history',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    forecasts=pd.read_csv(args.direction_predictions,parse_dates=['date']).set_index('date')
    results={}; checks=[]; portfolio=[]
    for code,frame in panel(args.snapshots,args.opening_labels):
        predictions={target: forecasts.loc[forecasts.experiment==f'{SYMBOLS[code]}/{target}/H1']
                     for target in ('gap','close_prior')}
        result={}
        size=(*SIZE,*(k+'_abs' for k in US))
        result['magnitude_median']=comparison(walk(frame,'abs_gap',SIZE,size,'median'),absolute=True)
        for value in (.01,.02):
            target=f'magnitude_{value:.2f}'
            event=frame.abs_gap.gt(value).astype(float).where(frame.abs_gap.notna())
            result[target]=comparison(walk(frame.assign(event=event),'event',SIZE,size,'binary'))
        for target,p in predictions.items():
            calibrated=calibration(p)
            result['cal_'+target]=comparison(calibrated)
            result['cal_'+target]['bins']=reliability(calibrated)
        measured=frame.join(predictions['gap'].US3.rename('direction_probability'))
        conf=measured.direction_probability.sub(.5).abs()
        subsets=pd.cut(conf,bins=[-.01,.1,.3,.5],labels=['50-60','60-80','80-100'],right=False,include_lowest=True)
        power=measured.groupby(subsets,observed=True).abs_gap.agg(['size','mean']).dropna()
        result['strength_descriptive']={'bins':{str(k):{'n':int(v['size']),'mean_gap':float(v['mean'])} for k,v in power.iterrows()},
            'correlation':float(conf.corr(measured.abs_gap))}
        result['reversal_pre']=comparison(walk(frame,'reversal',(),PRE,'binary'))
        result['reversal_options']=comparison(walk(frame,'reversal',PRE,(*PRE,*FLOWS),'binary'))
        result['reversal_15m']=comparison(walk(frame,'reversal',PRE,(*PRE,'gap','open_to_15','open_vs_prior_15'),'binary',short=True))
        trades=trade(frame,predictions['gap'],FEE_BPS)
        active=trades.n_trades.astype(bool)
        result['trading']={'session_n':len(trades),'trades':int(active.sum()),
                           'net_bps_trade':float(trades.loc[active,'net_bps'].mean()),
                           'gross_bps_trade':float(trades.loc[active,'gross_bps'].mean()),
                           **nw(trades.net_bps)}
        portfolio.append(trades.assign(ticker=code))
        checks.extend((code,k,v) for k,v in result.items() if 'p' in v)
        results[code]=result
    assert len(checks)==27, len(checks)
    adjusted=0.
    for rank,(_,_,v) in enumerate(sorted((t for t in checks if t[2]['p'] is not None),key=lambda row:row[2]['p'])):
        adjusted=min(1.,max(adjusted,v['p']*(len(checks)-rank)))
        v['p_holm_27']=adjusted
    port=pd.concat(portfolio)
    dates=port.groupby(level=0)[['n_trades','net_bps','gross_bps']].sum()
    total=int(port.n_trades.sum())
    meta={'data':'Research replay from Yahoo daily, Yahoo/Naver opening bars, KRX 15007 raw-backed board, and previous US3 walk-forward forecasts',
          'comparison':'positive delta favors candidate. Opening midpoint absolute loss in return units, binary Brier, trade daily net bp.',
          'tests':'NW lag 5 one-sided p values, Holm 27 primary tests. Outcome dates and decisions paired.',
          'trade':'market open to close, top confidence threshold 80%, equal unit observations, 20bp round trip. Index is a proxy. Net per day includes no-trade days.'}
    args.output.write_text(json.dumps({'method':meta,'results':results,
        'trading_portfolio_descriptive':{'trades':total,'net_bps_trade':{k:float(dates.gross_bps.sum()/total-k) for k in (20,25,30)}},
        'v1_display_archive':source_history(args.display_history)},indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    for code,k,v in checks:
        print(code,k,{l:round(z,6) if isinstance(z,float) else z for l,z in v.items() if l!='bins'})


if __name__=='__main__':
    main()

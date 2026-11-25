"""Korean semiconductor close to US regular-session direction, research only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

import exchange_calendars as xc
import numpy as np
import pandas as pd
import requests
from scipy.special import expit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from research_direction_diagnostics import ReviewedCalendar

SCHEMA = 'kr-to-us-semiconductor-v1'
MODEL = Path(__file__).with_name('models') / 'shadow' / 'kr_to_us_semiconductor_20261120.json'
TARGETS = ('sox', 'mu', 'nvda', 'amd', 'avgo')
SYMBOLS = {'kospi': '^KS11', 'samsung': '005930.KS', 'hynix': '000660.KS',
           'nasdaq': '^IXIC', **{k: k.upper() for k in TARGETS}, 'sox': '^SOX'}
US = ['previous_nasdaq', 'previous_sox', 'previous_asset', 'asset_vol20']
KR = ['kospi_gap', 'kospi_body']
SEMI = ['samsung_relative_gap', 'samsung_relative_body', 'hynix_relative_gap', 'hynix_relative_body']
HEADS = ['opening', 'intraday', 'closing']


def digest(doc):
    return hashlib.sha256(json.dumps({k:v for k,v in doc.items() if k != 'model_id'},
                                     sort_keys=True, allow_nan=False).encode()).hexdigest()


def fetch(directory):
    for key, symbol in SYMBOLS.items():
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + quote(symbol, safe='')
        response = requests.get(url, params={'range':'3mo', 'interval':'1d'},
                                headers={'User-Agent':'Mozilla/5.0'}, timeout=20)
        response.raise_for_status()
        (directory / (key + '.json')).write_bytes(response.content)


def prices(directory, key):
    doc = json.loads((directory / (key + '.json')).read_text())
    chart, = doc['chart']['result']
    meta = chart['meta']
    if meta['symbol'] != SYMBOLS[key] or meta['dataGranularity'] != '1d':
        raise ValueError(f'wrong daily series for {key}')
    dates = pd.to_datetime(chart['timestamp'],unit='s',utc=True).tz_convert(
        meta['exchangeTimezoneName']).tz_localize(None).normalize()
    if not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError(f'invalid dates for {key}')
    q = pd.DataFrame(chart['indicators']['quote'][0],index=dates)
    return q[['open','close']].where(q[['open','close']].gt(0) & np.isfinite(q[['open','close']]))


def panel(directory, end):
    quotes = {k:prices(directory,k) for k in SYMBOLS}
    start = min(q.index.min() for q in quotes.values()) - pd.Timedelta(days=10)
    kr = xc.get_calendar('XKRX',start=start,end=end + pd.Timedelta(days=2))
    ny = xc.get_calendar('XNYS',start=start,end=end + pd.Timedelta(days=2))
    sessions = ReviewedCalendar(kr).sessions
    domestic = pd.DataFrame(index=sessions)
    for k in ('kospi','samsung','hynix'):
        q = np.log(quotes[k].reindex(sessions))
        gap, body = q.open - q.close.shift(), q.close - q.open
        if k == 'kospi':
            domestic['kospi_gap'], domestic['kospi_body'] = gap, body
        else:
            domestic[k+'_relative_gap'] = gap - domestic.kospi_gap
            domestic[k+'_relative_body'] = body - domestic.kospi_body
    # A Korean holiday never carries the last Korean observation into a new US date.
    dates = ny.sessions[ny.sessions <= end]
    both = dates.intersection(sessions)
    assert (kr.schedule.loc[both,'close'] < ny.schedule.loc[both,'open']).all()
    common = domestic.reindex(dates)
    prior = {}
    for k in ('nasdaq', *TARGETS):
        prior[k] = np.log(quotes[k].close.reindex(dates)).diff().shift()
    common['previous_nasdaq'] = prior['nasdaq']
    common['previous_sox'] = prior['sox']
    outputs = {}
    for k in TARGETS:
        f = common.copy()
        f['previous_asset'] = prior[k]
        f['asset_vol20'] = prior[k].rolling(20).std()
        q = np.log(quotes[k].reindex(dates))
        moves = {'opening': q.open - q.close.shift(), 'intraday': q.close - q.open,
                 'closing': q.close.diff()}
        for h, move in moves.items():
            f[h] = move.gt(0).astype(float).where(move.notna() & move.ne(0))
        outputs[k] = f
    return outputs


def features(ticker):
    # For SOX the asset's own lag is already included as previous_sox.
    us = [f for f in US if ticker != 'sox' or f != 'previous_asset']
    return {'us': us, 'market': us + KR, 'semiconductors': us + KR + SEMI}


def fit(rows, head, cols):
    scaler = StandardScaler().fit(rows[cols])
    reg = LogisticRegression(C=1, max_iter=1000).fit(scaler.transform(rows[cols]), rows[head])
    return dict(features=cols, mean=scaler.mean_.tolist(), scale=scaler.scale_.tolist(),
                coef=reg.coef_[0].tolist(), intercept=float(reg.intercept_[0]))


def probabilities(model, rows):
    x = rows[model['features']].to_numpy()
    return expit((x-model['mean']) / model['scale'] @ model['coef'] + model['intercept'])


def validate(frame, head, groups):
    rows = frame.dropna(subset=[head,*groups['semiconductors']])
    parts = []
    period = rows.loc['2016':]
    for quarter, test in period.groupby(period.index.to_period('Q')):
        past = rows[rows.index < quarter.start_time]
        if len(past) < 252 or past[head].nunique() < 2:
            continue
        part = pd.DataFrame({'observed_up':test[head], 'base_rate':past[head].mean()}, index=test.index)
        for name, cols in groups.items():
            part[name] = probabilities(fit(past, head, cols), test)
        parts.append(part)
    scores = pd.concat(parts)
    y = scores.observed_up
    losses = scores.drop(columns='observed_up').sub(y,axis=0).pow(2)
    gains = (losses.market - losses.semiconductors).to_numpy()
    centered = gains - gains.mean()
    var = centered @ centered
    for lag in range(1,11):
        var += 2 * (1-lag/11) * (centered[lag:] @ centered[:-lag])
    se = np.sqrt(max(0,var)) / len(gains)
    up = scores.semiconductors >= .5
    summary = dict(n=len(scores), start=str(scores.index.min().date()), end=str(scores.index.max().date()),
                   base_rate=float(y.mean()), brier=losses.mean().to_dict(),
                   incremental_gain=float(gains.mean()),
                   ci95=(gains.mean()+np.array([-1,1])*1.96*se).tolist(),
                   p=float(norm.sf(gains.mean()/se)) if se else 1.,
                   recall_up=float(up[y==1].mean()), recall_down=float((~up[y==0]).mean()),
                   hit=float((up==y).mean()))
    return fit(rows, head, groups['semiconductors']), summary, scores


def check_completed_us_date(day, when):
    ny = xc.get_calendar('XNYS', start=day-pd.Timedelta(days=8), end=day+pd.Timedelta(days=8))
    if day not in ny.sessions or when.tzinfo is None or when < ny.session_close(day):
        raise ValueError('requires a completed US trading session')


def train(directory, through):
    check_completed_us_date(through, pd.Timestamp.now(tz='UTC'))
    fitted, reports, predictions = {}, {}, []
    for ticker, frame in panel(directory, through).items():
        groups = features(ticker)
        endpoint = prices(directory, ticker).reindex([through])
        if endpoint.isna().any().any() or frame.loc[[through], groups['semiconductors']].isna().any().any():
            raise ValueError(f'incomplete training cutoff prices or inputs for {ticker}')
        fitted[ticker], reports[ticker] = {}, {}
        for h in HEADS:
            model, result, scores = validate(frame, h, groups)
            fitted[ticker][h] = model
            reports[ticker][h] = result
            predictions.append(scores.assign(ticker=ticker, head=h))
    tests = sorted([r for ticker in reports.values() for r in ticker.values()], key=lambda r:r['p'])
    adjusted = 0.
    for i, r in enumerate(tests):
        adjusted = max(adjusted, min(1., (len(tests)-i)*r['p']))
        r.update(p_holm=adjusted, incremental_skill='detected' if adjusted < .05 else 'unconfirmed')
    artifact = dict(schema=SCHEMA, trained_through=str(through.date()), created_at=pd.Timestamp.now(tz='UTC').isoformat(),
                    models=fitted, validation=reports,
                    source_hashes={k:hashlib.sha256((directory / (k+'.json')).read_bytes()).hexdigest() for k in SYMBOLS})
    artifact['model_id'] = digest(artifact)
    return artifact, pd.concat(predictions)


def check_window(target, when):
    start, end = target - pd.Timedelta(days=8), target + pd.Timedelta(days=8)
    kr = xc.get_calendar('XKRX',start=start,end=end)
    ny = xc.get_calendar('XNYS',start=start,end=end)
    if target not in ReviewedCalendar(kr).sessions or target not in ny.sessions:
        raise ValueError('requires a joint KRX and US regular trading date')
    if when.tzinfo is None or not kr.session_close(target) <= when < ny.session_open(target):
        raise ValueError('requires a completed Korean session before the US opening')


def infer(model, directory, target, when, replay):
    check_window(target, when)
    if model['schema'] != SCHEMA or model['model_id'] != digest(model):
        raise ValueError('invalid frozen model')
    if target <= pd.Timestamp(model['trained_through']) or (not replay and when < pd.Timestamp(model['created_at'])):
        raise ValueError('target or issuance precedes the frozen model')
    ny = xc.get_calendar('XNYS', start=target-pd.Timedelta(days=14), end=target+pd.Timedelta(days=2))
    previous_us = ny.previous_session(target)
    results = {}
    for ticker, frame in panel(directory,target).items():
        last = frame.loc[[target]]
        if last[features(ticker)['semiconductors']].isna().any().any():
            results[ticker] = {'status':'unavailable'}
            continue
        results[ticker] = {}
        for h in HEADS:
            p = float(probabilities(model['models'][ticker][h],last)[0])
            results[ticker][h] = {'up':p,'down':1-p,'incremental_skill':model['validation'][ticker][h]['incremental_skill']}
    return dict(schema=SCHEMA,status='retrospective_replay' if replay else 'research_forecast',
                model_id=model['model_id'],target_date=str(target.date()), as_of=when.isoformat(),
                kr_source_date=str(target.date()), us_source_date=str(previous_us.date()), results=results)


def save_new(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as temp:
        staged = Path(temp)/'output.json'
        staged.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
        os.link(staged,path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['train','replay','predict'])
    p.add_argument('--date',required=True)
    p.add_argument('--model',type=Path,default=MODEL)
    p.add_argument('--prices',type=Path)
    p.add_argument('--as-of')
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    day = pd.Timestamp(args.date)
    if day.strftime('%Y-%m-%d') != args.date:
        p.error('date requires YYYY-MM-DD')
    if args.command=='train':
        if not args.prices or args.output.exists() or args.model.exists() or args.model.resolve()==args.output.resolve():
            p.error('train needs snapshots and two distinct new outputs')
        model, scores = train(args.prices,day)
        scores.to_csv(args.output,index_label='date',mode='x')
        save_new(args.model,model)
        return
    model = json.loads(args.model.read_text())
    if args.command=='replay':
        if not args.prices or not args.as_of:
            p.error('replay needs snapshots and an as-of timestamp')
        result = infer(model,args.prices,day,pd.Timestamp(args.as_of),True)
    else:
        if args.prices or args.as_of:
            p.error('predict requires fresh downloads and the actual clock')
        check_window(day,pd.Timestamp.now(tz='UTC'))
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            fetch(directory)
            result = infer(model,directory,day,pd.Timestamp.now(tz='UTC'),False)
    save_new(args.output,result)


if __name__=='__main__':
    main()

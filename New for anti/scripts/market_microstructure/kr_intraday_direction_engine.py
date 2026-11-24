"""Train or run the standalone KRX intraday direction research model.

Daily input snapshots use the codex_regime_{kospi,samsung,hynix,spy,nasdaq,sox}_1d.json
Yahoo chart format. Training also uses the normalized opening-15m labels from
the month study. Prediction uses only the two completed source markets.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

import exchange_calendars as xc
import numpy as np
import pandas as pd
import requests
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from research_direction_diagnostics import ReviewedCalendar


SYMBOLS = {'KOSPI': 'kospi', '005930': 'samsung', '000660': 'hynix'}
HEADS = ('first15_vs_open', 'close_vs_open')
US_KEYS = ('spy', 'nasdaq', 'sox')
FEATURES = ('kr_return1', 'kr_return5', *US_KEYS)
SCHEMA = 'kr-intraday-direction-research-v1'
DEFAULT_MODEL = Path(__file__).with_name('models') / 'shadow' / 'kr_intraday_direction_20261120.json'
YAHOO_SYMBOLS = {'kospi': '^KS11', 'samsung': '005930.KS', 'hynix': '000660.KS',
                 'spy': 'SPY', 'nasdaq': '^IXIC', 'sox': '^SOX'}


def fetch_prices(directory):
    with requests.Session() as session:
        for key, symbol in YAHOO_SYMBOLS.items():
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe="")}'
            response = session.get(url, params={'interval': '1d', 'range': '1mo'},
                                   headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            response.raise_for_status()
            payload = response.json()
            if payload['chart'].get('error') or not payload['chart'].get('result'):
                raise ValueError(f'Yahoo daily price data unavailable for {symbol}')
            write(directory / f'codex_regime_{key}_1d.json', payload)


def read(path):
    return json.loads(path.read_text())


def write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def chart(directory, name):
    raw = read(directory / f'codex_regime_{name}_1d.json')['chart']['result'][0]
    dates = pd.to_datetime(raw['timestamp'], unit='s', utc=True).tz_convert(
        raw['meta']['exchangeTimezoneName']).tz_localize(None).normalize()
    if not dates.is_unique:
        raise ValueError(f'duplicate session in {name}')
    frame = pd.DataFrame(raw['indicators']['quote'][0], index=dates)[['open', 'close']]
    if name == 'spy':
        frame['close'] = raw['indicators']['adjclose'][0]['adjclose']
    return frame.where(frame.gt(0)).sort_index()


def input_frames(directory):
    local = {ticker: chart(directory, name) for ticker, name in SYMBOLS.items()}
    us = pd.concat({k: chart(directory, k).close for k in US_KEYS}, axis=1)
    return local, us.pct_change(fill_method=None)


def domestic_features(prices):
    close = prices.close.where(prices.open.notna())
    return pd.DataFrame({
        'kr_return1': close.pct_change(fill_method=None),
        'kr_return5': close.pct_change(5, fill_method=None),
    })


def opening_returns(path):
    rows = pd.DataFrame(read(path)['rows'])
    if not rows.symbol.isin(SYMBOLS).all() or rows.duplicated(['symbol', 'date']).any():
        raise ValueError('invalid opening label symbol or duplicate label')
    rows['date'] = pd.to_datetime(rows.date, format='%Y-%m-%d')
    for name in ('session_open_kst', 'bar_end_kst'):
        times = rows[name].map(pd.Timestamp)
        if times.map(lambda value: value.tzinfo is None).any():
            raise ValueError('opening label timestamps must include a timezone')
        rows[name] = pd.to_datetime(times, utc=True).dt.tz_convert('Asia/Seoul')
    if not (rows.session_open_kst.dt.tz_localize(None).dt.normalize().eq(rows.date)
            & (rows.bar_end_kst - rows.session_open_kst).eq(pd.Timedelta(minutes=15))).all():
        raise ValueError('invalid opening label time window')
    for column in ('session_open', 'close_15m'):
        rows[column] = pd.to_numeric(rows[column], errors='raise')
        if not (np.isfinite(rows[column]) & rows[column].gt(0)).all():
            raise ValueError('invalid opening label price')
    return rows.assign(ret=rows.close_15m / rows.session_open - 1).set_index(['symbol', 'date']).ret


def fit(data):
    scaler = StandardScaler().fit(data[list(FEATURES)])
    model = LogisticRegression(C=1, max_iter=500).fit(scaler.transform(data[list(FEATURES)]), data.y)
    return {'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
            'coef': model.coef_[0].tolist(), 'intercept': float(model.intercept_[0])}


def probs(model, x):
    return expit(((x - model['mean']) / model['scale']) @ model['coef'] + model['intercept'])


def evaluate(data, head):
    blocks = []
    if head == 'first15_vs_open':
        if len(data) > 30 and data.y.iloc[:30].nunique() == 2:
            blocks.append((data.iloc[:30], data.iloc[30:]))
    else:
        for q, test in data.loc['2016':].groupby(data.loc['2016':].index.to_period('Q')):
            train = data.loc[data.index < q.start_time]
            if len(train) >= 120 and train.y.nunique() == 2:
                blocks.append((train, test))
    if not blocks:
        return {'n': 0}
    frame = pd.concat([test.assign(p=probs(fit(train), test[list(FEATURES)].to_numpy()))
                       for train, test in blocks])
    up = frame.y.eq(1)
    hit_up = float(frame.p[up].ge(.5).mean()) if up.any() else None
    hit_down = float(frame.p[~up].lt(.5).mean()) if (~up).any() else None
    return {'n': len(frame), 'start': str(frame.index.min().date()), 'end': str(frame.index.max().date()),
            'up_recall': hit_up, 'down_recall': hit_down,
            'balanced_accuracy': (hit_up + hit_down) / 2 if hit_up is not None and hit_down is not None else None,
            'brier': float(((frame.p - frame.y) ** 2).mean())}


def train_model(directory, labels, cutoff):
    local, us = input_frames(directory)
    index = local['KOSPI'].index
    us_sessions = pd.Series(us.index, index=us.index)
    aligned_sessions = us_sessions.reindex(index - pd.Timedelta(days=1), method='ffill').set_axis(index)
    aligned = us.reindex(aligned_sessions).set_axis(index).where(aligned_sessions.ne(aligned_sessions.shift()), axis=0)
    opening = opening_returns(labels)
    heads = {}
    for symbol, prices in local.items():
        features = domestic_features(prices.reindex(index)).shift().join(aligned)
        targets = {
            'first15_vs_open': opening.xs(symbol) if symbol in opening.index.get_level_values(0) else pd.Series(dtype=float),
            'close_vs_open': prices.close / prices.open - 1,
        }
        heads[symbol] = {}
        for name, returns in targets.items():
            cohort = features.join(returns.rename('return')).loc[:cutoff].dropna()
            cohort = cohort.loc[cohort['return'].abs() > 1e-10].assign(y=lambda f: f['return'].gt(0).astype(int))
            minimum = 30 if name == 'first15_vs_open' else 120
            if len(cohort) < minimum or cohort.y.nunique() < 2:
                heads[symbol][name] = {'status': 'insufficient_training_data', 'training_n': len(cohort)}
                continue
            heads[symbol][name] = dict(fit(cohort), status='research_only', training_n=len(cohort),
                                       validation=evaluate(cohort, name))
    document = {'schema': SCHEMA, 'trained_through': cutoff, 'features': list(FEATURES), 'heads': heads}
    document['model_id'] = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
    return document


def preopen_sessions(target, as_of):
    target_day = pd.Timestamp(target)
    if target_day.strftime('%Y-%m-%d') != target:
        raise ValueError('target must use YYYY-MM-DD')
    cutoff = pd.Timestamp(target + 'T08:30:00+09:00')
    if as_of.tzinfo is None or as_of > cutoff:
        raise ValueError('use a timezone-aware time at or before the 08:30 KST cutoff')
    cal_start = (target_day - timedelta(days=45)).strftime('%Y-%m-%d')
    kr = xc.get_calendar('XKRX', start=cal_start, end=target_day)
    reviewed = ReviewedCalendar(kr)
    if not reviewed.is_session(target):
        raise ValueError('target is not a reviewed KRX trading session')
    previous_kr = reviewed.sessions[reviewed.sessions < target_day][-6:]
    if len(previous_kr) != 6:
        raise ValueError('missing reviewed KRX calendar history')
    kr_day = previous_kr[-1]
    ny = xc.get_calendar('XNYS', start=cal_start, end=target_day)
    us_day = ny.sessions[ny.sessions < target_day][-1]
    prev_us = ny.previous_session(us_day)
    if as_of < max(kr.session_close(kr_day), ny.session_close(us_day)):
        raise ValueError('required source session is still open')
    return previous_kr, us_day, prev_us, us_day > ny.sessions[ny.sessions < kr_day][-1]


def predict(directory, model, target, as_of):
    if not (model['schema'] == SCHEMA and model['features'] == list(FEATURES)
            and set(model['heads']) == set(SYMBOLS)):
        raise ValueError('incompatible model')
    check = {k: v for k, v in model.items() if k != 'model_id'}
    if hashlib.sha256(json.dumps(check, sort_keys=True).encode()).hexdigest() != model['model_id']:
        raise ValueError('model ID does not match model contents')
    if target <= model['trained_through']:
        raise ValueError('target must be after model training')
    as_of = pd.Timestamp(as_of)
    previous_kr, us_day, prev_us, new_us_close = preopen_sessions(target, as_of)
    kr_day = previous_kr[-1]
    local, us = input_frames(directory)
    exact_us = us.loc[us.index <= us_day].index[-2:]
    us_vector = (us.loc[us_day] if new_us_close and list(exact_us) == [prev_us, us_day]
                 else pd.Series(index=US_KEYS, dtype=float))
    cards = {}
    for symbol, prices in local.items():
        features = domestic_features(prices.reindex(previous_kr)).loc[kr_day]
        x = pd.concat([features, us_vector]).reindex(FEATURES)
        cards[symbol] = {}
        for name in HEADS:
            head = model['heads'][symbol][name]
            if x.isna().any() or head['status'] != 'research_only':
                cards[symbol][name] = {'status': 'unavailable', 'up': None, 'down': None}
                continue
            p = float(probs(head, x.to_numpy()))
            cards[symbol][name] = {'status': 'research_only', 'up': p, 'down': 1-p,
                                   'validation_n': head['validation']['n']}
    return {'schema': SCHEMA, 'status': 'research_snapshot', 'target_date': target, 'as_of': as_of.isoformat(),
            'kr_source_date': str(kr_day.date()), 'us_source_date': str(us_day.date()), 'model_id': model['model_id'],
            'timing_evidence': 'user-supplied as-of time; read-only snapshot, no proof of original issue time',
            'probability_basis': 'conditional on a nonflat move vs the same-day regular-session opening price',
            'cards': cards}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('train', 'predict'))
    parser.add_argument('--prices-dir', type=Path, help='frozen Yahoo daily snapshots for offline research')
    parser.add_argument('--live', action='store_true', help='fetch current daily prices and use the actual clock')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--opening-labels', type=Path)
    parser.add_argument('--through')
    parser.add_argument('--target')
    parser.add_argument('--as-of')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'train':
        if args.live or not all([args.prices_dir, args.opening_labels, args.through]):
            parser.error('train requires --prices-dir, --opening-labels and --through')
        if args.model.resolve() == DEFAULT_MODEL.resolve():
            parser.error('train requires a new --model path')
        if args.model.exists():
            parser.error('training artifact already exists')
        if pd.Timestamp(args.through).strftime('%Y-%m-%d') != args.through:
            parser.error('--through must use YYYY-MM-DD')
        write(args.model, train_model(args.prices_dir, args.opening_labels, args.through))
    else:
        if not args.target or not args.output:
            parser.error('predict requires --target and --output')
        if args.live and (args.as_of or args.prices_dir) or not args.live and not (args.as_of and args.prices_dir):
            parser.error('use --live or provide both --as-of and --prices-dir')
        if args.output.resolve() == args.model.resolve():
            parser.error('forecast output must be different from the frozen model')
        model = read(args.model)
        if args.live:
            preopen_sessions(args.target, pd.Timestamp(datetime.now(timezone.utc)))
            with TemporaryDirectory() as folder:
                directory = Path(folder)
                fetch_prices(directory)
                out = predict(directory, model, args.target, datetime.now(timezone.utc))
            out['timing_evidence'] = 'local generation time, public availability unverified'
        else:
            out = predict(args.prices_dir, model, args.target, args.as_of)
        write(args.output, out)


if __name__ == '__main__':
    main()

"""Fit and run independent preopen and first-hour KOSPI gap reversal estimates."""

import argparse
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import exchange_calendars as xc
import numpy as np
import pandas as pd
from scipy.special import expit

from kr_gap_size_shadow import DEFAULT_MODEL as DEFAULT_SIZE_MODEL, SCHEMA as SIZE_SCHEMA, identity
from kr_intraday_direction_engine import preopen_sessions
from research_direction_diagnostics import ReviewedCalendar
from research_kr_move_power import SIZE, US, model, nw, panel, walk
from us_kr_direction_engine import write_immutable

SCHEMA = 'kr-gap-reversal-shadow-v1'
DEFAULT_MODEL = Path(__file__).with_name('models') / 'shadow' / 'kr_gap_reversal_20261120.json'
ARCHIVE = Path('data/forecasts/kr_gap_reversal_shadow')
MIN_TRAIN = 252
GAP_LOOKBACK = 126
FEATURES = ('relative_gap', 'gap_up', 'signed_first_hour_move')
SEOUL = 'Asia/Seoul'


def read(path):
    return json.loads(path.read_text())


def yahoo_frame(path, interval):
    result, = read(path)['chart']['result']
    meta = result['meta']
    if meta['symbol'] != '^KS11' or meta['dataGranularity'] not in interval:
        raise ValueError('expected Yahoo KOSPI prices at the requested interval')
    index = pd.to_datetime(result['timestamp'], unit='s', utc=True).tz_convert(SEOUL)
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError('Yahoo KOSPI timestamps must be ordered and unique')
    return pd.DataFrame(result['indicators']['quote'][0], index=index)[['open', 'close']]


def calendar(start, end):
    return xc.get_calendar('XKRX', start=start - pd.Timedelta(days=3), end=end + pd.Timedelta(days=3))


def daily_series(path, through):
    prices = yahoo_frame(path, ('1d',))
    prices.index = prices.index.tz_localize(None).normalize()
    if not prices.index.is_unique:
        raise ValueError('expected one daily KOSPI row per session')
    cal = calendar(prices.index.min(), through)
    sessions = ReviewedCalendar(cal).sessions_in_range(prices.index.min(), through)
    prices = prices.reindex(sessions)
    return prices.where(prices > 0)


def prior_context(prices):
    previous_close = prices.close.shift()
    prior_vol = np.log(prices.close).diff().rolling(20).std().shift()
    return previous_close, prior_vol.where(prior_vol > 0)


def first_hour_features(open_price, first_hour_close, prior_close, prior_vol):
    gap = np.log(open_price / prior_close)
    return pd.DataFrame({
        'relative_gap': gap.abs() / prior_vol,
        'gap_up': (gap > 0).astype(float),
        'signed_first_hour_move': np.sign(gap) * np.log(first_hour_close / open_price) / prior_vol,
    }).where(gap.ne(0), axis=0)


def reversal_labels(prices, previous_close):
    gap = prices.open - previous_close
    close_move = prices.close - previous_close
    eligible = gap.notna() & close_move.notna() & gap.ne(0) & close_move.ne(0)
    return ((gap * close_move) < 0).astype(float).where(eligible).rename('reverse')


def first_hour_panel(daily, hourly, cutoff):
    prior_close, prior_vol = prior_context(daily)
    cal = calendar(daily.index.min(), cutoff)
    session_opens = cal.schedule.open.dt.tz_convert(SEOUL)
    normal_days = session_opens.index[session_opens.dt.strftime('%H:%M').eq('09:00')]
    bars = hourly[hourly.index.strftime('%H:%M') == '09:00'].copy()
    bars.index = bars.index.tz_localize(None).normalize()
    bars = bars.reindex(daily.index)
    reliable = bars.index.isin(normal_days) & np.isclose(bars.open, daily.open, rtol=0, atol=.011)
    bars = bars.where(reliable & bars.open.gt(0) & bars.close.gt(0), axis=0)
    return first_hour_features(bars.open, bars.close, prior_close, prior_vol).join(
        reversal_labels(daily, prior_close)
    ).replace([np.inf, -np.inf], np.nan).dropna()


def gap_cuts(train):
    return train.predicted_abs_gap.tail(GAP_LOOKBACK).quantile([1/3, 2/3]).tolist()


def band(gap, cuts):
    return np.select([gap <= cuts[0], gap <= cuts[1]], ['low', 'middle'], default='high')


def fit_preopen(train):
    cuts = gap_cuts(train)
    grouped = train.groupby(band(train.predicted_abs_gap, cuts)).reverse.agg(['size', 'mean'])
    if set(grouped.index) != {'low', 'middle', 'high'}:
        raise ValueError('every predicted gap band needs training labels')
    return {'cuts': cuts, 'groups': grouped.rename(columns={'mean': 'rate'}).to_dict('index')}


def train_hour(train, features):
    return model('binary').fit(train[list(features)], train.reverse)


def validation(preopen, hour):
    preopen_losses, hour_losses = [], []
    for quarter, test in preopen.groupby(preopen.index.to_period('Q')):
        train = preopen[preopen.index < quarter.start_time]
        if len(train) < MIN_TRAIN:
            continue
        fitted = fit_preopen(train)
        p = pd.Series(band(test.predicted_abs_gap, fitted['cuts']), index=test.index).map(
            {name: values['rate'] for name, values in fitted['groups'].items()}
        )
        preopen_losses.append(pd.DataFrame({
            'baseline': (train.reverse.mean() - test.reverse) ** 2,
            'model': (p - test.reverse) ** 2,
        }))
    for quarter, test in hour.groupby(hour.index.to_period('Q')):
        train = hour[hour.index < quarter.start_time]
        if len(train) < MIN_TRAIN:
            continue
        losses = {}
        for name, columns in [('baseline', FEATURES[:2]), ('model', FEATURES)]:
            p = train_hour(train, columns).predict_proba(test[list(columns)])[:, 1]
            losses[name] = (p - test.reverse) ** 2
        hour_losses.append(pd.DataFrame(losses))
    out = {}
    for stage, parts in [('preopen', preopen_losses), ('first_hour', hour_losses)]:
        if not parts:
            raise ValueError(f'no out-of-sample quarters for {stage}')
        losses = pd.concat(parts)
        out[stage] = {
            'n': len(losses), 'start': str(losses.index[0].date()), 'end': str(losses.index[-1].date()),
            'brier': losses.mean().to_dict(), 'improvement_hac': nw(losses.baseline - losses.model),
        }
    return out


def freeze(daily_path, hourly_path, snapshots, labels, size_model, through, created_at):
    if size_model['schema'] != SIZE_SCHEMA or size_model['model_id'] != identity(size_model):
        raise ValueError('invalid gap-size model')
    cutoff = pd.Timestamp(through)
    if cutoff != cutoff.normalize() or cutoff > pd.Timestamp(size_model['trained_through']):
        raise ValueError('reversal training cutoff must be within the gap-size training history')
    daily = daily_series(daily_path, cutoff)
    hourly = yahoo_frame(hourly_path, ('1h', '60m'))
    # Refit the same gap-size specification on past quarters so each training
    # probability uses a gap estimate that had no access to that day's opening.
    _, frame = next(panel(snapshots, labels))
    cols = (*SIZE, *(key + '_abs' for key in US))
    gaps = walk(frame.loc[:cutoff], 'abs_gap', (), cols, 'median')
    preopen = gaps.candidate.rename('predicted_abs_gap').to_frame().join(
        reversal_labels(daily, daily.close.shift())
    ).dropna()
    hour = first_hour_panel(daily, hourly, cutoff)
    scores = validation(preopen, hour)
    scaler, reg = (step for _, step in train_hour(hour, FEATURES).steps)
    doc = {
        'schema': SCHEMA, 'ticker': 'KOSPI', 'created_at': created_at.isoformat(),
        'trained_through': through, 'gap_size_model_id': size_model['model_id'],
        'validation': scores,
        'preopen': fit_preopen(preopen),
        'first_hour': {
            'n': len(hour), 'features': list(FEATURES), 'mean': scaler.mean_.tolist(),
            'scale': scaler.scale_.tolist(), 'coefficients': reg.coef_[0].tolist(),
            'intercept': float(reg.intercept_[0]),
        },
    }
    doc['model_id'] = identity(doc)
    return doc


def infer_preopen(artifact, target, as_of, gap_forecast, replay):
    kr, us, _, fresh = preopen_sessions(target, as_of)
    if not fresh:
        raise ValueError('no new US close for target')
    expected = {
        'schema': SIZE_SCHEMA, 'model_id': artifact['gap_size_model_id'], 'target_date': target,
        'KR_source_date': str(kr[-1].date()), 'US_source_date': str(us.date()),
    }
    if any(gap_forecast.get(key) != value for key, value in expected.items()):
        raise ValueError('gap forecast does not match the target, sources or trained size model')
    statuses = {'research_preopen_forecast', 'retrospective_replay'} if replay else {'research_preopen_forecast'}
    issued = pd.Timestamp(gap_forecast['generated_at'])
    start = pd.Timestamp(target, tz=SEOUL)
    if gap_forecast.get('status') not in statuses or issued.tzinfo is None or not start <= issued <= as_of:
        raise ValueError('gap forecast was not issued in time for this session')
    gap = gap_forecast.get('results', {}).get('KOSPI', {}).get('median_abs_gap')
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap < 0:
        raise ValueError('missing KOSPI gap-size estimate')
    pre = artifact['preopen']
    group = band(gap, pre['cuts']).item()
    return pre['groups'][group]['rate'], {
        'predicted_median_abs_gap': gap, 'gap_size_band': group,
        'gap_size_model_id': gap_forecast['model_id'], 'gap_size_generated_at': issued.isoformat(),
        'KR_source_date': expected['KR_source_date'], 'US_source_date': expected['US_source_date'],
    }


def infer_first_hour(artifact, target, as_of, daily_path, hourly_path, replay):
    day = pd.Timestamp(target)
    cal = calendar(day - pd.Timedelta(days=65), day)
    reviewed = ReviewedCalendar(cal)
    if not reviewed.is_session(day):
        raise ValueError('target is not a reviewed KRX trading session')
    opening = cal.session_open(day).tz_convert(SEOUL)
    if opening.strftime('%H:%M') != '09:00':
        raise ValueError('first-hour model requires a 09:00 KRX opening')
    bar_end = opening + pd.Timedelta(hours=1)
    if not bar_end <= as_of < cal.session_close(day):
        raise ValueError('first-hour forecast requires a closed 09:00 bar before the KRX close')
    prior_session = reviewed.sessions[reviewed.sessions < day][-1]
    prices = daily_series(daily_path, prior_session)
    prior_window = prices.close.tail(21)
    if len(prior_window) != 21 or prior_window.isna().any():
        raise ValueError('incomplete 21-session KOSPI close history')
    prior_close = prior_window.iloc[-1]
    prior_vol = np.log(prior_window).diff().std()
    hourly = yahoo_frame(hourly_path, ('1h', '60m'))
    if opening not in hourly.index or (not replay and bar_end not in hourly.index):
        raise ValueError('first hourly bar is unavailable or Yahoo has not advanced to the next bar')
    bar = hourly.loc[opening]
    if bar.isna().any() or (bar <= 0).any() or bar.open == prior_close or prior_vol <= 0:
        raise ValueError('missing hourly prices, zero opening gap or invalid prior volatility')
    features = first_hour_features(
        pd.Series([bar.open]), pd.Series([bar.close]), prior_close, prior_vol
    ).iloc[0]
    head = artifact['first_hour']
    x = (features[list(FEATURES)].to_numpy() - head['mean']) / head['scale']
    p = float(expit(x @ head['coefficients'] + head['intercept']))
    close_up = 1 - p if features.gap_up else p
    return p, {
        'KR_source_date': str(prior_session.date()), 'first_hour_ended_at': bar_end.isoformat(),
        'previous_close': float(prior_close), 'open': float(bar.open), 'first_hour_close': float(bar.close),
        'probability_close_up_vs_previous_close': close_up,
        'probability_close_down_vs_previous_close': 1 - close_up,
    }


def infer(artifact, target, as_of, stage, *, gap=None, daily=None, hourly=None, replay=False):
    as_of = pd.Timestamp(as_of)
    if artifact['schema'] != SCHEMA or identity(artifact) != artifact['model_id']:
        raise ValueError('invalid reversal model')
    if pd.Timestamp(target).strftime('%Y-%m-%d') != target or target <= artifact['trained_through']:
        raise ValueError('target must be a date after training')
    if as_of.tzinfo is None or (not replay and as_of < pd.Timestamp(artifact['created_at'])):
        raise ValueError('forecast requires a timezone and cannot precede model creation')
    if stage == 'preopen':
        probability, inputs = infer_preopen(artifact, target, as_of, gap, replay)
    elif stage == 'first_hour':
        probability, inputs = infer_first_hour(artifact, target, as_of, daily, hourly, replay)
    else:
        raise ValueError('unknown forecast stage')
    return {
        'schema': SCHEMA, 'model_id': artifact['model_id'], 'ticker': 'KOSPI',
        'target_date': target, 'generated_at': as_of.isoformat(), 'stage': stage,
        'status': 'retrospective_replay' if replay else 'research_forecast',
        'conditional_on': 'nonflat_open_and_close_vs_previous_close',
        'probability_reversal': probability, 'probability_continuation': 1 - probability,
        **inputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('freeze', 'replay', 'record'))
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--size-model', type=Path, default=DEFAULT_SIZE_MODEL)
    parser.add_argument('--snapshots', type=Path)
    parser.add_argument('--opening-labels', type=Path)
    parser.add_argument('--through')
    parser.add_argument('--target')
    parser.add_argument('--as-of')
    parser.add_argument('--stage', choices=('preopen', 'first_hour'))
    parser.add_argument('--gap-forecast', type=Path)
    parser.add_argument('--daily', type=Path)
    parser.add_argument('--hourly', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    args = parser.parse_args()
    if args.command == 'freeze':
        if not all((args.snapshots, args.opening_labels, args.through, args.daily, args.hourly)):
            parser.error('freeze requires snapshots, opening labels, cutoff, daily and hourly prices')
        if args.model.exists():
            parser.error('freeze needs a new model file')
        doc = freeze(args.daily, args.hourly, args.snapshots, args.opening_labels,
                     read(args.size_model), args.through, pd.Timestamp.now(tz='UTC'))
        with TemporaryDirectory(dir=args.model.parent) as temp:
            staged = Path(temp) / args.model.name
            write_immutable(staged, doc)
            os.link(staged, args.model)
        return
    if not args.target or not args.stage:
        parser.error('inference requires a target and stage')
    if args.stage == 'preopen' and args.gap_forecast is None:
        parser.error('preopen requires a gap forecast')
    if args.stage == 'first_hour' and not all((args.daily, args.hourly)):
        parser.error('first_hour requires daily and hourly prices')
    artifact = read(args.model)
    kwargs = dict(gap=read(args.gap_forecast) if args.gap_forecast else None, daily=args.daily, hourly=args.hourly)
    if args.command == 'replay':
        if not args.as_of or not args.output or args.archive.resolve() in args.output.resolve().parents:
            parser.error('replay requires a timestamp and a scratch output outside the archive')
        if args.output.resolve() in {p.resolve() for p in
                                     (args.model, args.size_model, args.gap_forecast, args.daily, args.hourly) if p}:
            parser.error('replay output cannot overwrite an input')
        result = infer(artifact, args.target, args.as_of, args.stage, replay=True, **kwargs)
        write_immutable(args.output, result)
        return
    if args.as_of or args.output:
        parser.error('record uses the actual clock and the forecast archive')
    target = pd.Timestamp(args.target).strftime('%Y-%m-%d')
    if target != args.target or artifact['model_id'] != identity(artifact):
        parser.error('invalid target or model ID')
    first = args.archive / target / artifact['model_id'][:16] / args.stage / 'first.json'
    if first.exists():
        return
    result = infer(artifact, args.target, pd.Timestamp.now(tz='UTC'), args.stage, **kwargs)
    first.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=first.parent) as temp:
        staged = Path(temp) / first.name
        write_immutable(staged, result)
        try:
            os.link(staged, first)
        except FileExistsError:
            pass


if __name__ == '__main__':
    main()

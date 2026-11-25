"""Freeze or record the independently validated KRX opening gap size research model."""

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
from scipy.special import expit

from kr_intraday_direction_engine import YAHOO_SYMBOLS, preopen_sessions
from research_kr_move_power import SIZE, SYMBOLS, US, daily, model, panel
from us_kr_direction_engine import write_immutable

FEATURES = (*SIZE, *(key + '_abs' for key in US))
HEADS = {
    'KOSPI': ('median_abs_gap', 'probability_abs_gap_gt_1pct'),
    '005930': ('median_abs_gap', 'probability_abs_gap_gt_1pct', 'probability_abs_gap_gt_2pct'),
    '000660': ('median_abs_gap', 'probability_abs_gap_gt_1pct', 'probability_abs_gap_gt_2pct'),
}
SCHEMA = 'kr-gap-size-shadow-v1'
DEFAULT_MODEL = Path(__file__).with_name('models') / 'shadow' / 'kr_gap_size_20261120.json'


def identity(document):
    fields = {k: v for k, v in document.items() if k != 'model_id'}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()


def freeze(snapshots, labels, end, now):
    fitted = {}
    for code, frame in panel(snapshots, labels):
        train = frame.loc[:end, [*FEATURES, 'abs_gap']].dropna()
        if len(train) < 120:
            raise ValueError('insufficient training data')
        fitted[code] = {}
        for j, head in enumerate(HEADS[code]):
            is_median = j == 0
            y = train.abs_gap * 10000 if is_median else train.abs_gap.gt(j / 100)
            pipe = model('median' if is_median else 'binary').fit(train[list(FEATURES)], y)
            scaler, reg = pipe.steps[0][1], pipe.steps[1][1]
            fitted[code][head] = {
                'n': len(train), 'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
                'coefficients': np.asarray(reg.coef_).ravel().tolist(),
                'intercept': float(np.asarray(reg.intercept_).ravel()[0]),
            }
    out = {'schema': SCHEMA, 'trained_through': end, 'created_at': now.isoformat(),
           'features': list(FEATURES), 'heads': fitted}
    out['model_id'] = identity(out)
    return out


def fetch(snapshots):
    with requests.Session() as session:
        for key, ticker in YAHOO_SYMBOLS.items():
            url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + quote(ticker, safe='')
            rsp = session.get(url, params={'interval': '1d', 'range': '3mo'}, timeout=15,
                              headers={'User-Agent': 'Mozilla/5.0'})
            rsp.raise_for_status()
            doc = rsp.json()
            if doc['chart'].get('error') or not doc['chart'].get('result'):
                raise ValueError(f'daily source unavailable for {ticker}')
            (snapshots / f'codex_regime_{key}_1d.json').write_text(json.dumps(doc))


def features_for_day(snapshots, kr_day, us_day, us_prev):
    # The Korean index defines the observed trading-date sequence. Confirm the final date;
    # reindex stocks before any shifts so their missing sessions cannot be compressed out.
    kr_index = daily(snapshots, 'kospi').loc[:kr_day].index[-22:]
    if len(kr_index) != 22 or kr_index[-1] != kr_day:
        raise ValueError('missing required Korean price window')
    # Reconcile the whole lookback with the reviewed exchange calendar. A missing
    # daily KOSPI quote must not silently shrink or move a training-style window.
    import exchange_calendars as xc
    from research_direction_diagnostics import ReviewedCalendar
    cal = xc.get_calendar('XKRX', start=kr_day-pd.Timedelta(days=65), end=kr_day)
    expected = ReviewedCalendar(cal).sessions[-22:]
    if not kr_index.equals(expected):
        raise ValueError('Korean price window differs from reviewed trading calendar')
    us_abs = {}
    for key in US:
        p = daily(snapshots, key).close.reindex([us_prev, us_day])
        us_abs[key + '_abs'] = abs(p.iloc[1] / p.iloc[0] - 1)
    for code, key in SYMBOLS.items():
        p = daily(snapshots, key).reindex(kr_index)
        close = p.close.where(p.open.notna())
        r = close.pct_change(fill_method=None)
        g = (p.open / close.shift() - 1).abs()
        yield code, {'gap_abs20': g.iloc[-20:].mean(skipna=False),
                     'gap_abs1': g.iloc[-1],
                     'kr_vol20': r.iloc[-20:].std(skipna=False),
                     'kr_return1': r.iloc[-1],
                     'kr_return5': close.iloc[-1] / close.iloc[-6] - 1, **us_abs}


def infer(snapshots, artifact, target, as_of, replay):
    if (artifact['schema'] != SCHEMA or artifact['features'] != list(FEATURES)
            or identity(artifact) != artifact['model_id']
            or {k: set(v) for k, v in artifact['heads'].items()} != {k: set(v) for k, v in HEADS.items()}):
        raise ValueError('invalid frozen gap-size artifact')
    if target <= artifact['trained_through']:
        raise ValueError('target overlaps model training')
    as_of = pd.Timestamp(as_of)
    if not replay and as_of < pd.Timestamp(artifact['created_at']):
        raise ValueError('forecast precedes model creation')
    kr, us, previous_us, fresh = preopen_sessions(target, as_of)
    if not fresh:
        raise ValueError('no new US close for target')
    forecasts = {}
    for code, values in features_for_day(snapshots, kr[-1], us, previous_us):
        x = np.array([values[key] for key in FEATURES])
        if not np.isfinite(x).all():
            continue
        forecasts[code] = {}
        for head, m in artifact['heads'][code].items():
            f = ((x - m['mean']) / m['scale']) @ m['coefficients'] + m['intercept']
            value = max(0., float(f) / 10000) if head == 'median_abs_gap' else float(expit(f))
            if not math.isfinite(value):
                raise ValueError('nonfinite gap size forecast')
            forecasts[code][head] = value
    if not forecasts:
        raise ValueError('no valid asset inputs')
    return {'schema': SCHEMA, 'status': 'retrospective_replay' if replay else 'research_preopen_forecast',
            'target_date': target, 'generated_at': as_of.isoformat(), 'model_id': artifact['model_id'],
            'KR_source_date': str(kr[-1].date()), 'US_source_date': str(us.date()), 'results': forecasts}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('freeze', 'replay', 'record'))
    p.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    p.add_argument('--prices-dir', type=Path)
    p.add_argument('--opening-labels', type=Path)
    p.add_argument('--through')
    p.add_argument('--target')
    p.add_argument('--as-of')
    p.add_argument('--output', type=Path)
    p.add_argument('--archive', type=Path, default=Path('data/forecasts/kr_gap_size_shadow'))
    a = p.parse_args()
    if a.command == 'freeze':
        if not all((a.prices_dir, a.opening_labels, a.through)) or a.model.exists():
            p.error('freeze needs snapshots, labels, cutoff and a new model file')
        a.model.write_text(json.dumps(freeze(a.prices_dir, a.opening_labels, a.through, datetime.now(timezone.utc)),
                                     indent=2, allow_nan=False)+'\n')
        return
    if not a.target:
        p.error('target is required')
    artifact = json.loads(a.model.read_text())
    if a.command == 'replay':
        if not all((a.prices_dir, a.as_of, a.output)):
            p.error('replay needs snapshots, historical time and a scratch output path')
        replay_path = a.output.resolve()
        if a.model.resolve() == replay_path or a.archive.resolve() in replay_path.parents:
            p.error('replay output must be outside model and forecast archive')
        write_immutable(a.output, infer(a.prices_dir, artifact, a.target, a.as_of, replay=True))
        return
    if any((a.prices_dir, a.as_of, a.output)):
        p.error('record uses fresh sources and the actual clock')
    now = pd.Timestamp.now(tz='UTC')
    preopen_sessions(a.target, now)
    first = a.archive / a.target / artifact['model_id'][:16] / 'first.json'
    if first.exists():
        return
    with TemporaryDirectory() as folder:
        directory = Path(folder)
        fetch(directory)
        out = infer(directory, artifact, a.target, pd.Timestamp.now(tz='UTC'), replay=False)
    first.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=first.parent) as temp:
        staged = Path(temp) / first.name
        write_immutable(staged, out)
        try:
            os.link(staged, first)
        except FileExistsError:
            pass


if __name__ == '__main__':
    main()

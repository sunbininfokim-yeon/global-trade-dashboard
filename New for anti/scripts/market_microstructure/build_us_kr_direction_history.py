"""Forecast-vs-actual history for the next-session direction card.

One row per KRX session: the frozen v1 engine's up-probabilities (opening and
closing, both versus the previous close), the US-price-only factor when the
payload has it, and what actually happened (Naver daily chart, the source the
engine itself trains on).

Where a row comes from is never blurred:
  live   -- the immutable pre-open first record (data/forecasts/.../first.json)
  replay -- the same frozen engine run later with --replay on that day's
            inputs; NOT a pre-open forecast, shown muted on screen.
Sessions on or before the model's trained_through are in-sample and skipped.

Usage:
  python build_us_kr_direction_history.py --archive data/forecasts/us_kr_direction \
      --replays RUN_ROOT --model MODEL.json --out public/data/us_kr_direction_history.json
RUN_ROOT holds one run dir per target (RUN_ROOT/<date>/display_payload.json),
as written by run_us_kr_preopen.py --replay --run-dir RUN_ROOT/<date>.
"""

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_kospi200_price_panel import fetch_naver_chart

TICKERS = ['KOSPI', '005930', '000660']
HEADS = ['opening_up', 'closing_up']
SCHEMA = 'us-kr-direction-history-v1'


def prob(score):
    try:
        p = float((score or {}).get('probability', (score or {}).get('up_probability')))
    except (TypeError, ValueError):
        return None
    return round(p, 4) if 0 <= p <= 1 else None


def from_live(path):
    d = json.loads(Path(path).read_text())
    if d.get('status') != 'research_preopen_forecast':
        return None
    return {'target': d['target_date'], 'kind': 'live', 'generated_at': d['generated_at'], 'model_id': d.get('model_id'),
            'trained_through': d.get('trained_through'),
            'v1': {t: {h: prob(d['results'][t]['scores'].get(h)) for h in HEADS} for t in TICKERS if t in d.get('results', {})},
            'us_price': {}}


def from_replay(path):
    d = json.loads(Path(path).read_text())
    if d.get('status') != 'retrospective_replay':
        return None
    cards = {c['ticker']: c for c in d.get('cards') or []}
    us = ((d.get('factors') or {}).get('us_price') or {})
    us_cards = {c['ticker']: c for c in us.get('cards') or [] if c.get('status') == 'available'} \
        if us.get('as_of') and us.get('as_of') == us.get('expected_source_date') else {}
    return {'target': d['target_date'], 'kind': 'replay', 'generated_at': d['generated_at'], 'model_id': d.get('model_id'),
            'trained_through': d.get('trained_through'),
            'v1': {t: {h: prob(cards[t]['scores'].get(h)) for h in HEADS} for t in TICKERS if t in cards},
            'us_price': {t: {h: prob(us_cards[t]['scores'].get(h)) for h in HEADS} for t in TICKERS if t in us_cards},
            'us_price_kind': 'replay'}


def daily_bars(start, end):
    out = {}
    for t in TICKERS:
        out[t] = fetch_naver_chart(t, start.replace('-', ''), end.replace('-', ''))
    return out


def actual(bars, target):
    days = sorted(d for d in bars if d < target)
    if target not in bars or not days:
        return None
    prev, today = bars[days[-1]], bars[target]
    if not (prev.get('close') and today.get('open') and today.get('close')):
        return None
    return {'open_ret': round(today['open'] / prev['close'] - 1, 6),
            'close_ret': round(today['close'] / prev['close'] - 1, 6)}


def build(archive, replays, model, prior=(), today=None):
    """Rows from every model version are kept; each row is dropped only when its
    own model was trained through that target (in-sample)."""
    trained = model['trained_through']
    oos = lambda r: r and r['target'] > (r.get('trained_through') or trained)
    # Earlier replay rows stay (replays are not re-run every day); actuals are
    # always re-read so a row that was not yet matured fills in later.
    rows = {r['target']: {k: v for k, v in r.items() if k != 'actual'}
            for r in prior if r.get('kind') == 'replay' and oos(r)}
    # US-factor values a live row borrowed earlier survive an incremental rebuild
    prior_us = {r['target']: (r.get('us_price') or {}, r.get('us_price_kind')) for r in prior if r.get('us_price')}
    for path in sorted(Path(replays).glob('*/display_payload.json')) if replays else []:
        r = from_replay(path)
        if oos(r):
            rows[r['target']] = r
    for path in sorted(Path(archive).glob('*/*/first.json')):
        if path.parent.name == 'us_price':
            continue
        r = from_live(path)
        if oos(r):
            # live v1 records never carried the factor; borrow the replay's, labelled so
            r['us_price'] = rows.get(r['target'], {}).get('us_price') or prior_us.get(r['target'], ({}, None))[0]
            r['us_price_kind'] = 'replay'
            old = rows.get(r['target'])
            # a real pre-open record beats a replay; between two live records of
            # different models the newer model (later trained_through) wins
            if not old or old['kind'] != 'live' or (r.get('trained_through') or '') > (old.get('trained_through') or ''):
                rows[r['target']] = r
    us_first = Path(archive)
    for target, r in rows.items():  # #1077: immutable US-price first records win too
        for path in us_first.glob(f'{target}/us_price/*/first.json'):
            f = json.loads(path.read_text()).get('factor') or {}
            if f.get('status') == 'available':
                r['us_price'] = {c['ticker']: {h: prob(c['scores'].get(h)) for h in HEADS}
                                 for c in f.get('cards', []) if c.get('status') == 'available'}
                r['us_price_kind'] = 'live'
    if not rows:
        return {'schema_version': SCHEMA, 'rows': []}
    targets = sorted(rows)
    first = (datetime.fromisoformat(targets[0]).toordinal() - 14)
    bars = daily_bars(datetime.fromordinal(first).strftime('%Y-%m-%d'), targets[-1])
    out = []
    now_kst = (today or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=9)))
    for t in targets:
        r = rows[t]
        r.setdefault('model_id', model['model_id'])  # rows from before the field existed
        # a session still trading has a partial bar -- never score it as the outcome
        closed = t < now_kst.strftime('%Y-%m-%d') or (t == now_kst.strftime('%Y-%m-%d') and now_kst.hour * 60 + now_kst.minute >= 15 * 60 + 45)
        r['actual'] = {tk: actual(bars[tk], t) if closed else None for tk in TICKERS}
        out.append(r)
    return {'schema_version': SCHEMA, 'model_id': model['model_id'], 'trained_through': trained,
            'generated_at': (today or datetime.now(timezone.utc)).isoformat(),
            'note': 'live = 08:30 KST 이전 기록, replay = 같은 동결 엔진을 나중에 재생(사전 예측 아님). 확률은 모두 전일 종가 대비 상승.',
            'rows': out}


def atomic_write(path, doc):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(doc, f, ensure_ascii=False, allow_nan=False, indent=1); f.write('\n')
    os.replace(f.name, path)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--replays', type=Path)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--merge', type=Path, help='existing history JSON; its replay rows are kept unless rebuilt')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    prior = json.loads(a.merge.read_text()).get('rows', []) if a.merge and a.merge.exists() else []
    doc = build(a.archive, a.replays, json.loads(a.model.read_text()), prior)
    atomic_write(a.out, doc)
    print({'rows': len(doc['rows']), 'live': sum(r['kind'] == 'live' for r in doc['rows'])})

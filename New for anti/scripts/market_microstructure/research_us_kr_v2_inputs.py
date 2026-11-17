"""Walk-forward study (2026-11-17): does EWY / post-close futures / KRW add to price+US? Research only.

Usage: python research_us_kr_v2_fetch.py DATA_DIR && python research_us_kr_v2_inputs.py DATA_DIR report.json
"""
import json, sys, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

D = Path(sys.argv[1])
KST, NY = ZoneInfo('Asia/Seoul'), ZoneInfo('America/New_York')
rng = np.random.default_rng(0)


def daily(name, tz):
    j = json.loads((D / f'd_{name}.json').read_text())
    out = {}
    for r in j['rows']:
        if r['close'] is None or r['open'] is None: continue
        day = datetime.fromtimestamp(r['t'], tz).date().isoformat()
        out[day] = {'open': r['open'], 'close': r.get('adjclose') or r['close'], 'raw': r['close']}
    return pd.DataFrame(out).T.sort_index()


def hourly(name):
    j = json.loads((D / f'h_{name}.json').read_text())
    s = pd.Series({pd.Timestamp(r['t'], unit='s', tz='UTC') + pd.Timedelta(hours=1): r['close']
                   for r in j['rows'] if r['close'] is not None})  # bar END time
    return s.sort_index()


US = ['QQQ', 'SPY', 'SMH', 'MU', 'NVDA', 'AMD', 'VIX']
us = {s: daily(s, NY) for s in US + ['EWY']}
usdays = sorted(set.intersection(*[set(us[s].index) for s in US]))
ES, NQ, KRW, EWYH = hourly('ESF'), hourly('NQF'), hourly('KRWX'), hourly('EWY')


def asof(series, ts):
    s = series[series.index <= ts]
    return (s.iloc[-1], s.index[-1]) if len(s) else (None, None)


def build(ticker):
    kr = daily(ticker, KST)
    kr = kr[kr['open'] > 0]
    days = list(kr.index); rows = []
    ret = kr['raw'].pct_change()
    for i in range(21, len(days)):
        t, s = days[i], days[i - 1]
        pc, o, c = kr['raw'][s], kr['open'][t], kr['raw'][t]
        if o == pc or c == pc or o == c: continue
        prior = [d for d in usdays if d < t]
        if len(prior) < 2: continue
        d, dp = prior[-1], prior[-2]
        if (pd.Timestamp(t) - pd.Timestamp(d)).days > 4: continue
        x = {}
        k = kr['raw']
        x['momentum5'] = k[s] / k[days[i - 6]] - 1
        x['momentum20'] = k[s] / k[days[i - 21]] - 1
        x['volatility20'] = ret.iloc[i - 20:i].std()
        x['return1'] = k[s] / k[days[i - 2]] - 1
        x['gap1'] = kr['open'][s] / k[days[i - 2]] - 1
        x['intraday1'] = k[s] / kr['open'][s] - 1
        for sym in US:
            x[sym] = us[sym]['close'][d] / us[sym]['close'][dp] - 1
        x['log_VIX'] = math.log(us['VIX']['close'][d])
        e = us['EWY']
        x['EWY_intraday'] = e['raw'][d] / e['open'][d] - 1 if d in e.index else np.nan
        x['EWY_return'] = e['close'][d] / e['close'][dp] - 1 if d in e.index and dp in e.index else np.nan
        # hourly: US cash close of d (16:00 NY) and post-close (17:00 NY), KRW 06:00 KST t vs 15:00 KST s
        cash = pd.Timestamp(d + ' 16:00', tz=NY).tz_convert('UTC')
        post = pd.Timestamp(d + ' 17:00', tz=NY).tz_convert('UTC')
        for name, ser in (('ES_post', ES), ('NQ_post', NQ)):
            a, ta = asof(ser, cash); b, tb = asof(ser, post)
            ok = a and b and (cash - ta) <= pd.Timedelta(hours=1) and (post - tb) <= pd.Timedelta(hours=1)
            x[name] = b / a - 1 if ok else np.nan
        k1, tk1 = asof(KRW, pd.Timestamp(s + ' 15:00', tz=KST).tz_convert('UTC'))
        k2, tk2 = asof(KRW, pd.Timestamp(t + ' 06:00', tz=KST).tz_convert('UTC'))
        ok = k1 and k2 and tk2 > tk1 + pd.Timedelta(hours=6)
        x['KRW_overnight'] = k2 / k1 - 1 if ok else np.nan
        rows.append({'target': t, **x, 'opening_up': int(o > pc), 'closing_up': int(c > pc),
                     'intraday_up': int(c > o), 'intraday_ret': c / o - 1})
    return pd.DataFrame(rows).set_index('target')


PRICE = ['momentum5', 'volatility20', 'return1', 'gap1', 'intraday1', 'momentum20']
USF = US + ['log_VIX']
VARIANTS = {
    'v2cand': USF + ['return1','gap1','intraday1','EWY_intraday','KRW_overnight'],
    'v2cand_noKRW': USF + ['return1','gap1','intraday1','EWY_intraday'],
    'price_us(v2)': PRICE + USF,
    'us_only': USF,
    'us+return1': USF + ['return1', 'gap1', 'intraday1'],
    '+EWY': PRICE + USF + ['EWY_intraday'],
    '+futures': PRICE + USF + ['ES_post', 'NQ_post'],
    '+KRW': PRICE + USF + ['KRW_overnight'],
    '+all3': PRICE + USF + ['EWY_intraday', 'ES_post', 'NQ_post', 'KRW_overnight'],
    'us_only+all3': USF + ['EWY_intraday', 'ES_post', 'NQ_post', 'KRW_overnight'],
}


def walk(df, cols, y, min_train=250, step=20):
    df = df.dropna(subset=cols)
    p = pd.Series(np.nan, index=df.index)
    for start in range(min_train, len(df), step):
        tr = df.iloc[:start]; te = df.iloc[start:start + step]
        X = tr[cols].values; m, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
        clip = lambda A: np.clip((A - m) / sd, -3, 3)
        lr = LogisticRegression(C=0.5, max_iter=2000).fit(clip(X), tr[y].values)
        p.iloc[start:start + step] = lr.predict_proba(clip(te[cols].values))[:, 1]
    return p.dropna()


def block_ci(diff, block=10, n=2000):
    d = diff.values; k = len(d)
    starts = rng.integers(0, k - block, size=(n, k // block))
    means = np.array([d[(s[:, None] + np.arange(block)).ravel()].mean() for s in starts])
    return np.percentile(means, [2.5, 97.5])


report = {}
for ticker, label in (('KS11', 'KOSPI'), ('005930.KS', '삼성'), ('000660.KS', '하이닉스')):
    df = build(ticker)
    for sample, need in (('5y', ['EWY_intraday']), ('2y', ['ES_post', 'NQ_post', 'KRW_overnight', 'EWY_intraday'])):
        sub = df.dropna(subset=need)
        for y in ('opening_up', 'closing_up', 'intraday_up'):
            preds = {}
            for v, cols in VARIANTS.items():
                if sample == '5y' and any(c in cols for c in ['ES_post', 'NQ_post', 'KRW_overnight']): continue
                if v not in ('price_us(v2)','v2cand','v2cand_noKRW'): continue
                preds[v] = walk(sub, cols, y)
            common = sorted(set.intersection(*[set(p.index) for p in preds.values()]))
            yy = sub.loc[common, y]
            base = (preds['price_us(v2)'][common] - yy) ** 2
            line = {}
            for v, p in preds.items():
                p = p[common]; b = (p - yy) ** 2
                lo, hi = block_ci(b - base) if v != 'price_us(v2)' else (0, 0)
                line[v] = {'n': len(common), 'brier': round(b.mean(), 4), 'd_vs_v2': round((b - base).mean(), 4),
                           'ci': [round(lo, 4), round(hi, 4)], 'hit': round(((p > .5) == yy).mean(), 3),
                           'base_rate': round(yy.mean(), 3)}
            report[f'{label}|{sample}|{y}'] = line
            # confidence buckets for intraday tradability
            if y == 'intraday_up':
                for v in ('price_us(v2)', 'v2cand' if sample == '2y' else 'v2cand_noKRW'):
                    p = preds[v][common]; r = sub.loc[common, 'intraday_ret']
                    for k in (0.0, 0.02, 0.05):
                        m = (p - .5).abs() > k
                        pnl = np.sign(p[m] - .5) * r[m] * 1e4
                        report[f'{label}|{sample}|{y}|{v}|abstain>{k}'] = {
                            'n': int(m.sum()), 'mean_bp': round(pnl.mean(), 1) if m.sum() else None,
                            't': round(pnl.mean() / pnl.std() * math.sqrt(m.sum()), 2) if m.sum() > 2 else None}
    print('done', label, len(df), flush=True)
Path(sys.argv[2]).write_text(json.dumps(report, ensure_ascii=False, indent=1))

"""Fetch Yahoo daily + hourly bars for the v2 input study. Writes JSON per symbol."""
import json, sys, time
from pathlib import Path
import requests

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
DAILY = ['^KS11', '005930.KS', '000660.KS', 'QQQ', 'SPY', 'SMH', 'MU', 'NVDA', 'AMD', '^VIX', 'EWY', 'KRW=X']
HOURLY = ['ES=F', 'NQ=F', 'KRW=X', 'EWY']
H = {'User-Agent': 'Mozilla/5.0'}


def get(sym, interval, rng):
    r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}',
                     params={'range': rng, 'interval': interval}, headers=H, timeout=20)
    r.raise_for_status()
    c = r.json()['chart']['result'][0]
    q = c['indicators']['quote'][0]
    adj = c['indicators'].get('adjclose', [{}])[0].get('adjclose')
    rows = []
    for i, t in enumerate(c['timestamp']):
        row = {'t': t, 'open': q['open'][i], 'close': q['close'][i]}
        if adj: row['adjclose'] = adj[i]
        rows.append(row)
    return {'symbol': sym, 'interval': interval, 'gmtoffset': c['meta'].get('gmtoffset'),
            'tz': c['meta'].get('exchangeTimezoneName'), 'rows': rows}


for s in DAILY:
    (OUT / f'd_{s.replace("^", "").replace("=", "")}.json').write_text(json.dumps(get(s, '1d', '5y')))
    time.sleep(0.4); print('daily', s)
for s in HOURLY:
    (OUT / f'h_{s.replace("^", "").replace("=", "")}.json').write_text(json.dumps(get(s, '60m', '730d')))
    time.sleep(0.4); print('hourly', s)

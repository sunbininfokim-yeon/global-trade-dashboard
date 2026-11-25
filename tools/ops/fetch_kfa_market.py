#!/usr/bin/env python3
"""Daily market caps for the company calculator's market multiples.

Writes `New for anti/public/data/kfa_market_v1.json`: for every listed
company that has a PE/CR engine snapshot (kfa_pecr/index_v1.json), the
Naver Finance close and market capitalisation -- and the same for its first
preferred line when the snapshot shows preferred shares outstanding.

Why this split: the engine snapshot holds the *denominators* (net income,
equity, sales, EBITDA, net debt, FCF -- from OpenDART), which change only when
a new report is filed; this file holds the *numerator*, which changes daily.
The browser divides one by the other, so PER / PBR / EV/EBITDA move with the
market without rerunning the engine.

Naver's 시가총액 is the common line only (listed shares x price, treasury
shares included). The preferred line is a separate code (005930 -> 005935)
with its own 시가총액; the calculator adds the two for PER/PBR/EV.

Naver's own PER/PBR/EPS/BPS (with the period they use) are kept as a
cross-check -- they are not used in any ratio.

No key, no paid source. Exits 1 if more than 5 % of companies failed, after
writing the rest (failed ones keep their previous entry, flagged stale).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'New for anti' / 'public' / 'data'
INDEX = DATA / 'kfa_pecr' / 'index_v1.json'
OUT = DATA / 'kfa_market_v1.json'
API = 'https://m.stock.naver.com/api/stock/{code}/{kind}'
US_API = 'https://api.stock.naver.com/stock/{code}/basic'   # Reuters code: AAPL.O (NASDAQ), JPM (NYSE)
UA = {'User-Agent': 'Mozilla/5.0 (compatible; global-trade-dashboard/1.0)'}
KST = dt.timezone(dt.timedelta(hours=9))


def get(code: str, kind: str) -> dict:
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(API.format(code=code, kind=kind), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as res:
                return json.loads(res.read())
        except Exception as exc:          # noqa: BLE001 -- retried, then reported
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f'{code} {kind}: {last}')


UNITS = {'조': 10**12, '억': 10**8, '만': 10**4}


def korean_amount(text: str | None) -> int | None:
    """'1,140조 243억' -> 1140024300000000. None when unparsable."""
    if not text:
        return None
    total, seen = 0, False
    for num, unit in re.findall(r'([\d,]+)\s*(조|억|만)?', text):
        if not num.replace(',', ''):
            continue
        total += int(num.replace(',', '')) * UNITS.get(unit, 1)
        seen = True
    return total if seen else None


def number(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r'-?[\d,]+(?:\.\d+)?', text)
    return float(m.group(0).replace(',', '')) if m else None


def us_quote(code: str) -> dict:
    """US listing: close and 시가총액 in USD ('5조 615억 USD')."""
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(US_API.format(code=code), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as res:
                basic = json.loads(res.read())
            break
        except Exception as exc:          # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f'{code}: {last}')
    info = {x.get('code'): x for x in basic.get('stockItemTotalInfos') or []}
    price = number(basic.get('closePrice'))
    text = (info.get('marketValue') or {}).get('value')
    cap = korean_amount(text)
    if not price or not cap:
        raise RuntimeError(f'{code}: no price or market cap')

    def ref(key):
        x = info.get(key) or {}
        v = number(x.get('value'))
        return {'value': v, 'period': x.get('valueDesc')} if v is not None else None

    return {'code': code, 'name': basic.get('stockName'), 'exchange': basic.get('stockExchangeName'), 'currency': 'USD',
            'price': price, 'traded_at': basic.get('localTradedAt'), 'market_status': basic.get('marketStatus'),
            'market_cap': cap, 'market_cap_text': text, 'listed_shares_implied': round(cap / price),
            'naver_reference': {k: ref(k) for k in ('per', 'pbr', 'eps', 'bps', 'dividendYieldRatio')}}


def quote(code: str) -> dict:
    basic = get(code, 'basic')
    integ = get(code, 'integration')
    info = {x.get('code'): x for x in integ.get('totalInfos') or []}
    price = number(basic.get('closePrice'))
    cap = korean_amount((info.get('marketValue') or {}).get('value'))
    if not price or not cap:
        raise RuntimeError(f'{code}: no price or market cap')

    def ref(key):
        x = info.get(key) or {}
        v = number(x.get('value'))
        return {'value': v, 'period': x.get('valueDesc')} if v is not None else None

    return {
        'code': code, 'name': basic.get('stockName'), 'exchange': basic.get('stockExchangeName'),
        'price': price, 'traded_at': basic.get('localTradedAt'), 'market_status': basic.get('marketStatus'),
        'market_cap': cap, 'market_cap_text': (info.get('marketValue') or {}).get('value'),
        # Implied listed shares (Naver rounds the cap to 억원, so this is approximate).
        'listed_shares_implied': round(cap / price),
        'naver_reference': {k: ref(k) for k in ('per', 'pbr', 'eps', 'bps', 'dividendYieldRatio', 'dividend')},
    }


def main() -> int:
    index = json.loads(INDEX.read_text()).get('index') or {}
    prev = {}
    if OUT.exists():
        prev = json.loads(OUT.read_text()).get('quotes') or {}
    quotes, failed = {}, []
    for corp, meta in sorted(index.items()):
        stock = (meta.get('stock_code') or '').strip()
        if not stock:
            continue
        snap = json.loads((DATA / 'kfa_pecr' / f'{corp}_v1.json').read_text())
        try:
            if meta.get('market') == 'US':
                # Naver's Reuters codes: NASDAQ '.O', most NYSE plain, some NYSE '.K'
                # (SCCO.K, ORCL.K) -- not predictable from the exchange, so try in turn.
                base = stock.split('.')[0]
                q, last = None, None
                for cand in dict.fromkeys([stock, f'{base}.K', base, f'{base}.O']):
                    try:
                        q = us_quote(cand)
                        break
                    except Exception as exc:  # noqa: BLE001
                        last = exc
                if q is None:
                    raise last
                q['corp_code'] = corp
                quotes[stock] = q
                print(f'{stock} {q["name"]}: {q["price"]:,.2f} cap {q["market_cap_text"]}')
                time.sleep(0.3)
                continue
            q = quote(stock)
            q['corp_code'] = corp
            # Only the first preferred line, and only when DART shows preferred
            # shares outstanding (the snapshot's market_input records that).
            if 'preferred=' in (snap.get('market_input') or '') or 'preferred_unpriced' in (snap.get('market_input') or ''):
                pcode = stock[:-1] + '5'
                try:
                    p = quote(pcode)
                except Exception as exc:  # noqa: BLE001 -- unlisted preferred (삼성중공업): common still counts
                    p, q['preferred_note'] = None, f'{pcode}: no quote ({exc})'
                if p and (p.get('name') or '').endswith(('우', '우B')):
                    q['preferred'] = p
                elif p:
                    q['preferred_note'] = f'{pcode} is not a preferred line ({p.get("name")})'
            quotes[stock] = q
            print(f'{stock} {q["name"]}: {q["price"]:,.0f} cap {q["market_cap_text"]}'
                  + (f' + pref {q["preferred"]["market_cap_text"]}' if q.get('preferred') else ''))
        except Exception as exc:          # noqa: BLE001
            failed.append(stock)
            print(f'FAILED {stock}: {exc}', file=sys.stderr)
            if stock in prev:
                quotes[stock] = {**prev[stock], 'stale': True}
        time.sleep(0.3)
    doc = {
        'schema': 'kfa_market/1',
        'generated_at': dt.datetime.now(KST).isoformat(timespec='seconds'),
        'source': 'Naver Finance (m.stock.naver.com) close and 시가총액; common and first preferred line',
        'basis': 'market_cap = Naver 시가총액 (listed shares incl. treasury x close)',
        'quotes': quotes,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
    print(f'wrote {OUT.relative_to(ROOT)}: {len(quotes)} quotes, {len(failed)} failed')
    # With hundreds of companies a suspended or delisted line always fails;
    # fail the run only when it looks systemic (> 5 %).
    return 1 if failed and len(failed) > 0.05 * max(len(quotes), 1) else 0


if __name__ == '__main__':
    sys.exit(main())

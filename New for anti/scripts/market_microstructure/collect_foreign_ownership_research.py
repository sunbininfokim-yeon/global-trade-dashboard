"""Preserve provider-reported foreign holding percentages omitted by price-bin output."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from market_microstructure.investor_price_levels import fetch_naver_investor_trend, parse_signed_qty, trend_to_frame
from option_direction_model import unique, write


def holding_pct(value):
    if not isinstance(value, str) or not value.strip().endswith('%'):
        return None
    try:
        v = float(value.strip()[:-1].replace(',', ''))
    except ValueError:
        return None
    return v if math.isfinite(v) and 0 <= v <= 100 else None


def normalize(raw):
    rows = []
    for r in raw:
        text = str(r.get('bizdate', ''))
        if len(text) != 8 or not text.isdigit():
            raise ValueError('invalid provider bizdate')
        d = datetime.strptime(text, '%Y%m%d').strftime('%Y-%m-%d')
        p = holding_pct(r.get('foreignerHoldRatio'))
        rows.append({'date': d, 'foreign_holding_pct': p,
                     'foreign_net_shares_source_check': parse_signed_qty(r.get('foreignerPureBuyQuant')),
                     'quality': 'observed' if p is not None else 'missing'})
    unique(rows)
    return sorted(rows, key=lambda r: r['date'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--days', type=int, default=190)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--raw-output', type=Path, required=True)
    p.add_argument('--flow-output', type=Path, help='optional separate research net-share snapshot, never the public daily file')
    args = p.parse_args()
    paths = [args.output, args.raw_output]+([args.flow_output] if args.flow_output else [])
    if any(x.exists() for x in paths) or len({x.resolve() for x in paths}) != len(paths):
        p.error('new, distinct snapshot paths required')
    if args.days <= 0:
        p.error('positive days required')
    raw = {}; names = {}; errors = {}
    for ticker in ['005930', '000660']:
        try:
            raw[ticker] = fetch_naver_investor_trend(ticker, page_size=args.days)
            names[ticker] = normalize(raw[ticker])
            if not names[ticker]:
                errors[ticker] = 'empty provider response'
        except Exception as e:
            names[ticker] = []; errors[ticker] = type(e).__name__+': '+str(e)
    write(args.raw_output, raw)
    out = {'status': 'partial' if errors else 'collected', 'source': 'Naver stock trend foreignerHoldRatio',
           'collected_at': datetime.now(timezone.utc).isoformat(), 'provider_published_at': 'unknown',
           'scope': 'provider-reported foreign holdings percentage; denominator/corporate-action treatment unverified',
           'requested_rows_per_ticker': args.days, 'raw_sha256': hashlib.sha256(args.raw_output.read_bytes()).hexdigest(),
           'tickers': names, 'errors': errors}
    write(args.output, out)
    if args.flow_output:
        names = {}
        for ticker, data in raw.items():
            frame = trend_to_frame(data)
            rows = []
            for date, row in frame.iterrows():
                n, close = row.get('foreign_net_shares'), row.get('close_naver')
                rows.append({'date': date.strftime('%Y-%m-%d'),
                             'foreign_net_shares': int(n) if n is not None and math.isfinite(n) else None,
                             'close': float(close) if close is not None and math.isfinite(close) else None})
            names[ticker] = {'quality': 'observed' if rows else 'missing', 'net_shares_quality': 'observed',
                             'days': rows, 'source': 'Naver stock trend via existing trend_to_frame'}
        write(args.flow_output, {'as_of': out['collected_at'][:10], 'fetched_at': out['collected_at'],
            'tickers': names, 'raw_sha256': out['raw_sha256'], 'provider_published_at': 'unknown',
            'scope': 'research snapshot; observed net shares, no estimated KRW substitution'})
    print({'status': out['status'], 'rows': {t: len(a) for t, a in out['tickers'].items()}, 'errors': errors})
    if errors:
        raise SystemExit(2)

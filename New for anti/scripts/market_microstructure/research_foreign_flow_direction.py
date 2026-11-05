"""Describe next-session direction after stock-specific foreign net buying/selling.

Retrospective conditional frequencies only; no fitted forecast, causal claim, costs or PnL.
"""
import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

from option_direction_model import calendar, read, unique, write
from research_direction_diagnostics import ReviewedCalendar
from research_stock_open_close_direction import TARGETS, path_labels
from evaluate_us_kr_forward import wilson

EVENTS = TARGETS + ['intraday_up']


def number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def valid_bar(row):
    if row.get('quality') not in (None, 'observed'):
        return False
    if any(not number(row.get(k)) or row[k] <= 0 for k in ['open', 'high', 'low', 'close']):
        return False
    return row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']


def assemble(report, prices, ticker):
    source = report['tickers'][ticker]
    if source.get('quality') != 'observed' or source.get('net_shares_quality') != 'observed':
        raise ValueError('observed net-share source required; estimated KRW is not used')
    flows = unique(source['days'])
    candidates = [c for c in prices['candidates'] if c['ticker'] == ticker]
    if len(candidates) != 1:
        raise ValueError('exactly one independent price candidate required')
    bars = unique(candidates[0]['rows']); cal = ReviewedCalendar(calendar())
    valid = {}; reasons = Counter()
    for day, row in sorted(flows.items()):
        if not cal.is_session(day):
            reasons['non_session_flow'] += 1; continue
        if row.get('quality') not in (None, 'observed'):
            reasons['non_observed_flow'] += 1; continue
        n = row.get('foreign_net_shares')
        if not number(n) or int(n) != n:
            reasons['invalid_foreign_net_shares'] += 1; continue
        if day not in bars or not valid_bar(bars[day]):
            reasons['missing_or_invalid_source_price'] += 1; continue
        if not number(row.get('close')) or row['close'] != bars[day]['close']:
            reasons['price_basis_mismatch'] += 1; continue
        v = bars[day].get('volume')
        if not number(v) or v <= 0 or abs(n) > v:
            reasons['invalid_or_incompatible_volume'] += 1; continue
        valid[day] = {'foreign_net_shares': int(n), 'foreign_net_share_of_volume': n/v}
    rows = []
    for day, flow in valid.items():
        i = cal.sessions.get_loc(day)
        if i == 0 or i+1 == len(cal.sessions):
            reasons['calendar_boundary'] += 1; continue
        target = cal.sessions[i+1].strftime('%Y-%m-%d')
        previous = cal.sessions[i-1].strftime('%Y-%m-%d')
        if target not in bars or not valid_bar(bars[target]):
            reasons['missing_or_invalid_exact_next_session_price'] += 1; continue
        labels = path_labels(bars[day]['close'], bars[target]['open'], bars[target]['close'])
        labels['intraday_up'] = 1 if bars[target]['close'] > bars[target]['open'] else 0 if bars[target]['close'] < bars[target]['open'] else None
        price_move = None
        if previous in bars and valid_bar(bars[previous]):
            price_move = 'UP' if bars[day]['close'] > bars[previous]['close'] else 'DOWN' if bars[day]['close'] < bars[previous]['close'] else 'FLAT'
        recent = cal.sessions[max(0, i-2):i+1].strftime('%Y-%m-%d').tolist()
        streak = None
        if len(recent) == 3 and all(d in valid for d in recent):
            nets = [valid[d]['foreign_net_shares'] for d in recent]
            streak = 'BUY_3' if all(n > 0 for n in nets) else 'SELL_3' if all(n < 0 for n in nets) else 'MIXED'
        rows.append({'source_date': day, 'target_date': target, **flow,
                     'flow_side': 'BUY' if flow['foreign_net_shares'] > 0 else 'SELL' if flow['foreign_net_shares'] < 0 else 'ZERO',
                     'same_day_close_direction': price_move, 'three_session_flow': streak,
                     'source_close': bars[day]['close'], 'target_open': bars[target]['open'],
                     'target_close': bars[target]['close'], **labels})
    return rows, {'n_input_flow_rows': len(flows), 'first_flow_date': min(flows) if flows else None,
                  'last_flow_date': max(flows) if flows else None, 'n_eligible_pairs': len(rows),
                  'exclusions': dict(reasons), 'price_provider': candidates[0].get('source'),
                  'price_source_url': candidates[0].get('source_url'),
                  'price_adjustment': candidates[0].get('price_adjustment'),
                  'first_source': rows[0]['source_date'] if rows else None,
                  'last_source': rows[-1]['source_date'] if rows else None,
                  'last_target': rows[-1]['target_date'] if rows else None}


def frequencies(rows):
    out = {}
    for event in EVENTS:
        observed = [r[event] for r in rows if r[event] is not None]
        n = len(observed); yes = sum(observed)
        out[event] = {'n': n, 'yes': yes, 'flat_excluded': len(rows)-n,
                      'event_rate': yes/n if n else None, 'wilson95': wilson(yes, n),
                      'status': 'no_observations' if not n else 'small_sample' if n < 60 else 'descriptive_only'}
    return {'n_pairs': len(rows), 'events': out}


def analyze(report, prices, ticker):
    rows, audit = assemble(report, prices, ticker)
    groups = {'all': rows}
    for side in ['BUY', 'SELL', 'ZERO']:
        groups[side.lower()] = [r for r in rows if r['flow_side'] == side]
    for side in ['BUY', 'SELL']:
        selected = [r for r in rows if r['flow_side'] == side]
        # A fixed descriptive cutoff; never optimized for predictive accuracy.
        groups[side.lower()+'_abs_share_ge_10pct'] = [r for r in selected if abs(r['foreign_net_share_of_volume']) >= .1]
        for move in ['UP', 'DOWN', 'FLAT']:
            groups[side.lower()+'_same_day_'+move.lower()] = [r for r in selected if r['same_day_close_direction'] == move]
        groups[side.lower()+'_3_sessions'] = [r for r in selected if r['three_session_flow'] == side+'_3']
    return {'ticker': ticker, 'audit': audit, 'groups': {k: frequencies(v) for k, v in groups.items()},
            'pair_audit': rows,
            'model_readiness': 'insufficient_250_base_plus_60_calibration' if len(rows) < 310 else 'not_trained_or_temporally_validated'}


def markdown(result):
    lines = ['# 종목별 외국인 수급 이후 다음 거래일 방향', '',
             '과거 조건부 관측 빈도다. 미래 상승 확률이나 외국인 수급의 인과효과로 해석하지 않는다.', '',
             '| 종목 | 조건 | 유효 시가 n | 시가 상승 | 유효 종가 n | 종가 상승 |',
             '|---|---|---:|---:|---:|---:|']
    pct = lambda v: '—' if v is None else f'{100*v:.2f}%'
    for ticker, data in result['tickers'].items():
        for name in ['all', 'buy', 'sell', 'buy_same_day_up', 'buy_same_day_down', 'sell_same_day_up', 'sell_same_day_down']:
            g = data['groups'][name]['events']; a, b = g['opening_up'], g['closing_up']
            lines.append(f"| {ticker} | {name} | {a['n']} | {pct(a['event_rate'])} | {b['n']} | {pct(b['event_rate'])} |")
    lines += ['', '다음 장은 거래소 달력의 정확한 다음 세션이다. 중간 결측을 건너뛰어 다음 관측일로 대체하지 않았다.',
              '비율은 외국인 순매수 수량 / 동일 가격 패널의 당일 거래량. 화면의 추정 원화 금액은 사용하지 않았다.',
              '구간은 서로 중첩된다. 동가/표본 수/제외 사유와 Wilson 구간은 JSON에 보존했다.',
              '독립성 가정의 Wilson 구간은 설명용이다. 다중 비교 유의성 검정·별도 보정·미래 기간 검증을 수행하지 않았다.',
              '원본 수급의 최초 게시 시각 미확인. 상장주식 수 변화·분할과 제공처 시장 범위는 별도 검증이 필요하다.',
              '비용·손익 계산 없음. 일일 모델·UI·공개 데이터 갱신 없음.']
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flows', type=Path, required=True)
    p.add_argument('--prices', type=Path, required=True)
    p.add_argument('--tickers', default='005930,000660')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--markdown', type=Path)
    args = p.parse_args()
    inputs = {args.flows.resolve(), args.prices.resolve()}
    outputs = [args.output] + ([args.markdown] if args.markdown else [])
    if any(x.resolve() in inputs for x in outputs) or len({x.resolve() for x in outputs}) != len(outputs):
        p.error('outputs must be distinct and must not overwrite inputs')
    flow, prices = read(args.flows), read(args.prices)
    result = {'status': 'retrospective_descriptive_only', 'horizon': 'exact next KRX session',
              'flow_snapshot_as_of': flow.get('as_of'),
              'flow_fetched_at': flow.get('fetched_at'), 'price_collected_at': prices.get('collected_at'),
              'tickers': {t: analyze(flow, prices, t) for t in args.tickers.split(',')},
              'input_sha256': {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in [args.flows, args.prices]},
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limitations': ['No out-of-sample probability, model fitting, causal estimate, costs or PnL',
                              'Observed foreign net shares, not net shares times close as actual transaction value',
                              'Different subsets and per-event flat exclusions; not directly comparable to primary model historical cohort',
                              'Same-day price/flow association does not establish intraday ordering',
                              'Historical provider snapshots, first publication timestamps unverified',
                              'Thresholds and subset comparisons descriptive; no significance or best subgroup selection',
                              'Each event rate is on its own nonflat subset, not an unconditional live probability']}
    write(args.output, result)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True);args.markdown.write_text(markdown(result))
    print({t: r['audit'] for t, r in result['tickers'].items()})

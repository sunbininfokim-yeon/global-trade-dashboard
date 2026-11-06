"""Fixed 1..5-session flow horizons, exposure proxies and purged research forecasts.

No live model changes, lag winner selection, portfolio allocation, costs or PnL.
"""
import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

from option_direction_model import calendar, read, unique, write
from research_direction_diagnostics import ReviewedCalendar
from research_foreign_flow_direction import assemble as assemble_foreign, number, valid_bar
from research_option_dynamics import logit, sigmoid_calibration
from research_short_horizon_flow import components
from market_microstructure.derivatives_history import implied_rebalance_for_signal

HORIZONS = [1, 2, 3, 4, 5]
FEATURES = ['return1', 'momentum5', 'volatility5', 'foreign_share1', 'foreign_share5', 'call_net_share', 'put_net_share']
FAMILIES = {'price': [0, 1, 2], 'price_foreign1': [0, 1, 2, 3],
            'price_foreign5': [0, 1, 2, 3, 4], 'price_options': [0, 1, 2, 5, 6],
            'price_foreign_options': list(range(7))}
MIN_TRAIN, N_CAL, TEST_BLOCK = 250, 60, 20


def sign(v):
    return 'UP' if v > 0 else 'DOWN' if v < 0 else 'FLAT'


def labels(bars, days):
    """days = source and five exact future sessions; never skip missing days."""
    if len(days) != 6 or any(d not in bars or not valid_bar(bars[d]) for d in days):
        raise ValueError('complete exact source + five-session price window required')
    source = bars[days[0]]['close']; first_open = bars[days[1]]['open']
    out = {}
    for h in HORIZONS:
        row, prev = bars[days[h]], bars[days[h-1]]
        out[str(h)] = {'target_date': days[h],
            'cumulative_close': sign(row['close']-source),
            'delayed_session_close': sign(row['close']-prev['close']),
            'delayed_open_gap': sign(row['open']-prev['close']),
            'delayed_intraday': sign(row['close']-row['open']),
            'from_first_open': sign(row['close']-first_open),
            'cumulative_log_change_pct': 100*math.log(row['close']/source)}
    return out


def exposure(record):
    """Reported ETF basket exposure share, not foreign holdings or dealer positions."""
    if not record or record.get('quality') != 'observed':
        return None
    ps = record.get('products', [])
    if not ps or len({p.get('ticker') for p in ps}) != len(ps):
        return None
    if any(not p.get('ticker') or p.get('aum_quality') != 'observed' or not number(p.get('aum_krw')) or p['aum_krw'] < 0 or
           not number(p.get('L')) or p['L'] == 0 for p in ps):
        return None
    for side, select in [('long', lambda p: p['L'] > 0), ('inverse', lambda p: p['L'] < 0)]:
        claimed = record.get('letf_aum_'+side+'_krw')
        actual = sum(p['aum_krw'] for p in ps if select(p))
        if not number(claimed) or claimed < 0 or not math.isclose(claimed, actual, rel_tol=1e-9, abs_tol=1):
            return None
    gross = sum(p['aum_krw']*abs(p['L']) for p in ps)
    if gross <= 0:
        return None
    long = sum(p['aum_krw']*p['L'] for p in ps if p['L'] > 0)
    return {'reported_long_exposure_share': long/gross, 'reported_net_exposure_bias': 2*long/gross-1}


def pressure(record):
    if not record or record.get('quality') != 'observed' or record.get('implied_rebalance_quality') != 'estimated':
        return None
    estimate = implied_rebalance_for_signal(record)
    spot = record.get('spot_trading_value_krw')
    if not number(estimate) or not number(spot) or spot <= 0:
        return None
    return estimate/spot


def assemble(flows, prices, board, letf, ticker, ownership=None):
    one_day, audit = assemble_foreign(flows, prices, ticker)
    bars = unique(next(c['rows'] for c in prices['candidates'] if c['ticker'] == ticker))
    raw = unique(flows['tickers'][ticker]['days']); cal = ReviewedCalendar(calendar())
    basket = unique([r for r in letf if r['ticker'] == ticker])
    products = board['kr']['investor_nets']['detailed_15007']['products']
    opts = {s: unique(products['options_'+s]['series']) for s in ['call', 'put']}
    holdings = unique((ownership or {}).get('tickers', {}).get(ticker, []))
    rows = []; excluded = Counter(); availability = Counter()
    for r in one_day:
        d = r['source_date']; i = cal.sessions.get_loc(d)
        days = cal.sessions[i:i+6].strftime('%Y-%m-%d').tolist()
        try:
            outcome = labels(bars, days)
        except ValueError:
            excluded['incomplete_five_future_sessions'] += 1; continue
        lookback = cal.sessions[max(0, i-5):i+1].strftime('%Y-%m-%d').tolist()
        x = None
        if len(lookback) == 6 and all(t in bars and valid_bar(bars[t]) for t in lookback):
            past = lookback[1:]
            if all(t in raw and number(raw[t].get('foreign_net_shares')) and int(raw[t]['foreign_net_shares']) == raw[t]['foreign_net_shares'] and
                   raw[t].get('quality') in (None, 'observed') and number(raw[t].get('close')) and raw[t]['close'] == bars[t]['close'] and
                   number(bars[t].get('volume')) and bars[t]['volume'] > 0 and abs(raw[t]['foreign_net_shares']) <= bars[t]['volume'] for t in past):
                returns = [math.log(bars[b]['close']/bars[a]['close']) for a, b in zip(lookback, lookback[1:])]
                x = [math.expm1(returns[-1]), bars[d]['close']/bars[lookback[0]]['close']-1,
                     float(np.std(returns, ddof=1)), r['foreign_net_share_of_volume'],
                     sum(raw[t]['foreign_net_shares'] for t in past)/sum(bars[t]['volume'] for t in past)]
                opt = [components(opts[s].get(d, {})) for s in ['call', 'put']]
                if all(v is not None for v in opt):
                    x += [v['net_share'] for v in opt]
                else:
                    x = None; availability['missing_valid_call_put_components'] += 1
        else:
            availability['missing_six_source_price_sessions'] += 1
        current = exposure(basket.get(d)); previous = exposure(basket.get(cal.sessions[i-1].strftime('%Y-%m-%d')))
        delta = current['reported_long_exposure_share']-previous['reported_long_exposure_share'] if current and previous else None
        p = pressure(basket.get(d))
        holding = None
        past1 = cal.sessions[i-1].strftime('%Y-%m-%d')
        past5 = cal.sessions[i-5].strftime('%Y-%m-%d') if i >= 5 else None
        need = [d, past1, past5]
        if all(t in holdings and holdings[t].get('quality') == 'observed' and
               number(holdings[t].get('foreign_holding_pct')) and 0 <= holdings[t]['foreign_holding_pct'] <= 100 for t in need):
            mismatches = [t for t in need if t in raw and holdings[t].get('foreign_net_shares_source_check') != raw[t].get('foreign_net_shares')]
            if mismatches:
                availability['ownership_net_share_snapshot_mismatch'] += 1
            else:
                value = holdings[d]['foreign_holding_pct']
                holding = [value, value-holdings[past1]['foreign_holding_pct'], value-holdings[past5]['foreign_holding_pct']]
        month = [t for t in cal.sessions.strftime('%Y-%m-%d') if t[:7] == d[:7]]
        row = {'source_date': d, 'last_target_date': days[-1], 'flow_side': r['flow_side'],
               'foreign_share1': r['foreign_net_share_of_volume'], 'features': x, 'outcomes': outcome,
               'letf_exposure': current, 'letf_long_share_change': delta, 'rebalance_signed_share': p,
               'ownership_features': holding,
               'month_end_last3': d in month[-3:]}
        availability['feature_complete' if x is not None else 'feature_incomplete'] += 1
        availability['letf_exposure_available' if current else 'letf_exposure_missing'] += 1
        availability['rebalance_verified_available' if p is not None else 'rebalance_verified_missing'] += 1
        availability['ownership_available' if holding is not None else 'ownership_missing'] += 1
        rows.append(row)
    return rows, {'one_day_audit': audit, 'complete_five_session_rows': len(rows),
                  'common_first_source': rows[0]['source_date'] if rows else None,
                  'common_last_source': rows[-1]['source_date'] if rows else None,
                  'common_last_target': rows[-1]['last_target_date'] if rows else None,
                  'horizon_exclusions': dict(excluded), 'availability': dict(availability)}


def distribution(rows, h, event):
    count = Counter(r['outcomes'][str(h)][event] for r in rows)
    n = len(rows)
    return {'n': n, 'up': count['UP'], 'down': count['DOWN'], 'flat': count['FLAT'],
            'p_up': count['UP']/n if n else None, 'p_down': count['DOWN']/n if n else None,
            'p_flat': count['FLAT']/n if n else None, 'status': 'small_sample' if n < 60 else 'descriptive_only'}


def describe(rows):
    groups = {'all': rows, 'foreign_buy': [r for r in rows if r['flow_side'] == 'BUY'],
              'foreign_sell': [r for r in rows if r['flow_side'] == 'SELL'],
              'foreign_buy_abs_share_ge_10pct': [r for r in rows if r['foreign_share1'] >= .1],
              'foreign_sell_abs_share_ge_10pct': [r for r in rows if r['foreign_share1'] <= -.1],
              'letf_long_share_increased': [r for r in rows if r['letf_long_share_change'] is not None and r['letf_long_share_change'] > 0],
              'letf_long_share_decreased': [r for r in rows if r['letf_long_share_change'] is not None and r['letf_long_share_change'] < 0],
              'rebalance_estimated_buy': [r for r in rows if r['rebalance_signed_share'] is not None and r['rebalance_signed_share'] > 0],
              'rebalance_estimated_sell': [r for r in rows if r['rebalance_signed_share'] is not None and r['rebalance_signed_share'] < 0],
              'foreign_holding_pct_increased': [r for r in rows if r.get('ownership_features') is not None and r['ownership_features'][1] > 0],
              'foreign_holding_pct_decreased': [r for r in rows if r.get('ownership_features') is not None and r['ownership_features'][1] < 0],
              'foreign_holding_pct_unchanged': [r for r in rows if r.get('ownership_features') is not None and r['ownership_features'][1] == 0],
              'month_end_last3': [r for r in rows if r['month_end_last3']]}
    events = ['cumulative_close', 'delayed_session_close', 'delayed_open_gap', 'delayed_intraday', 'from_first_open']
    return {g: {str(h): {e: distribution(sub, h, e) for e in events} for h in HORIZONS} for g, sub in groups.items()}


def folds(rows):
    """Purge using the latest of all 5 outcomes at BOTH train/cal and cal/test edges."""
    result = []; i = 0
    while i < len(rows):
        test = rows[i:i+TEST_BLOCK]
        eligible = [r for r in rows[:i] if r['last_target_date'] < test[0]['source_date']]
        if len(eligible) < N_CAL:
            i += 1; continue
        calibration = eligible[-N_CAL:]
        train = [r for r in eligible[:-N_CAL] if r['last_target_date'] < calibration[0]['source_date']]
        if len(train) < MIN_TRAIN or any(sum(r['outcomes'][str(h)]['cumulative_close'] != 'FLAT' for r in train) < MIN_TRAIN for h in HORIZONS):
            i += 1; continue
        result.append((train, calibration, test)); i += TEST_BLOCK
    return result


def fit_logit(rows, indices, h):
    x = np.array([[r['features'][i] for i in indices] for r in rows])
    y = np.array([r['outcomes'][str(h)]['cumulative_close'] == 'UP' for r in rows], dtype=int)
    if len(set(y)) != 2:
        raise ValueError('both training classes required')
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    model = LogisticRegression(C=1, penalty='l2', solver='lbfgs', max_iter=2000, random_state=0).fit((x-mean)/scale, y)
    return mean, scale, model


def raw_probability(fitted, r, indices):
    mean, scale, model = fitted
    x = np.array([r['features'][i] for i in indices])
    return float(model.predict_proba(((x-mean)/scale).reshape(1, -1))[0, 1])


def binary_metrics(rows):
    if not rows:
        return {'n': 0, 'status': 'insufficient_temporal_test_history', 'brier': None}
    y = np.array([r['y'] for r in rows]); p = np.array([r['p_up'] for r in rows])
    up, down = p > .5, p < .5
    tp = int(sum(up & (y == 1))); tn = int(sum(down & (y == 0)))
    fp = int(sum(up & (y == 0))); fn = int(sum(down & (y == 1)))
    n = len(rows); decided = int(sum(up | down))
    signal = np.array([r['information_state'] == 'model_score_with_calibration' for r in rows])
    sup = up & signal; sdown = down & signal
    return {'n': n, 'status': 'small_retrospective_test', 'brier': float(np.mean((p-y)**2)),
            'accuracy': (tp+tn)/decided if decided else None, 'n_neutral': n-decided,
            'up_precision': tp/(tp+fp) if tp+fp else None, 'down_precision': tn/(tn+fn) if tn+fn else None,
            'up_recall': tp/int(sum(y == 1)) if sum(y == 1) else None,
            'down_recall': tn/int(sum(y == 0)) if sum(y == 0) else None,
            'confusion': {'true_up': tp, 'false_up': fp, 'true_down': tn, 'false_down': fn},
            'n_model_signal': int(sum(sup | sdown)),
            'signal_up_precision': int(sum(sup & (y == 1)))/int(sum(sup)) if sum(sup) else None,
            'signal_down_precision': int(sum(sdown & (y == 0)))/int(sum(sdown)) if sum(sdown) else None,
            'n_reference_only': sum(r['information_state'] == 'recent_base_rate_only' for r in rows),
            'always_up_accuracy': float(y.mean()), 'always_down_accuracy': float(1-y.mean()),
            'mean_p_up': float(p.mean()), 'mean_p_down': float(1-p.mean())}


def walk_forward(rows, extra=False, with_ownership=False):
    if extra and with_ownership:
        raise ValueError('separate ownership and LETF cohorts required')
    usable = [r for r in rows if r['features'] is not None and
              (not extra or r['letf_exposure'] is not None and r['rebalance_signed_share'] is not None) and
              (not with_ownership or r.get('ownership_features') is not None)]
    records = []; fold_audit = []
    families = FAMILIES if not extra else {'price_foreign_options': list(range(7)), 'plus_letf_exposure_rebalance': list(range(9))}
    if extra:
        usable = [{**r, 'features': r['features'] + [r['letf_exposure']['reported_net_exposure_bias'], r['rebalance_signed_share']]} for r in usable]
    if with_ownership:
        families = {'price': [0, 1, 2], 'price_ownership': [0, 1, 2, 7, 8, 9],
                    'price_foreign_options': list(range(7)), 'price_foreign_options_ownership': list(range(10))}
        usable = [{**r, 'features': r['features']+r['ownership_features']} for r in usable]
    for index, (train, calibration, test) in enumerate(folds(usable)):
        meta = {'n_train': len(train), 'n_calibration': len(calibration), 'n_test': len(test),
                'last_train_outcome': max(r['last_target_date'] for r in train),
                'first_calibration_source': calibration[0]['source_date'],
                'last_calibration_outcome': max(r['last_target_date'] for r in calibration),
                'first_test_source': test[0]['source_date'], 'last_test_source': test[-1]['source_date'], 'heads': {}}
        for h in HORIZONS:
            # Exclude only this head's flat label, never another future horizon's outcome.
            train_h = [r for r in train if r['outcomes'][str(h)]['cumulative_close'] != 'FLAT']
            cal_h = [r for r in calibration if r['outcomes'][str(h)]['cumulative_close'] != 'FLAT']
            test_h = [r for r in test if r['outcomes'][str(h)]['cumulative_close'] != 'FLAT']
            ys = [int(r['outcomes'][str(h)]['cumulative_close'] == 'UP') for r in cal_h]
            if len(cal_h) < 20:
                meta['heads'][str(h)] = {'status': 'too_few_nonflat_calibration_rows'}; continue
            if len(set(ys)) != 2:
                meta['heads'][str(h)] = {'status': 'calibration_one_class'}; continue
            fitted = {}
            try:
                for family, indices in families.items():
                    model = fit_logit(train_h, indices, h)
                    z = [logit(raw_probability(model, r, indices)) for r in cal_h]
                    c = sigmoid_calibration(z, ys)
                    fitted[family] = (model, c)
            except ValueError as e:
                meta['heads'][str(h)] = {'status': 'unavailable', 'reason': str(e)}; continue
            meta['heads'][str(h)] = {'status': 'evaluated', 'n_train_nonflat': len(train_h),
                'n_calibration_nonflat': len(cal_h), 'n_test_nonflat': len(test_h),
                'n_test_flat_excluded': len(test)-len(test_h), 'calibrators': {k: c for k, (_, c) in fitted.items()}}
            for r in test_h:
                common = {'source_date': r['source_date'], 'target_date': r['outcomes'][str(h)]['target_date'],
                          'horizon': h, 'y': int(r['outcomes'][str(h)]['cumulative_close'] == 'UP'), 'fold': index}
                for family, (model, c) in fitted.items():
                    p = float(expit(c['slope']*logit(raw_probability(model, r, families[family]))+c['intercept']))
                    records.append({**common, 'family': family, 'p_up': p, 'p_down': 1-p,
                                    'information_state': 'recent_base_rate_only' if c['at_zero_slope'] else 'model_score_with_calibration'})
                p = sum(ys)/len(ys)
                records.append({**common, 'family': 'recent_frequency', 'p_up': p, 'p_down': 1-p,
                                'information_state': 'recent_base_rate_only'})
        fold_audit.append(meta)
    scores = {str(h): {family: binary_metrics([r for r in records if r['horizon'] == h and r['family'] == family])
                      for family in list(families)+['recent_frequency']} for h in HORIZONS}
    comparisons = {}
    for h in HORIZONS:
        subset = [r for r in records if r['horizon'] == h]
        lookup = {(r['source_date'], r['family']): r for r in subset}
        comparisons[str(h)] = {}
        for family in families:
            comparisons[str(h)][family] = {}
            for baseline in ['price' if not extra else 'price_foreign_options', 'recent_frequency']:
                pairs = [(r, lookup[(r['source_date'], baseline)]) for r in subset
                         if r['family'] == family and (r['source_date'], baseline) in lookup]
                delta = [(a['p_up']-a['y'])**2-(b['p_up']-b['y'])**2 for a, b in pairs]
                comparisons[str(h)][family][baseline] = {'n': len(delta), 'mean_brier_difference': float(np.mean(delta)) if delta else None}
    return {'n_usable_common_source_days': len(usable), 'folds': fold_audit, 'scores': scores, 'paired_brier': comparisons,
            'status': 'small_retrospective_test' if records else 'insufficient_temporal_test_history'}, records


def local_projections(rows):
    import statsmodels.api as sm
    usable = [r for r in rows if r['features'] is not None]
    if len(usable) < 60:
        return {'status': 'insufficient_history', 'n': len(usable), 'horizons': {}}
    x = sm.add_constant(np.array([r['features'] for r in usable]), has_constant='add')
    if np.linalg.matrix_rank(x) < x.shape[1]:
        return {'status': 'rank_deficient', 'n': len(usable), 'horizons': {}}
    out = {}
    for h in HORIZONS:
        y = np.array([r['outcomes'][str(h)]['cumulative_log_change_pct'] for r in usable])
        fitted = sm.OLS(y, x).fit(cov_type='HAC', cov_kwds={'maxlags': 5, 'use_correction': True})
        ci = fitted.conf_int()
        out[str(h)] = {FEATURES[i-1]: {'coefficient': float(fitted.params[i]), 'p_value': float(fitted.pvalues[i]),
                        'effect_per_plus_10pct_volume_share_pp': float(fitted.params[i]*.1),
                        'pointwise95_effect_pp': [float(v*.1) for v in ci[i]]}
                      for i in [4, 5]}
    return {'status': 'conditional_association_not_causal', 'n': len(usable), 'covariance': 'HAC maxlags=5, finite sample correction',
            'controls': FEATURES, 'horizons': out}


def holm(results):
    values = [(t, h, k, v) for t, r in results.items() for h, d in r['local_projections']['horizons'].items() for k, v in d.items()]
    previous = 0
    for i, (_, _, _, v) in enumerate(sorted(values, key=lambda a: a[3]['p_value'])):
        previous = max(previous, min(1, (len(values)-i)*v['p_value']))
        v['holm_p_all_stocks_horizons_flow_ratios'] = previous
    return len(values)


def write_predictions(path, records):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    text = ''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in records)
    if path.suffix == '.gz':
        path.write_bytes(gzip.compress(text.encode(), mtime=0))
    else:
        path.write_text(text)


def markdown(result):
    lines = ['# 1~5거래일·외국인 수급 비율·LETF 노출 연구', '',
             '과거 관측과 과거 시계열 검증이며 운영 모델/미래 확률/인과효과가 아니다.', '',
             '각 종목은 5개 미래 세션을 모두 가진 같은 source 날짜를 사용한다. 아래 빈도에는 동가를 포함한다.', '',
             '| 종목 | 조건 | h | n | 누적 상승 | 누적 하락 | 동가 | h번째 당일 상승 | h번째 당일 하락 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    pct = lambda x: '—' if x is None else f'{100*x:.1f}%'
    for ticker, r in result['tickers'].items():
        for group in ['foreign_buy', 'foreign_sell']:
            for h in HORIZONS:
                a = r['descriptive'][group][str(h)]['cumulative_close']; b = r['descriptive'][group][str(h)]['delayed_session_close']
                lines.append(f"| {ticker} | {group} | {h} | {a['n']} | {pct(a['p_up'])} | {pct(a['p_down'])} | {pct(a['p_flat'])} | {pct(b['p_up'])} | {pct(b['p_down'])} |")
        lines += ['', f'## {ticker} 시계열 검증 (누적 종가 방향)', '',
                  '| h | 모델 | test n | Brier | 모델 신호 상승 정밀도 | 모델 신호 하락 정밀도 | reference-only n |',
                  '|---|---|---:|---:|---:|---:|---:|']
        for h in HORIZONS:
            for family, s in r['walk_forward']['scores'][str(h)].items():
                lines.append(f"| {h} | {family} | {s['n']} | {s.get('brier')} | {pct(s.get('signal_up_precision'))} | {pct(s.get('signal_down_precision'))} | {s.get('n_reference_only', 0)} |")
        lines += ['', f"LETF 노출/검증된 리밸런싱 포함 검증 상태: {r['rebalance_walk_forward']['status']}; 같은 조건의 유효 source {r['rebalance_walk_forward']['n_usable_common_source_days']}일.", '']
        lines += [f"외국인 제공처 보유율 수준·1일/5일 변화 검증 상태: {r['ownership_walk_forward']['status']}; 유효 source {r['ownership_walk_forward']['n_usable_common_source_days']}일.", '',
                  '| h | 모델 | test n | Brier | 평균 상승 확률 | 평균 하락 확률 |',
                  '|---|---|---:|---:|---:|---:|']
        for h in HORIZONS:
            for family, s in r['ownership_walk_forward']['scores'][str(h)].items():
                lines.append(f"| {h} | {family} | {s['n']} | {s.get('brier')} | {pct(s.get('mean_p_up'))} | {pct(s.get('mean_p_down'))} |")
    lines += [f"모델: L2 logistic C=1 + 별도 {result['protocol']['calibration']} source일 보정 창. 최소 base {result['protocol']['min_base']} 유효일.",
              '운영 모델의 6개월 보정 구간과 다른 연구 프로토콜이며 운영 모델/계수는 바꾸지 않았다.',
              '학습/보정/평가 양 경계에서 5일 결과가 겹치지 않도록 purge. 무작위 분할/최적 h 선택 없음.',
              'LP: horizon별 OLS + HAC(5), 2종목×5h×2수급비율의 p값을 함께 Holm 보정. 인과효과가 아니다.',
              '외국인 순매수/거래량 비율은 실제 보유 비중이 아니다. LETF AUM 기반 노출도 실제 외국인 포지션이 아니다.',
              '리밸런싱 추정은 관측 ETF 주문/체결/가격 영향이 아니다. t마감 추정으로 t마감 전 거래를 예측하지 않는다.',
              '원천 공개시각 미확인, 데이터 공급자별 가격 기준 차이, 소표본/겹치는 결과/다중 실험 제약이 있다.']
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['flows', 'prices', 'board', 'letf', 'output', 'markdown', 'predictions']:
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--ownership', type=Path, required=True)
    p.add_argument('--exploratory-small-sample', action='store_true', help='explicit 80/30 initial-probe reproduction only; never operational validation')
    args = p.parse_args(); inputs = [args.flows, args.prices, args.board, args.letf, args.ownership]
    if args.exploratory_small_sample:
        MIN_TRAIN, N_CAL = 80, 30
    outputs = [args.output, args.markdown, args.predictions]
    if len({x.resolve() for x in outputs}) != len(outputs) or {x.resolve() for x in inputs} & {x.resolve() for x in outputs}:
        p.error('outputs must be distinct and must not overwrite inputs')
    flow, price, board, ownership = read(args.flows), read(args.prices), read(args.board), read(args.ownership)
    letf = [json.loads(s) for s in args.letf.read_text().splitlines() if s.strip()]
    tickers = {}; predictions = []
    for ticker in ['005930', '000660']:
        rows, audit = assemble(flow, price, board, letf, ticker, ownership)
        wf, records = walk_forward(rows); rebalance, extra = walk_forward(rows, extra=True)
        owned, owned_records = walk_forward(rows, with_ownership=True)
        tickers[ticker] = {'audit': audit, 'descriptive': describe(rows), 'walk_forward': wf,
                          'rebalance_walk_forward': rebalance, 'ownership_walk_forward': owned, 'local_projections': local_projections(rows)}
        predictions += [{'ticker': ticker, 'cohort': 'base', **r} for r in records]
        predictions += [{'ticker': ticker, 'cohort': 'letf', **r} for r in extra]
        predictions += [{'ticker': ticker, 'cohort': 'foreign_ownership', **r} for r in owned_records]
    result = {'schema_version': 'flow-horizons-research-v1', 'status': 'retrospective_research_only',
              'horizons': HORIZONS, 'features': FEATURES, 'families': FAMILIES, 'tickers': tickers,
              'ownership_features': ['provider_foreign_holding_pct', 'holding_delta1_pp', 'holding_delta5_pp'],
              'protocol': {'min_base': MIN_TRAIN, 'calibration': N_CAL, 'test_block': TEST_BLOCK, 'purge_outcome_sessions': 5,
                           'regularization_C': 1, 'lag_selection': 'none', 'operational_model_change': False},
              'input_sha256': {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime': {key: version(key) for key in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'statsmodels', 'exchange-calendars']},
              'limitations': ['Source first publication times unverified; no genuine prospective forecasts',
                 'Common source windows/split dates; each horizon excludes only its own flat labels; descriptive rates retain flats',
                 'Historical sample was already explored; temporal holdout is not genuine prospective validation',
                 'LETF rebalance uses KRX-verified source returns; price labels use Naver basis, scope differences unresolved',
                 'Reported ETF exposure is not investor holdings; trading flow is not a stock of positions',
                 'Provider foreignerHoldRatio is a holdings measure but denominator/corporate-action basis and original publication time remain unverified',
                 'Overlapping horizon outcomes, small test sets, multiple explored families; no best-lag/model selection',
                 'No causal identification, trading fees, PnL or position-sizing recommendation']}
    result['LP_holm_family_size'] = holm(tickers)
    write(args.output, result); args.markdown.parent.mkdir(parents=True, exist_ok=True); args.markdown.write_text(markdown(result))
    write_predictions(args.predictions, predictions)
    print({t: {'audit': r['audit'], 'base': r['walk_forward']['status'], 'rebalance': r['rebalance_walk_forward']['status']} for t, r in tickers.items()})

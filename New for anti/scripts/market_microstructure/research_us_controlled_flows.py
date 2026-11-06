"""US-controlled direction, option-value activity and training-only flow residuals.

Historical research only. Never read a frozen production model or publish live predictions.
"""
import argparse
import hashlib
import math
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import exchange_calendars as xc
import numpy as np
from scipy.special import expit
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

from option_direction_model import calendar, fit, option_features, price_data, probability, read, unique, window, write
from research_direction_diagnostics import ReviewedCalendar, richer_price_features
from research_flow_horizons import assemble as flow_rows, binary_metrics, sign, write_predictions
from research_foreign_flow_direction import valid_bar
from research_option_dynamics import logit, sigmoid_calibration
from research_short_horizon_flow import components
from research_us_lag1_direction import SYMBOLS, us_vector

HEADS = ['opening1', 'closing1', 'closing2', 'closing3', 'closing4', 'closing5', 'intraday1']
VOLS = ['absolute_gap_pct', 'absolute_intraday_pct', 'range_pct']
ADDITIONS = ['us_flow', 'us_ownership', 'us_flow_ownership', 'us_residual_flow', 'us_activity', 'us_flow_activity']
FAMILIES = ['domestic_controls', 'us_controls'] + ADDITIONS
VOL_FAMILIES = ['us_controls', 'us_activity', 'us_flow_activity']
MIN_TRAIN, N_CAL, TEST_BLOCK = 250, 60, 20
BASE_NAMES = ['momentum5', 'volatility20', 'return1', 'gap1', 'intraday1', 'momentum20',
              'call_rank60', 'put_rank60', 'call_mean5', 'put_mean5',
              'QQQ_return1', 'SPY_return1', 'VIX_return1', 'log_VIX',
              'SMH_return1', 'MU_return1', 'NVDA_return1', 'AMD_return1', 'log_stock_volume', 'stock_relative_volume20']
RESIDUAL_CONTROLS = list(range(6)) + [18, 19]
REVIEWED_US_CLOSURES = {'2025-01-09': 'https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx'}


class ReviewedUSCalendar:
    """Review official exceptional closures without changing frozen production helpers."""
    def __init__(self, base):
        self.base = base
        self.sessions = base.sessions[~base.sessions.strftime('%Y-%m-%d').isin(REVIEWED_US_CLOSURES)]

    def previous_session(self, day):
        i = self.sessions.get_loc(day)
        if i == 0: raise ValueError('previous reviewed US session unavailable')
        return self.sessions[i-1]

    def session_close(self, day):
        if day not in self.sessions: raise ValueError('not a reviewed US session')
        return self.base.session_close(day)


def activity_vector(products, cal, day):
    days = window(cal, day, 20)
    if len(days) != 21:
        raise ValueError('twenty exact prior sessions required for activity')
    values = []
    for side in ['call', 'put']:
        series = products[side]
        if any(d not in series or components(series[d]) is None for d in days):
            raise ValueError('invalid or missing exact option activity session')
        # One-side market value; buy == sell already checked. Do not double-count.
        amounts = [series[d]['market_total']['buy_krw'] for d in days]
        values.append((amounts[-1], float(np.mean(amounts[:-1]))))
    c, p = values
    return [math.log(c[0]/c[1]), math.log(p[0]/p[1]), p[0]/(c[0]+p[0])]


def align_us(data, us_cal, target):
    v, meta = us_vector(data, us_cal, target)
    if v is None:
        raise ValueError('missing expected US session pair: '+str(meta))
    day = meta['US_session']; previous = us_cal.previous_session(day).strftime('%Y-%m-%d')
    if any(data[s][d].get('quality') not in (None, 'observed') for s in SYMBOLS for d in [previous, day]):
        raise ValueError('non-observed US session price')
    return v[0]+v[1], meta


def assemble(flows, prices, board, ownership, us, ticker):
    initial, previous_audit = flow_rows(flows, prices, board, [], ticker, ownership)
    cal = ReviewedCalendar(calendar()); us_cal = ReviewedUSCalendar(xc.get_calendar('XNYS', start='2018-01-01', end='2027-12-31'))
    bars = unique(next(c['rows'] for c in prices['candidates'] if c['ticker'] == ticker))
    pf, _ = price_data(prices, cal, ticker); opts = option_features(board, cal)
    raw = board['kr']['investor_nets']['detailed_15007']['products']
    products = {s: unique(raw['options_'+s]['series']) for s in ['call', 'put']}
    data = {s: unique(us['symbols'][s]) for s in SYMBOLS}; exclusions = Counter(); rows = []
    for r in initial:
        d = r['source_date']
        try:
            if r['features'] is None or r['ownership_features'] is None or d not in pf or d not in opts:
                raise ValueError('incomplete common flow/ownership/price/option features')
            days = window(cal, d, 20); optdays = window(cal, d, 60)
            if len(days) != 21 or any(t not in bars or not valid_bar(bars[t]) for t in days):
                raise ValueError('missing observed 21-session OHLC window')
            if len(optdays) != 61 or any(components(products[s].get(t, {})) is None for s in products for t in optdays):
                raise ValueError('missing valid 61-session call/put window')
            vols = [bars[t].get('volume') for t in days]
            if any(v is None or not math.isfinite(v) or v <= 0 for v in vols):
                raise ValueError('invalid stock volume window')
            rich = richer_price_features([{'date': d, 'price_only': pf[d], 'option_only': opts[d]}], bars, cal)
            if not rich:
                raise ValueError('missing richer price controls')
            first = cal.next_session(d).strftime('%Y-%m-%d')
            uv, aligned = align_us(data, us_cal, first)
            base = rich[0]['price_only']+opts[d]+uv+[math.log(vols[-1]), vols[-1]/float(np.mean(vols[:-1]))]
            activity = activity_vector(products, cal, d)
            if len(base) != 20 or not np.isfinite(base+activity).all():
                raise ValueError('invalid feature vector')
            start, following = bars[d], bars[first]
            binary = {'opening1': sign(following['open']-start['close']),
                      'intraday1': sign(following['close']-following['open'])}
            targets = {'opening1': first, 'intraday1': first}
            for h in range(1, 6):
                binary['closing'+str(h)] = r['outcomes'][str(h)]['cumulative_close']
                targets['closing'+str(h)] = r['outcomes'][str(h)]['target_date']
            vol = {'absolute_gap_pct': 100*abs(math.log(following['open']/start['close'])),
                   'absolute_intraday_pct': 100*abs(math.log(following['close']/following['open'])),
                   'range_pct': 100*math.log(following['high']/following['low'])}
            rows.append({'source_date': d, 'last_target_date': r['last_target_date'], 'first_target_date': first,
                         'base': base, 'foreign': r['features'][3:5], 'ownership': r['ownership_features'],
                         'activity': activity, 'binary': binary, 'target_dates': targets, 'volatility': vol,
                         'alignment': aligned})
        except (ValueError, KeyError, StopIteration) as e:
            exclusions[str(e)] += 1
    return rows, {'previous_stage': previous_audit, 'common_rows': len(rows), 'exclusions': dict(exclusions),
                  'first_source': rows[0]['source_date'] if rows else None,
                  'last_source': rows[-1]['source_date'] if rows else None,
                  'US_alignment_examples': [{'source': r['source_date'], **r['alignment']} for r in rows[-3:]]}


def folds(rows):
    i = 0; result = []
    while i < len(rows):
        test = rows[i:i+TEST_BLOCK]
        eligible = [r for r in rows[:i] if r['last_target_date'] < test[0]['source_date']]
        if len(eligible) < N_CAL:
            i += 1; continue
        calibration = eligible[-N_CAL:]
        train = [r for r in eligible[:-N_CAL] if r['last_target_date'] < calibration[0]['source_date']]
        if any(sum(r['binary'][h] != 'FLAT' for r in train) < MIN_TRAIN for h in HEADS):
            i += 1; continue
        result.append((train, calibration, test)); i += TEST_BLOCK
    return result


def ridge_fit(x, y):
    x = np.asarray(x, dtype=float); mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    model = Ridge(alpha=1).fit((x-mean)/scale, np.asarray(y, dtype=float))
    return mean, scale, model


def ridge_predict(fitted, x):
    mean, scale, model = fitted
    return model.predict((np.asarray(x, dtype=float)-mean)/scale)


def residualizer(train):
    return ridge_fit([[r['base'][i] for i in RESIDUAL_CONTROLS] for r in train], [r['foreign'] for r in train])


def vector(r, family, nuisance):
    b = r['base']
    if family == 'domestic_controls': return b[:10]+b[18:]
    if family == 'us_controls': return b
    if family == 'us_flow': return b+r['foreign']
    if family == 'us_ownership': return b+r['ownership']
    if family == 'us_flow_ownership': return b+r['foreign']+r['ownership']
    if family == 'us_activity': return b+r['activity']
    if family == 'us_flow_activity': return b+r['foreign']+r['activity']
    if family == 'us_residual_flow':
        expected = ridge_predict(nuisance, [[b[i] for i in RESIDUAL_CONTROLS]])[0]
        return b+[float(a-c) for a, c in zip(r['foreign'], expected)]
    raise ValueError('unknown family')


def calibrations(records):
    out = []
    for lo, hi in zip([0, .4, .45, .5, .55, .6], [.4, .45, .5, .55, .6, 1]):
        sub = [r for r in records if lo <= r['p_up'] and (r['p_up'] < hi or hi == 1)]
        out.append({'lower': lo, 'upper': hi, 'n': len(sub),
                    'mean_p_up': float(np.mean([r['p_up'] for r in sub])) if sub else None,
                    'observed_up': float(np.mean([r['y'] for r in sub])) if sub else None})
    return out


def record_context(r):
    a = r.get('alignment', {})
    return {'research_only': True, 'eligible_for_prospective_evaluation': False,
            'status': 'retrospective_research_only', 'decision_date': r['first_target_date'],
            'US_session': a.get('US_session'), 'US_close_UTC': a.get('US_close_UTC'),
            'hypothetical_cutoff_KST': a.get('forecast_cutoff_KST')}


def evaluate(rows):
    records = []; audits = []
    for fold, (train, calibration, test) in enumerate(folds(rows)):
        nuisance = residualizer(train)
        meta = {'fold': fold, 'n_train': len(train), 'n_calibration': len(calibration), 'n_test': len(test),
                'last_train_outcome': max(r['last_target_date'] for r in train),
                'first_calibration_source': calibration[0]['source_date'],
                'last_calibration_outcome': max(r['last_target_date'] for r in calibration),
                'first_test_source': test[0]['source_date'], 'last_test_source': test[-1]['source_date'],
                'residualizer': {'mean': nuisance[0].tolist(), 'scale': nuisance[1].tolist(),
                    'coef': nuisance[2].coef_.tolist(), 'intercept': nuisance[2].intercept_.tolist()}, 'heads': {}}
        for head in HEADS:
            tr = [r for r in train if r['binary'][head] != 'FLAT']
            ca = [r for r in calibration if r['binary'][head] != 'FLAT']
            te = [r for r in test if r['binary'][head] != 'FLAT']
            observed = dict(Counter(r['binary'][head] for r in test))
            ys = [int(r['binary'][head] == 'UP') for r in ca]
            if len(ca) < 30 or len(set(ys)) != 2:
                meta['heads'][head] = {'status': 'insufficient_calibration', 'observed_test_counts': observed}; continue
            fitted = {}
            try:
                for family in FAMILIES:
                    model = fit([{'x': vector(r, family, nuisance), 'y': int(r['binary'][head] == 'UP')} for r in tr], 'x')
                    c = sigmoid_calibration([logit(probability(model, vector(r, family, nuisance))) for r in ca], ys)
                    fitted[family] = (model, c)
            except ValueError as e:
                meta['heads'][head] = {'status': 'unavailable', 'reason': str(e), 'observed_test_counts': observed}; continue
            meta['heads'][head] = {'status': 'evaluated', 'n_train_nonflat': len(tr), 'n_calibration_nonflat': len(ca),
                                  'n_test_nonflat': len(te), 'n_test_flat': len(test)-len(te),
                                  'observed_test_counts': observed,
                                  'calibrators': {f: c for f, (_, c) in fitted.items()}}
            for r in te:
                common = {**record_context(r), 'kind': 'direction', 'head': head, 'source_date': r['source_date'],
                          'target_date': r['target_dates'][head], 'fold': fold, 'y': int(r['binary'][head] == 'UP')}
                for family, (model, c) in fitted.items():
                    raw = probability(model, vector(r, family, nuisance))
                    p = float(expit(c['slope']*logit(raw)+c['intercept']))
                    records.append({**common, 'family': family, 'p_up': p, 'p_down': 1-p,
                                    'information_state': 'recent_base_rate_only' if c['at_zero_slope'] else 'model_score_with_calibration'})
                p = sum(ys)/len(ys)
                records.append({**common, 'family': 'recent_frequency', 'p_up': p, 'p_down': 1-p,
                                'information_state': 'recent_base_rate_only'})
        for head in VOLS:
            models = {f: ridge_fit([vector(r, f, nuisance) for r in train], [r['volatility'][head] for r in train]) for f in VOL_FAMILIES}
            prior = float(np.mean([r['volatility'][head] for r in calibration]))
            for r in test:
                common = {**record_context(r), 'kind': 'magnitude', 'head': head, 'source_date': r['source_date'],
                          'target_date': r['first_target_date'], 'fold': fold, 'actual': r['volatility'][head]}
                for family, model in models.items():
                    p = max(0, float(ridge_predict(model, [vector(r, family, nuisance)])[0]))
                    records.append({**common, 'family': family, 'predicted': p})
                records.append({**common, 'family': 'recent_mean', 'predicted': prior})
        audits.append(meta)
    return records, audits


def magnitude_metrics(rows, reference):
    if not rows:
        return {'n': 0, 'mae': None, 'rmse': None, 'skill_vs_recent_mean': None}
    p = np.array([r['predicted'] for r in rows]); y = np.array([r['actual'] for r in rows])
    loss = (p-y)**2; base = np.array([(reference[r['source_date']]['predicted']-r['actual'])**2 for r in rows])
    rank = float(spearmanr(p, y).statistic) if np.ptp(p) > 1e-12 and np.ptp(y) > 1e-12 else None
    return {'n': len(rows), 'mae': float(np.mean(abs(p-y))), 'rmse': float(np.sqrt(loss.mean())),
            'skill_vs_recent_mean': float(1-loss.sum()/base.sum()) if base.sum() > 0 else None,
            'spearman': rank if rank is not None and math.isfinite(rank) else None}


def paired(candidate, baseline, primary):
    lookup = {r['source_date']: r for r in baseline}
    if len(lookup) != len(baseline) or len({r['source_date'] for r in candidate}) != len(candidate):
        raise ValueError('duplicate test source dates')
    deltas = []
    for r in sorted(candidate, key=lambda r: r['source_date']):
        if r['source_date'] not in lookup: continue
        b = lookup[r['source_date']]
        if r['target_date'] != b['target_date']: raise ValueError('mismatched target dates')
        if r['kind'] == 'direction':
            if r['y'] != b['y']: raise ValueError('mismatched labels')
            d = (r['p_up']-r['y'])**2-(b['p_up']-r['y'])**2
        else:
            if r['actual'] != b['actual']: raise ValueError('mismatched magnitudes')
            d = abs(r['predicted']-r['actual'])-abs(b['predicted']-r['actual'])
        deltas.append(d)
    out = {'n_common': len(deltas), 'mean_loss_difference': float(np.mean(deltas)) if deltas else None,
           'primary': primary, 'interpretation': 'negative favors added input; historical conditional comparison'}
    if not primary: return out
    if len(deltas) < 50:
        return {**out, 'p_value': None, 'status': 'too_short_for_hac'}
    if np.ptp(deltas) < 1e-14:
        return {**out, 'p_value': 1., 'pointwise95': [float(np.mean(deltas))]*2, 'status': 'degenerate_loss_difference'}
    import statsmodels.api as sm
    result = sm.OLS(np.asarray(deltas), np.ones((len(deltas), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': 5, 'use_correction': True})
    if not np.isfinite(result.pvalues).all() or not np.isfinite(result.conf_int()).all():
        return {**out, 'p_value': None, 'status': 'hac_uncertainty_unavailable'}
    return {**out, 'p_value': float(result.pvalues[0]), 'pointwise95': result.conf_int()[0].tolist(),
            'status': 'exploratory_hac_5_ordered_observations'}


def summarize(records):
    out = {'direction': {}, 'magnitude': {}, 'paired': {}}
    for head in HEADS:
        sub = [r for r in records if r['kind'] == 'direction' and r['head'] == head]
        scores = {}
        for family in FAMILIES+['recent_frequency']:
            selected = [r for r in sub if r['family'] == family]
            scores[family] = {**binary_metrics(selected), 'calibration_bins': calibrations(selected)}
        out['direction'][head] = scores
        baseline = [r for r in sub if r['family'] == 'us_controls']
        for family in ADDITIONS:
            out['paired']['direction:'+head+':'+family] = paired([r for r in sub if r['family'] == family], baseline, head in ['opening1', 'closing1'])
    for head in VOLS:
        sub = [r for r in records if r['kind'] == 'magnitude' and r['head'] == head]
        reference = {r['source_date']: r for r in sub if r['family'] == 'recent_mean'}
        out['magnitude'][head] = {f: magnitude_metrics([r for r in sub if r['family'] == f], reference) for f in VOL_FAMILIES+['recent_mean']}
        baseline = [r for r in sub if r['family'] == 'us_controls']
        for family in ['us_activity', 'us_flow_activity']:
            out['paired']['magnitude:'+head+':'+family] = paired([r for r in sub if r['family'] == family], baseline, True)
    return out


def adjust_primary(tickers):
    tests = [v for t in tickers.values() for v in t['results']['paired'].values() if v['primary']]
    if len(tests) != 36: raise ValueError('declared primary family must contain 36 comparisons')
    previous = 0
    for i, test in enumerate(sorted(tests, key=lambda t: t.get('p_value') if t.get('p_value') is not None else 1)):
        p = test.get('p_value') if test.get('p_value') is not None else 1
        previous = max(previous, min(1, (len(tests)-i)*p))
        test['holm_p_primary36'] = previous


def markdown(result):
    lines = ['# 미국 통제 후 수급·보유율·옵션 활동 연구', '',
             '모든 숫자는 이미 탐색한 과거의 재학습·재현이다. 실제 사전 예측이나 오늘의 확률이 아니다.', '',
             '## 다음 장 방향 (Brier: 낮을수록 좋음)', '',
             '| 종목 | 목표 | test n | 미국 기준 | +수급 | +보유율 | +둘 다 | +잔차 수급 | +옵션 활동 | 최근 빈도 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    fmt = lambda x: '—' if x is None else f'{x:.5f}'
    for ticker, t in result['tickers'].items():
        for head in ['opening1', 'closing1', 'intraday1']:
            s = t['results']['direction'][head]
            values = [s[f].get('brier') for f in ['us_controls', 'us_flow', 'us_ownership', 'us_flow_ownership', 'us_residual_flow', 'us_activity', 'recent_frequency']]
            lines.append(f"| {ticker} | {head} | {s['us_controls']['n']} | "+' | '.join(fmt(v) for v in values)+' |')
    lines += ['', '## 다음 장 움직임 크기 (MAE: 낮을수록 좋음, 단위는 로그변화×100)', '',
              '| 종목 | 목표 | test n | 미국 기준 | +옵션 활동 | +수급·활동 | 최근 평균 |', '|---|---|---:|---:|---:|---:|---:|']
    for ticker, t in result['tickers'].items():
        for head in VOLS:
            s = t['results']['magnitude'][head]
            values = [s[f]['mae'] for f in VOL_FAMILIES+['recent_mean']]
            lines.append(f"| {ticker} | {head} | {s['us_controls']['n']} | "+' | '.join(fmt(v) for v in values)+' |')
    lines += ['', '## 1차36검정', '', '| 종목 | 비교 | n | 평균 loss 차이 | Holm p |', '|---|---|---:|---:|---:|']
    for ticker, t in result['tickers'].items():
        for key, p in t['results']['paired'].items():
            if p['primary']:
                lines.append(f"| {ticker} | {key} | {p['n_common']} | {fmt(p['mean_loss_difference'])} | {fmt(p['holm_p_primary36'])} |")
    lines += ['', '음수 loss 차이는 추가 입력에 유리하다. p값은 작은 과거 표본의 HAC 근사이며 전향 검증이나 인과효과를 증명하지 않는다.',
              '상승/하락 정밀도·재현율, 동가 제외 수, reference-only, 보정 구간별 빈도,2~5일 결과는 JSON에 보존했다.',
              '옵션 활동은 국내 콜풋 시장 거래금액이다. 계약 거래량·미국 옵션·변동성 순매수·딜러 포지션이 아니다.',
              '수급 잔차화는 정보를 새로 추가하지 않는다. 원래 수급과의 차이는 규제/정규화 효과일 수도 있다.',
              '현재 운영 모델/계수/UI/워크플로/공개 데이터 변경 없음. 비용·손익 계산 없음.']
    return '\n'.join(lines)+'\n'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['flows', 'prices', 'board', 'ownership', 'us', 'output', 'markdown', 'predictions']:
        p.add_argument('--'+key, type=Path, required=True)
    args = p.parse_args(); inputs = [args.flows, args.prices, args.board, args.ownership, args.us]
    outputs = [args.output, args.markdown, args.predictions]
    if len({x.resolve() for x in outputs}) != len(outputs) or {x.resolve() for x in inputs} & {x.resolve() for x in outputs}:
        p.error('distinct output paths must not overwrite inputs')
    flows, prices, board, owned, us = [read(x) for x in inputs]
    tickers = {}; records = []
    for ticker in ['005930', '000660']:
        rows, audit = assemble(flows, prices, board, owned, us, ticker)
        predictions, fa = evaluate(rows)
        tickers[ticker] = {'audit': audit, 'folds': fa, 'results': summarize(predictions)}
        records += [{'ticker': ticker, **r} for r in predictions]
        print(ticker, {'rows': len(rows), 'folds': len(fa), 'records': len(predictions)}, flush=True)
    adjust_primary(tickers)
    result = {'status': 'retrospective_research_only', 'generated_at': datetime.now(timezone.utc).isoformat(),
              'base_features': BASE_NAMES, 'families': FAMILIES, 'reviewed_US_closures': REVIEWED_US_CLOSURES,
              'binary_heads': HEADS, 'magnitude_targets': VOLS, 'primary_tests': 36,
              'protocol': {'min_base': MIN_TRAIN, 'calibration_window': N_CAL, 'test_block': TEST_BLOCK,
                           'purge_max_horizon': 5, 'logistic_C': 1, 'ridge_alpha': 1, 'auto_selection': False},
              'tickers': tickers, 'input_sha256': {x.name: hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime': {k: version(k) for k in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'statsmodels', 'exchange-calendars']},
              'limitations': ['Same explored historical period, not genuine prospective performance',
                  'Binary probabilities exclude only the named head flat labels; flat observation share is separate',
                  'Local generation/provider first publication timing not verified historically',
                  'Fixed first KR preopen US information for all horizons; no future US refresh',
                  'Domestic index-option value activity, not stock-native option positions or signed volatility demand',
                  'Two individual stock targets, not a market-wide foreign ownership model',
                  'Ownership denominator/corporate actions and price-provider market scope remain unverified',
                  'HAC5 ordered-observation approximation and primary36 Holm do not cover all earlier exploratory research',
                  'No causal identification, live model change, portfolio weighting, costs or PnL']}
    write(args.output, result);args.markdown.parent.mkdir(parents=True, exist_ok=True);args.markdown.write_text(markdown(result))
    write_predictions(args.predictions, records)

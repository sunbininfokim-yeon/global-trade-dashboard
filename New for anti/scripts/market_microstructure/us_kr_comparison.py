"""Frozen ablations beside the primary model; never select or retrain during inference."""
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.special import expit

from option_direction_model import digest, fit, probability, read, write
from research_option_dynamics import logit, sigmoid_calibration
from research_stock_open_close_direction import TARGETS
from research_us_lag1_direction import assemble
from us_kr_direction_engine import FEATURES, TICKERS, interpret, validate_model

VERSION = 'us-kr-frozen-comparison-v1'
FAMILIES = {'domestic_price_options': list(range(10)),
            'price_us': list(range(6)) + list(range(10, 18))}
DEFAULT_MODEL = Path(__file__).with_name('models') / 'shadow' / 'us_kr_comparison_20261022_v1.json'


def implementation_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def train(primary, board, prices, chain, us):
    validate_model(primary)
    supplied = {'board': digest(board), 'prices': digest(prices), 'chain': digest(chain), 'us': digest(us)}
    if supplied != primary['input_hashes']:
        raise ValueError('comparison must use the exact primary training inputs')
    cutoff = primary['trained_through']
    start = (pd.Timestamp(cutoff) + pd.Timedelta(days=1) - pd.DateOffset(months=6)).strftime('%Y-%m-%d')
    models = {}
    for ticker in TICKERS:
        rows, _, _, _ = assemble(board, prices, chain, us, ticker)
        rows = [r for r in rows if r['target_date'] <= cutoff]
        base = [r for r in rows if r['target_date'] < start]
        calibration = [r for r in rows if r['date'] >= start]
        meta = primary['models'][ticker]
        if (len(base), len(calibration)) != (meta['n_base'], meta['n_calibration']):
            raise ValueError('comparison cohort differs from primary')
        if max(r['target_date'] for r in base) >= min(r['date'] for r in calibration):
            raise ValueError('train/calibration overlap')
        heads = {}
        for target in TARGETS:
            families = {}
            for family, indices in FAMILIES.items():
                prepared = [{**r, 'y': r[target], family: [r['us_all'][i] for i in indices]} for r in base]
                model = fit(prepared, family)
                raw = [logit(probability(model, [r['us_all'][i] for i in indices])) for r in calibration]
                calibrator = sigmoid_calibration(raw, [r[target] for r in calibration])
                families[family] = {'model': model, 'calibrator': calibrator}
            heads[target] = {'families': families,
                             'frozen_recent_probability': sum(r[target] for r in calibration) / len(calibration)}
        models[ticker] = {'heads': heads, 'n_base': len(base), 'n_calibration': len(calibration)}
    out = {'schema_version': VERSION, 'primary_model_id': primary['model_id'],
           'trained_through': cutoff, 'created_at': datetime.now(timezone.utc).isoformat(),
           'feature_indices': FAMILIES, 'models': models, 'input_hashes': supplied,
           'implementation_sha256': implementation_hash(),
           'purpose': 'paired prospective ablations, no automatic model selection',
           'cohort': 'same nonflat historical train/calibration cohort as primary',
           'limitations': ['retrospective fitting; prospective validation pending',
                           'feature ablation measures predictive contribution, not causality']}
    out['comparison_id'] = digest(out)
    return out


def validate(artifact, primary):
    validate_model(primary)
    if artifact.get('comparison_id') != digest({k: v for k, v in artifact.items() if k != 'comparison_id'}):
        raise ValueError('comparison integrity check failed')
    if (artifact.get('schema_version') != VERSION or artifact.get('feature_indices') != FAMILIES or
            artifact.get('implementation_sha256') != implementation_hash()):
        raise ValueError('frozen comparison implementation changed')
    if (artifact.get('primary_model_id') != primary['model_id'] or
            artifact.get('trained_through') != primary['trained_through'] or
            artifact.get('input_hashes') != primary['input_hashes']):
        raise ValueError('comparison and primary training provenance differ')


def predict(artifact, primary, forecast):
    validate(artifact, primary)
    if forecast['model_id'] != primary['model_id']:
        raise ValueError('forecast model differs from comparison primary')
    if forecast['status'] not in ('research_preopen_forecast', 'retrospective_replay'):
        return {'status': 'unavailable', 'reason': 'primary forecast unavailable'}
    if (forecast['status'] != 'retrospective_replay' and
            datetime.fromisoformat(forecast['generated_at']) < datetime.fromisoformat(artifact['created_at'])):
        raise ValueError('cannot backdate before comparison creation')
    results = {}
    for ticker in TICKERS:
        x = [forecast['results'][ticker]['feature_values'][key] for key in FEATURES]
        scores = {}
        for target in TARGETS:
            head = artifact['models'][ticker]['heads'][target]
            families = {}
            for family, indices in FAMILIES.items():
                h = head['families'][family]
                raw = probability(h['model'], [x[i] for i in indices])
                c = h['calibrator']
                p = float(expit(c['slope'] * logit(raw) + c['intercept']))
                families[family] = {'probability': p, 'direction': interpret(p, target, c['at_zero_slope']),
                                    'information_state': 'recent_base_rate_only' if c['at_zero_slope'] else 'model_score_with_calibration'}
            families['frozen_recent'] = {'probability': head['frozen_recent_probability'],
                                        'information_state': 'frozen_calibration_frequency'}
            scores[target] = families
        results[ticker] = scores
    return {'status': forecast['status'], 'comparison_id': artifact['comparison_id'],
            'created_at': artifact['created_at'], 'trained_through': artifact['trained_through'], 'results': results}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['primary', 'board', 'stocks', 'kospi', 'chain', 'us', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error('new artifact path required; daily execution must never train')
    prices = {'candidates': read(args.stocks)['candidates'] + read(args.kospi)['candidates']}
    result = train(read(args.primary), read(args.board), prices, read(args.chain), read(args.us))
    write(args.output, result)
    print({'comparison_id': result['comparison_id'], 'trained_through': result['trained_through']})

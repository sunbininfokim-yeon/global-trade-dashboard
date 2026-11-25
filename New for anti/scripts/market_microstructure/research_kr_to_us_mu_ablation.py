"""Compare Samsung and SK Hynix separately on Micron, then score the frozen heads."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

import kr_to_us_semiconductor as engine
from research_kr_to_us_futures_control import futures_control

# Use the same KRX and US dates for all comparisons, even with fewer inputs.
CONTRASTS = (('market', 'samsung'), ('market', 'hynix'),
             ('samsung', 'semiconductors'), ('hynix', 'semiconductors'))


def score(y, p):
    up = p >= .5
    return {
        'brier': float(((p - y) ** 2).mean()),
        'recall_up': float(up[y.eq(1)].mean()) if y.eq(1).any() else None,
        'recall_down': float((~up[y.eq(0)]).mean()) if y.eq(0).any() else None,
    }


def compare(scores, ref, candidate):
    y = scores.observed_up
    gain = ((scores[ref] - y) ** 2 - (scores[candidate] - y) ** 2).to_numpy()
    centered = gain - gain.mean()
    variance = centered @ centered
    for lag in range(1, 11):
        variance += 2 * (1 - lag / 11) * (centered[lag:] @ centered[:-lag])
    se = np.sqrt(max(0., variance)) / len(gain)
    return {'gain': float(gain.mean()), 'ci95': (gain.mean() + np.array([-1,1]) * 1.96 * se).tolist(),
            'p': float(norm.sf(gain.mean() / se)) if se else 1.}


def groups():
    result = engine.features('mu')
    result['samsung'] = result['market'] + [key for key in engine.SEMI if key.startswith('samsung')]
    result['hynix'] = result['market'] + [key for key in engine.SEMI if key.startswith('hynix')]
    return result


def loss_report(scores, variants):
    return {'n': len(scores), 'last_date': str(scores.index[-1].date()),
            **{name: score(scores.observed_up, scores[name]) for name in variants}}


def test_periods(scores, variants):
    first_years = {'2016-2019': (2016, 2019), '2020-2022': (2020, 2022),
                   '2023-2025': (2023, 2025), '2026': (2026, 2026)}
    return {label: loss_report(scores[scores.index.year.isin(range(lo, hi + 1))], variants)
            for label, (lo, hi) in first_years.items()
            if scores.index.year.isin(range(lo, hi + 1)).any()}


def study(frame, frozen, cutoff, through, source_prices):
    variants = groups()
    train = frame.loc[:cutoff]
    if train.index[-1] != cutoff or through <= cutoff:
        raise ValueError('expected frozen cutoff and a later holdout')
    holdout = frame.loc[frame.index > cutoff]
    actual = {name: engine.prices(source_prices, name).reindex(frame.index) for name in ('mu', 'sox')}
    complete = train.dropna(subset=variants['semiconductors'])
    output, predictions, tests = {}, [], []
    for head in engine.HEADS:
        _, _, scores = engine.validate(train, head, variants)
        models = {name: engine.fit(complete.dropna(subset=[head]), head, cols) for name, cols in variants.items()}
        replay_dates = holdout.dropna(subset=variants['semiconductors']).index
        observations = []
        for date in replay_dates:
            row = holdout.loc[[date]]
            if pd.isna(row[head].iloc[0]):
                continue
            probability = {name: float(engine.probabilities(model, row)[0]) for name, model in models.items()}
            p_v1 = float(engine.probabilities(frozen['models']['mu'][head], row)[0])
            if not np.isclose(p_v1, probability['semiconductors'], atol=1e-12, rtol=0.):
                raise ValueError('could not reproduce the frozen Micron probabilities')
            observations.append({'date':str(date.date()), 'observed_up':bool(row[head].iloc[0]),
                                 'probability_up':probability})
        contrasts = {f'{ref}_to_{cand}': compare(scores, ref, cand) for ref, cand in CONTRASTS}
        tests.extend(contrasts.values())
        output[head] = {'common_sample':loss_report(scores, variants),
                        'periods':test_periods(scores, variants),
                        'comparisons':contrasts, 'after_cutoff_replay':observations}
        predictions.append(scores.assign(head=head))
    adjusted = 0.
    for i, item in enumerate(sorted(tests, key=lambda row: row['p'])):
        adjusted = max(adjusted, min(1., (len(tests) - i) * item['p']))
        item['p_holm'] = adjusted

    # Price facts are kept separate from the predicted probabilities.
    realized = {}
    for name, q in actual.items():
        prev = q.close.shift()
        pct = pd.DataFrame({'opening':q.open / prev - 1, 'intraday':q.close / q.open - 1,
                            'closing':q.close / prev - 1})
        realized[name] = {str(d.date()): row.to_dict()
                          for d, row in pct.loc[(pct.index > cutoff) & (pct.index <= through)].dropna().iterrows()}
    return {'model_id':frozen['model_id'], 'trained_through':str(cutoff.date()),
            'holdout_through':str(through.date()), 'micron':output,
            'actual_returns_after_cutoff':realized}, pd.concat(predictions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prices', type=Path, required=True)
    parser.add_argument('--through', required=True)
    parser.add_argument('--futures', type=Path)
    parser.add_argument('--model', type=Path, default=engine.MODEL)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    args = parser.parse_args()

    frozen = json.loads(args.model.read_text())
    if frozen['schema'] != engine.SCHEMA or frozen['model_id'] != engine.digest(frozen):
        raise ValueError('invalid frozen model')
    cutoff, through = pd.Timestamp(frozen['trained_through']), pd.Timestamp(args.through)
    engine.check_completed_us_date(through, pd.Timestamp.now(tz='UTC'))
    frame = engine.panel(args.prices, through)['mu']
    result, predictions = study(frame, frozen, cutoff, through, args.prices)
    variants = groups()
    common = frame.dropna(subset=variants['semiconductors'])
    result['hynix_only_candidate'] = {
        'trained_through': str(through.date()),
        'status': 'research_candidate',
        'models': {
            head: engine.fit(common.dropna(subset=[head]), head, variants['hynix'])
            for head in ('opening', 'closing')
        },
    }
    if args.futures:
        controls = futures_control(args.futures, frame.index)
        aligned = frame.loc[:cutoff].join(controls)
        futures_variants = {name: cols + list(controls.columns) for name, cols in variants.items()}
        result['futures_sensitivity'] = {}
        for head in ('opening', 'closing'):
            _, _, rows = engine.validate(aligned, head, futures_variants)
            result['futures_sensitivity'][head] = {
                **loss_report(rows, variants),
                'first_date': str(rows.index[0].date()),
                'market_to_hynix': compare(rows, 'market', 'hynix'),
            }
    engine.save_new(args.output, result)
    predictions.to_csv(args.predictions, mode='x', index_label='date')


if __name__ == '__main__':
    main()

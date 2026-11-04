"""Stock opening/closing direction and sign persistence, without PnL or cost analysis."""
import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

from option_direction_model import PUBLIC, read, unique, write
from research_direction_diagnostics import directional_scores
from research_mixed_option_activity import build
from research_option_dynamics import evaluate
from research_short_horizon_prediction import paired_loss, holm

FAMILIES=['price','existing','money','volume','mixed']
TARGETS=['opening_up','closing_up','direction_persists','opening_extends']


def path_labels(previous_close, next_open, next_close):
    if any(not math.isfinite(v) or v<=0 for v in (previous_close,next_open,next_close)):
        raise ValueError('invalid OHLC')
    opening=(next_open>previous_close)-(next_open<previous_close)
    closing=(next_close>previous_close)-(next_close<previous_close)
    intraday=(next_close>next_open)-(next_close<next_open)
    label=lambda v:'UP' if v>0 else 'DOWN' if v<0 else 'FLAT'
    return {'opening_direction':label(opening),'closing_direction':label(closing),
            'intraday_direction':label(intraday),
            'opening_up':int(opening>0) if opening else None,
            'closing_up':int(closing>0) if closing else None,
            'direction_persists':int(opening==closing) if opening and closing else None,
            'opening_extends':int(intraday==opening) if opening else None,
            'path':label(opening)+'_TO_'+label(closing)}


def analyze(board,prices,chain,ticker):
    rows,exclusions=build(board,prices,chain,ticker=ticker)
    bars=unique(next(c['rows'] for c in prices['candidates'] if c['ticker']==ticker))
    labelled=[];flats=Counter()
    for r in rows:
        labels=path_labels(bars[r['date']]['close'],bars[r['target_date']]['open'],bars[r['target_date']]['close'])
        if any(labels[t] is None for t in TARGETS):flats[labels['path']]+=1;continue
        labelled.append({**r,**labels})
    output={};comparisons={}
    for target in TARGETS:
        prepared=[{**r,'y':r[target]} for r in labelled]
        preds,folds=evaluate(prepared,FAMILIES)
        if not folds:raise ValueError('insufficient independent train/calibration/test history')
        for family in FAMILIES:
            for r in preds[family+'_calibrated']:
                f=next(f for f in reversed(folds) if f['test_start']<=r['date'])
                r['information_state']='recent_base_rate_only' if f['calibrators'][family]['at_zero_slope'] else 'model_score_with_calibration'
        for records in preds.values():
            for r in records:r.pop('return',None)
        for family in FAMILIES[1:]:
            for baseline in ('price_calibrated','prior_recent'):
                comparisons[target+':'+family+'_vs_'+baseline]=paired_loss(preds[family+'_calibrated'],preds[baseline])
        output[target]={'scores':{k:directional_scores(v) for k,v in preds.items()},'folds':folds,'predictions':preds}
    # All targets/families evaluated on exactly the same dates, excluding flat boundary outcomes.
    reference=output['opening_up']['predictions']['prior_recent']
    dates={r['date'] for r in reference}
    path_counts=dict(Counter(r['path'] for r in labelled if r['date'] in dates))
    lookup={r['date']:r for r in labelled}
    examples=[{'source_date':r['date'],'target_date':r['target_date'],
               **{k:r[k] for k in ('opening_direction','closing_direction','intraday_direction','path')}}
              for r in labelled if r['date'] in dates][-10:]
    return {'ticker':ticker,'market_inputs':'KOSPI200 options, not this stock own option flow',
            'n_source_rows':len(rows),'n_nonflat_labelled_rows':len(labelled),'flat_exclusions':dict(flats),
            'chain_exclusions':exclusions,'targets':output,'comparisons':comparisons,
            'evaluated_path_counts':path_counts,'recent_observed_path_examples':examples,
            'evaluation_first_source':min(dates),'evaluation_last_source':max(dates),
            'evaluation_last_target':lookup[max(dates)]['target_date']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prices',type=Path,required=True)
    p.add_argument('--chain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();board=PUBLIC/'derivatives_board_v1.json'
    results={t:analyze(read(board),read(args.prices),read(args.chain),t) for t in ('005930','000660')}
    combined={t+':'+k:v for t,r in results.items() for k,v in r['comparisons'].items()};holm(combined)
    result={'status':'retrospective_research_only','stocks':results,
        'target_contract':{'decision_time':'source day after close, historical publication time unverified',
            'opening_up':'next open > source close','closing_up':'next close > source close',
            'direction_persists':'sign(next open-source close) == sign(next close-source close)',
            'opening_extends':'sign(next close-next open) == sign(next open-source close); flat intraday is not extension',
            'intraday_direction':'sign(next close-next open), descriptive, not an additional fitted target',
            'flat':'FLAT retained in audit; excluded from the common binary-model comparison cohort',
            'scores':'100*p of the named event, 50 equal probability; persistence is not an UP score',
            'scope':'No transaction cost, PnL, trading strategy or option profitability calculations'},
        'input_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (board,args.prices,args.chain)},
        'implementation_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__),Path(__file__).with_name('research_mixed_option_activity.py'),
             Path(__file__).with_name('research_short_horizon_prediction.py')]},
        'limitations':['Stock-native price controls; shared KOSPI200 option features; own stock cash flows/options not yet included',
            'All targets on same nonflat outcome cohort; exclusion uses labels only, never model features; unconditional live cohort includes flats',
            '64 paired calibrated Brier comparisons (2 stocks * 4 targets * 4 candidates * 2 baselines) Holm-adjusted together',
            'Already-explored historical period and newly fetched provider chart data, no prospective validation',
            'Naver chart price basis; corporate-action adjustment and KRX vs provider market scope not independently verified',
            'Separate marginal/persistence heads are not a coherent joint distribution; do not multiply them to get joint path probabilities',
            'Persistence compares with source close; it does not establish an uninterrupted intraday path',
            'Preclose model cannot use next opening price as an input; it is used only to define evaluation labels',
            'Zero-slope calibration reflects recent class frequency only, not a reactive option signal']}
    write(args.output,result);print('wrote',args.output)

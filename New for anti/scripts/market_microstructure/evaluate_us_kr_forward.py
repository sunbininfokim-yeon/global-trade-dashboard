"""Score immutable pre-open forecasts and count every expected KRX session. No PnL."""
import argparse
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from option_direction_model import calendar, digest, read, unique
from build_kospi200_price_panel import fetch_naver_chart, NAVER_CHART
from research_direction_diagnostics import ReviewedCalendar
from research_stock_open_close_direction import TARGETS, path_labels
from run_us_kr_preopen import atomic_json, timing
from us_kr_comparison import DEFAULT_MODEL, validate as validate_comparison
from us_kr_direction_engine import TICKERS, validate_model
from us_kr_publication import publication_evidence

BINS = [0, .4, .45, .5, .55, .6, 1]


def collect_outcomes(start, end, now=None):
    """Use the training price provider; keep a fresh snapshot, never splice sources."""
    now = timestamp(now or datetime.now(timezone.utc))
    base = calendar(); cal = ReviewedCalendar(base)
    if start > end or start < cal.sessions[0].strftime('%Y-%m-%d') or end > cal.sessions[-1].strftime('%Y-%m-%d'):
        raise ValueError('outcome range outside reviewed calendar')
    days = [d for d in cal.sessions.strftime('%Y-%m-%d')
            if start <= d <= end and now >= base.session_close(d)]
    out = {'source': 'Naver chart, same provider basis as primary training',
           'collected_at': now.isoformat(), 'provider_published_at': 'unknown', 'candidates': [], 'errors': []}
    if not days:
        return out
    first_position = cal.sessions.get_loc(days[0])
    if first_position == 0:
        raise ValueError('previous outcome source session outside calendar')
    previous = cal.sessions[first_position-1].strftime('%Y-%m-%d')
    expected = [previous] + days
    for ticker in TICKERS:
        try:
            raw = fetch_naver_chart(ticker, previous.replace('-', ''), days[-1].replace('-', ''))
            rows = [dict(date=d, quality='observed', **raw[d]) for d in expected if d in raw]
            missing = sorted(set(expected)-set(raw))
            out['candidates'].append({'ticker': ticker, 'rows': rows, 'missing_sessions': missing,
                'source_url': NAVER_CHART.format(symbol=ticker, start=previous.replace('-', ''), end=days[-1].replace('-', '')),
                'price_adjustment': 'provider chart basis; KRX-only scope and corporate actions not independently verified'})
            if missing:
                out['errors'].append({'ticker': ticker, 'missing_sessions': missing})
        except Exception as e:
            out['errors'].append({'ticker': ticker, 'reason': type(e).__name__ + ': ' + str(e)})
    return out


def timestamp(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('timezone-aware timestamp required')
    return t


def valid_probability(score):
    p = score.get('probability')
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError('invalid probability')
    return p


def validate_first(forecast, primary, target, now):
    if (forecast.get('status') != 'research_preopen_forecast' or
            forecast.get('record_role') != 'first_preopen_forecast' or
            forecast.get('eligible_for_primary_evaluation') is not True or
            forecast.get('eligible_for_prospective_evaluation') is not True):
        raise ValueError('not an eligible first pre-open forecast')
    if (forecast.get('model_id') != primary['model_id'] or forecast.get('target_date') != target or
            forecast.get('trained_through') != primary['trained_through'] or target <= primary['trained_through']):
        raise ValueError('forecast identity or training cutoff mismatch')
    generated = timestamp(forecast['generated_at'])
    if generated > now or generated < timestamp(primary['created_at']):
        raise ValueError('generation before model creation or after evaluation time')
    gate = timing(target, generated.to_pydatetime())
    if gate['reasons']:
        raise ValueError('invalid pre-open timing: ' + '; '.join(gate['reasons']))
    if (forecast.get('KR_source_date') != gate['source'] or
            forecast.get('required_US_session') != gate['us_source'] or
            timestamp(forecast['forecast_cutoff_KST']) != timestamp(gate['cutoff'])):
        raise ValueError('source session or cutoff mismatch')
    for ticker in TICKERS:
        for target_name in TARGETS:
            score = forecast['results'][ticker]['scores'][target_name]
            valid_probability(score)
            if score.get('information_state') not in ('recent_base_rate_only', 'model_score_with_calibration'):
                raise ValueError('unknown information state')


def comparison_scores(forecast, artifact):
    c = forecast.get('comparisons', {})
    if (c.get('status') != 'research_preopen_forecast' or
            c.get('comparison_id') != artifact['comparison_id'] or
            c.get('trained_through') != artifact['trained_through'] or
            timestamp(c['created_at']) != timestamp(artifact['created_at']) or
            timestamp(forecast['generated_at']) < timestamp(artifact['created_at'])):
        raise ValueError('comparison absent, unavailable or from another frozen version')
    for ticker in TICKERS:
        for target in TARGETS:
            for family in ('domestic_price_options', 'price_us', 'frozen_recent'):
                score = c['results'][ticker][target][family]
                valid_probability(score)
                if family == 'frozen_recent' and score['probability'] != artifact['models'][ticker]['heads'][target]['frozen_recent_probability']:
                    raise ValueError('frozen baseline probability changed')
    return c['results']


def actual_labels(bars, source, target):
    # Dates must be present exactly; carried-forward data is never an outcome.
    a, b = bars[source], bars[target]
    for row in (a, b):
        if row.get('quality') not in (None, 'observed'):
            raise ValueError('outcome price is not observed')
        values = [row[k] for k in ('open', 'high', 'low', 'close')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('invalid outcome OHLC')
        if row['low'] > min(row['open'], row['close']) or row['high'] < max(row['open'], row['close']) or row['low'] > row['high']:
            raise ValueError('inconsistent outcome OHLC')
    return path_labels(a['close'], b['open'], b['close'])


def wilson(hits, n):
    if not n:
        return None
    z = 1.959963984540054
    p = hits / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [max(0, center-radius), min(1, center+radius)]


def metrics(rows):
    if not rows:
        return {'n': 0, 'status': 'awaiting_observations', 'brier': None, 'accuracy': None,
                'signal_accuracy': None, 'signal_accuracy_wilson95': None, 'reliability': []}
    decided = [r for r in rows if r['p'] != .5]
    signal = [r for r in decided if r['information_state'] == 'model_score_with_calibration']
    hit = lambda r: int((r['p'] > .5) == bool(r['y']))
    reliability = []
    for lo, hi in zip(BINS, BINS[1:]):
        bucket = [r for r in rows if lo <= r['p'] and (r['p'] < hi or hi == 1)]
        reliability.append({'lower': lo, 'upper': hi, 'n': len(bucket),
                            'mean_probability': sum(r['p'] for r in bucket)/len(bucket) if bucket else None,
                            'event_rate': sum(r['y'] for r in bucket)/len(bucket) if bucket else None})
    return {'n': len(rows), 'status': 'small_sample' if len(rows) < 60 else 'descriptive_forward_evaluation',
            'brier': sum((r['p']-r['y'])**2 for r in rows)/len(rows),
            'always_yes_accuracy': sum(r['y'] for r in rows)/len(rows),
            'half_probability_brier': .25,
            'n_decided': len(decided), 'n_neutral': len(rows)-len(decided),
            'accuracy': sum(hit(r) for r in decided)/len(decided) if decided else None,
            'n_model_signal': len(signal), 'n_reference_only': sum(r['information_state'] == 'recent_base_rate_only' for r in rows),
            'signal_accuracy': sum(hit(r) for r in signal)/len(signal) if signal else None,
            'signal_accuracy_wilson95': wilson(sum(hit(r) for r in signal), len(signal)),
            'mean_probability': sum(r['p'] for r in rows)/len(rows), 'reliability': reliability}


def summarize(records):
    output = {}
    for ticker in TICKERS:
        output[ticker] = {}
        for target in TARGETS:
            rows = [r for r in records if r['ticker'] == ticker and r['target'] == target]
            families = sorted({r['family'] for r in rows} | {'primary'})
            output[ticker][target] = {f: metrics([r for r in rows if r['family'] == f]) for f in families}
            lookup = {(r['date'], r['family']): r for r in rows}
            pairs = {}
            for baseline in ('domestic_price_options', 'price_us', 'frozen_recent'):
                matched = [(r, lookup[(r['date'], baseline)]) for r in rows
                           if r['family'] == 'primary' and (r['date'], baseline) in lookup]
                deltas = [(a['p']-a['y'])**2 - (b['p']-b['y'])**2 for a, b in matched]
                pairs['primary_vs_' + baseline] = {
                    'n_common': len(matched),
                    'mean_brier_difference': sum(deltas)/len(deltas) if deltas else None,
                    'interpretation': 'negative favors primary; descriptive only, no causal or significance claim'}
            output[ticker][target]['paired_comparisons'] = pairs
    return output


def evaluate(root, primary, comparison, prices, start, end, now=None):
    validate_model(primary)
    validate_comparison(comparison, primary)
    now = timestamp(now or datetime.now(timezone.utc))
    for day in (start, end):
        if pd.Timestamp(day).strftime('%Y-%m-%d') != day:
            raise ValueError('dates must use YYYY-MM-DD')
    if start > end:
        raise ValueError('start must not follow end')
    base = calendar()
    cal = ReviewedCalendar(base)
    if start < cal.sessions[0].strftime('%Y-%m-%d') or end > cal.sessions[-1].strftime('%Y-%m-%d'):
        raise ValueError('evaluation range outside reviewed calendar')
    sessions = [d for d in cal.sessions.strftime('%Y-%m-%d') if start <= d <= end]
    bars = {c['ticker']: unique(c['rows']) for c in prices['candidates']}
    if len(bars) != len(prices['candidates']):
        raise ValueError('duplicate price candidates')
    days = []; records = []; reasons = Counter()
    for day in sessions:
        cutoff = pd.Timestamp(day, tz='Asia/Seoul') + pd.Timedelta(hours=8, minutes=30)
        if now < cutoff:
            continue
        entry = {'target_date': day, 'matured': now >= base.session_close(day), 'issued': False,
                 'attempt_count': 0, 'tickers': {}}
        directory = Path(root) / day / primary['model_id'][:16]
        attempts = []
        for path in sorted((directory/'attempts').glob('*.json')):
            attempt = read(path)
            if (attempt.get('model_id') == primary['model_id'] and attempt.get('target_date') == day and
                    attempt.get('status') != 'retrospective_replay' and timestamp(attempt['generated_at']) <= now):
                attempts.append(attempt)
        entry['attempt_count'] = len(attempts)
        if attempts:
            latest = max(attempts, key=lambda a: timestamp(a['generated_at']))
            entry['last_attempt_status'] = latest['status']
            entry['last_attempt_reasons'] = latest.get('reasons', [])
        first = directory/'first.json'
        if not first.exists():
            entry['reason'] = 'no_valid_first_forecast' if attempts else 'no_recorded_attempt'
            reasons[entry['reason']] += 1
            days.append(entry)
            continue
        try:
            forecast = read(first)
            validate_first(forecast, primary, day, now)
        except (ValueError, KeyError, TypeError) as e:
            entry.update(reason='invalid_first_forecast', detail=str(e))
            reasons[entry['reason']] += 1
            days.append(entry)
            continue
        entry.update(issued=True, generated_at=forecast['generated_at'], forecast_sha256=digest(forecast))
        entry['publication'] = publication_evidence(directory, forecast, now)
        try:
            comparisons = comparison_scores(forecast, comparison)
            entry['comparison_status'] = 'available'
        except (ValueError, KeyError, TypeError) as e:
            comparisons = None
            entry.update(comparison_status='unavailable', comparison_reason=str(e))
        if entry['matured']:
            for ticker in TICKERS:
                source = forecast['KR_source_date']
                try:
                    labels = actual_labels(bars[ticker], source, day)
                except (KeyError, ValueError, TypeError) as e:
                    entry['tickers'][ticker] = {'status': 'outcome_unavailable', 'reason': str(e)}
                    continue
                flat = any(labels[t] is None for t in TARGETS)
                entry['tickers'][ticker] = {'status': 'flat_excluded' if flat else 'scored', 'labels': labels,
                                           'previous_close': bars[ticker][source]['close'],
                                           'open': bars[ticker][day]['open'], 'close': bars[ticker][day]['close']}
                if flat:
                    continue
                for target in TARGETS:
                    scores = {'primary': forecast['results'][ticker]['scores'][target]}
                    if comparisons:
                        scores.update(comparisons[ticker][target])
                    for family, score in scores.items():
                        records.append({'date': day, 'ticker': ticker, 'target': target, 'family': family,
                                        'p': valid_probability(score), 'y': labels[target],
                                        'information_state': score.get('information_state')})
        days.append(entry)
    issued = sum(d['issued'] for d in days)
    recent = {d['target_date'] for d in days if d['matured']}
    recent = set(sorted(recent)[-20:])
    published = {d['target_date'] for d in days if d.get('publication', {}).get('status') == 'verified'}
    published_records = [r for r in records if r['date'] in published]
    return {'schema_version': 'us-kr-forward-evaluation-v1',
            'status': 'forward_records_scored' if records else 'awaiting_forward_outcomes',
            'generated_at': now.isoformat(), 'start': start, 'end': end,
            'model_id': primary['model_id'], 'comparison_id': comparison['comparison_id'],
            'price_input_sha256': digest(prices),
            'issuance': {'expected_sessions_past_cutoff': len(days), 'issued_sessions': issued,
                         'issuance_rate': issued/len(days) if days else None,
                         'matured_sessions': sum(d['matured'] for d in days),
                         'unissued_reasons': dict(reasons)},
            'all': summarize(records), 'last_20_matured_sessions': summarize([r for r in records if r['date'] in recent]),
            'publication_verified': {
                'verified_sessions': len(published),
                'verified_publication_rate': len(published)/len(days) if days else None,
                'generated_without_verified_publication': issued-len(published),
                'all': summarize(published_records),
                'last_20_matured_sessions': summarize([r for r in published_records if r['date'] in recent]),
                'basis': 'remote payload observed before cutoff and matched to immutable first forecast'},
            'days': days,
            'limitations': ['Only original eligible first forecasts; revisions and replay excluded',
                            'Local generation timestamp is not independent proof of public availability',
                            'Missing invocation is no_recorded_attempt, not an inferred provider failure',
                            'Flat boundary outcomes retained in audit, excluded from the common binary cohort',
                            'Outcome provider/adjustment basis must match training; KRX-only scope remains unverified',
                            'Ablations share primary input-availability gating, not independent forecast coverage',
                            'Reference-only and neutral forecasts separated from model direction signals',
                            'Wilson intervals assume independent outcomes; descriptive, not evidence of an edge',
                            'Always-yes accuracy is a realized reference, not an ex-ante fitted forecast',
                            'No auto selection, retraining, threshold tuning, trading costs or PnL']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive-dir', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--comparison-model', type=Path, default=DEFAULT_MODEL)
    p.add_argument('--stocks', type=Path)
    p.add_argument('--kospi', type=Path)
    p.add_argument('--refresh-prices', action='store_true', help='collect closed-session outcome prices only')
    p.add_argument('--run-dir', type=Path, help='new directory for the outcome price snapshot; required with refresh')
    p.add_argument('--start', required=True)
    p.add_argument('--end', default=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d'))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.refresh_prices and (not args.run_dir or args.stocks or args.kospi):
        p.error('refresh requires --run-dir and must not mix with --stocks/--kospi')
    if not args.refresh_prices and not all([args.stocks, args.kospi]):
        p.error('offline evaluation requires --stocks and --kospi')
    inputs = [x for x in [args.model, args.comparison_model, args.stocks, args.kospi] if x]
    if (args.output.resolve() in {x.resolve() for x in inputs} or
            args.archive_dir.resolve() == args.output.resolve() or args.archive_dir.resolve() in args.output.resolve().parents):
        p.error('output must not overwrite inputs or any forecast archive record')
    if args.refresh_prices:
        if args.run_dir.exists():
            p.error('new outcome run directory required; preserve previous snapshots')
        if args.output.resolve() == (args.run_dir/'outcome_prices.json').resolve():
            p.error('report must not overwrite the outcome price snapshot')
        if args.archive_dir.resolve() == args.run_dir.resolve() or args.archive_dir.resolve() in args.run_dir.resolve().parents:
            p.error('outcome snapshots must be outside the forecast archive')
        prices = collect_outcomes(args.start, args.end)
        atomic_json(args.run_dir/'outcome_prices.json', prices)
    else:
        prices = {'candidates': read(args.stocks)['candidates'] + read(args.kospi)['candidates']}
    report = evaluate(args.archive_dir, read(args.model), read(args.comparison_model), prices, args.start, args.end)
    if args.refresh_prices:
        report['outcome_collection'] = {'snapshot': str(args.run_dir/'outcome_prices.json'), 'errors': prices['errors']}
        if prices['errors']:
            report['status'] = 'partial_outcome_collection'
    atomic_json(args.output, report)
    print({'status': report['status'], 'issuance': report['issuance']})
    if args.refresh_prices and prices['errors']:
        raise SystemExit(2)

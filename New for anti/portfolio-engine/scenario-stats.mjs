// Descriptive strategy statistics, deliberately separate from T25's CAGR Sharpe.
import {finite, vector, sum, histVarCvar} from './math.mjs';
const mean = x => sum(x) / x.length;
const variance = x => {
  if (x.length < 2) return null;
  const m = mean(x);
  return sum(x.map(v => (v - m) ** 2)) / (x.length - 1);
};
export function quantile(x, p) {
  vector(x); finite(p);
  if (p < 0 || p > 1) throw new RangeError('quantile outside [0,1]');
  const a = x.slice().sort((a, b) => a - b), h = (a.length - 1) * p, i = Math.floor(h);
  return a[i] + (a[Math.ceil(h)] - a[i]) * (h - i);
}
export function regression(x, y) {
  vector(x, 'factor returns', 0); vector(y, 'response returns', 0);
  if (x.length !== y.length) throw new RangeError('regression lengths differ');
  const empty = {n_obs: x.length, beta: null, intercept: null, correlation: null, r_squared: null};
  if (x.length < 3) return empty;
  const vx = variance(x), vy = variance(y);
  if (vx <= 1e-24) return empty;
  const mx = mean(x), my = mean(y);
  const cov = sum(x.map((v, i) => (v - mx) * (y[i] - my))) / (x.length - 1);
  const beta = cov / vx, corr = vy > 1e-24 ? Math.max(-1, Math.min(1, cov / Math.sqrt(vx * vy))) : null;
  return {...empty, beta, intercept: mean(y) - beta * mean(x), correlation: corr,
    r_squared: corr === null ? null : corr * corr};
}
export function summarizeReturns(simple, {confidence = 0.95, rfAnn = 0, periods = 252} = {}) {
  vector(simple, 'simple returns', 0); finite(confidence); finite(rfAnn); finite(periods);
  if (confidence <= 0 || confidence >= 1 || rfAnn <= -1 || periods <= 0) throw new RangeError('invalid risk settings');
  const n = simple.length, curve = [1];
  for (const r of simple) {
    if (curve.at(-1) <= 0) throw new RangeError('returns must stop at insolvency');
    curve.push(finite(curve.at(-1) * (1 + r), 'equity index'));
  }
  let peak = 1, peakIndex = 0, maxDD = 0, troughIndex = 0, ddPeakIndex = 0;
  curve.forEach((v, i) => {
    if (v > peak) { peak = v; peakIndex = i; }
    const dd = 1 - v / peak;
    if (dd > maxDD) { maxDD = dd; troughIndex = i; ddPeakIndex = peakIndex; }
  });
  const recovery = maxDD > 0 ? curve.findIndex((v, i) => i > troughIndex && v >= curve[ddPeakIndex]) : null;
  const sd = n >= 2 ? Math.sqrt(variance(simple)) : null;
  const [var1, cvar1] = n ? histVarCvar(simple, confidence) : [null, null];
  const dailyRF = Math.expm1(Math.log1p(rfAnn) / periods);
  return {n_obs: n, total_return: n ? curve.at(-1) - 1 : null,
    mean_daily_return: n ? mean(simple) : null, daily_volatility: sd,
    annualized_volatility: sd === null ? null : sd * Math.sqrt(periods),
    cagr: n >= periods && curve.at(-1) > 0 ? Math.expm1(Math.log(curve.at(-1)) * periods / n) : null,
    sharpe_arithmetic: n >= 2 && sd > 1e-12 ? (mean(simple) - dailyRF) / sd * Math.sqrt(periods) : null,
    max_drawdown: n ? maxDD : null, drawdown_peak_index: ddPeakIndex, drawdown_trough_index: troughIndex,
    recovery_bars: maxDD > 0 && recovery !== -1 ? recovery - ddPeakIndex : null,
    recovered: maxDD > 0 ? recovery !== -1 : null,
    var_1bar: var1, cvar_1bar: cvar1, confidence,
    historical_tail_count: n ? simple.filter(r => r <= quantile(simple, 1 - confidence)).length : 0,
    win_day_fraction: n ? simple.filter(r => r > 0).length / n : null,
    worst_bar: n ? Math.min(...simple) : null, best_bar: n ? Math.max(...simple) : null};
}

/** Circular moving-block percentile bootstrap of mean return, not a p-value.
 * Fixed seed: reproducible and pure. Preserves dependence WITHIN each block.
 * Does not repair ex-post selection, structural breaks, or multiple testing.
 */
export function blockBootstrapMean(simple, {blockLength = 5, replications = 500, seed = 1729} = {}) {
  vector(simple, 'simple returns', 0);
  if (!Number.isInteger(blockLength) || blockLength < 1 || !Number.isInteger(replications) || replications < 100 || replications > 5000 || !Number.isInteger(seed))
    throw new RangeError('invalid bootstrap settings');
  if (simple.length < Math.max(40, blockLength * 4)) return {status: 'insufficient_observations', lower: null, upper: null};
  let state = seed >>> 0;
  const random = () => { state = (Math.imul(1664525, state) + 1013904223) >>> 0; return state / 4294967296; };
  const samples = [];
  for (let b = 0; b < replications; b++) {
    let total = 0, count = 0;
    while (count < simple.length) {
      const start = Math.floor(random() * simple.length);
      for (let k = 0; k < blockLength && count < simple.length; k++, count++) total += simple[(start + k) % simple.length];
    }
    samples.push(total / simple.length);
  }
  return {status: 'exploratory', method: 'circular_moving_block_percentile', statistic: 'mean_daily_return',
    confidence: 0.95, lower: quantile(samples, 0.025), upper: quantile(samples, 0.975),
    block_length: blockLength, replications, seed, multiple_testing_adjusted: false};
}

export function rollingHistoricalVar(dates, simple, {window = 60, confidence = 0.95} = {}) {
  vector(simple, 'simple returns', 0);
  if (!Number.isInteger(window) || window < 2 || dates.length !== simple.length) throw new RangeError('invalid rolling window');
  if (!(confidence > 0 && confidence < 1)) throw new RangeError('invalid confidence');
  const rows = simple.map((r, i) => {
    const prior = simple.slice(Math.max(0, i - window), i);
    const [v, cv] = prior.length === window ? histVarCvar(prior, confidence) : [null, null];
    return {date: dates[i], var_1bar: v, cvar_1bar: cv, observed_loss: -r,
      breach: v === null ? null : -r > v, estimation_end: i > 0 ? dates[i - 1] : null,
      n_estimation: prior.length};
  });
  const evaluated = rows.filter(r => r.breach !== null);
  return {method: 'prior_realized_strategy_returns_not_current_holdings_forecast', window, confidence, rows,
    n_evaluated: evaluated.length, n_breaches: evaluated.filter(r => r.breach).length,
    breach_fraction: evaluated.length ? evaluated.filter(r => r.breach).length / evaluated.length : null,
    target_exceedance_fraction: 1 - confidence};
}

/** Portfolio Lab browser engine v1. Pure ESM; no I/O, storage, clocks, or DOM.
 * See README.md for the required resolved/valued input boundary.
 */
import {finite, vector, matrix, sum, ewmaCov, ledoitWolfCov, corrFromCov,
  hierarchicalRiskParity, riskContribution, portfolioReturns, annReturn,
  annVol, sharpe, histVarCvar, parametricVar} from './math.mjs';
export * from './math.mjs';

const DAY = 86400000;
function dateValue(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new TypeError('date must be YYYY-MM-DD');
  const t = Date.parse(s + 'T00:00:00Z');
  if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== s) throw new RangeError('invalid date');
  return t;
}
function validateDates(dates, n) {
  if (!Array.isArray(dates) || dates.length !== n) throw new RangeError('date length mismatch');
  let last = -Infinity;
  for (const d of dates) {
    const t = dateValue(d);
    if (t <= last || [0, 6].includes(new Date(t).getUTCDay())) throw new RangeError('dates must be unique, increasing weekdays');
    last = t;
  }
}
function currency(s) {
  if (!['KRW', 'USD'].includes(s)) throw new RangeError('baseCurrency must be KRW or USD');
  return s;
}
function weeklyReturns(dates, r) {
  const byFriday = new Map();
  dates.forEach((d, i) => {
    const t = dateValue(d), day = new Date(t).getUTCDay(), friday = t + ((5 - day + 7) % 7) * DAY;
    byFriday.set(friday, (byFriday.get(friday) ?? 0) + r[i]);
  });
  const first = Math.min(...byFriday.keys()), last = Math.max(...byFriday.keys()), out = [];
  // pandas resample('W-FRI').sum() includes empty intervening weeks as zero.
  for (let t = first; t <= last; t += 7 * DAY) out.push(byFriday.get(t) ?? 0);
  return out;
}

/** Numerical entry point for already-aligned BASE-CURRENCY LOG returns.
 * weights are signed fractions of NAV, never normalized by gross exposure.
 */
export function analyzeRisk({dates, logReturns, weights, riskFreeRateAnn = 0.03, netAssetValue = null, baseCurrency = 'KRW'}) {
  matrix(logReturns); validateDates(dates, logReturns.length); currency(baseCurrency);
  if (netAssetValue !== null && finite(netAssetValue) <= 0) throw new RangeError('NAV must be positive');
  const pr = portfolioReturns(logReturns, weights), short = pr.slice(-252);
  const long = weeklyReturns(dates, pr).slice(-260), longUsed = long.length > 3 ? long : pr;
  const longPeriods = long.length > 3 ? 52 : 252;
  const covarianceShort = ewmaCov(logReturns.slice(-252)), lw = ledoitWolfCov(logReturns);
  const [var1, cvar1] = histVarCvar(short.map(Math.expm1));
  const [varWeek, cvarWeek] = histVarCvar(long.map(Math.expm1));
  const vol = annVol(short), var10 = parametricVar(vol, 0.95, 10);
  const money = x => netAssetValue === null ? null : finite(x * netAssetValue);
  return {
    base_currency: baseCurrency,
    performance: {
      ann_return_short: annReturn(short), ann_return_long: annReturn(longUsed, longPeriods),
      ann_volatility_short: vol, ann_volatility_long: annVol(longUsed, longPeriods),
      sharpe_short: sharpe(short, riskFreeRateAnn), sharpe_long: sharpe(longUsed, riskFreeRateAnn, longPeriods),
      risk_free_rate_ann: riskFreeRateAnn,
      horizon_returns: Object.fromEntries(Object.entries({'1M': 21, '3M': 63, '1Y': 252})
        .map(([key, n]) => [key, pr.length >= n ? Math.expm1(sum(pr.slice(-n))) : null])),
    },
    risk: {
      short: {method: 'historical_1d + parametric_10d', lookback: `${short.length}d`,
        var_1d_95: var1, cvar_1d_95: cvar1, var_10d_95: var10,
        var_10d_95_of_nav: var10, var_10d_95_hist_scaled: var1 * Math.sqrt(10),
        var_1d_95_amount: money(var1), var_10d_95_amount: money(var10)},
      long: {method: 'historical_weekly', lookback: `${long.length}w`,
        var_1w_95: varWeek, cvar_1w_95: cvarWeek, var_1w_95_amount: money(varWeek)},
    },
    covariance_short: covarianceShort, covariance_long: lw.covariance,
    covariance_long_shrinkage: lw.shrinkage, covariance_long_mean_corr: lw.mean_corr,
    correlation_short: corrFromCov(covarianceShort),
    risk_contribution: riskContribution(weights, covarianceShort),
    hrp_weights: hierarchicalRiskParity(lw.covariance),
    portfolio_log_returns: pr,
    methodology: {version: 'portfolio-engine-v1', return_basis: 'constant_weight_simple_mix_then_log',
      weight_denominator: 'NAV', sharpe_numerator: 'historical_CAGR_minus_annual_rf',
      covariance_long: 'python_simplified_LW_constant_correlation',
      var_10d: 'zero_mean_normal_sqrt_time', long_var_horizon: '1_week',
      no_expected_return: true, transaction_costs: false, taxes: false, financing_costs: false},
    data_quality: {n_obs: dates.length, start: dates[0], end: dates.at(-1)},
  };
}

/** Convert supplied base-currency price rows, without dropping an asset or
 * filling a missing price. Caller owns dated FX, corporate-action policy and
 * holiday/staleness decisions. Actual leveraged ETF series must use factor 1.
 */
export function pricesToLogReturns({dates, prices, syntheticLeverage}) {
  const n = matrix(prices); validateDates(dates, prices.length);
  const factors = syntheticLeverage ?? Array(n).fill(1);
  vector(factors); if (factors.length !== n) throw new RangeError('leverage length mismatch');
  prices.forEach(row => row.forEach(p => { if (p <= 0) throw new RangeError('prices must be positive'); }));
  const logReturns = prices.slice(1).map((row, i) => row.map((px, j) => {
    const simple = factors[j] * (px / prices[i][j] - 1);
    if (simple <= -1) throw new RangeError('synthetic return <= -100%');
    return finite(Math.log1p(simple));
  }));
  return {dates: dates.slice(1), logReturns};
}

/** Bounded long-sleeve allocation. Caps and budget are fractions of NAV.
 * Infeasible caps are reported, never renormalized into a cap violation.
 */
export function allocateLongSleeve({covariance, weights, fixed, caps}) {
  vector(weights); if (matrix(covariance, 1) !== weights.length || covariance.length !== weights.length)
    throw new RangeError('covariance length mismatch');
  const n = weights.length;
  if (!Array.isArray(fixed) || fixed.length !== n || fixed.some(v => typeof v !== 'boolean')) throw new TypeError('fixed boolean mask required');
  if (caps !== undefined && (!Array.isArray(caps) || caps.length !== n)) throw new RangeError('cap length mismatch');
  const limits = weights.map((_, i) => caps?.[i] ?? null);
  limits.forEach(v => { if (v !== null && finite(v) < 0) throw new RangeError('negative cap'); });
  const ids = weights.map((_, i) => i).filter(i => !fixed[i] && weights[i] > 0);
  const budget = sum(ids.map(i => weights[i]));
  const result = weights.slice();
  if (!ids.length) return {weights: result, status: 'no_long_sleeve', breaches: []};
  const capacity = sum(ids.map(i => limits[i] ?? budget));
  if (capacity < budget - 1e-12) return {weights: null, status: 'infeasible_caps', breaches: ['caps_below_long_budget']};
  const hrp = hierarchicalRiskParity(ids.map(i => ids.map(j => covariance[i][j])));
  const reference = new Map(ids.map((i, k) => [i, hrp[k]]));
  let active = ids.slice(), remaining = budget;
  while (active.length) {
    const total = sum(active.map(i => reference.get(i)));
    const proposed = new Map(active.map(i => [i, remaining * (total > 0 ? reference.get(i) / total : 1 / active.length)]));
    const over = active.filter(i => limits[i] !== null && proposed.get(i) > limits[i] + 1e-12);
    if (!over.length) { active.forEach(i => { result[i] = proposed.get(i); }); break; }
    over.forEach(i => { result[i] = limits[i]; remaining -= limits[i]; });
    active = active.filter(i => !over.includes(i));
  }
  const breaches = weights.map((_, i) => i).filter(i => (fixed[i] || weights[i] < 0) && limits[i] !== null && Math.abs(weights[i]) > limits[i] + 1e-12);
  return {weights: result, status: breaches.length ? 'fixed_positions_exceed_caps' : 'ok', breaches};
}

/** Account-level adapter shared by manual and spreadsheet entry points.
 * positions are resolved and valued in base currency, ordered like logReturns.
 * Not a ticker resolver, workbook parser, quote client, or a report renderer.
 */
export function analyzePortfolio({positions, dates, logReturns, baseCurrency = 'KRW', netAssetValue = null,
  creditUsed = 0, riskFreeRateAnn = 0.03, caps}) {
  currency(baseCurrency); finite(creditUsed);
  if (creditUsed < 0 || !Array.isArray(positions) || !positions.length) throw new RangeError('invalid account');
  const seen = new Set();
  positions.forEach(p => {
    if (typeof p.id !== 'string' || !p.id || seen.has(p.id)) throw new TypeError('unique resolved instrument ids required');
    if (typeof p.currency !== 'string' || !/^[A-Z]{3}$/.test(p.currency) || typeof p.asset_class !== 'string')
      throw new TypeError('instrument currency/asset_class required');
    seen.add(p.id); finite(p.value, 'signed base-currency value');
  });
  if (matrix(logReturns) !== positions.length) throw new RangeError('position/return column mismatch');
  const signed = sum(positions.map(p => p.value)), hasShort = positions.some(p => p.value < 0);
  if (netAssetValue === null && (creditUsed > 0 || hasShort)) throw new RangeError('explicit NAV required for credit/short');
  const nav = netAssetValue === null ? signed : finite(netAssetValue);
  if (nav <= 0) throw new RangeError('NAV must be positive');
  const residual = nav - (signed - creditUsed), tolerance = Math.max(1e-8, nav * 1e-10);
  if ((hasShort || creditUsed > 0) && Math.abs(residual) > tolerance) throw new RangeError('signed values minus credit must equal NAV');
  if (!hasShort && creditUsed === 0 && residual < -tolerance) throw new RangeError('holdings exceed NAV without declared credit');
  const ps = positions.map(p => ({...p})), x = logReturns.map(row => row.slice());
  const engineCaps = caps === undefined ? undefined : caps.slice();
  if (engineCaps && engineCaps.length !== ps.length) throw new RangeError('cap length mismatch');
  if (!hasShort && creditUsed === 0 && residual > tolerance) {
    const baseIndex = ps.findIndex(p => p.asset_class === 'cash' && p.currency === baseCurrency);
    if (baseIndex >= 0) ps[baseIndex].value += residual;
    else {
      const id = '__residual_base_cash__';
      if (seen.has(id)) throw new RangeError('reserved residual id');
      ps.push({id, value: residual, currency: baseCurrency, asset_class: 'cash'});
      x.forEach(row => row.push(0)); engineCaps?.push(null);
    }
  }
  const fixed = ps.map(p => p.value < 0 || (p.asset_class === 'cash' && p.currency === baseCurrency));
  ps.forEach((p, i) => {
    if (p.asset_class === 'cash' && p.currency === baseCurrency && x.some(row => row[i] !== 0))
      throw new RangeError('base cash must have flat returns; interest-bearing products are not flat cash');
  });
  const weights = ps.map(p => p.value / nav), gross = sum(ps.map(p => Math.abs(p.value)));
  const result = analyzeRisk({dates, logReturns: x, weights, riskFreeRateAnn, netAssetValue: nav, baseCurrency});
  const allocation = allocateLongSleeve({covariance: result.covariance_long, weights, fixed, caps: engineCaps});
  const baseCash = sum(ps.filter(p => p.asset_class === 'cash' && p.currency === baseCurrency).map(p => Math.max(p.value, 0)));
  const foreignCash = sum(ps.filter(p => p.asset_class === 'cash' && p.currency !== baseCurrency).map(p => Math.abs(p.value)));
  // The account-facing API must not expose unconstrained all-asset HRP as a
  // competing target. Only advice.target_weights respects cash/short sleeves.
  const {hrp_weights: _unconstrained, ...riskResult} = result;
  return {...riskResult, schema_version: 'portfolio_engine_v1', asset_ids: ps.map(p => p.id),
    positions: ps.map((p, i) => ({...p, weight: weights[i]})),
    accounting: {net_asset_value: nav, gross_exposure: gross, gross_exposure_of_nav: gross / nav,
      signed_positions_value: sum(ps.map(p => p.value)), credit_used: creditUsed},
    cash_breakdown: {base_cash_value: baseCash, foreign_cash_value: foreignCash,
      base_cash_weight_of_nav: baseCash / nav, foreign_cash_weight_of_nav: foreignCash / nav},
    advice: {method: 'HRP_long_risky_sleeve', no_expected_return: true,
      current_weights: weights, target_weights: allocation.weights,
      delta_weights: allocation.weights?.map((w, i) => w - weights[i]) ?? null,
      allocation_status: allocation.status, constraint_breaches: allocation.breaches,
      fixed_mask: fixed, caps: engineCaps ?? null},
    data_quality: {...result.data_quality, residual_cash_added: Math.max(residual, 0)},
  };
}

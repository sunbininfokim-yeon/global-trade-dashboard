import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runScenario, compareScenarioVariants, summarizeReturns, regression, blockBootstrapMean, rollingHistoricalVar} from '../../New for anti/portfolio-engine/scenario.mjs';

function close(a, b, tol = 1e-10) { assert.ok(Number.isFinite(a) && Math.abs(a - b) < tol, `${a} != ${b}`); }
function weekdays(n) {
  const out = [];
  for (let i = 0; out.length < n; i++) {
    const d = new Date(Date.UTC(2024, 0, 1 + i));
    if (![0, 6].includes(d.getUTCDay())) out.push(d.toISOString().slice(0, 10));
  }
  return out;
}
const asset = (id, prices) => ({id, prices, baseCurrency: 'KRW', source: 'synthetic_test_only', priceBasis: 'adjusted_total_return'});
function input(a = [100, 110, 121], b = [100, 90, 81]) {
  return {dates: weekdays(a.length), assets: [asset('LONG_TEST', a), asset('SHORT_TEST', b)],
    strategy: {weights: [0.5, -0.5]}, risk: {window: 2}};
}

test('buy-and-hold tracks units, shorts and collateral; normalized NAV optional money', () => {
  const r = runScenario(input()).strategy;
  close(r.metrics.total_return, 0.2); // 0.5*(121/100-1) - 0.5*(81/100-1)
  close(r.curve[0].cash, 100); close(r.curve.at(-1).nav, 120);
  close(r.pnl_attribution[0].return_on_initial_nav, 0.105);
  close(r.pnl_attribution[1].return_on_initial_nav, 0.095);
  close(r.attribution_residual, 0);
  assert.equal(r.monetary_results, null);
  assert.equal(r.initial_capital, null);
  assert.equal(r.assessment.investment_decision, null);
  assert.ok(runScenario(input()).warnings.some(w => w.code === 'SHORT_AVAILABILITY_UNVERIFIED'));
});
test('capital scales amounts, never percentage performance', () => {
  const x = input(), a = runScenario(x).strategy;
  x.strategy.initialCapital = 10000000;
  const b = runScenario(x).strategy;
  close(a.metrics.total_return, b.metrics.total_return);
  close(b.monetary_results.pnl, 2000000, 1e-8);
  close(b.pnl_attribution[0].amount, 1050000, 1e-8);
});
test('daily vs buy-and-hold are economically distinct', () => {
  const x = input(); x.strategy.rebalance = 'daily';
  close(runScenario(x).strategy.metrics.total_return, 0.21);
  close(runScenario(input()).strategy.metrics.total_return, 0.2);
});
test('monthly rebalance executes at first observed close in the new month', () => {
  const x = input(); x.dates = ['2024-01-30', '2024-02-01', '2024-02-02'];
  x.strategy.rebalance = 'monthly';
  const r = runScenario(x).strategy;
  close(r.metrics.total_return, 0.21);
  assert.ok(r.trade_ledger.some(t => t.reason === 'rebalance' && t.date === '2024-02-01'));
});
test('selected period metrics exclude outside prices and do not use trailing252', () => {
  const x = input([1, 100, 110, 121, 10000], [10000, 100, 90, 81, 1]);
  x.startDate = x.dates[1]; x.endDate = x.dates[3];
  const r = runScenario(x);
  close(r.strategy.metrics.total_return, 0.2);
  assert.equal(r.strategy.metrics.n_obs, 2);
  close(r.relationship.series[0].metrics.total_return, 0.21);
});
test('relation only: no strategy/capital needed; flat correlations unavailable, not invented', () => {
  const x = input([100, 100, 100, 100], [100, 110, 105, 120]); delete x.strategy;
  const r = runScenario(x);
  assert.equal(r.strategy, null);
  assert.equal(r.relationship.correlation[0][1], null);
  close(r.relationship.correlation[1][1], 1);
});
test('known regression slopes, constant factor, difference factor rates below zero', () => {
  const r = regression([1, 2, 3, 4], [5, 8, 11, 14]);
  close(r.beta, 3); close(r.intercept, 2); close(r.r_squared, 1);
  assert.equal(regression([1, 1, 1], [2, 3, 4]).beta, null);
  const x = input([100, 101, 100, 104], [100, 100, 99, 98]); delete x.strategy;
  x.factors = [{id: 'RATE_TEST', values: [-1, -0.5, -0.6, 0], change: 'difference', unit: 'percentage_points', source: 'synthetic'}];
  const result = runScenario(x).relationship;
  assert.equal(result.series[2].metrics.return_metrics, null);
  close(result.series[2].metrics.total_change, 1);
  assert.equal(result.factor_exposures[0].factor_change, 'difference');
});
test('conditional signal executes NEXT close, holds explicit bars, no overlap', () => {
  const x = input([100, 100, 100, 200, 220, 242, 250], [100, 100, 100, 100, 100, 100, 100]);
  x.factors = [{id: 'FACTOR_TEST', values: [100, 100, 120, 120, 120, 120, 120]}];
  x.condition = {factorId: 'FACTOR_TEST', lookbackBars: 1, threshold: 0.1, holdingBars: 2};
  const r = runScenario(x).strategy;
  const trade = r.trade_ledger.find(t => t.reason === 'entry');
  assert.equal(trade.signal_date, x.dates[2]); assert.equal(trade.date, x.dates[3]);
  close(r.metrics.total_return, 0.105); // Must not profit from 100 -> 200 jump at fill.
  assert.equal(r.episodes.length, 1); assert.equal(r.episodes[0].exit, x.dates[5]);
});
test('changing future data cannot change an earlier signal/fill', () => {
  const x = input([100, 100, 100, 100, 101, 102, 103], [100, 100, 100, 100, 99, 98, 97]);
  x.factors = [{id: 'F', values: [100, 100, 120, 120, 120, 120, 120]}];
  x.condition = {factorId: 'F', lookbackBars: 1, threshold: 0.1, holdingBars: 2};
  const before = runScenario(x).strategy;
  x.factors[0].values[5] = 10000; x.assets[0].prices[5] = 400;
  const after = runScenario(x).strategy;
  assert.deepEqual(before.trade_ledger.filter(t => t.date <= x.dates[4]), after.trade_ledger.filter(t => t.date <= x.dates[4]));
});
test('generic AND/OR conditions support different factors, not hardcoded gas/stocks', () => {
  const x = input([100, 100, 100, 100, 110, 120], [100, 100, 100, 100, 100, 100]);
  x.factors = [{id: 'FX', values: [1, 1, 1.2, 1.2, 1.2, 1.2]},
    {id: 'YIELD', values: [-1, -1, 0, 0, 0, 0], change: 'difference'}];
  const leaves = [{factorId: 'FX', lookbackBars: 1, threshold: 0.1}, {factorId: 'YIELD', lookbackBars: 1, threshold: 0.5}];
  x.condition = {all: leaves, holdingBars: 1};
  assert.equal(runScenario(x).strategy.n_completed_episodes, 1);
  x.condition.all[1].threshold = 2;
  assert.equal(runScenario(x).strategy.episodes.length, 0);
  x.condition = {any: leaves, holdingBars: 1};
  assert.equal(runScenario(x).strategy.n_completed_episodes, 1);
});
test('pre-period warmup allows first period entry; final truncated holding is flagged', () => {
  const x = input([100, 100, 100, 100, 110, 120], [100, 100, 100, 100, 100, 100]);
  x.factors = [{id: 'F', values: [100, 100, 120, 120, 120, 120]}];
  x.condition = {factorId: 'F', lookbackBars: 1, threshold: 0.1, holdingBars: 20};
  x.startDate = x.dates[3];
  const r = runScenario(x).strategy;
  assert.equal(r.episodes[0].entry, x.dates[3]);
  assert.equal(r.episodes[0].completed_holding, false); assert.equal(r.n_completed_episodes, 0);
});
test('rolling VaR excludes current return, counts breaches against prior estimate', () => {
  const d = weekdays(4), before = rollingHistoricalVar(d, [-0.01, 0.01, -0.2, 0], {window: 2});
  const after = rollingHistoricalVar(d, [-0.01, 0.01, -0.8, 0], {window: 2});
  assert.equal(before.rows[0].var_1bar, null);
  close(before.rows[2].var_1bar, 0.009);
  close(before.rows[2].var_1bar, after.rows[2].var_1bar);
  assert.equal(before.rows[2].estimation_end, d[1]); assert.equal(before.rows[2].breach, true);
});
test('period metrics MDD, recovery, linear VaR, undefined Sharpe', () => {
  const m = summarizeReturns([0.1, -0.2, 0.3]);
  close(m.total_return, 0.144); close(m.max_drawdown, 0.2); close(m.var_1bar, 0.17);
  close(m.cvar_1bar, 0.2); assert.equal(m.recovery_bars, 2); assert.equal(m.recovered, true);
  assert.equal(summarizeReturns([0, 0]).sharpe_arithmetic, null);
  assert.equal(summarizeReturns([0.01, 0.02]).cagr, null);
});
test('insolvency stops rather than clipping losses or continuing negative NAV', () => {
  const x = input([100, 250, 300, 100], [100, 100, 100, 100]); x.strategy.weights = [-1, 0];
  const r = runScenario(x);
  assert.equal(r.strategy.status, 'insolvent');
  close(r.strategy.metrics.total_return, -1.5); assert.equal(r.strategy.curve.length, 2);
  assert.equal(r.strategy.assessment.status, 'not_supported_in_period');
  close(r.strategy.attribution_residual, 0);
});
test('known unavailable short and bad data fail closed, not dropped or zero-filled', () => {
  const x = input(); x.assets[1].shortable = false;
  assert.throws(() => runScenario(x), /short unavailable/);
  delete x.assets[1].shortable; x.assets[1].prices[1] = null;
  assert.throws(() => runScenario(x), /finite/);
  x.assets[1].prices[1] = 90; x.assets[0].baseCurrency = 'USD';
  assert.throws(() => runScenario(x), /base currency/);
  assert.throws(() => runScenario({...input(), endDate: '2030-01-01'}), /outside/);
});
test('bootstrap deterministic, not a significance or multiple-testing claim', () => {
  const r = Array.from({length: 100}, (_, i) => 0.002 + Math.sin(i) * 0.01);
  assert.deepEqual(blockBootstrapMean(r), blockBootstrapMean(r));
  assert.equal(blockBootstrapMean(r).multiple_testing_adjusted, false);
  assert.equal(blockBootstrapMean(r.slice(0, 10)).status, 'insufficient_observations');
  const negative = blockBootstrapMean(Array(100).fill(-0.01));
  close(negative.lower, -0.01); close(negative.upper, -0.01);
});
test('benchmark, holdout and conflicting factor sign are separate evidence checks', () => {
  const n = 150, dates = weekdays(n), a = Array.from({length: n}, (_, i) => 100 * 1.003 ** i), b = Array(n).fill(100);
  const x = input(a, b); x.dates = dates;
  x.benchmark = asset('BM_TEST', b); x.holdoutStart = dates[60];
  let result = runScenario(x).strategy;
  assert.equal(result.assessment.status, 'historical_support_only');
  assert.equal(result.assessment.execution_validated, false);
  assert.equal(result.split.selection_independence_verified, false);
  x.factors = [{id: 'F', values: a}];
  x.hypotheses = [{assetId: 'LONG_TEST', factorId: 'F', expectedSign: -1}];
  result = runScenario(x).strategy;
  assert.notEqual(result.assessment.status, 'historical_support_only');
});
test('no mutation / no network or storage in the new module graph', () => {
  const x = input(), saved = structuredClone(x);
  const freeze = o => { Object.values(o).forEach(v => {if (v && typeof v === 'object') freeze(v);}); Object.freeze(o); };
  freeze(x); runScenario(x); assert.deepEqual(x, saved);
  for (const file of ['scenario.mjs', 'scenario-stats.mjs']) {
    const src = readFileSync(new URL(`../../New for anti/portfolio-engine/${file}`, import.meta.url), 'utf8');
    assert.doesNotMatch(src, /\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage|indexedDB|supabase|console)\s*[.(]/);
  }
});
test('explicit sensitivity variants retain all results, never choose a winning strategy', () => {
  const base = input();
  const result = compareScenarioVariants(base, [
    {id: 'hold', overrides: {strategy: {weights: [0.5, -0.5], rebalance: 'buy_and_hold'}}},
    {id: 'daily', overrides: {strategy: {weights: [0.5, -0.5], rebalance: 'daily'}}},
  ]);
  assert.equal(result.automatic_selection, false);
  assert.equal(result.multiple_testing_adjusted, false);
  close(result.results[0].result.strategy.metrics.total_return, 0.2);
  close(result.results[1].result.strategy.metrics.total_return, 0.21);
  assert.equal(base.strategy.rebalance, undefined);
});
test('validate consumed factor values even when a redundant prices array exists', () => {
  const x = input();
  x.factors = [{id: 'F', prices: [1, 2, 3], values: [1, null, 3]}];
  assert.throws(() => runScenario(x), /finite/);
  x.factors[0].values = [1, 2];
  assert.throws(() => runScenario(x), /observations/);
});
test('standalone statistics cannot resurrect an insolvent strategy', () => {
  assert.throws(() => summarizeReturns([-1.5, -2]), /insolvency/);
  assert.throws(() => summarizeReturns([-1, 0.1]), /insolvency/);
  close(summarizeReturns([0.1, -1.5]).total_return, -1.55);
});
test('benchmark metadata warnings and episode independence remain explicit', () => {
  const x = input();
  x.benchmark = {id: 'BM', prices: [100, 101, 102], baseCurrency: 'KRW'};
  const r = runScenario(x);
  assert.ok(r.warnings.some(w => w.code === 'CORPORATE_ACTIONS_UNVERIFIED'));
  assert.ok(r.warnings.some(w => w.code === 'SOURCE_UNSPECIFIED'));
  assert.equal(r.strategy.assessment.episode_independence_verified, false);
  assert.equal(r.strategy.assessment.checks.enough_completed_episodes, null);
});

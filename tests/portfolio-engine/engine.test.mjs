import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import * as engine from '../../New for anti/portfolio-engine/index.mjs';

const fixture = JSON.parse(readFileSync(new URL('./golden/numerical.json', import.meta.url)));
function close(got, expected, path = '', abs = 1e-11, rel = 1e-9) {
  if (typeof expected === 'number') {
    assert.ok(Number.isFinite(got), `${path} non-finite: ${got}`);
    assert.ok(Math.abs(got - expected) <= Math.max(abs, rel * Math.abs(expected)), `${path}: ${got} != ${expected}`);
  } else if (Array.isArray(expected)) {
    assert.equal(got.length, expected.length, path);
    expected.forEach((v, i) => close(got[i], v, `${path}[${i}]`, abs, rel));
  } else if (expected && typeof expected === 'object') {
    Object.entries(expected).forEach(([k, v]) => close(got[k], v, `${path}.${k}`, abs, rel));
  } else assert.equal(got, expected, path);
}
function parity(c) {
  const got = engine.analyzeRisk(c.input), e = c.expected;
  close(engine.sampleCov(c.input.logReturns), e.sample_covariance, 'sample');
  close(got.covariance_short, e.covariance_short, 'ewma');
  close(got.covariance_long, e.covariance_long, 'LW');
  close(got.covariance_long_shrinkage, e.shrinkage, 'shrinkage');
  close(got.covariance_long_mean_corr, e.mean_corr, 'mean_corr');
  close(got.hrp_weights, e.hrp_weights, 'HRP');
  close(got.risk_contribution, e.risk_contribution, 'RC');
  close(got.performance, e.performance, 'performance');
  close(got.portfolio_log_returns, e.portfolio_log_returns, 'portfolio returns');
  for (const key of ['var_1d_95', 'cvar_1d_95', 'var_10d_95', 'var_10d_95_hist_scaled'])
    close(got.risk.short[key], e.risk.short[key], key);
  close(got.risk.short.var_1d_95_amount, e.risk.short.var_1d_95_krw);
  close(got.risk.short.var_10d_95_amount, e.risk.short.var_10d_95_krw);
  close(got.risk.long.var_1w_95, e.risk.long.var_1m_95, 'weekly VaR (corrected name)');
  close(got.risk.long.cvar_1w_95, e.risk.long.cvar_1m_95, 'weekly CVaR (corrected name)');
  const clusters = engine.hierarchicalClusters(engine.corrFromCov(e.covariance_long));
  assert.deepEqual(clusters.order, e.order);
  assert.deepEqual(clusters.merges, e.merges);
  return got;
}
for (const c of fixture) test(`Python numerical golden: ${c.name}`, () => parity(c));

test('fresh Python oracle matches checked-in fixtures (explicit opt-in, offline)', {skip: !process.env.PORTFOLIO_PYTHON}, () => {
  const run = spawnSync(process.env.PORTFOLIO_PYTHON, [fileURLToPath(new URL('./python_reference.py', import.meta.url))],
    {encoding: 'utf8', maxBuffer: 8e6, env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
  assert.equal(run.status, 0, run.stderr);
  const fresh = JSON.parse(run.stdout);
  close(fresh, fixture, 'oracle');
  fresh.forEach(parity);
});

function originalGoldenMetrics(got) {
  return {horizon_1y: got.performance.horizon_returns['1Y'], sharpe_short: got.performance.sharpe_short,
    ann_vol_short: got.performance.ann_volatility_short, ann_return_short: got.performance.ann_return_short};
}
const originalGolden = JSON.parse(readFileSync(new URL('../../New for anti/scripts/금융_재무분석/tests/golden/user_balanced_metrics.json', import.meta.url)));
function assertOriginalGolden(got) {
  for (const [key, value] of Object.entries(originalGoldenMetrics(got))) {
    assert.equal(typeof originalGolden[key], 'number', `${key} missing from original golden`);
    close(value, originalGolden[key], `original gross golden ${key}`);
  }
}
test('original golden reproduced offline on its LEGACY GROSS basis; NAV baseline kept separate', () => {
  const f = JSON.parse(readFileSync(new URL('./golden/legacy-snapshot-input.json', import.meta.url)));
  assertOriginalGolden(engine.analyzeRisk({...f, weights: f.legacyGrossWeights}));
  const nav = engine.analyzeRisk({...f, weights: f.navWeights});
  close(nav.performance, f.expectedNavShort);
  assert.ok(Math.abs(nav.performance.ann_return_short - originalGolden.ann_return_short) > 0.05,
    'NAV must not be silently renormalized into old gross-based golden');
});

test('current Python + full local cache parity, plus old gross golden provenance', {skip: !process.env.PORTFOLIO_CACHE}, () => {
  assert.ok(process.env.PORTFOLIO_PYTHON, 'PORTFOLIO_PYTHON required with PORTFOLIO_CACHE');
  const run = spawnSync(process.env.PORTFOLIO_PYTHON,
    [fileURLToPath(new URL('./python_reference.py', import.meta.url)), '--cache', process.env.PORTFOLIO_CACHE],
    {encoding: 'utf8', maxBuffer: 8e6, env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}});
  assert.equal(run.status, 0, run.stderr);
  const [c] = JSON.parse(run.stdout), got = parity(c);
  assertOriginalGolden(parity(c.legacy_gross_reference));
  const metrics = originalGoldenMetrics(got);
  console.log('Existing sample parity:', JSON.stringify({observations: c.input.dates.length,
    start: c.input.dates[0], end: c.input.dates.at(-1), metrics, cache_sha256: c.cache_sha256}));
});

const dates = ['2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09', '2025-01-10'];
const returns = [[0.01, -0.005], [-0.02, 0.01], [0.03, -0.02], [0, 0.01], [-0.01, 0.01]];
const stock = (id, value, currency = 'KRW') => ({id, value, currency, asset_class: 'equity'});
const cash = (id, value, currency = 'KRW') => ({id, value, currency, asset_class: 'cash'});
test('NAV/gross preserve 130% credit exposure without normalization', () => {
  const r = engine.analyzePortfolio({positions: [stock('a', 100), stock('b', 30)], netAssetValue: 100,
    creditUsed: 30, dates, logReturns: returns});
  assert.equal(r.accounting.gross_exposure_of_nav, 1.3);
  close(r.positions.map(p => p.weight), [1, 0.3]);
  close(r.risk.short.var_10d_95_amount, r.risk.short.var_10d_95 * 100);
  close(engine.sum(r.advice.target_weights), 1.3);
});
test('short collateral preserved; fixed-only portfolio is not replaced by long HRP', () => {
  const r = engine.analyzePortfolio({positions: [cash('cash', 120), stock('short', -20)], netAssetValue: 100,
    dates, logReturns: returns.map(row => [0, row[1]])});
  close(r.accounting.gross_exposure_of_nav, 1.4);
  assert.deepEqual(r.advice.target_weights, [1.2, -0.2]);
  assert.equal(r.advice.allocation_status, 'no_long_sleeve');
});
test('USD base cash fixed regardless of legacy fx_as_asset flag; HKD cash is foreign', () => {
  const r = engine.analyzePortfolio({positions: [{...cash('usd', 20, 'USD'), fx_as_asset: true}, cash('hkd', 80, 'HKD')],
    dates, logReturns: returns.map(row => [0, row[1]]), baseCurrency: 'USD'});
  assert.equal(r.cash_breakdown.base_cash_weight_of_nav, 0.2);
  assert.equal(r.cash_breakdown.foreign_cash_weight_of_nav, 0.8);
  assert.deepEqual(r.advice.fixed_mask, [true, false]);
  assert.ok(!Object.keys(r.risk.short).some(k => k.endsWith('_krw')));
});
test('residual base cash appended, not silently lost; zero-risk cash-only finite', () => {
  const r = engine.analyzePortfolio({positions: [stock('a', 80)], netAssetValue: 100,
    dates, logReturns: returns.map(row => [row[0]])});
  assert.equal(r.cash_breakdown.base_cash_value, 20);
  assert.deepEqual(r.advice.fixed_mask, [false, true]);
  const flat = engine.analyzePortfolio({positions: [cash('cash', 100)], dates, logReturns: dates.map(() => [0])});
  assert.equal(flat.performance.ann_volatility_short, 0);
  assert.equal(flat.risk.short.var_10d_95, 0);
  assert.deepEqual(flat.advice.target_weights, [1]);
});
test('reject ledger mismatch, missing NAV for debt, duplicate/unresolved ids', () => {
  const input = {positions: [stock('a', 100), stock('b', 30)], dates, logReturns: returns};
  assert.throws(() => engine.analyzePortfolio({...input, creditUsed: 30}), /explicit NAV/);
  assert.throws(() => engine.analyzePortfolio({...input, creditUsed: 30, netAssetValue: 120}), /equal NAV/);
  assert.throws(() => engine.analyzePortfolio({...input, netAssetValue: 100}), /exceed NAV/);
  assert.throws(() => engine.analyzePortfolio({...input, positions: [stock('a', 50), stock('a', 50)]}), /unique/);
});
test('caps expressed on NAV, fixed budget preserved, infeasibility explicit', () => {
  const common = {covariance: [[1, 0, 0], [0, 4, 0], [0, 0, 0]], weights: [0.4, 0.4, 0.2], fixed: [false, false, true]};
  const capped = engine.allocateLongSleeve({...common, caps: [0.5, 0.5, null]});
  close(capped.weights, [0.5, 0.3, 0.2]);
  const bad = engine.allocateLongSleeve({...common, caps: [0.15, 0.15, null]});
  assert.equal(bad.status, 'infeasible_caps'); assert.equal(bad.weights, null);
  assert.deepEqual(engine.hierarchicalRiskParity([[0, 0], [0, 0]]), [0.5, 0.5]);
});
test('price simple leverage, actual leveraged ETF is not doubled again', () => {
  const converted = engine.pricesToLogReturns({dates: dates.slice(0, 3), prices: [[100, 100], [110, 120], [99, 96]], syntheticLeverage: [2, 1]});
  close(converted.logReturns, [[Math.log1p(0.2), Math.log1p(0.2)], [Math.log1p(-0.2), Math.log1p(-0.2)]]);
});
test('missing/nonfinite/ragged input, insufficient history, weekends rejected; no ffill/drop', () => {
  assert.throws(() => engine.sampleCov([Array(2), [0, 0]]), /finite/);
  assert.throws(() => engine.analyzeRisk({dates, logReturns: [[NaN]], weights: [1]}));
  assert.throws(() => engine.analyzeRisk({dates: dates.slice(0, 1), logReturns: [[0]], weights: [1]}));
  assert.throws(() => engine.sampleCov([[1, 2], [1]]), /ragged/);
  assert.throws(() => engine.pricesToLogReturns({dates: dates.slice(0, 2), prices: [[100], [null]]}));
  assert.throws(() => engine.pricesToLogReturns({dates: ['2025-01-04', '2025-01-06'], prices: [[100], [100]]}), /weekdays/);
  assert.throws(() => engine.pricesToLogReturns({dates: ['2025-02-30', '2025-03-03'], prices: [[100], [100]]}), /invalid date/);
});
test('20-asset, five-year matrix remains finite and normalized', () => {
  const x = Array.from({length: 1260}, (_, t) => Array.from({length: 20}, (_, j) =>
    0.01 * Math.sin(t * 0.21 + j * 0.6) + 0.005 * Math.cos(t * 0.07 * (j + 1))));
  const lw = engine.ledoitWolfCov(x), w = engine.hierarchicalRiskParity(lw.covariance);
  w.forEach(v => assert.ok(Number.isFinite(v) && v >= 0));
  close(engine.sum(w), 1);
  close(engine.sum(engine.riskContribution(w, lw.covariance)), 1);
});
test('insolvency is an explicit error rather than a clipped finite result', () => {
  assert.throws(() => engine.portfolioReturns([[Math.log(0.4)], [0]], [2]), /-100%/);
  assert.throws(() => engine.pricesToLogReturns({dates: dates.slice(0, 2), prices: [[100], [40]], syntheticLeverage: [2]}), /-100%/);
});
test('quantile interpolation, inclusive tail, flat Sharpe and supported VaR confidences', () => {
  close(engine.histVarCvar([-0.2, -0.1, 0, 0.1]), [0.185, 0.2]);
  close(engine.histVarCvar([0.1, 0.2]), [0, 0]);
  assert.equal(engine.sharpe([0, 0], 0.03), 0);
  close(engine.parametricVar(Math.sqrt(252), 0.99, 1), 2.3263478740408408);
  assert.throws(() => engine.parametricVar(0.2, 0.9), /invalid/);
});
test('equal-distance cluster ties use sorted Python IDs', () => {
  assert.deepEqual(engine.hierarchicalClusters([[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
    {order: [2, 0, 1], merges: [[0, 1, 3], [2, 3, 4]]});
});
test('no mutation; no network, storage, telemetry, or external imports in module graph', () => {
  const input = structuredClone(fixture[0].input), before = structuredClone(input);
  const freeze = o => { Object.values(o).forEach(v => { if (v && typeof v === 'object') freeze(v); }); Object.freeze(o); };
  freeze(input); engine.analyzeRisk(input); assert.deepEqual(input, before);
  for (const name of ['index.mjs', 'math.mjs']) {
    const source = readFileSync(new URL(`../../New for anti/portfolio-engine/${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage|indexedDB|supabase|console)\s*[.(]/);
    assert.doesNotMatch(source, /(?:from\s*|import\s*\()['"](?:https?:|node:)/);
  }
});

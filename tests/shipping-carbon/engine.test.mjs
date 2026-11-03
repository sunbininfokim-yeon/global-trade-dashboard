// The browser port in shipping-carbon.js must reproduce tools/shipping_carbon
// (Python, Decimal) for every case below, field by field.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const engine = require(path.join(here, '../../New for anti/shipping-carbon.js'));

const CASES = [
  {},
  { price_shock: '10' },
  { price_shock: '-30', hedge_basis_shock: '-2.5' },
  { emissions_basis: 'scope_adjusted', emissions_tco2e: '100000' },
  { delivery_date: '2027-10-01' },
  { scope_confirmed: false },
  { gases_complete: false },
  { ship_hedge_delta: '90000' },
  { dealer_role: 'agency' },
  { dealer_lots: '35', future_bucket: '2027-12' },
  { dealer_lots: '50.5' },
  { future_price: '' },
  { future_price: '5', price_shock: '-10' },
  { price_mode: 'manual', manual_price: '72.4' },
  { price_mode: 'manual', manual_price: '' },
  { initial_margin: '250000' },
  { initial_margin: '250000', price_path: 'persistent', price_shock: '-15' },
  { initial_margin: '250000', future_delivery_date: '2027-10-05', replacement_price: '88' },
  { initial_margin: '250000', future_delivery_date: '2027-10-05' },
  { initial_margin: '250000', customer_payment_date: '2027-09-01', funding_rate_pct: '7.25' },
  { initial_margin: '250000', dealer_lots: '60' },
  { initial_margin: '250000', cash_buffer: '0', trade_fees: '12345.67' },
  { future_delivery_date: '2026-11-02' },
  { customer_payment_date: '2026-10-01' },
  { route_weight: '1.2' },
  { emissions_tco2e: 'abc' },
  { emissions_tco2e: '-5' },
  { fuel_actual: '88', pool_quote: '' },
  { available_eua: '500000' },
];

const reference = JSON.parse(execFileSync('python3', ['-I', path.join(here, 'python_reference.py')],
  { input: JSON.stringify(CASES), encoding: 'utf8' }));
const SNAP = engine.SYNTHETIC_SNAPSHOT;

function same(actual, expected, where) {
  if (expected === null || expected === undefined) return assert.equal(actual ?? null, null, where);
  if (typeof expected === 'string' && /^-?\d+(\.\d+)?$/.test(expected) && typeof actual === 'number') {
    const e = Number(expected);
    return assert.ok(Math.abs(actual - e) <= 1e-6 * Math.max(1, Math.abs(e)), `${where}: ${actual} != ${expected}`);
  }
  if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, `${where}.length`);
    return expected.forEach((v, i) => same(actual[i], v, `${where}[${i}]`));
  }
  if (typeof expected === 'object') {
    for (const key of Object.keys(expected)) same(actual[key], expected[key], `${where}.${key}`);
    return;
  }
  assert.equal(actual, expected, where);
}

CASES.forEach((changes, i) => {
  test(`case ${i}: ${JSON.stringify(changes)}`, () => {
    const p = { ...engine.defaults(SNAP), ...changes };
    const ref = reference[i];
    if (ref.error) {
      assert.throws(() => engine.calculate(p, SNAP), err => err.message === ref.error);
    } else {
      same(engine.calculate(p, SNAP), ref.ok, 'result');
    }
  });
});

test('defaults match the Python defaults', () => {
  const py = JSON.parse(execFileSync('python3', ['-I', '-c',
    `import sys,json;sys.path.insert(0,${JSON.stringify(path.join(here, '../../tools/shipping_carbon'))});` +
    `from engine import defaults;print(json.dumps(defaults({"as_of":"2026-11-01"})))`], { encoding: 'utf8' }));
  assert.deepEqual(engine.defaults({ as_of: '2026-11-01' }), py);
});

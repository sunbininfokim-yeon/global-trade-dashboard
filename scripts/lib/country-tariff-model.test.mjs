import { test } from 'node:test';
import assert from 'node:assert/strict';
import { example, simulate, ModelError } from '../../New for anti/policy-simulator/country-model.mjs';
const close = (a, b, tolerance = 1e-7) => assert.ok(Math.abs(a - b) < tolerance, `${a} != ${b}`);

test('unchanged tariffs reproduce a baseline with existing duties', () => {
  const input = example();
  input.rows[1].tariff_before = input.rows[1].tariff_after = 15;
  const r = simulate(input, false);
  close(r.market_price_change_pct, 0); close(r.duties_after, r.duties_before);
  for (const row of r.rows) { close(row.volume_change_pct, 0); close(row.revenue_change_pct, 0); close(row.share_change_pp, 0); }
});
test('foreign-only common tariff shock matches the independent closed-form solution', () => {
  const input = example(); input.eta = -1.3;
  input.rows = [input.rows[1], input.rows[2]];
  for (const row of input.rows) Object.assign(row, { tariff_before: 10, tariff_after: 30, supply_elasticity: 3 });
  const r = simulate(input, false), price = (1.3 / 1.1) ** (3 / 4.3);
  close(r.market_price_change_pct, (price - 1) * 100);
  for (const row of r.rows) { close(row.volume_change_pct, (price ** -1.3 - 1) * 100); close(row.share_change_pp, 0); }
});
test('official USITC workbook cached benchmark agrees within 0.01 percentage points', () => {
  // Unmodified 2019 ces_tariff_model.xlsx, Model!DKL19:DKL24.
  // Reference cached outputs, not a new Excel-engine recalculation.
  const input = example(); input.sigma = 6;
  input.rows.forEach((row, i) => Object.assign(row, { expenditure: 100, supply_elasticity: [1, 10, 10][i] }));
  const r = simulate(input, false);
  const prices = [1.0502955690539701, 1.174608147092419, 1.021701049249381];
  const quantities = [105.02955690539707, 53.67655030022116, 123.9468072970644];
  r.rows.forEach((row, i) => { close(row.price_change_pct, (prices[i] - 1) * 100, 0.01); close(row.volume_change_pct, quantities[i] - 100, 0.01); });
});
test('tariff increase reduces affected supply; other sources gain; endogenous exporter absorption', () => {
  const r = simulate(example());
  assert.ok(r.rows[1].volume_change_pct < 0); assert.ok(r.rows[1].producer_price_change_pct < 0);
  assert.ok(r.rows[0].volume_change_pct > 0); assert.ok(r.rows[2].volume_change_pct > 0);
  close(r.rows[1].volume_change_pct, -27.989391049707947);
  assert.ok(r.sensitivity[0].volume_change_pct > r.sensitivity[2].volume_change_pct);
});
test('spending identity, shares and the tariff-exclusive tax base hold', () => {
  const input = example(); input.eta = -1.5; input.rows[1].tariff_before = 10;
  const r = simulate(input, false);
  close(r.checks.expenditure_identity_error, 0); close(r.checks.shares_sum_pct, 100);
  for (let i = 0; i < r.rows.length; i++) {
    const row = r.rows[i], rate = input.rows[i].tariff_after / 100;
    close(row.duties_after, row.spending_after * rate / (1 + rate));
    close(row.share_after_pct, 100 * row.spending_after / r.spending_after);
  }
});
test('Cobb-Douglas limit is continuous; fixed output and a large shock converge', () => {
  const input = example(); input.sigma = 1;
  const a = simulate(input, false); input.sigma = 1.00001;
  close(a.market_price_change_pct, simulate(input, false).market_price_change_pct, 0.001);
  input.rows[1].tariff_after = 150; input.rows[0].supply_elasticity = 0;
  const b = simulate(input, false); close(b.rows[0].volume_change_pct, 0);
  assert.ok(b.checks.max_log_residual < 1e-8);
});
test('country permutation and monetary scaling preserve ratios; eight suppliers work', () => {
  const input = example(), original = simulate(input, false);
  input.rows.reverse(); input.rows.forEach(row => row.expenditure *= 100);
  const scaled = simulate(input, false);
  for (const row of scaled.rows) {
    const ref = original.rows.find(x => x.country === row.country);
    close(row.volume_change_pct, ref.volume_change_pct); close(row.revenue_after, ref.revenue_after * 100);
  }
  const many = example();
  for (const country of ['CHN', 'JPN', 'CAN', 'MEX', 'VNM']) many.rows.push({ country, expenditure: 5, tariff_before: 10, tariff_after: 30, supply_elasticity: 3 });
  assert.equal(simulate(many).rows.length, 8);
});
test('invalid, missing, duplicate, domestic-tariff and zero purchase inputs are rejected', () => {
  for (const field of ['sigma', 'eta']) for (const value of [NaN, Infinity, null, '', false, ' ']) {
    const input = example(); input[field] = value; assert.throws(() => simulate(input), ModelError);
  }
  for (const value of [0, -1, '', null, Infinity]) {
    const input = example(); input.rows[1].expenditure = value; assert.throws(() => simulate(input), ModelError);
  }
  const duplicate = example(); duplicate.rows[2].country = 'KOR'; assert.throws(() => simulate(duplicate), /중복/);
  const domestic = example(); domestic.rows[0].tariff_after = 10; assert.throws(() => simulate(domestic), /국내/);
  const focus = example(); focus.focus = 'CHN'; assert.throws(() => simulate(focus), /관심국가/);
});
test('tariff reduction reverses direction and inputs are not mutated', () => {
  const input = example(); input.rows[1].tariff_before = 25; input.rows[1].tariff_after = 0;
  const copy = structuredClone(input), r = simulate(input);
  assert.ok(r.rows[1].volume_change_pct > 0); assert.ok(r.rows[0].volume_change_pct < 0);
  assert.deepEqual(input, copy); assert.equal(r.inputs.basis, 'user_scenario');
});

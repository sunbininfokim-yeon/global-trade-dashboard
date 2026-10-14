import { test } from 'node:test';
import assert from 'node:assert/strict';
import { simulateCompany } from '../../New for anti/policy-simulator/company-model.mjs';
import { simulate as simulateCountry, example } from '../../New for anti/policy-simulator/country-model.mjs';

const input = overrides => ({ company: '가상 기업', product: 'transformer', origin: 'KOR', policy_confirmed: true, period: '가상 연간',
  price: 100, quantity: 10000, cost: 70, fixed_cost: 100000, cost_change_pct: 0, tariff_before: 15, tariff_after: 15,
  absorption_pct: 50, price_elasticity: 2, locked_share_pct: 0, competitor_change_pct: 0, market_change_pct: 0,
  capacity: '', competitor_price: '', response_mode: 'manual', source_note: '테스트 가정', ...overrides });
const close = (a, b, epsilon = 1e-8) => assert.ok(Math.abs(a - b) <= epsilon * Math.max(1, Math.abs(b)), `${a} != ${b}`);
test('unchanged tariffs preserve prices, volume and explicit product profit; inputs are immutable', () => {
  const config = input(), old = structuredClone(config), r = simulateCompany(config);
  close(r.price_after, 100); close(r.buyer_price_after, 115); close(r.quantity_after, 10000); close(r.profit_after, 200000);
  close(r.profit_change, 0); close(r.break_even_quantity, 100000 / 30); close(r.unit_cost_ceiling, 90);
  assert.deepEqual(config, old); assert.equal(r.checks.profit_identity_error, 0);
});
test('buyer pass-through retains exporter price; volume follows the independent price-demand equation', () => {
  const r = simulateCompany(input({ tariff_after: 25, absorption_pct: 0 }));
  close(r.price_after, 100); close(r.buyer_price_after, 125); close(r.quantity_after, 10000 * (125 / 115) ** -2);
  close(r.duties_after, 25 * r.quantity_after); assert.ok(r.profit_after < r.profit_before);
});
test('full exporter absorption preserves buyer price but reduces customs value and profit', () => {
  const r = simulateCompany(input({ tariff_after: 25, absorption_pct: 100 }));
  close(r.price_after, 92); close(r.buyer_price_after, 115); close(r.quantity_after, 10000); close(r.profit_after, 120000);
  close(r.duties_after, 230000); close(r.checks.buyer_price_identity_error, 0);
});
test('partial absorption splits the original-value tariff shock without double-counting the reduced tax base', () => {
  const r = simulateCompany(input({ tariff_before: 0, tariff_after: 25 }));
  close(r.price_after, 90); close(r.buyer_price_after, 112.5); close(r.duties_after / r.quantity_after, 22.5);
  close(r.quantity_after, 10000 * 1.125 ** -2); close(r.profit_after, 20 * r.quantity_after - 100000);
});
test('locked contracts resist relative-price shifts while total-market demand remains explicit', () => {
  const locked = simulateCompany(input({ tariff_after: 25, locked_share_pct: 100, absorption_pct: 0 }));
  close(locked.quantity_after, 10000);
  const contraction = simulateCompany(input({ tariff_after: 25, locked_share_pct: 100, market_change_pct: -10 }));
  close(contraction.quantity_after, 9000);
  const competition = simulateCompany(input({ competitor_change_pct: 10, competitor_price: 110 }));
  assert.ok(competition.quantity_after > 10000); close(competition.competitor_price_after, 121);
  close(competition.price_gap_pct, (115 / 121 - 1) * 100);
});
test('capacity is a bound, not a fabricated equilibrium, and unattainable break-even is flagged', () => {
  const r = simulateCompany(input({ competitor_change_pct: 100, capacity: 11000 }));
  assert.ok(r.demanded_quantity > 11000); close(r.quantity_after, 11000); assert.ok(r.capacity_binding);
  const limited = simulateCompany(input({ fixed_cost: 400000, capacity: 11000 }));
  assert.equal(limited.break_even_status, 'above_capacity');
});
test('losses, zero market volume and nonpositive unit contribution never produce NaN or fake profitable break-even', () => {
  const loss = simulateCompany(input({ cost: 120 }));
  assert.equal(loss.break_even_quantity, null); assert.equal(loss.profit_change_pct, null); assert.equal(loss.break_even_status, 'nonpositive_contribution');
  const zero = simulateCompany(input({ market_change_pct: -100 }));
  close(zero.quantity_after, 0); close(zero.profit_after, -100000); assert.equal(zero.margin_after_pct, null); assert.equal(zero.unit_cost_ceiling, null);
  assert.doesNotMatch(JSON.stringify(zero), /NaN|Infinity/);
});
test('tariff cuts can benefit buyers or exporters according to the stated split; negative cost shock is supported', () => {
  const buyer = simulateCompany(input({ tariff_before: 25, tariff_after: 0, absorption_pct: 0 }));
  close(buyer.price_after, 100); assert.ok(buyer.quantity_after > 10000);
  const exporter = simulateCompany(input({ tariff_before: 25, tariff_after: 0, absorption_pct: 100, cost_change_pct: -10 }));
  close(exporter.buyer_price_after, 125); close(exporter.price_after, 125); close(exporter.unit_cost_after, 63);
});
test('absorption comparison includes user point and endpoints with independently valid accounting', () => {
  const r = simulateCompany(input({ tariff_after: 25, absorption_pct: 33 }));
  assert.deepEqual(r.sensitivity.map(x => x.absorption_pct), [0, 25, 33, 50, 75, 100]);
  for (const s of r.sensitivity) close(s.profit_after, (s.price_after - s.unit_cost_after) * s.quantity_after - 100000);
});
test('country proxy is recomputed from matching inputs and applied once; manual response assumptions are ignored', () => {
  const country = example(), r0 = simulateCountry(country), row = r0.rows.find(r => r.country === 'KOR');
  const r = simulateCompany(input({ response_mode: 'country', tariff_before: 0, tariff_after: 25, country_inputs: country,
    price_elasticity: '', market_change_pct: -90, absorption_pct: 100, competitor_price: 'ignored' }));
  close(r.price_after, 100 * (1 + row.producer_price_change_pct / 100));
  close(r.quantity_after, 10000 * (1 + row.volume_change_pct / 100));
  close(r.profit_after, (r.price_after - 70) * r.quantity_after - 100000);
  assert.deepEqual(r.sensitivity, []); assert.equal(r.inputs.price_elasticity, 0);
  assert.equal(r.country_proxy.model_version, 'country-ces-1'); assert.ok(r.country_proxy.max_log_residual < 1e-8);
  assert.equal(JSON.parse(JSON.stringify(r)).country_proxy.inputs.product, 'transformer');
});
test('country linking rejects absent/mismatched product, origin or tariff rather than fabricating a company response', () => {
  assert.throws(() => simulateCompany(input({ response_mode: 'country' })), /국가 결과/);
  const country = example();
  for (const overrides of [{ product: 'tire' }, { origin: 'JPN' }, { tariff_before: 15 }]) {
    assert.throws(() => simulateCompany(input({ response_mode: 'country', tariff_before: 0, tariff_after: 25, country_inputs: country, ...overrides })), /품목|원산지·관세/);
  }
});
test('required numeric fields, ranges, policy confirmation and domestic tariffs are validated', () => {
  for (const field of ['price', 'quantity', 'cost', 'fixed_cost', 'tariff_before', 'tariff_after', 'price_elasticity']) {
    for (const value of ['', ' ', null, undefined, true, NaN, Infinity]) assert.throws(() => simulateCompany(input({ [field]: value })));
  }
  for (const overrides of [{ policy_confirmed: false }, { origin: 'ROW' }, { origin: 'USA' }, { absorption_pct: 101 }, { market_change_pct: -101 }, { cost_change_pct: -101 }, { capacity: 9999 }, { response_mode: 'unknown' }]) assert.throws(() => simulateCompany(input(overrides)));
  const local = simulateCompany(input({ origin: 'USA', tariff_before: 0, tariff_after: 0 })); close(local.duties_after, 0);
});

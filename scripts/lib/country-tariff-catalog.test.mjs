import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PRODUCTS, COUNTRIES, policyOptions, initialDraft, newRow, tariffPair, modelInput, SUPPLIER_SNAPSHOT, elasticityCalibration } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { simulate } from '../../New for anti/policy-simulator/country-model.mjs';

test('metal floor, metal additive and preferential combinations are distinct', () => {
  assert.deepEqual(policyOptions('transformer', 'KOR').map(p => p.rate), [15, 10]);
  assert.deepEqual(policyOptions('cable', 'KOR').map(p => p.rate), [28.7, 25, 13.7, 10]);
  assert.deepEqual(policyOptions('cable', 'JPN').map(p => p.rate), [28.7, 13.7]);
  assert.equal(policyOptions('vehicle', 'KOR')[0].rate, 15);
  assert.equal(policyOptions('vehicle', 'JPN')[0].rate, 15);
});
test('301 floor versus additional rate; 232 and memory exemption avoid double stacking', () => {
  assert.equal(policyOptions('switchgear', 'KOR')[0].rate, 12.5);
  assert.equal(policyOptions('switchgear', 'DEU')[0].rate, 10);
  assert.equal(policyOptions('switchgear', 'VNM')[0].rate, 15.2);
  assert.equal(policyOptions('fiber', 'IND')[0].rate, 15.8);
  assert.equal(policyOptions('semiconductor', 'KOR')[0].rate, 0);
  assert.equal(policyOptions('transformer', 'KOR')[0].rate, 15); // Not 15+12.5.
});
test('unreviewed origin, quotas, custom products and ROW never silently receive zero', () => {
  for (const product of Object.keys(PRODUCTS)) for (const country of ['CHN', 'CAN', 'MEX', 'ROW']) {
    assert.equal(policyOptions(product, country).length, 0);
    assert.throws(() => tariffPair(product, newRow(product, country)), /현행 관세/);
  }
  for (const country of ['KHM', 'MYS', 'IDN']) assert.equal(policyOptions('fiber', country).length, 0);
  assert.equal(policyOptions('vehicle', 'DEU').length, 0);
  assert.equal(policyOptions('custom', 'KOR').length, 0);
  assert.throws(() => tariffPair('tire', { ...newRow('tire', 'KOR'), scenario_policy: 'us_metal' }), /비교할 관세/);
});
test('direct input is a TOTAL rate, extras are carried once and source note is mandatory', () => {
  const row = { ...newRow('transformer', 'KOR'), extra_duty: 4.32, scenario_policy: 'us_metal' };
  let pair = tariffPair('transformer', row);
  assert.equal(pair.tariff_before, 19.32); assert.equal(pair.tariff_after, 14.32);
  pair = tariffPair('transformer', { ...row, scenario_policy: 'manual', manual_after: 30 });
  assert.equal(pair.tariff_after, 30);
  const direct = { ...row, baseline_policy: 'manual', manual_before: 20, tariff_note: 'Broker-reviewed entry, 2026-10-11', scenario_policy: 'current' };
  pair = tariffPair('transformer', direct); assert.equal(pair.tariff_before, 20); assert.equal(pair.tariff_after, 20);
  assert.throws(() => tariffPair('transformer', { ...direct, tariff_note: '' }), /출처/);
  assert.throws(() => tariffPair('transformer', { ...row, extra_duty: '' }), /추가세/);
  assert.throws(() => tariffPair('transformer', { ...row, scenario_policy: 'manual', manual_after: '' }), /가정 관세/);
});
test('current baseline is retained in calculation and condition/source metadata survives JSON export', () => {
  const draft = initialDraft();
  assert.throws(() => modelInput(draft), /조건/);
  draft.policy_confirmed = true;
  const baseline = simulate(modelInput(draft));
  assert.equal(baseline.inputs.rows[1].tariff_before, 15);
  assert.ok(Math.abs(baseline.rows[1].volume_change_pct) < 1e-8);
  draft.rows[1].scenario_policy = 'us_metal';
  const result = simulate(modelInput(draft));
  assert.ok(result.rows[1].volume_change_pct > 0);
  assert.equal(result.inputs.calibration.policy_as_of, '2026-10-11');
  assert.equal(result.inputs.calibration.hts, '8504.23.00');
  assert.equal(result.inputs.calibration.elasticity.kind, 'literature_range_midpoint');
  const provenance = JSON.parse(JSON.stringify(result)).inputs.rows[1].provenance;
  assert.equal(provenance.status, 'conditional_policy_snapshot');
  assert.ok(provenance.sources.some(s => s.url.includes('2026/06/')));
});
test('only sourced product elasticities auto-apply; tire sensitivity uses published range', () => {
  assert.equal(initialDraft('semiconductor').sigma, 3.32);
  assert.equal(initialDraft('semiconductor').elasticity_basis, 'literature');
  const draft = initialDraft('tire'); draft.policy_confirmed = true;
  const result = simulate(modelInput(draft));
  assert.equal(result.inputs.sigma, 4.5); assert.equal(result.inputs.eta, -0.375);
  assert.deepEqual(result.sensitivity.map(s => s.sigma), [3, 4.5, 6]);
  assert.equal(result.inputs.calibration.elasticity.kind, 'literature_range_midpoint');
  draft.elasticity_basis = 'manual'; draft.sigma = 5;
  assert.equal(modelInput(draft).calibration.elasticity.kind, 'user_assumption');
  assert.equal(modelInput(draft).sensitivity_sigmas, undefined);
  for (const p of ['cable', 'custom']) {
    assert.equal(PRODUCTS[p].elasticity, undefined);
    assert.equal(initialDraft(p).elasticity_basis, 'manual');
  }
});
test('product presets distinguish observed estimates, range midpoints and old broader sectors', () => {
  const expected = { transformer: [3.5, -0.15], switchgear: [3, -1], semiconductor: [3.32, -1], vehicle: [7.58, -0.82], tire: [4.5, -0.375], fiber: [3.5, -1], cable: [4, -1], custom: [4, -1] };
  for (const [id, [sigma, eta]] of Object.entries(expected)) {
    const draft = initialDraft(id), c = elasticityCalibration(draft);
    assert.equal(draft.sigma, sigma); assert.equal(draft.eta, eta);
    if (['cable', 'custom'].includes(id)) assert.equal(c.sigma.kind, 'user_assumption');
    else assert.ok(c.sigma.source.url.startsWith('https://www.usitc.gov/'));
    if (!['transformer', 'vehicle', 'tire'].includes(id)) assert.equal(c.eta.kind, 'user_assumption');
  }
  assert.equal(elasticityCalibration(initialDraft('switchgear')).sigma.year, 2004);
  assert.equal(elasticityCalibration(initialDraft('fiber')).sigma.kind, 'historical_sector_proxy');
  const auto = elasticityCalibration(initialDraft('vehicle'));
  assert.notEqual(auto.sigma.source.url, auto.eta.source.url);
  assert.equal(auto.eta.kind, 'literature_review_midpoint');
  assert.deepEqual(auto.eta.range, [-1.27, -0.37]);
});
test('changing one parameter preserves the other source; unmarked changed values never inherit literature claims', () => {
  const draft = initialDraft('tire'); draft.policy_confirmed = true;
  draft.eta = -0.8; draft.elasticity_overrides.eta = true;
  let input = modelInput(draft);
  assert.equal(input.calibration.elasticity.sigma.kind, 'literature_range_midpoint');
  assert.equal(input.calibration.elasticity.eta.kind, 'user_assumption');
  assert.deepEqual(input.sensitivity_sigmas, [3, 4.5, 6]);
  draft.sigma = 6;
  input = modelInput(draft);
  assert.equal(input.calibration.elasticity.sigma.kind, 'user_assumption');
  assert.equal(input.sensitivity_sigmas, undefined);
  assert.equal(input.calibration.elasticity.sigma.source, undefined);
});
test('transformer literature range propagates through simulation and JSON provenance', () => {
  const draft = initialDraft('transformer'); draft.policy_confirmed = true;
  draft.rows[1].scenario_policy = 'us_metal';
  const r = JSON.parse(JSON.stringify(simulate(modelInput(draft))));
  assert.deepEqual(r.sensitivity.map(s => s.sigma), [2, 3.5, 5]);
  assert.equal(r.inputs.calibration.elasticity.eta.year, 2024);
  assert.match(r.inputs.calibration.elasticity.sigma.scope, /60MVA/);
  assert.ok(r.checks.max_log_residual < 1e-8);
});
test('tariff validation identifies the control to correct without parsing translated error messages', () => {
  const check = (row, field) => assert.throws(() => tariffPair('transformer', row), err => err.field === field);
  check(newRow('transformer', 'MEX'), 'baseline_policy');
  check({ ...newRow('transformer', 'KOR'), extra_duty: '' }, 'extra_duty');
  check({ ...newRow('transformer', 'KOR'), extra_duty: 290 }, 'extra_duty');
  check({ ...newRow('transformer', 'KOR'), baseline_policy: 'manual', manual_before: 15, tariff_note: '  ' }, 'tariff_note');
  check({ ...newRow('transformer', 'KOR'), scenario_policy: 'manual', manual_after: '' }, 'manual_after');
});
test('public supplier snapshot is product-specific, descending and contains valid known countries', () => {
  assert.equal(SUPPLIER_SNAPSHOT.year, 2025);
  assert.equal(Object.keys(SUPPLIER_SNAPSHOT.products).length, 7);
  for (const [id, p] of Object.entries(SUPPLIER_SNAPSHOT.products)) {
    assert.equal(p.hts6, PRODUCTS[id].hts6); assert.equal(p.suppliers.length, 8);
    assert.equal(new Set(p.suppliers.map(s => s.country)).size, 8);
    p.suppliers.forEach((s, i) => {
      assert.ok(COUNTRIES[s.country]); assert.notEqual(s.country, 'USA');
      assert.ok(s.customs_value_usd > 0);
      if (i) assert.ok(s.customs_value_usd <= p.suppliers[i - 1].customs_value_usd);
    });
    assert.equal(newRow(id, p.suppliers[0].country).expenditure, '');
  }
  assert.equal(SUPPLIER_SNAPSHOT.products.transformer.suppliers[0].country, 'MEX');
  assert.equal(SUPPLIER_SNAPSHOT.products.fiber.suppliers[0].country, 'VNM');
});

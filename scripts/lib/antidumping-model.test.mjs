import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import { lookupAD, simulateDeposit, nonSelectedScenario } from '../../New for anti/policy-simulator/antidumping-model.mjs';
import { COMPANY_PROFILES, companyCalibration } from '../../New for anti/policy-simulator/company-profiles.mjs';
import { simulateCompany } from '../../New for anti/policy-simulator/company-model.mjs';
const lookup = (company_id = 'ls', entry_date = '2026-10-11', case_id = 'A-580-867') => lookupAD({ company_id, entry_date, case_id });
const scenario = extra => ({ case_id: 'A-580-867', company_id: 'ls', entry_date: '2026-10-11', entered_value_usd: '1000000', scenario_rate_pct: '16.87', annual_finance_pct: '5', holding_days: '180', scope_confirmed: true, identity_confirmed: true, ...extra });
test('curated catalog has unique official document and company keys; only final notices have effective deposit rates', () => {
  const ids = new Set(); assert.equal(AD_CATALOG.cases.length, 5);
  for (const c of AD_CATALOG.cases) {
    assert.equal(new Set(c.companies.map(x => x.id)).size, c.companies.length);
    for (const s of c.segments) {
      const d = AD_CATALOG.documents[s.document_id]; assert.ok(d); assert.match(d.url, /^https:\/\/www.govinfo.gov\//);
      assert.equal(d.kind, s.stage === 'final' ? 'review_final' : 'review_preliminary');
      if (s.cash_deposit_effective) { assert.equal(s.stage, 'final'); assert.ok(s.cash_deposit_effective >= d.published); }
      for (const r of s.rates) { const key = `${c.case_id}:${s.document_id}:${r.company_id}`; assert.ok(!ids.has(key)); ids.add(key); assert.ok(c.companies.some(x => x.id === r.company_id)); }
    }
  }
});
test('preliminary margin does not change deposit; exact final effective-date boundary does', () => {
  assert.equal(lookup('ls', '2026-02-10').rate_pct, '16.87'); assert.equal(lookup('ls', '2026-08-13').rate_pct, '16.87');
  assert.equal(lookup('ls', '2026-08-14').rate_pct, '4.32');
  assert.equal(lookup('ls', '2023-07-31').rate_pct, null); // POR is not prospective entry effective date.
});
test('unknown company, missing history, and future entries stay unresolved; actual zero stays zero', () => {
  for (const r of [lookup('unknown'), lookup('hyosung', '2025-04-08'), lookup('ls', '2026-10-12')]) { assert.equal(r.status, 'unresolved'); assert.equal(r.rate_pct, null); }
  assert.equal(lookup('hyundai').rate_pct, '0'); assert.equal(lookup('LS전선').rate_pct, null); assert.equal(lookup('LS').rate_pct, null);
  assert.equal(lookup('ILJIN').company.id, 'iljin');
});
test('tire companies use their own case and final reference; review initiation has no rate effect', () => {
  for (const [id, rate] of [['hankook', '13.03'], ['nexen', '8.02'], ['kumho', '10.53']]) assert.equal(lookup(id, '2026-10-11', 'A-580-908').rate_pct, rate);
  assert.equal(lookup('ls', '2026-10-01').document.document_id, '2026-16663');
});
test('deposit and simple financing independently agree with USD amounts; export keeps assumptions/source separate', () => {
  const input = scenario(), original = structuredClone(input), r = simulateDeposit(input);
  assert.equal(r.reference_deposit_usd, '43200.00'); assert.equal(r.scenario_deposit_usd, '168700.00'); assert.equal(r.deposit_change_usd, '125500.00'); assert.equal(r.reference_financing_cost_usd, '1065.21');
  assert.equal(r.reference.status, 'published_reference'); assert.equal(r.inputs.scenario_rate_pct, '16.87'); assert.doesNotThrow(() => JSON.stringify(r)); assert.deepEqual(input, original);
});
test('money is exact decimal half-up at cents and negative differences preserve their sign', () => {
  const r = simulateDeposit(scenario({ entered_value_usd: '0.10', scenario_rate_pct: '5' })); assert.equal(r.scenario_deposit_usd, '0.01');
  const cut = simulateDeposit(scenario({ scenario_rate_pct: '0' })); assert.equal(cut.deposit_change_usd, '-43200.00');
  assert.equal(simulateDeposit(scenario({ entered_value_usd: '1000000000000', scenario_rate_pct: '9999.999999' })).scenario_deposit_usd, '99999999990000.00');
});
test('scope and producer/exporter conditions must both be explicitly checked', () => {
  for (const key of ['scope_confirmed', 'identity_confirmed']) for (const value of [false, 'true', null]) assert.throws(() => simulateDeposit(scenario({ [key]: value })));
});
test('unresolved references never generate a zero deposit', () => {
  const r = simulateDeposit(scenario({ company_id: 'unknown' })); assert.equal(r.status, 'unresolved'); assert.equal(r.reference_deposit_usd, null);
});
test('manual case is supported with explicit source and law identity; no fuzzy or all-others fallback', () => {
  const p = scenario({ reference_mode: 'manual', case_id: 'A-000-123', company_name: '실제 다른 법인', reference_rate_pct: '7.25', reference_url: 'https://www.govinfo.gov/example', reference_note: '사용자 확인 적용 조건' });
  const r = simulateDeposit(p); assert.equal(r.reference.status, 'user_verified_reference'); assert.equal(r.reference_deposit_usd, '72500.00');
  for (const extra of [{ reference_url: 'javascript:alert(1)' }, { reference_url: 'http://example.com' }, { reference_note: ' ' }, { case_id: 'C-000-123' }, { company_name: '' }]) assert.throws(() => simulateDeposit({ ...p, ...extra }));
});
test('malformed numbers and dates are rejected; fractional holding days are not silently rounded', () => {
  for (const key of ['entered_value_usd', 'scenario_rate_pct', 'annual_finance_pct', 'holding_days']) for (const bad of [null, true, -1, '', 'NaN', 'Infinity', '1e3']) assert.throws(() => simulateDeposit(scenario({ [key]: bad })));
  assert.throws(() => simulateDeposit(scenario({ holding_days: '1.2' })));
  for (const date of ['', '2026-02-30', '2026-2-01']) assert.throws(() => lookup('ls', date));
});
test('all zero, de minimis or entirely FA margins require another reasonable method, never zero', () => {
  const r = nonSelectedScenario({ rows: [{ margin_pct: '0' }, { margin_pct: '0.49' }, { margin_pct: '20', entirely_facts_available: true }] });
  assert.equal(r.status, 'requires_reasonable_method'); assert.equal(r.rate_pct, null); assert.equal(r.excluded.length, 3);
});
test('one eligible margin and 0.5 boundary work; excluded weights never enter denominator', () => {
  assert.equal(nonSelectedScenario({ rows: [{ margin_pct: '0' }, { margin_pct: '16.87' }] }).rate_pct, '16.87');
  assert.equal(nonSelectedScenario({ rows: [{ margin_pct: '0.499999' }, { margin_pct: '0.5' }] }).rate_pct, '0.5');
  assert.equal(nonSelectedScenario({ rows: [{ margin_pct: '0', weight: '999' }, { margin_pct: '10', weight: '1' }, { margin_pct: '20', weight: '3' }] }).rate_pct, '17.500000');
});
test('missing weights do not become a silent average; equal weights are an explicit scenario', () => {
  const p = { rows: [{ margin_pct: '13.03' }, { margin_pct: '8.02' }] };
  assert.equal(nonSelectedScenario(p).status, 'weights_required');
  const r = nonSelectedScenario({ ...p, equal_weights_assumption: true }); assert.equal(r.rate_pct, '10.525000'); assert.equal(r.status, 'equal_weight_scenario'); assert.equal(r.educational_only, true);
  assert.throws(() => nonSelectedScenario({ rows: [] })); assert.throws(() => nonSelectedScenario({ rows: [{ margin_pct: '10', weight: '0' }, { margin_pct: '20', weight: '0' }] }));
});
test('seven named companies have official financial context, consistent KRW units and no invented US product data', () => {
  assert.equal(Object.values(COMPANY_PROFILES).filter(p => p.financial).length, 7);
  assert.equal(Object.values(COMPANY_PROFILES).filter(p => p.financial === null && p.ad).length, 30);
  assert.equal(Object.values(COMPANY_PROFILES).filter(p => p.financial === null && !p.ad).length, 3);
  for (const p of Object.values(COMPANY_PROFILES)) {
    if (p.financial) { assert.equal(p.financial.unit, 'KRW million'); assert.equal(p.financial.use, 'context_only'); assert.match(p.financial.source_url, /^https:/); }
    else { assert.match(p.source.url, p.ad ? /^https:\/\/www.govinfo.gov\// : /^https:\/\/www\.(hyundai|mobis|hlmando)\.com\//); assert.ok(p.official_name); }
    for (const key of ['product_origin', 'product_price', 'product_quantity', 'product_variable_cost', 'product_fixed_cost']) assert.equal(p[key], null);
  }
  assert.equal(COMPANY_PROFILES['ls-cable'].ad, null); assert.equal(COMPANY_PROFILES.hyosung.ad.case_id, 'A-580-867'); assert.equal(COMPANY_PROFILES.hankook.ad.case_id, 'A-580-908');
  const ls = COMPANY_PROFILES['ls-electric'];
  assert.equal(ls.financial.revenue, 4965799); assert.equal(ls.financial.operating_profit, 426407); assert.equal(ls.financial.checked_on, '2026-10-12');
  assert.deepEqual(ls.ad, { case_id: 'A-580-867', company_id: 'ls' });
  assert.equal(lookupAD({ ...ls.ad, entry_date: '2026-10-11' }).company.official_name, 'LS Electric Co., Ltd.');
  assert.equal(COMPANY_PROFILES['ls-cable'].financial.checked_on, '2026-10-11');
  assert.equal(COMPANY_PROFILES.hankook.financial.revenue, 10318600); assert.match(COMPANY_PROFILES.hankook.financial.scope, /타이어 사업부/);
});
test('real financial context is serialized but cannot substitute for missing product unit cost', () => {
  const p = { company: '효성중공업', origin: 'KOR', product: 'transformer', policy_confirmed: true, price: 100, quantity: 10000, cost: 70, fixed_cost: 100000, cost_change_pct: 0, tariff_before: 15, tariff_after: 15, absorption_pct: 50, price_elasticity: 2, locked_share_pct: 0, competitor_change_pct: 0, market_change_pct: 0, calibration: companyCalibration('hyosung') };
  const r = simulateCompany(p); assert.equal(r.profit_after, 200000); assert.equal(r.inputs.calibration.public_company_context.financial.revenue, 5968512);
  assert.throws(() => simulateCompany({ ...p, cost: '' }));
});

test('steel references respect final effective dates, case-specific identity and later preliminary results', () => {
  for (const [caseId, id, rate, effective, previous] of [
    ['A-580-883', 'hyundai-steel', '1.49', '2026-05-14', '2026-05-13'],
    ['A-580-883', 'posco-pic', '1.22', '2026-05-14', '2026-05-13'],
    ['A-580-897', 'hyundai-pipe', '0', '2026-05-01', '2026-04-30'],
    ['A-580-897', 'seah', '0.80', '2026-05-01', '2026-04-30'],
  ]) {
    assert.equal(lookup(id, previous, caseId).rate_pct, null);
    assert.equal(lookup(id, effective, caseId).rate_pct, rate);
    assert.equal(lookup(id, '2026-10-11', caseId).rate_pct, rate);
    assert.equal(lookup('unknown', effective, caseId).rate_pct, null);
    assert.equal(lookup(id, '2026-10-12', caseId).rate_pct, null);
  }
  const seah = lookup('seah', '2026-07-30', 'A-580-897');
  assert.equal(seah.rate_pct, '0.80'); assert.equal(seah.document.document_id, '2026-08489');
  assert.equal(lookup('hyundai-steel', '2026-10-11', 'A-580-897').rate_pct, null);
  assert.equal(lookup('hyundai-pipe', '2026-10-11', 'A-580-883').rate_pct, null);
  assert.equal(lookup('POSCO Holdings', '2026-10-11', 'A-580-883').rate_pct, null);
  assert.equal(AD_CATALOG.documents['2026-09707'].verified_on, '2026-10-12');
  assert.equal(AD_CATALOG.documents['2026-16663'].verified_on, '2026-10-11');
});
test('steel deposit scenarios retain only the selected AD burden, including a published zero', () => {
  const seah = simulateDeposit(scenario({ case_id: 'A-580-897', company_id: 'seah', entered_value_usd: '100000', scenario_rate_pct: '5.80' }));
  assert.equal(seah.reference_deposit_usd, '800.00'); assert.equal(seah.scenario_deposit_usd, '5800.00');
  assert.equal(seah.reference.company.official_name, 'SeAH Steel Corporation');
  assert.equal(simulateDeposit(scenario({ case_id: 'A-580-897', company_id: 'hyundai-pipe' })).reference_deposit_usd, '0.00');
  assert.match(seah.limitations.join(' '), /CVD/);
});

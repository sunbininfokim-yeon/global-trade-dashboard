import { test } from 'node:test';
import assert from 'node:assert/strict';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import { simulateDeposit } from '../../New for anti/policy-simulator/antidumping-model.mjs';
import { createADExample, describeADInputs, AD_REVIEW_RECORDS, reviewRecords, caseReviewRecords, reviewProgress } from '../../New for anti/policy-simulator/antidumping-guide.mjs';
const context = (extra = {}) => ({ reference_mode: 'published', case_id: 'A-580-867', company_id: 'hyosung', entry_date: '2026-10-11', ...extra });

test('product examples supply transaction totals and explicit financial assumptions, not industry estimates', () => {
  const lpt = createADExample(context()), tires = createADExample(context({ case_id: 'A-580-908', company_id: 'hankook' }));
  assert.equal(lpt.values.entered_value_usd, '1000000'); assert.equal(tires.values.entered_value_usd, '100000');
  assert.equal(lpt.values.scenario_rate_pct, '9.32'); assert.equal(tires.values.scenario_rate_pct, '18.03');
  assert.equal(lpt.values.annual_finance_pct, '5'); assert.equal(lpt.values.holding_days, '365');
  assert.match(lpt.notes.entered_value_usd, /평균 가격.*아닙니다/); assert.match(lpt.notes.annual_finance_pct, /업종 평균.*아닙니다/);
  const calculated = simulateDeposit({ ...context(), ...lpt.values, scope_confirmed: true, identity_confirmed: true });
  assert.equal(calculated.reference_deposit_usd, '43200.00'); assert.equal(calculated.scenario_deposit_usd, '93200.00');
});
test('comparison examples follow the exact company/date reference, including a zero, never another company', () => {
  assert.equal(createADExample(context({ company_id: 'hyundai' })).values.scenario_rate_pct, '5.00');
  const old = createADExample(context({ company_id: 'ls', entry_date: '2026-08-13' }));
  assert.equal(old.values.scenario_rate_pct, '21.87'); assert.equal(old.basis.document_id, '2025-05960');
  for (const extra of [{ company_id: 'unknown' }, { entry_date: '2026-10-12' }, { entry_date: 'bad' }, { reference_mode: 'manual' }]) {
    const example = createADExample(context(extra)); assert.equal(example.values.scenario_rate_pct, ''); assert.equal(example.basis.reference_rate_pct, null);
  }
});
test('export provenance distinguishes unchanged examples from edited values and stale company/date contexts', () => {
  const input = context(), example = createADExample(input), filled = { ...input, ...example.values };
  assert.ok(describeADInputs(filled, example).every(x => x.origin === 'editable_example'));
  const edited = describeADInputs({ ...filled, entered_value_usd: '2000000' }, example, ['annual_finance_pct']);
  assert.equal(edited.find(x => x.key === 'entered_value_usd').origin, 'user_input');
  assert.equal(edited.find(x => x.key === 'annual_finance_pct').origin, 'user_input');
  assert.equal(describeADInputs({ ...filled, company_id: 'ls' }, example).find(x => x.key === 'scenario_rate_pct').origin, 'user_input');
});
test('progress isolates case, review period and recorded companies; mutation cannot alter source records', () => {
  const newer = reviewProgress('A-580-867', 'lpt-2025-26'), previous = reviewProgress('A-580-867', 'lpt-2023-24', 'hyundai');
  assert.equal(newer.latest_stage, 'initiation'); assert.equal(newer.stages.find(x => x.id === 'final').state, 'unknown');
  assert.equal(previous.latest_stage, 'final'); assert.equal(previous.stages.find(x => x.id === 'liquidation').state, 'unknown');
  assert.equal(previous.stages.find(x => x.id === 'selection').event.date, '2024-10-30');
  assert.equal(previous.deposit.date, '2026-08-14'); assert.equal(newer.deposit, undefined);
  assert.throws(() => reviewProgress('A-580-908', 'lpt-2023-24'));
  assert.deepEqual(reviewRecords('A-580-867', 'unknown'), []);
  assert.ok(!reviewRecords('A-580-867', 'hyosung').some(x => x.id === 'lpt-2022-23'));
  newer.events[0].date = '2000-01-01'; assert.equal(reviewProgress('A-580-867', 'lpt-2025-26').events[0].date, '2026-10-01');
});
test('later final results do not invent earlier stages, CBP liquidation, court filings or future dates', () => {
  const sparse = reviewProgress('A-580-867', 'lpt-2022-23');
  assert.equal(sparse.stages.filter(x => x.state !== 'unknown').length, 1);
  const tires = reviewProgress('A-580-908', 'tires-2023-24', 'hankook');
  assert.equal(tires.stages.find(x => x.id === 'selection').event.date, null);
  for (const p of [sparse, tires]) { assert.ok(p.litigation.every(x => x.state === 'unknown' && x.event === null)); assert.equal(p.stages.find(x => x.id === 'liquidation').state, 'unknown'); }
  assert.ok(tires.litigation.some(x => x.id === 'remand')); assert.ok(tires.litigation.some(x => x.id === 'injunction'));
});
test('every recorded event resolves to an official source and stays within evidence cutoff and its case', () => {
  assert.equal(new Set(AD_REVIEW_RECORDS.map(r => r.id)).size, AD_REVIEW_RECORDS.length);
  for (const r of AD_REVIEW_RECORDS) {
    for (const e of r.events) { assert.ok(AD_CATALOG.documents[e.source]); if (e.date) assert.ok(e.date <= AD_CATALOG.checked_on); }
    assert.ok(AD_CATALOG.cases.some(c => c.case_id === r.case_id));
    assert.ok(r.por_start < r.por_end);
  }
  assert.match(AD_CATALOG.documents['ACCESS-4943770-02'].notes, /4943770-02/);
});

test('steel examples and POR progress keep preliminary zero separate from final deposit and unknown stages', () => {
  for (const [case_id, company_id, rate] of [['A-580-883', 'posco-pic', '6.22'], ['A-580-897', 'seah', '5.80']]) {
    const example = createADExample(context({ case_id, company_id }));
    assert.equal(example.values.entered_value_usd, '100000'); assert.equal(example.values.scenario_rate_pct, rate);
    assert.match(example.notes.entered_value_usd, /실제 거래가가 아닙니다/);
  }
  const newer = reviewProgress('A-580-897', 'welded-pipe-2024-25');
  assert.equal(newer.latest_stage, 'preliminary'); assert.equal(newer.deposit, undefined);
  assert.equal(newer.stages.find(x => x.id === 'final').state, 'unknown');
  const older = reviewProgress('A-580-897', 'welded-pipe-2023-24');
  assert.equal(older.latest_stage, 'final'); assert.equal(older.deposit.date, '2026-05-01');
  assert.equal(older.stages.find(x => x.id === 'liquidation').state, 'unknown');
  const steel = reviewProgress('A-580-883', 'hot-rolled-2023-24');
  assert.equal(steel.stages.find(x => x.id === 'initiation').event.date, '2024-11-14');
  assert.equal(steel.latest_stage, 'final');
});


test('case overview excludes firm rescissions and individually scoped selection events', () => {
  const records = caseReviewRecords('A-580-897');
  assert.ok(records.length > 0); assert.ok(records.every(r => r.status !== 'rescinded'));
  const overview = reviewProgress('A-580-867', 'lpt-2023-24');
  assert.equal(overview.stages.find(s => s.id === 'selection').state, 'unknown');
  assert.equal(overview.stages.find(s => s.id === 'final').state, 'latest');
  assert.ok(overview.events.every(e => !e.companies));
  const copied = caseReviewRecords('A-580-867'); copied[0].events.length = 0;
  assert.ok(caseReviewRecords('A-580-867')[0].events.length > 0);
  assert.deepEqual(caseReviewRecords('unknown'), []);
});

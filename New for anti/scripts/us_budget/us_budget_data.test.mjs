// Published 정책 › 미국 › 예산 data. The annual checks are Codex's prototype
// tests from PR #758 (tests/us-budget-preview.test.cjs), pointed at the
// published copy; the rest pin the live monthly file and the page's guard.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { usableLive } from '../../policy-budget/view.mjs';

const dir = new URL('../../public/data/us_budget/', import.meta.url);
const bytes = readFileSync(new URL('annual_v1.json', dir));
const snapshot = JSON.parse(bytes);
const sources = JSON.parse(readFileSync(new URL('sources.json', dir)));
const live = JSON.parse(readFileSync(new URL('mts_live_v1.json', dir)));
const { budget, defense, fy2027 } = snapshot;
const sum = (rows) => rows.reduce((n, r) => n + r.value, 0);
function close(actual, expected, tolerance = 0.01) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
}
function rollup(node) {
  assert.ok(Number.isFinite(node.value));
  if (node.prior !== null) assert.ok(Number.isFinite(node.prior));
  if (node.children?.length) {
    close(sum(node.children), node.value);
    close(node.children.reduce((n, r) => n + r.prior, 0), node.prior);
    node.children.forEach(rollup);
  }
}

test('reviewed snapshot is unchanged and its official sources match', () => {
  assert.equal(snapshot.schema_version, 1);
  assert.equal(sources.snapshot_sha256, createHash('sha256').update(bytes).digest('hex'));
  assert.equal(sources.normalized_unit, 'USD');
  assert.equal(sources.sources.length, 10);
  for (const source of sources.sources) {
    assert.ok(['www.whitehouse.gov', 'api.fiscaldata.treasury.gov'].includes(new URL(source.url).hostname));
    assert.match(source.raw_sha256 || source.data_sha256, /^[a-f0-9]{64}$/);
  }
});

test('annual actual receipts, outlays and deficit reconcile', () => {
  for (const [year, values] of Object.entries(budget.years)) {
    close(values.outlays - values.receipts, values.deficit);
    close(sum(budget.receipts[year]), values.receipts, 1e6);
    assert.notEqual(values.estimate, true);
  }
});

test('historical expenditure types and discretionary hierarchy reconcile', () => {
  assert.equal(budget.types[2026], undefined);
  for (const r of Object.values(budget.types)) close(r.mandatory + r.discretionary + r.interest, r.total, 2e8);
  for (const [year, rows] of Object.entries(budget.discretionary)) {
    close(sum(rows), budget.years[year].discretionaryExact);
    rows.forEach(rollup);
  }
  for (const [year, rows] of Object.entries(defense)) {
    const reference = budget.discretionary[year].find((r) => r.id === '7');
    close(sum(rows), reference.value);
    rows.forEach(rollup);
  }
});

test('the proposal year stays a separate April government estimate', () => {
  assert.equal(fy2027.year.estimate, true);
  assert.match(fy2027.year.source, /최종 확정액 아님/);
  assert.match(fy2027.baseline, /FY2026 정부 추정/);
  close(fy2027.year.outlays - fy2027.year.receipts, fy2027.year.deficit);
  close(fy2027.types.mandatory + fy2027.types.discretionary + fy2027.types.interest, fy2027.year.outlays);
  close(fy2027.discretionary.find((r) => r.id === '7').prior, 903223000000);
  [...fy2027.discretionary, ...fy2027.mandatory, ...fy2027.interest].forEach(rollup);
  assert.ok(fy2027.discretionary.find((r) => r.id === '38').value < 0);
  const f = budget.finance2026;
  close(f.borrowing - f.cashIncrease + f.other, f.deficit);
});

test('live monthly file: 36 consecutive observed months, never a proposal', () => {
  assert.equal(live.schema_version, 1);
  assert.ok(usableLive(live), 'page guard accepts the published live file');
  assert.equal(live.months.at(-1).vintage <= live.mts_record_date, true);
  for (const m of live.months) assert.ok(m.month <= live.mts_record_date.slice(0, 7), `${m.month} is after its report`);
  if (live.fytd) close(live.fytd.outlays - live.fytd.receipts, live.fytd.deficit);
});

test('page guard rejects a gap, a broken identity or a short series', () => {
  const months = live.months.map((m) => ({ ...m }));
  assert.equal(usableLive({ ...live, months: months.slice(1) }), null);
  assert.equal(usableLive({ ...live, months: [...months.slice(0, 10), ...months.slice(11), months[0]] }), null);
  const broken = months.map((m) => ({ ...m }));
  broken[5].deficit += 1e9;
  assert.equal(usableLive({ ...live, months: broken }), null);
});

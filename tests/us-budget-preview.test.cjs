const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const dir = path.join(__dirname, '../docs/prototypes/us-budget');
const bytes = fs.readFileSync(path.join(dir, 'budget-data.json'));
const snapshot = JSON.parse(bytes);
const sources = JSON.parse(fs.readFileSync(path.join(dir, 'sources.json')));
const { budget, defense, fy2027 } = snapshot;
const sum = rows => rows.reduce((n, r) => n + r.value, 0);
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

test('snapshot hash and official source references match', () => {
  assert.equal(snapshot.schema_version, 1);
  assert.equal(sources.snapshot_sha256, crypto.createHash('sha256').update(bytes).digest('hex'));
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
    close(sum(budget.receipts[year]), values.receipts, 1e6); // published receipts rounded to millions
    assert.notEqual(values.estimate, true);
  }
});

test('36 unique observed months retain the cash-budget identity', () => {
  assert.equal(budget.monthly.length, 36);
  assert.equal(new Set(budget.monthly.map(r => r.month)).size, 36);
  assert.equal(budget.monthly[0].month, '2023-10');
  assert.equal(budget.monthly.at(-1).month, '2026-09');
  for (const r of budget.monthly) close(r.outlays - r.receipts, r.deficit);
});

test('historical expenditure types retain published rounding and missing FY2026 split', () => {
  assert.equal(budget.types[2026], undefined);
  for (const r of Object.values(budget.types)) {
    close(r.mandatory + r.discretionary + r.interest, r.total, 2e8);
  }
  for (const [year, rows] of Object.entries(budget.discretionary)) {
    close(sum(rows), budget.years[year].discretionaryExact);
    rows.forEach(rollup);
  }
});

test('historical defense hierarchy matches national-defense discretionary scope', () => {
  for (const [year, rows] of Object.entries(defense)) {
    const reference = budget.discretionary[year].find(r => r.id === '7');
    close(sum(rows), reference.value);
    close(rows.reduce((n, r) => n + r.prior, 0), reference.prior);
    rows.forEach(rollup);
  }
});

test('FY2027 is an explicitly separate April government proposal', () => {
  assert.equal(fy2027.year.estimate, true);
  assert.match(fy2027.year.source, /2026년 4월/);
  assert.match(fy2027.year.source, /최종 확정액 아님/);
  assert.match(fy2027.baseline, /FY2026 정부 추정/);
  close(fy2027.year.outlays - fy2027.year.receipts, fy2027.year.deficit);
  close(sum(fy2027.receipts), fy2027.year.receipts);
  close(fy2027.types.mandatory + fy2027.types.discretionary + fy2027.types.interest, fy2027.year.outlays);
  close(sum(fy2027.discretionary), fy2027.types.discretionary);
  close(sum(fy2027.mandatory), fy2027.types.mandatory);
  close(sum(fy2027.interest), fy2027.types.interest);
});

test('forecast defense and program accounts reconcile against the same-vintage baseline', () => {
  const nationalDefense = fy2027.discretionary.find(r => r.id === '7');
  close(nationalDefense.prior, 903223000000); // OMB April FY2026 estimate, not later MTS actual
  [...fy2027.discretionary, ...fy2027.mandatory, ...fy2027.interest].forEach(rollup);
  const allowances = fy2027.discretionary.find(r => r.id === '38');
  assert.ok(allowances.value < 0, 'preserve the source negative planning adjustment');
});

test('FY2026 financing reconciles without treating borrowing as receipts', () => {
  const f = budget.finance2026;
  close(f.borrowing - f.cashIncrease + f.other, f.deficit);
  close(f.deficit, budget.years[2026].deficit);
});

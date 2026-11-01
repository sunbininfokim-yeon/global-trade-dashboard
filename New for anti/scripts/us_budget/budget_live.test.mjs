import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { usableBundle, usableLive, collectionState } from '../../policy-budget/data.mjs';

const dir = process.env.US_BUDGET_STAGED_DIR || fileURLToPath(new URL('../../public/data/us_budget/', import.meta.url));
const bundle = JSON.parse(readFileSync(resolve(dir, 'budget_live_v1.json')));
const status = JSON.parse(readFileSync(resolve(dir, 'collection_status_v1.json')));
const frozen = JSON.parse(readFileSync(new URL('../../public/data/us_budget/annual_v1.json', import.meta.url)));
const copy = () => structuredClone(bundle);
const close = (a, b, tolerance = 1) => assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`);

test('regenerated annual and monthly bundle passes the production data contract', () => {
  assert.equal(usableBundle(bundle), bundle);
  assert.equal(status.state, 'ok');
  assert.equal(status.dataset_id, bundle.dataset_id);
  assert.equal(bundle.annual.sources.length, 6);
  for (const source of bundle.annual.sources) {
    assert.equal(new URL(source.url).hostname, 'www.whitehouse.gov');
    assert.match(source.sha256, /^[a-f0-9]{64}$/);
  }
});

test('same-publication regenerated history and proposal reproduce the reviewed snapshot', () => {
  if (bundle.annual.publication !== '2026/04' || bundle.annual.proposal_fy !== 2027) return;
  for (const y of ['2022', '2023', '2024', '2025']) {
    for (const key of ['receipts', 'outlays', 'deficit']) close(bundle.annual.budget.years[y][key], frozen.budget.years[y][key]);
    close(bundle.annual.budget.discretionary[y].reduce((n, r) => n + r.value, 0), frozen.budget.years[y].discretionaryExact);
  }
  for (const key of ['receipts', 'outlays', 'deficit']) close(bundle.annual.proposal.year[key], frozen.fy2027.year[key]);
  close(bundle.annual.proposal.discretionary[0].prior, 903223000000);
  assert.equal(bundle.annual.budget.types[2026], undefined, 'never fill missing actuals with FY2026 estimates');
});

test('proposal, enacted budget authority and actual cash outlays stay distinct', () => {
  assert.equal(bundle.annual.proposal.year.status, 'proposal_estimate');
  assert.equal(bundle.annual.enacted_budget.status, 'not_collected');
  assert.equal(bundle.annual.enacted_budget.amount, null);
  assert.equal(bundle.annual.enacted_budget.metric, 'budget_authority');
  const bad = copy(); bad.annual.enacted_budget.amount = bad.annual.proposal.year.outlays;
  assert.equal(usableBundle(bad), null);
});

test('invalid totals, missing years, forecast-as-actual or broken hierarchy are rejected', () => {
  for (const mutate of [
    b => { b.annual.proposal.year.receipts += 1e9; },
    b => { delete b.annual.budget.years[Object.keys(b.annual.budget.years)[0]]; },
    b => { Object.values(b.annual.budget.years)[0].status = 'proposal_estimate'; },
    b => { b.annual.proposal.discretionary[0].children[0].value += 1e6; },
    b => { b.annual.proposal.receipts[0].value = null; }
  ]) {
    const bad = copy(); mutate(bad); assert.equal(usableBundle(bad), null);
  }
});

test('failure, stale collection, stale accounting period and mismatched deploy are visible', () => {
  const now = new Date(status.last_checked_at);
  assert.equal(collectionState(bundle, status, now).state, 'ok');
  assert.equal(collectionState(bundle, {...status, state:'failed'}, now).state, 'failed');
  assert.equal(collectionState(null, null, now).state, 'unverified');
  assert.equal(collectionState(bundle, {...status, dataset_id:'other'}, now).state, 'unverified');
  assert.equal(collectionState(bundle, status, new Date(now.getTime() + 97 * 3600e3)).state, 'stale_check');
  const later = new Date(Date.parse(bundle.live.mts_record_date) + 70 * 86400e3);
  assert.equal(collectionState(bundle, {...status, last_checked_at:later.toISOString()}, later).state, 'stale_period');
});

test('monthly guard rejects future months, wrong FYTD year or invalid month labels', () => {
  const bad = structuredClone(bundle.live); bad.months.at(-1).month = '2099-10';
  assert.equal(usableLive(bad), null);
  const wrong = structuredClone(bundle.live); wrong.fytd.fy += 1;
  assert.equal(usableLive(wrong), null);
  const label = structuredClone(bundle.live); label.months[0].month = '2025-99';
  assert.equal(usableLive(label), null);
});

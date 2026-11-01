import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { usableBundle, usableLive, collectionState } from '../../policy-budget/data.mjs';
import { usableFunding, financeForBill, renderBillFinance, renderFunding, mountBillFinance } from '../../policy-budget/finance.mjs';

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

test('agency detail covers non-defense agencies and reconciles each BEA category', () => {
  const details=bundle.annual.agency_details;
  assert.ok(details);
  for (const entry of Object.values(details)) {
    for (const kind of ['mandatory','discretionary','interest']) {
      close(entry[kind].reduce((n,r)=>n+r.value,0),entry.totals[kind]);
    }
  }
  const proposal=details[bundle.annual.proposal_fy];
  for (const code of ['005','009','019','020']) {
    const agency=proposal.discretionary.find(r=>r.code===code);
    assert.ok(agency?.children.length,`agency ${code} has bureau/account detail`);
  }
  if (bundle.annual.proposal_fy===2027) assert.equal(details[2026],undefined,'unverified actual FY2026 account detail is not replaced by proposal-year estimates');
});

test('identical account numbers in different Treasury agencies remain distinct', () => {
  if (!bundle.annual.agency_details[2023]) return;
  const offsets=bundle.annual.agency_details[2023].interest.find(r=>r.code==='902');
  const leaves=offsets.children.flatMap(r=>r.children).filter(r=>r.code==='977120');
  assert.equal(leaves.length,2);
  assert.equal(new Set(leaves.map(r=>r.id)).size,2);
  assert.equal(new Set(leaves.map(r=>r.treasury_agency_code)).size,2);
});

test('fiscal links require the exact Congress and bill identity', () => {
  const funding=bundle.funding;
  assert.equal(usableFunding(funding),funding);
  const id=funding.measures[0].bill_id;
  assert.equal(financeForBill(funding,id).measures.length,1);
  assert.equal(financeForBill(funding,id.replace(/^\d{3}/,'120')),null);
  assert.equal(financeForBill(funding,'hr6500'),null);
  assert.equal(financeForBill(funding,'119-hr-3633'),null);
  assert.match(renderBillFinance(funding,'119-hr-3633'),/미조사/);
});

test('CBO estimates retain draft, annualized, unavailable-source and baseline labels', () => {
  const f=bundle.funding, html=renderBillFinance(f,f.measures[0].bill_id);
  assert.match(html,/초안 추정/);
  assert.match(html,/버전 일치 미검증/);
  assert.match(html,/연간 환산/);
  assert.match(html,/February 2026/);
  assert.match(html,/재확인 불가|재검토 필요/);
  const invalid=structuredClone(f);invalid.cost_estimates[0].budget_effects.deficit_million[0]=99;
  assert.equal(usableFunding(invalid),null);
  invalid.cost_estimates[0].budget_effects.deficit_million[0]=f.cost_estimates[0].budget_effects.deficit_million[0];
  invalid.cost_estimates[0].budget_effects.cumulative[0].outlays_million=null;
  assert.equal(usableFunding(invalid),null);
});

test('unavailable discovery is not displayed as zero new funding laws', () => {
  const f=structuredClone(bundle.funding);f.discovery.status='source_unavailable';f.discovery.candidates=[];
  const html=renderFunding(f,f.measures[0].fiscal_year);
  assert.match(html,/새 공고 검토 후보: 확인 불가/);
  assert.doesNotMatch(html,/새 공고 검토 후보: 0건/);
  assert.match(html,/조기 종료/);
});

test('source text is escaped and nonofficial executable links are rejected', () => {
  const f=structuredClone(bundle.funding);
  f.measures[0].title='<script>alert(1)</script>';
  f.measures[0].govinfo_url='javascript:alert(1)';
  const html=renderBillFinance(f,f.measures[0].bill_id);
  assert.doesNotMatch(html,/<script>|href="javascript:/);
  assert.match(html,/&lt;script&gt;/);
});

test('bill finance downloads only on click and ignores replies after leaving the view', async t => {
  const oldFetch=globalThis.fetch;let finish,calls=0;
  globalThis.fetch=()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
  t.after(()=>{globalThis.fetch=oldFetch;});
  const button={},result={};
  const root={querySelector:selector=>selector==='[data-budget-finance-load]'?button:result};
  const cleanup=mountBillFinance(root,bundle.funding.measures[0].bill_id);
  assert.equal(calls,0);
  const load=button.onclick();assert.equal(calls,1);
  cleanup();finish({ok:true,json:async()=>bundle});await load;
  assert.equal(button.onclick,null);
  assert.equal(result.innerHTML,undefined);
});

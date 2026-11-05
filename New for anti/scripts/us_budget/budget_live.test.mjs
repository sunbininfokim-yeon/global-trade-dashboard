import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { usableBundle, usableLive, collectionState } from '../../policy-budget/data.mjs';
import { usableFunding, financeForBill, renderBillFinance, renderFunding, mountBillFinance } from '../../policy-budget/finance.mjs';
import { usableContext,contextState,renderContext,initialYear,renderBasis } from '../../policy-budget/context.mjs';
import { completedAgencyActuals,actualMetric,sortActuals } from '../../policy-budget/actuals.mjs';

const dir = process.env.US_BUDGET_STAGED_DIR || fileURLToPath(new URL('../../public/data/us_budget/', import.meta.url));
const bundle = JSON.parse(readFileSync(resolve(dir, 'budget_live_v1.json')));
const status = JSON.parse(readFileSync(resolve(dir, 'collection_status_v1.json')));
const frozen = JSON.parse(readFileSync(new URL('../../public/data/us_budget/annual_v1.json', import.meta.url)));
// Synthetic completed-year contract, independent of future live MTS rollovers.
const historicalAnnual={schema_version:2,budget:{years:{2026:{status:'actual',outlays:95}}}};
const historicalLive={fytd:{fy:2026,through:'2026-09',complete:true,outlays:95,agencies:[
  {id:'a',name:'Agency A',value:110,prior:100,status:'actual'},
  {id:'b',name:'Offsets',value:-15,prior:-10,status:'actual'},
  {id:'c',name:'Unconfirmed',value:null,prior:null,status:'missing'}]}};
const copy = () => structuredClone(bundle);
const close = (a, b, tolerance = 1) => assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`);
const context=JSON.parse(readFileSync(new URL('../../public/data/us_budget/funding_context_v1.json',import.meta.url)));

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
  delete f.discovery;
  assert.equal(usableFunding(f),null);
  assert.match(renderFunding(f,2027),/검증 미완료/);
});

test('source text is escaped and nonofficial executable links are rejected', () => {
  const f=structuredClone(bundle.funding);
  f.measures[0].title='<script>alert(1)</script>';
  f.measures[0].govinfo_url='javascript:alert(1)';
  f.measures[0].areas[0].item='<script>alert(2)</script>';
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

test('current funding context reproduces the reviewed source profile', () => {
  assert.equal(usableContext(context),context);
  const profile=JSON.parse(readFileSync(new URL('./funding_context_review.json',import.meta.url)));
  assert.deepEqual(context,profile);
  assert.equal(context.procedure.as_of,'2026-11-03');
  assert.equal(context.procedure.senate_passed,0);
});

test('context does not assert current funding beyond its review window or CR deadline', () => {
  assert.equal(contextState(context,new Date('2026-11-05T12:00:00Z')),'reviewed');
  for(const day of ['2026-10-30T12:00:00Z','2026-11-13T12:00:00Z','2026-12-12T12:00:00Z']) {
    assert.equal(contextState(context,new Date(day)),'needs_review');
    assert.match(renderContext(context,new Date(day)),/현황 재확인 필요/);
  }
  const extended=structuredClone(context);extended.review_valid_until='2027-01-01';
  assert.equal(contextState(extended,new Date('2026-12-12T12:00:00Z')),'needs_review');
});

test('resolved CR conditions and dated negotiation positions have separate labels', () => {
  const html=renderContext(context,new Date('2026-11-05T12:00:00Z'));
  assert.match(html,/CR에서 일단 조치한 사항/);
  assert.match(html,/출처에서 미해결로 확인된 쟁점/);
  assert.match(html,/2026-10-27/);
  assert.match(html,/임시예산 기간 전체 금액은 미집계/);
  assert.doesNotMatch(html,/셧다운 확정|8\.093/);
});

test('bad context sources, future evidence or impossible passage counts are rejected', () => {
  for(const mutate of [d=>d.sources[0].url='javascript:alert(1)',d=>d.sources[0].url='https://example.com/',
    d=>d.procedure.senate_passed=13,d=>d.issues[0].as_of='2026-10-20',d=>d.reviewed_on='2026-11-01']) {
    const d=structuredClone(context);mutate(d);assert.equal(usableContext(d),null);
  }
  const escaped=structuredClone(context);escaped.issues[0].summary='<img src=x onerror=alert(1)>';
  assert.doesNotMatch(renderContext(escaped,new Date('2026-11-05T12:00:00Z')),/<img/);
  assert.match(renderContext(null),/現況|현황을 확인하지 못/);
});

test('default year is the latest actual and proposal arithmetic is explicit', () => {
  assert.equal(initialYear(bundle.annual),Math.max(...Object.keys(bundle.annual.budget.years).map(Number)));
  assert.equal(initialYear(frozen),2026);
  assert.match(renderBasis(frozen,2027),/계정표를 합산/);
  assert.match(renderBasis(frozen,2027),/세출−세입/);
  assert.match(renderBasis(frozen,2026),/결산 실적/);
  assert.match(renderBasis(frozen,2026),/FY2026 상세는 비어 있는데 FY2027/);
});

test('completed Treasury contract retains negatives and missing values', () => {
  const data=completedAgencyActuals(historicalLive,historicalAnnual,2026);
  assert.ok(data);assert.equal(data.rows.length,3);
  assert.equal(data.missing,1);
  assert.equal(data.rows.find(r=>r.name==='Offsets').value,-15);
  assert.equal(data.rows.find(r=>r.status==='missing').value,null);
  close(data.rows.reduce((n,r)=>n+(r.value??0),0),historicalAnnual.budget.years[2026].outlays);
  const legacy=structuredClone(historicalAnnual);legacy.schema_version=1;delete legacy.budget.years[2026].status;
  assert.equal(completedAgencyActuals(historicalLive,legacy,2026).rows.length,3);
});

test('partial FY, mismatched totals and duplicate agencies cannot look like annual actuals', () => {
  const a=structuredClone(historicalAnnual);
  for(const mutate of [d=>d.fytd.complete=false,d=>d.fytd.fy=2027,d=>d.fytd.agencies[0].value+=1e6,
    d=>d.fytd.agencies.push(d.fytd.agencies[0])]) {
    const live=structuredClone(historicalLive);mutate(live);
    assert.equal(completedAgencyActuals(live,a,2026),null);
  }
});

test('completed-year agency detail survives the next FY monthly rollover', () => {
  const fy=Math.max(...Object.keys(bundle.annual.budget.agency_actuals).map(Number));
  assert.ok(bundle.annual.budget.agency_actuals[fy]);
  const rolled=structuredClone(bundle.live);
  rolled.fytd={fy:fy+1,through:`${fy}-10`,complete:false,outlays:1,agencies:[]};
  assert.equal(completedAgencyActuals(rolled,bundle.annual,fy).fy,fy);
  assert.equal(completedAgencyActuals(rolled,bundle.annual,fy+1),null);
});

test('actual sorting preserves missing values and excludes invalid growth baselines', () => {
  const data=completedAgencyActuals(historicalLive,historicalAnnual,2026),before=JSON.stringify(data.rows);
  for(const sort of ['value','delta','rate']) {
    const ordered=sortActuals(data.rows,sort);
    assert.equal(actualMetric(ordered.at(-1),sort),null);
    const valid=ordered.map(r=>actualMetric(r,sort)).filter(n=>n!==null);
    assert.ok(valid.every((n,i)=>!i||n<=valid[i-1]));
  }
  assert.equal(actualMetric({value:5,prior:0},'rate'),null);
  assert.equal(actualMetric({value:5,prior:-2},'rate'),null);
  assert.equal(JSON.stringify(data.rows),before);
});

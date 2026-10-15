import test from 'node:test';
import assert from 'node:assert/strict';
import {productVerification,verificationMarkup,adCoverageStatus} from '../../New for anti/policy-simulator/product-verification.mjs';
import {industryMonitor} from '../../New for anti/policy-simulator/industry-monitor.mjs';
import {AD_CATALOG} from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import {mountAntidumping,selectAntidumping} from '../../New for anti/policy-simulator/antidumping-view.mjs';

test('Japan historical revocation and pipe continuation remain product-bound, dated and non-calculable',()=>{
  const original=JSON.stringify(AD_CATALOG);
  const t=productVerification('transformer','JPN');
  assert.equal(t.coverage.procedure.state,'historical_revocation');assert.deepEqual(t.ad.case_ids,[]);
  assert.equal(t.ad.research.findings[0].case_id,'A-588-032');
  assert.equal(t.ad.research.findings[0].published,'1998-10-09');assert.equal(t.ad.research.findings[0].revoked_effective_date,'2000-01-01');
  assert.equal(t.ad.rate_pct,null);assert.equal(t.ad.review,undefined);
  const p=productVerification('welded-pipe','JPN');assert.deepEqual(p.ad.case_ids,['A-588-857']);
  assert.equal(p.coverage.procedure.state,'ad_order_continued');
  assert.equal(p.ad.research.findings[0].published,'2026-01-16');assert.equal(p.ad.research.findings[0].continuation_effective_date,'2025-12-29');
  assert.equal(p.ad.rate_pct,null);assert.equal(industryMonitor('welded-pipe','JPN').calculation_enabled,false);
  assert.equal(JSON.stringify(AD_CATALOG),original);
});
test('Japan final margin table preserves a confirmed zero and flags textual conflict without promoting a deposit',()=>{
  const v=productVerification('hot-rolled','JPN'),table=v.ad.published_margins;
  assert.deepEqual(v.ad.case_ids,['A-588-874']);assert.equal(v.ad.rate_pct,null);
  assert.equal(table.por_start,'2023-10-01');assert.equal(table.por_end,'2024-09-30');assert.equal(table.published,'2026-10-14');
  assert.equal(table.rows.find(r=>r.company.startsWith('Tokyo')).rate_pct,'0.00');
  assert.equal(table.rows.find(r=>r.company.startsWith('Nippon')).rate_pct,'13.96');assert.equal(table.rows.length,7);
  assert.equal(v.coverage.integration.state,'source_discrepancy_held');assert.equal(v.coverage.procedure.state,'final_published_conflict');
  const html=verificationMarkup('hot-rolled','JPN');assert.match(html,/data-published-margins/);assert.match(html,/본문 불일치/);
  for(const product of ['fiber','carbon-fiber','aramid','tire','truck-tire']) {
    const r=productVerification(product,'JPN');assert.equal(r.coverage.procedure.state,'case_unconfirmed');assert.equal(r.ad.rate_pct,null);
    assert.deepEqual(r.ad.case_ids,[]);assert.ok(!verificationMarkup(product,'JPN').includes('C-552-829'));
  }
  assert.equal(adCoverageStatus('switchgear','JPN').research.state,'not_recorded');
  const copy=productVerification('hot-rolled','JPN');copy.ad.published_margins.rows[1].rate_pct='99';
  assert.equal(productVerification('hot-rolled','JPN').ad.published_margins.rows[1].rate_pct,'0.00');
});
test('Japan UI switch isolates Japanese final table and historical record from China, Vietnam and Korea calculations',()=>{
  selectAntidumping({case_id:'A-580-867',company_id:'hyosung'});
  const nodes=new Map(),handlers=new Map();
  const root={contains:()=>true,querySelector:selector=>{
    if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',open:false,focus(){}});return nodes.get(selector);
  },addEventListener:(name,fn)=>handlers.set(name,fn)};
  const dispose=mountAntidumping(root);
  const input=(attr,value)=>handlers.get('input')({target:{value,hasAttribute:k=>k===attr}});
  const choose=value=>handlers.get('click')({target:{closest(){return this},dataset:{adIndustry:value},hasAttribute:k=>k==='data-ad-industry'}});
  const history=()=>nodes.get('[data-ad-history]').innerHTML;
  input('data-ad-origin-country','JPN');assert.match(history(),/A-588-032/);
  assert.ok(!nodes.get('[data-ad-editor]').innerHTML.includes('data-ad-form'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-company'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-stage'));
  input('data-ad-family','steel');assert.match(history(),/data-published-margins/);assert.match(history(),/Tokyo Steel/);
  assert.equal(nodes.get('[data-ad-calculator]').open,false);
  choose('welded-pipe');assert.match(history(),/A-588-857/);assert.ok(!history().includes('A-588-874'));
  input('data-ad-family','tires');assert.ok(!history().includes('A-570-016'));
  input('data-ad-origin-country','CHN');assert.match(history(),/A-570-016/);
  input('data-ad-origin-country','VNM');assert.match(history(),/2026-10-22/);
  input('data-ad-origin-country','JPN');assert.ok(!history().includes('2026-10-22'));
  input('data-ad-origin-country','KOR');input('data-ad-family','power');
  assert.match(nodes.get('[data-ad-editor]').innerHTML,/data-ad-form/);
  dispose();
});

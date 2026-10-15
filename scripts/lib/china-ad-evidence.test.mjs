import test from 'node:test';
import assert from 'node:assert/strict';
import {productVerification,verificationMarkup,adCoverageStatus} from '../../New for anti/policy-simulator/product-verification.mjs';
import {industryMonitor} from '../../New for anti/policy-simulator/industry-monitor.mjs';
import {AD_CATALOG} from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import {mountAntidumping,selectAntidumping} from '../../New for anti/policy-simulator/antidumping-view.mjs';

test('China tyre continuations preserve two regimes, product boundaries and dates without producing rates',()=>{
  const original=JSON.stringify(AD_CATALOG);
  for(const [product,ids,published,effective] of [
    ['tire',['A-570-016','C-570-017'],'2026-07-16','2026-07-07'],
    ['truck-tire',['A-570-040','C-570-041'],'2024-08-29','2024-08-21'],
  ]) {
    const v=productVerification(product,'CHN'),f=v.ad.research.findings[0];
    assert.deepEqual(v.ad.case_ids,ids);assert.equal(v.ad.country,'CHN');assert.equal(v.ad.review,undefined);
    assert.equal(f.published,published);assert.equal(f.continuation_effective_date,effective);
    assert.equal(v.ad.rate_pct,null);assert.equal(v.ad.official_schedule,undefined);
    assert.equal(v.coverage.procedure.state,'orders_continued');
    assert.equal(v.coverage.integration.state,'current_rates_unresolved');
    assert.match(verificationMarkup(product,'CHN'),/명령 유지 효력/);
    const monitor=industryMonitor(product,'CHN');assert.equal(monitor.calculation_enabled,false);
    assert.equal(monitor.events.length,0);assert.ok(monitor.sources.every(s=>!s.url.includes('C-552-829')));
  }
  assert.equal(productVerification('truck-tire','VNM'),null);
  assert.equal(JSON.stringify(AD_CATALOG),original);
});
test('China material search gaps stay unknown and cannot inherit other-origin evidence or become zero',()=>{
  for(const product of ['fiber','carbon-fiber','aramid']) {
    const v=productVerification(product,'CHN');assert.equal(v.checked_on,'2026-10-15');
    assert.equal(v.ad.rate_pct,null);assert.deepEqual(v.ad.case_ids,[]);
    assert.equal(v.coverage.procedure.state,'case_unconfirmed');
    const html=verificationMarkup(product,'CHN');assert.ok(!html.includes('A-580-839'));assert.ok(!html.includes('A-421-805'));assert.ok(!html.includes('A-552-832'));
  }
  assert.equal(productVerification('fiber','CHN').ad.research.findings[0].case_id,'A-570-097');
  assert.equal(productVerification('fiber','CHN').ad.research.findings[0].disposition,'different_product');
  assert.equal(adCoverageStatus('switchgear','CHN').research.state,'not_recorded');
  assert.equal(industryMonitor('switchgear','CHN').status,'origin_not_reviewed');
  assert.equal(adCoverageStatus('aramid','JPN').research.state,'not_recorded');
  const copy=productVerification('tire','CHN');copy.ad.case_ids.pop();
  assert.equal(productVerification('tire','CHN').ad.case_ids.length,2);
});
test('China switch clears Korean computation and separates PVLT, TBT, materials and Vietnamese schedules',()=>{
  selectAntidumping({case_id:'A-580-867',company_id:'hyosung'});
  const nodes=new Map(),handlers=new Map();
  const root={contains:()=>true,querySelector:selector=>{
    if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',open:false,focus(){}});
    return nodes.get(selector);
  },addEventListener:(name,fn)=>handlers.set(name,fn)};
  const dispose=mountAntidumping(root);
  const input=(attr,value)=>handlers.get('input')({target:{value,hasAttribute:k=>k===attr}});
  const choose=value=>handlers.get('click')({target:{closest(){return this},dataset:{adIndustry:value},hasAttribute:k=>k==='data-ad-industry'}});
  const history=()=>nodes.get('[data-ad-history]').innerHTML;
  input('data-ad-origin-country','CHN');input('data-ad-family','tires');
  assert.match(history(),/A-570-016/);assert.ok(!history().includes('C-552-829'));
  assert.ok(!nodes.get('[data-ad-editor]').innerHTML.includes('data-ad-form'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-stage'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-profile'));
  assert.equal(nodes.get('[data-ad-calculator]').open,false);
  choose('truck-tire');assert.match(history(),/A-570-040/);assert.ok(!history().includes('A-570-016'));
  input('data-ad-family','materials');assert.match(history(),/A-570-097/);
  input('data-ad-origin-country','VNM');assert.match(history(),/A-552-832/);assert.ok(!history().includes('A-570-097'));
  input('data-ad-family','tires');assert.match(history(),/2026-10-22/);
  input('data-ad-origin-country','CHN');assert.ok(!history().includes('2026-10-22'));
  input('data-ad-origin-country','KOR');input('data-ad-family','power');
  assert.match(nodes.get('[data-ad-editor]').innerHTML,/data-ad-form/);
  dispose();
});

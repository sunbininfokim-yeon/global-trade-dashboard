import test from 'node:test';
import assert from 'node:assert/strict';
import { industryMonitor, industryMonitorMarkup } from '../../New for anti/policy-simulator/industry-monitor.mjs';
import { COMPANY_INDUSTRIES } from '../../New for anti/policy-simulator/company-profiles.mjs';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import { policyOptions } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { mountAntidumping } from '../../New for anti/policy-simulator/antidumping-view.mjs';

test('all 17 non-calculable industry products expose bounded evidence without activating rates', () => {
  const products=COMPANY_INDUSTRIES.filter(i=>!i.case_id), original=JSON.stringify(AD_CATALOG);
  assert.equal(products.length,17);
  for (const {product} of products) {
    const r=industryMonitor(product), html=industryMonitorMarkup(product);
    assert.ok(r.sources.length>0,product); assert.equal(r.calculation_enabled,false);
    assert.equal(new Set(r.sources.map(s=>s.url)).size,r.sources.length);
    assert.ok(r.sources.every(s=>new URL(s.url).protocol==='https:'));
    assert.match(html,/공식 공고·정책 근거/); assert.match(html,/예치율 계산은 별개/);
    assert.ok(!html.includes('data-ad-stage')); assert.ok(!html.includes('data-ad-form'));
    assert.ok(r.events.every(e=>!('rate_pct' in e)&&!('deposit_rate_pct' in e)));
  }
  assert.equal(JSON.stringify(AD_CATALOG),original); assert.equal(AD_CATALOG.cases.length,5);
});
test('seven auto presets link a Korean 232 implementation notice, distinct from AD and publication date', () => {
  for (const product of ['vehicle','vehicle-hev','vehicle-phev','vehicle-ev','auto-brake','auto-steering','auto-suspension']) {
    const event=industryMonitor(product).events.find(e=>e.kind==='section_232');
    assert.equal(event.document_id,'2025-21940'); assert.equal(event.published,'2025-12-04');
    assert.equal(event.entry_effective_date,'2025-11-01'); assert.equal(event.checked_on,'2026-10-13');
    assert.match(event.note,/AD\/CVD 판정이 아닙니다/);
    assert.equal(policyOptions(product,'KOR')[0].rate,15);
    assert.match(industryMonitorMarkup(product),/대상 통관 적용일: 2025-11-01/);
  }
  const motor=industryMonitor('auto-electric-drive'); assert.equal(motor.events.length,0);
  assert.equal(motor.status,'sources_only'); assert.deepEqual(policyOptions('auto-electric-drive','KOR'),[]);
});
test('OCTG final notice can be monitored without a fabricated cash rate or pipe case inheritance', () => {
  const r=industryMonitor('octg'),html=industryMonitorMarkup('octg');
  assert.equal(r.events.length,1); assert.equal(r.events[0].document_id,'2026-19529');
  assert.deepEqual(r.events[0].case_ids,['A-580-870']); assert.equal(r.events[0].por_start,'2023-09-01');
  assert.match(html,/행정재심 최종결과/); assert.match(html,/현재 예치율로 사용하지 않습니다/);
  assert.ok(!html.includes('A-580-897')); assert.ok(!html.includes('0.80'));
});
test('related cylinder evidence stays contextual, and origin/product switches cannot leak notices', () => {
  const r=industryMonitor('auto-suspension');
  assert.deepEqual(r.events.slice(0,2).map(e=>e.document_id),['2026-19374','2026-18706']);
  assert.ok(r.events.filter(e=>e.kind==='related_scope').every(e=>e.note.includes('단계 확정이 아닙니다')));
  for(const product of ['power-cable','carbon-fiber','truck-tire','auto-electric-drive']) {
    assert.equal(industryMonitor(product).events.length,0);
    const html=industryMonitorMarkup(product); assert.match(html,/목록 미수록/); assert.ok(!html.includes('2025-21940'));
  }
  for (const country of ['CHN','JPN','',null]) {
    assert.equal(industryMonitor('vehicle',country).events.length,0);
    assert.ok(!industryMonitorMarkup('vehicle',country).includes('2025-21940'));
  }
  assert.equal(industryMonitor('<img src=x>'),null);
  const copy=industryMonitor('vehicle'); copy.events[0].title='edited';
  assert.notEqual(industryMonitor('vehicle').events[0].title,'edited');
});

test('mounted industry selection renders non-calculable notices independently and restores curated AD', () => {
  // In-memory rendering harness, no browser/network. Exercise real event handlers and paint.
  const nodes=new Map(), handlers=new Map();
  const root={contains:()=>true, querySelector:selector=>{
    if(!nodes.has(selector)) nodes.set(selector,{innerHTML:'',open:false,focus(){}});
    return nodes.get(selector);
  },addEventListener:(name,fn)=>handlers.set(name,fn)};
  const dispose=mountAntidumping(root);
  const choose=(attribute,value)=>{
    const dataset=attribute==='data-ad-family'?{}:{adIndustry:value};
    const el={value,dataset,hasAttribute:key=>key===attribute,closest(){return this;}};
    handlers.get(attribute==='data-ad-family'?'input':'click')({target:el});
    return root.querySelector('[data-ad-notice-review]').innerHTML;
  };
  choose('data-ad-family','auto');
  assert.match(choose('data-ad-industry','vehicle-hev'),/2025-21940/);
  assert.ok(!root.querySelector('[data-ad-editor]').innerHTML.includes('data-ad-form'));
  assert.ok(!root.querySelector('[data-ad-process]').innerHTML.includes('data-ad-stage'));
  choose('data-ad-family','steel');
  assert.match(choose('data-ad-industry','octg'),/2026-19529/);
  choose('data-ad-family','cables');
  const cable=choose('data-ad-industry','submarine-cable');
  assert.match(cable,/개별 시행·조사 공고 목록 미수록/); assert.ok(!cable.includes('2026-19529'));
  choose('data-ad-family','materials');
  for(const product of ['fiber','carbon-fiber','aramid']) {
    const material=choose('data-ad-industry',product);
    const editor=root.querySelector('[data-ad-history]').innerHTML;
    assert.match(editor,/data-material-research/); assert.match(editor,/품목별 공식 조사 근거 연결/);
    assert.match(editor,/data-coverage-research="product_search_reviewed"/);
    assert.match(editor,/data-coverage-procedure="case_unconfirmed"/);
    assert.ok(!editor.includes('data-ad-form')); assert.equal(industryMonitor(product).events.length,0);
    assert.equal(industryMonitor(product).calculation_enabled,false);
    assert.ok(!root.querySelector('[data-ad-process]').innerHTML.includes('data-ad-stage'));
    assert.ok(!material.includes('2026-19529'));
    assert.ok(industryMonitor(product).sources.some(s=>s.kind==='AD/CVD 관련 원문'));
  }
  choose('data-ad-family','power');
  assert.match(root.querySelector('[data-ad-notice-review]').innerHTML,/A-580-867/);
  assert.match(root.querySelector('[data-ad-editor]').innerHTML,/data-ad-form/);
  dispose();
});

test('Vietnam origin switches quarantine Korean case, firm, rate and stage UI and restore Korea', () => {
  const nodes=new Map(),handlers=new Map();
  const root={contains:()=>true,querySelector:selector=>{
    if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',open:false,focus(){}});
    return nodes.get(selector);
  },addEventListener:(name,fn)=>handlers.set(name,fn)};
  const dispose=mountAntidumping(root);
  const input=(attribute,value)=>handlers.get('input')({target:{value,hasAttribute:k=>k===attribute}});
  const choose=value=>handlers.get('click')({target:{closest(){return this},dataset:{adIndustry:value},hasAttribute:k=>k==='data-ad-industry'}});
  input('data-ad-origin-country','VNM');
  assert.ok(!nodes.get('[data-ad-editor]').innerHTML.includes('data-ad-form'));
  input('data-ad-family','tires');
  assert.match(nodes.get('[data-ad-history]').innerHTML,/C-552-829/);
  assert.match(nodes.get('[data-ad-history]').innerHTML,/2026-10-22/);
  assert.ok(!nodes.get('[data-ad-history]').innerHTML.includes('A-580-908'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-company'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-profile'));
  assert.ok(!nodes.get('[data-ad-process]').innerHTML.includes('data-ad-stage'));
  assert.ok(!nodes.get('[data-ad-editor]').innerHTML.includes('data-ad-form'));
  choose('truck-tire');
  assert.ok(!nodes.get('[data-ad-history]').innerHTML.includes('C-552-829'));
  input('data-ad-family','materials');
  assert.match(nodes.get('[data-ad-history]').innerHTML,/A-552-832/);
  assert.ok(!nodes.get('[data-ad-history]').innerHTML.includes('A-580-839'));
  input('data-ad-origin-country','KOR');
  assert.match(nodes.get('[data-ad-history]').innerHTML,/A-580-839/);
  input('data-ad-family','power');
  assert.match(nodes.get('[data-ad-editor]').innerHTML,/data-ad-form/);
  assert.match(nodes.get('[data-ad-notice-review]').innerHTML,/A-580-867/);
  dispose();
});

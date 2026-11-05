import test from 'node:test';
import assert from 'node:assert/strict';
import {SOLVENT_MANUFACTURERS,solventManufacturers} from '../../New for anti/policy-simulator/solvent-manufacturers.mjs';
import {COMPANY_PROFILES,COMPANY_INDUSTRIES,companyCalibration,companyADLink} from '../../New for anti/policy-simulator/company-profiles.mjs';
import {INDUSTRIAL_CASES,INDUSTRIAL_IDENTITIES,industrialCases,industrialResearchStatus,industrialEvidenceMarkup} from '../../New for anti/policy-simulator/refractory-solvents-evidence.mjs';
import {PRODUCTS,policyOptions} from '../../New for anti/policy-simulator/policy-catalog.mjs';
import {lookupRemedy,simulateRemedy} from '../../New for anti/policy-simulator/trade-remedy-model.mjs';
import {mountAntidumping} from '../../New for anti/policy-simulator/antidumping-view.mjs';

test('manufacturers join only verified products while trader and product origins remain independent',()=>{
 assert.equal(SOLVENT_MANUFACTURERS.length,4);assert.equal(Object.keys(COMPANY_PROFILES).length,46);
 assert.deepEqual(solventManufacturers('acetone').map(m=>m.id),['kumho-pnb']);
 assert.deepEqual(solventManufacturers('dimethylformamide').map(m=>m.official_name),['聊城鲁西甲胺化工有限公司']);
 assert.equal(solventManufacturers('dimethyl-carbonate')[0].role,'manufacturer_group');
 assert.deepEqual(solventManufacturers('methyl-ethyl-ketone'),[]);
 assert.ok(!COMPANY_INDUSTRIES.find(p=>p.product==='isopropyl-alcohol').profiles.includes('foosung-corporation'));
 for(const m of SOLVENT_MANUFACTURERS){
  const firm=COMPANY_PROFILES[m.id];assert.equal(firm.financial,null);assert.equal(firm.ad,null);assert.equal(firm.product_origin,null);
  for(const p of m.products){
   const g=COMPANY_INDUSTRIES.find(g=>g.product===p.product);assert.ok(g.profiles.includes(m.id));
   assert.equal(companyCalibration(m.id,p.product).selected_product_source.url,p.source.url);
   assert.equal(companyCalibration(m.id,p.product).selected_product_source.checked_on,'2026-11-05');
   assert.equal(companyADLink(m.id,p.product),null);assert.deepEqual(policyOptions(p.product,'CHN'),[]);
  }
 }
 assert.equal(companyCalibration('foosung-corporation','acetone').selected_product_source.checked_on,'2026-11-04');
 const copy=solventManufacturers('acetone');copy[0].products[0].source.url='https://invalid.example';assert.ok(!solventManufacturers('acetone')[0].products[0].source.url.includes('invalid'));
});
test('MIBK Chinese published rates cannot become MEK, acetone or US company cash-deposit quotes',()=>{
 const r=industrialCases('methyl-isobutyl-ketone','KOR','CHN')[0];
 assert.equal(r.effective_date,'2024-03-20');assert.deepEqual(r.published_rates.map(v=>v.amount),[18.5,32.3]);
 assert.equal(r.published_rates[0].profile,'kumho-pnb');assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);
 assert.equal(industrialResearchStatus(r.product,'KOR','CHN').state,'official_measure_publication_identified');
 assert.equal(industrialCases(r.product,'CHN','CHN').length,0);assert.equal(industrialCases(r.product,'KOR','USA').length,0);
 assert.equal(industrialCases('methyl-ethyl-ketone','KOR','CHN').length,0);
 const html=industrialEvidenceMarkup(r.product,'KOR');assert.match(html,/18.5 %/);assert.match(html,/data-published-duty-reference/);assert.match(html,/후속 변경·거래 적용 미확인/);
 assert.equal(lookupRemedy({import_country:'CHN',product:r.product,origin:'KOR'}).status,'unresolved');assert.throws(()=>simulateRemedy({import_country:'CHN'}),/다른 수입국/);
});
test('Indian IPA initiation and Chinese-product duty publication have independent origin scope, units and procedure stages',()=>{
 const kr=industrialCases('isopropyl-alcohol','KOR','IND')[0],cn=industrialCases('isopropyl-alcohol','CHN','IND')[0];
 assert.equal(kr.stage,'investigation_in_progress');assert.equal(kr.scope_reference.classification_is_dispositive,false);
 assert.equal(kr.scope_reference.jurisdiction,'IND');assert.equal(PRODUCTS['isopropyl-alcohol'].hts,'');
 assert.equal(kr.steps.at(-1)[1],'unknown');assert.equal(kr.published_rates,undefined);
 assert.equal(cn.published_rates[0].amount,82);assert.equal(cn.published_rates[0].unit,'USD/MT');assert.equal(cn.published_rates[0].export_country,'CHN');
 assert.equal(cn.published_rates[0].profile,undefined);assert.equal(cn.rate_pct,null);assert.equal(cn.steps.at(-1)[1],'unknown');
 assert.equal(industrialResearchStatus(kr.product,'KOR','IND').state,'official_investigation_identified');
 assert.equal(industrialResearchStatus(cn.product,'CHN','IND').state,'official_measure_publication_identified');
 assert.equal(industrialCases(kr.product,'KOR','USA').length,0);assert.equal(industrialCases(kr.product,'CHN','USA').length,0);
 for(const c of INDUSTRIAL_CASES){assert.equal(c.rate_pct,null);assert.equal(c.calculation_ready,false);}
});
test('manufacturer identity and product-specific sources render without pretending a sales company manufactures all products',()=>{
 assert.equal(INDUSTRIAL_IDENTITIES['methyl-isobutyl-ketone'].cas,'108-10-1');assert.equal(INDUSTRIAL_IDENTITIES['methyl-ethyl-ketone'].cas,'78-93-3');
 assert.equal(INDUSTRIAL_IDENTITIES['isopropyl-alcohol'].cas,'67-63-0');assert.equal(INDUSTRIAL_IDENTITIES['dimethyl-carbonate'].cas,'616-38-6');
 assert.match(industrialEvidenceMarkup('acetone','KOR'),/data-solvent-manufacturer="kumho-pnb"/);
 const dmf=industrialEvidenceMarkup('dimethylformamide','CHN');assert.match(dmf,/聊城鲁西甲胺化工有限公司/);assert.match(dmf,/2025 연차보고서/);
 const ipa=industrialEvidenceMarkup('isopropyl-alcohol','KOR');assert.match(ipa,/이수스페셜티케미컬/);assert.ok(!ipa.includes('foosungcorp.com'));
 const dmc=industrialEvidenceMarkup('dimethyl-carbonate','CHN');assert.match(dmc,/제조기업 그룹/);assert.match(dmc,/제품 원산지 별도 확인/);
});
test('mounted manufacturer selections reset prior US calculations and keep foreign proceedings in read-only evidence',()=>{
 const nodes=new Map(),handlers={};const root={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',focus(){},classList:{add(){}}});return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 let opened;const clean=mountAntidumping(root,{openCompany:(...args)=>opened=args});
 const send=(type,attr,value,dataset={})=>{const el={value,dataset,hasAttribute:k=>k===attr,closest(){return this;}};handlers[type].forEach(f=>f({target:el}));};
 send('input','data-ad-family','chemicals');
 for(const [product,profile,expected] of [['methyl-isobutyl-ketone','kumho-pnb','MOFCOM 2024'],['isopropyl-alcohol','isu-specialty-chemical','6/62/2026-DGTR'],['dimethyl-carbonate','shida-shenghua','시다승화'],['dimethylformamide','liaocheng-luxi-methylamine','랴오청 루시']]){
  send('click','data-ad-industry',null,{adIndustry:product});send('click','data-ad-related-origin',null,{adRelatedOrigin:'KOR'});
  send('click','data-ad-profile',null,{adProfile:profile});send('click','data-ad-open-company',null);
  assert.deepEqual(opened,[profile,product]);assert.match(nodes.get('[data-ad-notice-review]').innerHTML,new RegExp(expected));assert.ok(!nodes.get('[data-ad-editor]').innerHTML.includes('data-ad-form'));
 }
 clean();
});

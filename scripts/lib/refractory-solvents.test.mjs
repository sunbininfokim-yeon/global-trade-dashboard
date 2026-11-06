import test from 'node:test';
import assert from 'node:assert/strict';
import {INDUSTRIAL_PRODUCTS,INDUSTRIAL_CASES,industrialCases,industrialEvidenceMarkup,industrialImportRequirements,industrialResearchStatus,industrialComparisonEvidence,INDUSTRIAL_SOURCE_EXCLUSIONS,verifiedEmptyComparison,USITC_COMPARISON_EVIDENCE,INDUSTRIAL_IDENTITIES} from '../../New for anti/policy-simulator/refractory-solvents-evidence.mjs';
import {COMPANY_PROFILES,COMPANY_INDUSTRIES,companyADLink,companyCalibration} from '../../New for anti/policy-simulator/company-profiles.mjs';
import {PRODUCTS,policyOptions} from '../../New for anti/policy-simulator/policy-catalog.mjs';
import {productVerification,adCoverageStatus} from '../../New for anti/policy-simulator/product-verification.mjs';
import {simulateRemedy,lookupRemedy,REMEDY_QUOTES} from '../../New for anti/policy-simulator/trade-remedy-model.mjs';
import {AD_CATALOG} from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import {mountAntidumping,selectAntidumping,antidumpingMarkup} from '../../New for anti/policy-simulator/antidumping-view.mjs';
import {REMEDY_MONITOR_CATALOG} from '../../New for anti/policy-simulator/remedy-monitor-catalog.mjs';

test('source-backed companies expose three refractory and twelve separate solvent products, without invented business inputs',()=>{
 assert.equal(INDUSTRIAL_PRODUCTS.length,15);
 for(const p of INDUSTRIAL_PRODUCTS){const group=COMPANY_INDUSTRIES.find(g=>g.product===p.id),firm=COMPANY_PROFILES[p.profile];assert.equal(group.case_id,null);assert.ok(group.profiles.includes(p.profile));assert.equal(firm.financial,null);assert.equal(firm.ad,null);assert.equal(firm.product_origin,null);assert.equal(firm.product_price,null);assert.equal(companyADLink(p.profile,p.id),null);assert.equal(companyCalibration(p.profile,p.id).selected_product_source.checked_on,p.checked_on||'2026-11-04');assert.equal(PRODUCTS[p.id].hts,'');assert.deepEqual(policyOptions(p.id,'CHN'),[]);assert.deepEqual(policyOptions(p.id,'KOR'),[]);}
 assert.match(COMPANY_PROFILES['foosung-corporation'].note,/제조사와 구분/);
});
test('importing market, origin, and product are all needed to match a proceeding',()=>{
 assert.equal(industrialCases('ethyl-acetate','CHN','KOR').length,1);assert.equal(industrialCases('ethyl-acetate','CHN','USA').length,0);
 assert.equal(industrialCases('magnesia-carbon-bricks','CHN','USA').length,2);assert.equal(industrialCases('magnesia-carbon-bricks','KOR','USA').length,0);
 assert.equal(industrialCases('high-alumina-bricks','CHN','USA').length,0);assert.equal(industrialCases('monolithic-refractories','CHN','USA').length,0);
 assert.equal(industrialCases('acetone','KOR','USA')[0].case_id,'A-580-899');assert.equal(industrialCases('acetone','CHN','USA').length,0);
});
test('sunset/rescission facts never become company cash rates or blanket revocation',()=>{
 const rows=industrialCases('magnesia-carbon-bricks','CHN','USA');for(const r of rows){assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);assert.equal(r.steps[0][1],'confirmed');assert.equal(r.steps[1][1],'unknown');assert.equal(r.steps[2][1],'unknown');assert.equal(r.company_application,'unconfirmed');}
 assert.match(rows[0].note,/명령 철회가 아니며/);assert.equal(AD_CATALOG.cases.length,5);assert.equal(REMEDY_QUOTES.length,6);assert.equal(REMEDY_MONITOR_CATALOG.cases.length,13);
 rows[0].steps[0][1]='unknown';assert.equal(industrialCases('magnesia-carbon-bricks','CHN','USA')[0].steps[0][1],'confirmed');
});
test('Korean EA initiation is separate from American coverage and cannot create a final rate or full process',()=>{
 const r=industrialCases('ethyl-acetate','CHN','KOR')[0];assert.equal(r.date,'2026-08-18');assert.equal(r.steps.filter(s=>s[1]==='confirmed').length,1);assert.equal(r.rate_pct,null);
 assert.equal(adCoverageStatus('ethyl-acetate','CHN').procedure.state,'unconfirmed');assert.deepEqual(productVerification('ethyl-acetate','CHN').ad.case_ids,[]);
 for(const product of ['methyl-ethyl-ketone','dimethylformamide']){assert.equal(adCoverageStatus(product,'CHN').research.state,'bounded_search_no_confirmed_case');assert.equal(adCoverageStatus(product,'CHN').procedure.state,'unconfirmed');assert.equal(productVerification(product,'CHN').ad.rate_pct,null);}
});
test('American verification uses the exact origin and cannot claim an old Korea roster reviewed new products',()=>{
 assert.deepEqual(productVerification('magnesia-carbon-bricks','CHN').ad.case_ids,['A-570-954','C-570-955']);
 const wrong=productVerification('magnesia-carbon-bricks','KOR');assert.deepEqual(wrong.ad.case_ids,[]);assert.equal(wrong.ad.review,undefined);assert.equal(wrong.checked_on,'2026-11-04');
 assert.deepEqual(productVerification('acetone','KOR').ad.case_ids,['A-580-899']);assert.equal(productVerification('acetone','CHN').ad.rate_pct,null);
});
test('foreign-jurisdiction rates are rejected by the US calculation boundary',()=>{
 assert.equal(lookupRemedy({import_country:'KOR'}).status,'unresolved');assert.throws(()=>simulateRemedy({import_country:'KOR'}),/다른 수입국/);
 for(const r of INDUSTRIAL_CASES)assert.equal(r.rate_pct,null);
});
test('related-market markup labels mismatched origins and supplies working controls only in AD view',()=>{
 const wrong=industrialEvidenceMarkup('magnesia-carbon-bricks','KOR');assert.match(wrong,/현재 선택 원산지와 다름/);assert.ok(!wrong.includes('data-evidence-stage="confirmed"'));assert.match(wrong,/data-ad-related-origin="CHN"/);
 const right=industrialEvidenceMarkup('magnesia-carbon-bricks','CHN');assert.match(right,/중국산 → 미국 수입/);assert.match(right,/data-evidence-stage="confirmed"/);
 const kr=industrialEvidenceMarkup('ethyl-acetate','CHN');assert.match(kr,/중국산 → 한국 수입/);assert.match(kr,/구제23-2026-6호/);assert.ok(!kr.includes('미국 수입 · AD'));
 const company=industrialEvidenceMarkup('ethyl-acetate','KOR',{originControls:false});assert.ok(!company.includes('data-ad-related-origin'));assert.match(company,/위 제품 원산지 입력/);
});
test('mounted industry/company selection and related-origin controls reset computation while showing the correct market',()=>{
 selectAntidumping({case_id:'A-580-867',company_id:'hyosung'});
 const nodes=new Map(),handlers={};const root={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',focus(){},classList:{add(){}}});return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 let opened;const clean=mountAntidumping(root,{openCompany:(...args)=>{opened=args;}});
 const send=(type,attr,value,dataset={})=>{const el={value,dataset,hasAttribute:k=>k===attr,closest(){return this;}};handlers[type].forEach(f=>f({target:el}));};
 send('input','data-ad-family','refractories');assert.match(root.querySelector('[data-ad-process]').innerHTML,/조선내화/);
 send('click','data-ad-related-origin',null,{adRelatedOrigin:'CHN'});assert.match(root.querySelector('[data-ad-process]').innerHTML,/data-ad-profile="chosun-refractories"/);send('click','data-ad-profile',null,{adProfile:'chosun-refractories'});assert.match(root.querySelector('[data-ad-history]').innerHTML,/조선내화/);send('click','data-ad-open-company',null);assert.deepEqual(opened,['chosun-refractories','magnesia-carbon-bricks']);assert.match(root.querySelector('[data-ad-notice-review]').innerHTML,/A-570-954/);assert.ok(!root.querySelector('[data-ad-editor]').innerHTML.includes('data-ad-form'));assert.ok(!root.querySelector('[data-ad-process]').innerHTML.includes('data-ad-stage'));
 send('input','data-ad-family','chemicals');assert.match(root.querySelector('[data-ad-notice-review]').innerHTML,/중국산 → 한국 수입/);assert.match(root.querySelector('[data-ad-notice-review]').innerHTML,/구제23-2026-6호/);
 send('click','data-ad-industry',null,{adIndustry:'methyl-ethyl-ketone'});assert.ok(!root.querySelector('[data-ad-notice-review]').innerHTML.includes('구제23-2026-6호'));
 send('click','data-ad-related-origin',null,{adRelatedOrigin:'KOR'});assert.match(root.querySelector('[data-ad-process]').innerHTML,/후성코퍼레이션/);clean();
});

test('Mexican brick AD is selectable without inheriting Chinese CVD or unrelated company rates',()=>{
 assert.deepEqual(industrialCases('magnesia-carbon-bricks','MEX','USA').map(r=>[r.case_id,r.duty]),[['A-201-837','AD']]);
 assert.deepEqual(productVerification('magnesia-carbon-bricks','MEX').ad.case_ids,['A-201-837']);
 const html=industrialEvidenceMarkup('magnesia-carbon-bricks','MEX');assert.match(html,/멕시코산 → 미국 수입/);assert.match(html,/2021-17790/);
 selectAntidumping({case_id:'A-580-867',company_id:'hyosung'});
 const nodes=new Map(),handlers={};const root={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',focus(){},classList:{add(){}}});return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 const clean=mountAntidumping(root);assert.match(antidumpingMarkup(),/value="MEX"/);
 const send=(type,attr,value,dataset={})=>{const el={value,dataset,hasAttribute:k=>k===attr,closest(){return this;}};handlers[type].forEach(f=>f({target:el}));};
 send('input','data-ad-family','refractories');send('click','data-ad-related-origin',null,{adRelatedOrigin:'MEX'});
 assert.match(root.querySelector('[data-ad-origin]').textContent,/멕시코/);assert.match(root.querySelector('[data-ad-process]').innerHTML,/조선내화/);assert.ok(!root.querySelector('[data-ad-editor]').innerHTML.includes('data-ad-form'));clean();
});
test('Indian historical recommendations preserve price-floor versus specific-duty units and cannot become current US quotes',()=>{
 const mek=industrialCases('methyl-ethyl-ketone','CHN','IND')[0],dmf=industrialCases('dimethylformamide','CHN','IND')[0];
 assert.equal(mek.reported_values[0].kind,'historical_reference_price_recommendation');assert.equal(mek.reported_values[0].amount,1147.06);assert.equal(mek.reported_values[0].unit,'USD/MT');
 assert.deepEqual(dmf.reported_values.map(v=>v.amount),[377.21,405.75]);
 assert.equal(mek.stage,'historical_measure_termination_reported');assert.equal(mek.termination_date,'2021-04-23');assert.equal(mek.steps[1][1],'confirmed');assert.equal(dmf.stage,'historical_recommendation');assert.equal(dmf.steps[1][1],'unknown');
 for(const row of [mek,dmf]){assert.equal(row.rate_pct,null);assert.equal(row.calculation_ready,false);assert.equal(industrialCases(row.product,'CHN','USA').length,0);assert.equal(lookupRemedy({import_country:'IND',product:row.product,origin:'CHN'}).status,'unresolved');}
 const html=industrialEvidenceMarkup('methyl-ethyl-ketone','CHN');assert.match(html,/중국산 → 인도 수입/);assert.match(html,/1,147.06 USD\/MT/);assert.match(html,/기준가격 권고/);assert.match(html,/기존 조치 종료 보고/);
});
test('import compliance frameworks remain conditional and never become a blanket China ban or duty quote',()=>{
 const chemicals=industrialImportRequirements('dimethylformamide','CHN');assert.deepEqual(chemicals.map(r=>r.id),['us-section301-check','us-uflpa','us-tsca']);
 for(const r of chemicals){assert.equal(r.import_country,'USA');assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);}
 assert.deepEqual(industrialImportRequirements('magnesia-carbon-bricks','MEX'),[]);assert.deepEqual(industrialImportRequirements('dimethylformamide','KOR').map(r=>r.id),['us-tsca']);
 assert.ok(!industrialImportRequirements('magnesia-carbon-bricks','CHN').some(r=>r.id==='us-tsca'));
 const copy=industrialCases('dimethylformamide','CHN','IND')[0];copy.reported_values[0].amount=0;assert.equal(industrialCases('dimethylformamide','CHN','IND')[0].reported_values[0].amount,377.21);
});

test('research distinguishes unresearched, bounded misses, investigation and specific terminated measures',()=>{
 const r=(p,o,m)=>industrialResearchStatus(p,o,m);
 assert.equal(r('high-alumina-bricks','CHN','USA').state,'not_researched');assert.equal(r('high-alumina-bricks','CHN','USA').checked_on,null);
 assert.equal(r('methyl-ethyl-ketone','CHN','USA').state,'bounded_search_no_confirmed_case');assert.match(r('methyl-ethyl-ketone','CHN','USA').note,/ACCESS.*오류/);
 assert.equal(r('dimethylformamide','CHN','KOR').state,'bounded_search_no_confirmed_case');assert.match(r('dimethylformamide','CHN','KOR').note,/KTC 내부 품목 검색/);
 assert.equal(r('ethyl-acetate','CHN','KOR').state,'official_investigation_identified');assert.equal(r('magnesia-carbon-bricks','CHN','USA').state,'official_case_identified');
 assert.equal(r('methyl-ethyl-ketone','CHN','IND').state,'specific_measure_termination_reported');assert.equal(r('dimethylformamide','CHN','IND').state,'historical_recommendation_only');
 assert.equal(r('methyl-ethyl-ketone','JPN','CHN').state,'specific_measure_terminated');
 for(const [p,o,m] of [['methyl-ethyl-ketone','CHN','USA'],['methyl-ethyl-ketone','CHN','IND'],['methyl-ethyl-ketone','JPN','CHN']]){const row=r(p,o,m);assert.equal(row.absence_confirmed,false);assert.equal(row.rate_pct,null);assert.equal(row.calculation_ready,false);}
 assert.equal(r('methyl-ethyl-ketone',null,'CHN').state,'not_researched');
 const html=industrialEvidenceMarkup('methyl-ethyl-ketone','CHN');assert.match(html,/data-industrial-research-status/);assert.match(html,/WTO 공식 보고/);assert.ok(!industrialCases('methyl-ethyl-ketone','CHN','USA').length);
});
test('Japanese MEK termination is a Chinese import case and Korean precursor listing is not an AD rate or first-group approval',()=>{
 const r=industrialCases('methyl-ethyl-ketone','JPN','CHN')[0];assert.equal(r.date,'2019-11-21');assert.equal(r.stage,'measure_terminated');assert.equal(r.rate_pct,null);assert.equal(industrialCases('methyl-ethyl-ketone','CHN','CHN').length,0);
 const rule=industrialImportRequirements('methyl-ethyl-ketone','CHN').find(r=>r.id==='kr-mek-precursor');assert.equal(rule.import_country,'KOR');assert.equal(rule.origin_specific,false);assert.equal(rule.rate_pct,null);assert.match(rule.note,/1군.*2군/);
 assert.ok(!industrialImportRequirements('dimethylformamide','CHN').some(r=>r.id==='kr-mek-precursor'));
});

test('official KTC empty searches have query confirmation and a positive control, not failure-as-zero',()=>{
 for(const p of ['methyl-ethyl-ketone','dimethylformamide']){
  const rows=industrialComparisonEvidence(p);assert.ok(rows.length>=3);for(const r of rows){assert.equal(verifiedEmptyComparison(r),true);assert.equal(r.checked_on,'2026-11-05');assert.equal(r.absence_confirmed,false);assert.ok(r.sha256?.match(/^[a-f0-9]{64}$/));}
  const r=rows[0];assert.equal(verifiedEmptyComparison({...r,http_status:403}),false);assert.equal(verifiedEmptyComparison({...r,expected_table_present:false}),false);assert.equal(verifiedEmptyComparison({...r,result_count:null}),false);assert.equal(verifiedEmptyComparison({...r,query_echo_verified:false}),false);assert.equal(verifiedEmptyComparison({...r,positive_control:{observed_first_page_rows:0}}),false);
 }
 assert.equal(industrialResearchStatus('methyl-ethyl-ketone','CHN','KOR').checked_on,'2026-11-05');assert.equal(industrialResearchStatus('methyl-ethyl-ketone','CHN','USA').checked_on,'2026-11-05');
 assert.equal(INDUSTRIAL_SOURCE_EXCLUSIONS[0].data_as_of,'2014-11-03');assert.equal(INDUSTRIAL_SOURCE_EXCLUSIONS[0].status,'excluded_stale');
});
test('EA importer participation, Korean scope and petitioner allegation remain separate from an executable duty',()=>{
 const r=industrialCases('ethyl-acetate','CHN','KOR')[0];assert.equal(r.checked_on,'2026-11-05');assert.equal(r.company_roles[0].profile,'foosung-corporation');assert.equal(r.company_roles[0].role,'domestic_importer');assert.equal(r.company_roles[0].submitted,'2026-09-21');assert.equal(r.company_application,'unconfirmed');
 assert.equal(r.scope_reference.hsk,'2915.31.0000');assert.equal(r.scope_reference.jurisdiction,'KOR');assert.equal(r.scope_reference.classification_is_dispositive,false);assert.equal(PRODUCTS['ethyl-acetate'].hts,'');
 assert.equal(r.alleged_values[0].amount,28.8);assert.equal(r.alleged_values[0].kind,'petitioner_alleged_dumping_margin');assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);assert.equal(r.steps.filter(s=>s[1]==='confirmed').length,1);
 assert.deepEqual([r.investigation_period.start,r.investigation_period.end],['2025-01-01','2025-12-31']);assert.equal(r.investigation_period.may_be_adjusted,true);
 const html=industrialEvidenceMarkup('ethyl-acetate','CHN');assert.match(html,/국내수입자 답변서 제출/);assert.match(html,/28.80%.*확정·잠정 관세 아님/);assert.match(html,/data-petitioner-allegation/);assert.ok(!html.includes('28.80 USD'));
});

test('USITC JSON searches preserve a successful control and remain distinct from Commerce order coverage',()=>{
 assert.equal(USITC_COMPARISON_EVIDENCE.length,6);
 for(const p of ['methyl-ethyl-ketone','dimethylformamide']){
  const rows=industrialComparisonEvidence(p,'USA');assert.equal(rows.length,3);
  for(const r of rows){assert.equal(verifiedEmptyComparison(r),true);assert.equal(r.positive_control.query,'magnesia carbon bricks');assert.equal(verifiedEmptyComparison({...r,expected_result_structure:false}),false);assert.equal(verifiedEmptyComparison({...r,empty_cases_array:false}),false);assert.equal(verifiedEmptyComparison({...r,http_status:429}),false);assert.equal(r.absence_confirmed,false);}
  const r=industrialResearchStatus(p,'CHN','USA');assert.match(r.label,/USITC/);assert.match(r.note,/상무부 명령 전수 판정이 아닙니다/);assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);assert.equal(r.checked_on,'2026-11-05');
  assert.match(industrialEvidenceMarkup(p,'CHN'),/data-substance-identity/);assert.equal(productVerification(p,'CHN').checked_on,'2026-11-05');
 }
 assert.equal(INDUSTRIAL_IDENTITIES['methyl-ethyl-ketone'].cas,'78-93-3');assert.equal(INDUSTRIAL_IDENTITIES.dimethylformamide.cas,'68-12-2');assert.ok(!INDUSTRIAL_IDENTITIES['methyl-ethyl-ketone'].aliases.includes('MIBK'));assert.ok(!INDUSTRIAL_IDENTITIES.dimethylformamide.aliases.includes('Dimethyl fumarate'));
});

const addedSolvents=['dimethyl-carbonate','toluene','methanol','perchloroethylene','chloroform','trichloroethylene'];
test('additional official-catalog solvents stay selectable without borrowing EA or acetone duties or changing old evidence dates',()=>{
 for(const product of addedSolvents){
  assert.equal(COMPANY_INDUSTRIES.find(p=>p.product===product).profiles[0],'foosung-corporation');
  assert.equal(companyCalibration('foosung-corporation',product).selected_product_source.checked_on,'2026-11-05');
  assert.deepEqual(industrialCases(product),[]);assert.deepEqual(productVerification(product,'CHN').ad.case_ids,[]);
  assert.equal(productVerification(product,'CHN').ad.rate_pct,null);assert.equal(companyADLink('foosung-corporation',product),null);
  assert.deepEqual(policyOptions(product,'CHN'),[]);assert.equal(PRODUCTS[product].hts,'');
  const rows=industrialComparisonEvidence(product,'KOR');assert.equal(rows.length,1);assert.ok(verifiedEmptyComparison(rows[0]));
  assert.equal(industrialResearchStatus(product,'CHN','KOR').state,'bounded_search_no_confirmed_case');
  assert.match(industrialResearchStatus(product,'CHN','KOR').note,/한정된 품명 검색/);
  assert.equal(industrialResearchStatus(product,'JPN','KOR').state,'not_researched');
 }
 assert.equal(companyCalibration('foosung-corporation','acetone').selected_product_source.checked_on,'2026-11-04');
 assert.equal(industrialCases('acetone','KOR','USA')[0].checked_on,'2026-11-04');
});
test('a failed US solvent query remains unavailable instead of a zero-result success or a government pending decision',()=>{
 const rows=industrialComparisonEvidence('dimethyl-carbonate','USA'),r=industrialResearchStatus('dimethyl-carbonate','CHN','USA');
 assert.equal(rows.length,1);assert.equal(rows[0].http_status,503);assert.equal(rows[0].result_count,null);assert.equal(verifiedEmptyComparison(rows[0]),false);
 assert.equal(r.state,'search_unavailable');assert.equal(r.absence_confirmed,false);assert.equal(r.rate_pct,null);
 assert.equal(adCoverageStatus('dimethyl-carbonate','CHN').research.state,'search_unavailable');assert.equal(adCoverageStatus('dimethyl-carbonate','CHN').procedure.state,'unconfirmed');
 assert.equal(industrialResearchStatus('toluene','CHN','USA').state,'not_researched');
 const html=industrialEvidenceMarkup('dimethyl-carbonate','CHN');assert.match(html,/HTTP 503/);assert.match(html,/data-research-state="search_unavailable"/);assert.match(html,/data-research-state="bounded_search_no_confirmed_case"/);
});
test('PCE final compliance extension and TCE proposed extension remain different regulations without an AD rate or blanket China-only ban',()=>{
 const pce=industrialImportRequirements('perchloroethylene','CHN').find(r=>r.id==='us-pce-risk-management');
 const tce=industrialImportRequirements('trichloroethylene','KOR').find(r=>r.id==='us-tce-risk-management');
 assert.deepEqual(pce.events.map(e=>e.stage),['final','final']);assert.deepEqual(tce.events.map(e=>e.stage),['final','postponed_conditions','proposed']);
 assert.equal(tce.events[2].date,'2026-10-14');assert.match(tce.note,/확정 규칙이 아닙니다/);assert.match(tce.note,/전체 금지 해제가 아닙니다/);
 assert.match(pce.note,/2027-06-21/);assert.match(pce.note,/전면 수입금지가 아닙니다/);
 for(const rule of [pce,tce]){assert.equal(rule.origin_specific,false);assert.equal(rule.checked_on,'2026-11-05');assert.equal(rule.rate_pct,null);assert.equal(rule.calculation_ready,false);}
 assert.ok(!industrialImportRequirements('chloroform','CHN').some(r=>r.id==='us-pce-risk-management'||r.id==='us-tce-risk-management'));
 assert.match(industrialEvidenceMarkup('trichloroethylene','CHN'),/기한 연장 제안/);
});
test('mounted solvent selection replaces unrelated process evidence and never enables a fabricated calculator',()=>{
 const nodes=new Map(),handlers={};const root={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',focus(){},classList:{add(){}}});return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 const clean=mountAntidumping(root);
 const send=(type,attr,value,dataset={})=>{const el={value,dataset,hasAttribute:k=>k===attr,closest(){return this;}};handlers[type].forEach(f=>f({target:el}));};
 send('input','data-ad-family','chemicals');
 for(const product of addedSolvents){
  send('click','data-ad-industry',null,{adIndustry:product});
  assert.match(root.querySelector('[data-ad-process]').innerHTML,/후성코퍼레이션/);
  const html=root.querySelector('[data-ad-notice-review]').innerHTML;assert.ok(!html.includes('구제23-2026-6호'));assert.ok(!html.includes('A-580-899'));
  assert.ok(!root.querySelector('[data-ad-editor]').innerHTML.includes('data-ad-form'));
 }
 assert.match(root.querySelector('[data-ad-notice-review]').innerHTML,/TCE 용도별 금지/);clean();
});

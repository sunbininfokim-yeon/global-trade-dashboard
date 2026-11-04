import test from 'node:test';
import assert from 'node:assert/strict';
import {INDUSTRIAL_PRODUCTS,INDUSTRIAL_CASES,industrialCases,industrialEvidenceMarkup,industrialImportRequirements} from '../../New for anti/policy-simulator/refractory-solvents-evidence.mjs';
import {COMPANY_PROFILES,COMPANY_INDUSTRIES,companyADLink,companyCalibration} from '../../New for anti/policy-simulator/company-profiles.mjs';
import {PRODUCTS,policyOptions} from '../../New for anti/policy-simulator/policy-catalog.mjs';
import {productVerification,adCoverageStatus} from '../../New for anti/policy-simulator/product-verification.mjs';
import {simulateRemedy,lookupRemedy,REMEDY_QUOTES} from '../../New for anti/policy-simulator/trade-remedy-model.mjs';
import {AD_CATALOG} from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import {mountAntidumping,selectAntidumping,antidumpingMarkup} from '../../New for anti/policy-simulator/antidumping-view.mjs';
import {REMEDY_MONITOR_CATALOG} from '../../New for anti/policy-simulator/remedy-monitor-catalog.mjs';

test('two source-backed companies expose three refractory and four separate solvent products, without invented business inputs',()=>{
 assert.equal(INDUSTRIAL_PRODUCTS.length,7);
 for(const p of INDUSTRIAL_PRODUCTS){const group=COMPANY_INDUSTRIES.find(g=>g.product===p.id),firm=COMPANY_PROFILES[p.profile];assert.equal(group.case_id,null);assert.ok(group.profiles.includes(p.profile));assert.equal(firm.financial,null);assert.equal(firm.ad,null);assert.equal(firm.product_origin,null);assert.equal(firm.product_price,null);assert.equal(companyADLink(p.profile,p.id),null);assert.equal(companyCalibration(p.profile,p.id).selected_product_source.checked_on,'2026-11-04');assert.equal(PRODUCTS[p.id].hts,'');assert.deepEqual(policyOptions(p.id,'CHN'),[]);assert.deepEqual(policyOptions(p.id,'KOR'),[]);}
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
 for(const product of ['methyl-ethyl-ketone','dimethylformamide']){assert.equal(adCoverageStatus(product,'CHN').research.state,'company_product_confirmed');assert.equal(adCoverageStatus(product,'CHN').procedure.state,'unconfirmed');assert.equal(productVerification(product,'CHN').ad.rate_pct,null);}
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
 for(const row of [mek,dmf]){assert.equal(row.stage,'historical_recommendation');assert.equal(row.rate_pct,null);assert.equal(row.calculation_ready,false);assert.equal(row.steps[1][1],'unknown');assert.equal(industrialCases(row.product,'CHN','USA').length,0);assert.equal(lookupRemedy({import_country:'IND',product:row.product,origin:'CHN'}).status,'unresolved');}
 const html=industrialEvidenceMarkup('methyl-ethyl-ketone','CHN');assert.match(html,/중국산 → 인도 수입/);assert.match(html,/1,147.06 USD\/MT/);assert.match(html,/기준가격 권고/);assert.match(html,/현행 미확인/);
});
test('import compliance frameworks remain conditional and never become a blanket China ban or duty quote',()=>{
 const chemicals=industrialImportRequirements('dimethylformamide','CHN');assert.deepEqual(chemicals.map(r=>r.id),['us-section301-check','us-uflpa','us-tsca']);
 for(const r of chemicals){assert.equal(r.import_country,'USA');assert.equal(r.rate_pct,null);assert.equal(r.calculation_ready,false);}
 assert.deepEqual(industrialImportRequirements('magnesia-carbon-bricks','MEX'),[]);assert.deepEqual(industrialImportRequirements('dimethylformamide','KOR').map(r=>r.id),['us-tsca']);
 assert.ok(!industrialImportRequirements('magnesia-carbon-bricks','CHN').some(r=>r.id==='us-tsca'));
 const copy=industrialCases('dimethylformamide','CHN','IND')[0];copy.reported_values[0].amount=0;assert.equal(industrialCases('dimethylformamide','CHN','IND')[0].reported_values[0].amount,377.21);
});

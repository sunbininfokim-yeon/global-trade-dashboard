import test from 'node:test';
import assert from 'node:assert/strict';
import {supplierObservations,supplierObservationMarkup,parseMarketInputs,parseCompanyInputs} from '../../New for anti/policy-simulator/observed-inputs.mjs';
import {SUPPLIER_SNAPSHOT} from '../../New for anti/policy-simulator/suppliers-2025.mjs';
import {REMEDY_MONITOR_CATALOG,scheduleReviews} from '../../New for anti/policy-simulator/remedy-monitor-catalog.mjs';
const ev={url:'https://www.census.gov/example',note:'Test fixture, scope/valuation reviewed'};
const market=()=>({schema_version:1,product:'transformer',currency:'USD',valuation:'purchaser_expenditure_including_tariffs',scope_reviewed:true,coverage_reviewed:true,coverage_note:'Test complete market, no overlap',period:{start:'2025-01-01',end:'2025-12-31'},rows:[{country:'USA',purchase_usd:2000000,measure:'domestic_sales_in_us',evidence:ev},{country:'KOR',purchase_usd:1000000,measure:'imports_converted_to_purchaser_expenditure',evidence:ev}]});
test('DataWeb observations use displayed subtotal, never full-market share or domestic zero',()=>{const o=supplierObservations(SUPPLIER_SNAPSHOT,'transformer');assert.equal(o.rows.length,8);assert.equal(o.world_total_usd,null);assert.equal(o.domestic_us_sales_usd,null);assert.ok(Math.abs(o.rows.reduce((a,r)=>a+r.displayed_subtotal_share_pct,0)-100)<1e-8);assert.equal(o.rows[0].customs_value_usd,798931853);assert.match(supplierObservationMarkup(SUPPLIER_SNAPSHOT,'transformer'),/미국 전체 수입·시장 점유율이 아닙니다/);assert.equal(supplierObservations(SUPPLIER_SNAPSHOT,'missing'),null);});
test('market import requires same scope/period/valuation and domestic US sales, provenance remains user reviewed',()=>{const v=parseMarketInputs(market(),'transformer',['USA','KOR']);assert.deepEqual(v.rows.map(r=>r.expenditure),[2,1]);assert.equal(v.provenance.status,'user_reviewed_not_independently_verified');for(const patch of [{product:'tire'},{currency:'KRW'},{valuation:'customs_value'},{scope_reviewed:false}])assert.throws(()=>parseMarketInputs({...market(),...patch},'transformer',['USA','KOR']));const m=market();m.rows[0].measure='shipments_total';assert.throws(()=>parseMarketInputs(m,'transformer',['USA','KOR']));m.rows.shift();assert.throws(()=>parseMarketInputs(m,'transformer',['USA','KOR']));});
test('transaction import never derives unit cost from company financials and rejects entity/origin/unit mismatches',()=>{const v={schema_version:1,company:'Exact legal entity',product:'transformer',origin:'KOR',currency:'USD',quantity_unit:'unit',cost_scope:'same_product_period_allocated',price_basis:'customs_value_per_unit',period:market().period,price:100,quantity:10,cost:70,fixed_cost:10,evidence:ev};const r=parseCompanyInputs(v,v.company,v.product,v.origin);assert.equal(r.cost,'70');assert.equal(r.transaction_evidence.status,'user_supplied_not_independently_verified');for(const patch of [{company:'Another entity'},{origin:'VNM'},{quantity_unit:''},{cost_scope:'consolidated_margin'},{cost:null}])assert.throws(()=>parseCompanyInputs({...v,...patch},v.company,v.product,v.origin));});
test('13 confirmed AD/CVD cases are isolated; time alone cannot complete a result',()=>{assert.equal(REMEDY_MONITOR_CATALOG.cases.length,13);assert.equal(new Set(REMEDY_MONITOR_CATALOG.cases.map(c=>c.case_id)).size,13);for(const c of REMEDY_MONITOR_CATALOG.cases){assert.ok(c.product);assert.equal(c.duty,c.case_id[0]==='C'?'CVD':'AD');}assert.ok(!REMEDY_MONITOR_CATALOG.cases.some(c=>['A-588-032','A-552-828','A-552-832'].includes(c.case_id)));assert.equal(scheduleReviews('2026-10-21')[0].status,'planned_not_completed');assert.equal(scheduleReviews('2026-10-22')[0].status,'due_requires_official_result_or_extension');});

test('mounted country import applies reviewed purchases and retains provenance in the actual calculation',async()=>{
 const {mount}=await import('../../New for anti/policy-simulator/view.mjs');
 const nodes=new Map(),handlers={};const node=()=>({innerHTML:'',textContent:'',hidden:false,checked:false,disabled:false,classList:{add(){},toggle(){}}});
 const body={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 const root={contains:()=>true,querySelector:()=>body,querySelectorAll:()=>[],addEventListener(){}};
 const cleanup=mount(root);body.querySelector('[data-market-import]').value=JSON.stringify(market());
 const button={dataset:{},hasAttribute:k=>k==='data-market-apply',closest(){return this;}};
 handlers.click.forEach(f=>f({target:button}));assert.match(body.querySelector('[data-editor]').innerHTML,/사용자 검토자료 연결/);
 handlers.input.forEach(f=>f({target:{dataset:{key:'policy_confirmed'},checked:true}}));
 handlers.submit.forEach(f=>f({target:{matches:()=>true,elements:[]},preventDefault(){}}));
 assert.match(body.querySelector('[data-results]').innerHTML,/국가별|공급 변화/);assert.doesNotMatch(body.querySelector('[data-results]').innerHTML,/NaN/);cleanup();
});
test('mounted company import fills only same-context transaction values',async()=>{
 const {mountCompany,selectCompanyProfile}=await import('../../New for anti/policy-simulator/company-view.mjs');selectCompanyProfile('hyosung');
 const nodes=new Map(),handlers={};const root={contains:()=>true,querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',hidden:false,checked:false,classList:{add(){}}});return nodes.get(s);},querySelectorAll:()=>[],addEventListener(t,f){(handlers[t]??=[]).push(f);}};
 const cleanup=mountCompany(root,{});handlers.input.forEach(f=>f({target:{hasAttribute:()=>false,dataset:{companyKey:'origin'},value:'KOR'}}));
 const v={schema_version:1,company:'효성중공업',product:'transformer',origin:'KOR',currency:'USD',quantity_unit:'unit',cost_scope:'same_product_period_allocated',price_basis:'customs_value_per_unit',period:market().period,price:100,quantity:10,cost:70,fixed_cost:10,evidence:ev};
 root.querySelector('[data-company-import]').value=JSON.stringify(v);const button={hasAttribute:k=>k==='data-company-apply',closest(){return this;}};
 handlers.click.forEach(f=>f({target:button}));assert.match(root.querySelector('[data-company-editor]').innerHTML,/사용자 거래자료 연결/);assert.match(root.querySelector('[data-company-editor]').innerHTML,/value="70"/);cleanup();
});

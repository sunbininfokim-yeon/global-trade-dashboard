import test from 'node:test';
import assert from 'node:assert/strict';
import { basisMarkup, marketCalibration } from '../../New for anti/policy-simulator/default-basis.mjs';
import { initialDraft, modelInput, SUPPLIER_SNAPSHOT } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { simulate } from '../../New for anti/policy-simulator/country-model.mjs';
import { simulateCompany } from '../../New for anti/policy-simulator/company-model.mjs';
import { simulateDeposit, depositPer100k } from '../../New for anti/policy-simulator/antidumping-model.mjs';
import { markup } from '../../New for anti/policy-simulator/view.mjs';
import { companyMarkup } from '../../New for anti/policy-simulator/company-view.mjs';
import { antidumpingMarkup, selectAntidumping } from '../../New for anti/policy-simulator/antidumping-view.mjs';

const country = product => {
  const d=initialDraft(product); d.policy_confirmed=true;
  d.rows[1].scenario_policy='manual'; d.rows[1].manual_after=25;
  return d;
};
const company = overrides => ({company:'테스트',product:'transformer',origin:'KOR',policy_confirmed:true,price:100,quantity:10000,cost:70,fixed_cost:100000,
  cost_change_pct:0,tariff_before:15,tariff_after:25,absorption_pct:50,price_elasticity:2,locked_share_pct:0,competitor_change_pct:0,market_change_pct:0,capacity:'',response_mode:'manual',...overrides});
const ad = overrides => ({reference_mode:'published',case_id:'A-580-867',company_id:'hyosung',entry_date:'2026-10-11',entered_value_usd:'1000000',scenario_rate_pct:'9.32',annual_finance_pct:'5',holding_days:'365',scope_confirmed:true,identity_confirmed:true,...overrides});

test('official supplier observations cannot silently become observed market shares or domestic supply', () => {
  const d=country('transformer'), input=modelInput(d), m=input.calibration.market_calibration;
  assert.deepEqual(d.rows.map(r=>r.expenditure),[50,25,25]); assert.ok(d.rows.every(r=>r.purchase_origin==='editable_example'));
  assert.equal(m.applied,false); assert.equal(m.domestic_supply,null); assert.equal(m.comparable_market_shares,null);
  assert.equal(m.supplier_reference.year,2025); assert.match(m.note,/편집한 구매액은 실측.*검증되지/);
  d.rows[1].expenditure=999; assert.equal(modelInput(d).calibration.market_calibration.status,'not_calibrated');
  assert.equal(marketCalibration('auto-brake',SUPPLIER_SNAPSHOT).supplier_reference,null);
});
test('joint range includes baseline and preserves literature eta/sigma while supply variation stays assumed', () => {
  const d=country('transformer'), input=modelInput(d), old=structuredClone(input), r=simulate(input), envelope=r.scenario_range;
  assert.equal(envelope.trials.length,27); assert.equal(envelope.calculated+envelope.unavailable,27);
  assert.deepEqual(envelope.axes.sigma.values,[2,3.5,5]); assert.deepEqual(envelope.axes.eta.values,[-.25,-.15,-.05]);
  assert.equal(envelope.axes.supply_multiplier.kind,'user_assumption');
  const focus=r.rows.find(x=>x.country==='KOR');
  assert.ok(envelope.volume_change_pct.min<=focus.volume_change_pct+1e-8); assert.ok(envelope.volume_change_pct.max>=focus.volume_change_pct-1e-8);
  assert.match(envelope.note,/신뢰구간.*아닙니다/); assert.deepEqual(input,old);
  const trial=envelope.trials.find(t=>t.sigma===2&&t.eta===-.25&&t.supply_multiplier===.5);
  const independent=simulate({...input,sigma:2,eta:-.25,rows:input.rows.map(row=>({...row,supply_elasticity:row.supply_elasticity*.5}))},false);
  assert.ok(Math.abs(trial.volume_change_pct-independent.rows.find(x=>x.country==='KOR').volume_change_pct)<1e-8);
  assert.equal(independent.scenario_range,undefined);
});
test('edited parameters drop literature ranges and sensitivity axes stay inside input bounds', () => {
  const d=country('transformer'); d.sigma=20; d.eta=-.05; d.elasticity_overrides={sigma:true,eta:true};
  const r=simulate(modelInput(d));
  assert.equal(r.scenario_range.axes.sigma.kind,'user_assumption'); assert.equal(r.scenario_range.axes.eta.kind,'user_assumption');
  assert.ok(r.scenario_range.axes.sigma.values.every(x=>x>=.1&&x<=20));
  assert.ok(r.scenario_range.axes.eta.values.every(x=>x>=-10&&x<=-.05));
  assert.ok(r.scenario_range.trials.length<=27);
});
test('company three responses remain scenarios and blank capacity is explicitly unbounded', () => {
  const input=company(),r=simulateCompany(input);
  assert.equal(r.capacity_status,'unbounded_assumption'); assert.equal(r.input_basis.response,'user_assumption');
  assert.deepEqual(r.response_scenarios.map(s=>s.absorption_pct),[0,50,100]);
  for(const s of r.response_scenarios) assert.equal(s.profit_after,simulateCompany(company({absorption_pct:s.absorption_pct})).profit_after);
  const capped=simulateCompany(company({capacity:10000})); assert.equal(capped.capacity_status,'user_supplied_cap');
  const d=country('transformer'); d.rows[1].manual_after=25;
  const proxy=simulateCompany(company({response_mode:'country',country_inputs:modelInput(d)}));
  assert.equal(proxy.input_basis.response,'country_average_proxy'); assert.deepEqual(proxy.response_scenarios,[]);
});
test('100k deposit reference uses exact rate arithmetic, never rounded actual deposits or unresolved rates', () => {
  const r=simulateDeposit(ad()); assert.equal(r.normalized_reference.reference_deposit_usd,'4320.00');
  assert.equal(r.normalized_reference.scenario_deposit_usd,'9320.00'); assert.equal(r.reference_deposit_usd,'43200.00');
  const tiny=simulateDeposit(ad({entered_value_usd:'0.01'}));
  assert.equal(tiny.reference_deposit_usd,'0.00'); assert.equal(tiny.normalized_reference.reference_deposit_usd,'4320.00');
  assert.equal(depositPer100k('0'),'0.00'); assert.equal(depositPer100k('1.555555'),'1555.56');
  assert.throws(()=>depositPer100k('-1'));
  const unknown=simulateDeposit(ad({company_id:'unknown'})); assert.equal(unknown.status,'unresolved'); assert.equal(unknown.normalized_reference,undefined);
  const future=simulateDeposit(ad({entry_date:'2026-10-14'})); assert.equal(future.status,'unresolved');
});
test('rendered forms explain example basis; AD unit quote is selected-firm only', () => {
  const html=markup(); assert.match(html,/실제 시장 보정 미완료/); assert.match(html,/data-row-purchase-basis/);
  assert.match(companyMarkup(),/업계 평균·회사 실증값이 아닙니다/);
  const escaped=basisMarkup([{label:'<img src=x>',kind:'official_reference',note:'<script>'}]);
  assert.ok(!escaped.includes('<img')); assert.match(escaped,/&lt;script&gt;/);
  assert.ok(!antidumpingMarkup().includes('data-ad-unit-reference'));
  selectAntidumping({case_id:'A-580-867',company_id:'hyosung'});
  assert.match(antidumpingMarkup(),/신고가격 10만 USD당 예치 참고액: \$4,320.00/);
  selectAntidumping({case_id:'A-580-897',company_id:'aju'});
  assert.match(antidumpingMarkup(),/10만 USD당 예치 참고액: 미확인/);
});

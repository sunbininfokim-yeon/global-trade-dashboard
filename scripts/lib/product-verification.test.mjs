import test from 'node:test';
import assert from 'node:assert/strict';
import { KOREA_AD_REVIEW, PRODUCT_VERIFICATIONS, productVerification, verificationMarkup } from '../../New for anti/policy-simulator/product-verification.mjs';
import { PRODUCTS, policyOptions, initialDraft, newRow, tariffPair, modelInput } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { simulate } from '../../New for anti/policy-simulator/country-model.mjs';
import { companyADLink } from '../../New for anti/policy-simulator/company-profiles.mjs';

test('bounded Korean roster review is auditable, never a no-duty determination or another-origin result', () => {
  assert.equal(new Set(KOREA_AD_REVIEW.case_ids).size,51); assert.equal(KOREA_AD_REVIEW.pages_reviewed,6);
  assert.ok(KOREA_AD_REVIEW.case_ids.includes('A-580-870')); assert.ok(KOREA_AD_REVIEW.case_ids.includes('C-580-913'));
  for (const [product, row] of Object.entries(PRODUCT_VERIFICATIONS)) {
    assert.equal(productVerification(product).ad.rate_pct,null);
    assert.equal(productVerification(product,'CHN').ad.status,'origin_not_reviewed');
    assert.equal(productVerification(product,'JPN').ad.rate_pct,null);
    assert.equal(productVerification(product,'').ad.status,'origin_not_reviewed');
    assert.equal(productVerification(product,'USA').ad.case_ids.length,0);
    if (row.ad.status === 'reviewed_no_direct_match') assert.match(row.ad.note,/면제나 0% 판정이 아닙니다/);
  }
  const cloned=productVerification('auto-brake'); cloned.ad.review.case_ids.pop(); assert.equal(KOREA_AD_REVIEW.case_ids.length,51);
});
test('three representative part specifications use verified part headings and never inherit complete-car or Chinese tariffs', () => {
  const specs={'auto-brake':'8708.30.50','auto-steering':'8708.94.50.00','auto-suspension':'8708.80.16'};
  for (const [product, code] of Object.entries(specs)) {
    assert.equal(PRODUCTS[product].hts,code); assert.equal(PRODUCTS[product].mfn,2.5);
    assert.equal(productVerification(product).classification.hts,code);
    for (const [country,heading] of [['KOR','9903.94.63'],['JPN','9903.94.43']]) {
      const choice=policyOptions(product,country)[0]; assert.equal(choice.rate,15); assert.match(choice.condition,/33\(g\)/);
      assert.ok(choice.sources.some(s=>s.url.includes(heading))); assert.ok(!choice.sources.some(s=>/9903\.94\.(61|41)$/.test(s.url)));
      assert.equal(tariffPair(product,newRow(product,country)).tariff_before,15);
    }
    for (const country of ['CHN','MEX','CAN','ROW','DEU']) assert.deepEqual(policyOptions(product,country),[]);
    const draft=initialDraft(product); assert.throws(()=>modelInput(draft),/적용 조건/);
    draft.policy_confirmed=true; draft.rows[1].scenario_policy='manual'; draft.rows[1].manual_after=30;
    const result=simulate(modelInput(draft));
    assert.equal(result.inputs.calibration.supplier_source,null);
    assert.equal(result.inputs.calibration.supplier_statistics_year,null);
    assert.ok(result.inputs.calibration.product_verification.some(v=>v.ad.country==='KOR'&&v.ad.rate_pct===null));
    assert.equal(companyADLink('hl-mando',product),null);
  }
});
test('inverter/motor ambiguity and related cylinder investigation cannot supply a fabricated AD rate or stage', () => {
  assert.equal(PRODUCTS['auto-electric-drive'].hts,''); assert.deepEqual(policyOptions('auto-electric-drive','KOR'),[]);
  assert.equal(productVerification('auto-electric-drive').classification.status,'specification_required');
  const cylinder=productVerification('auto-suspension');
  assert.equal(cylinder.ad.status,'related_scope_review_required'); assert.equal(cylinder.ad.rate_pct,null);
  assert.ok(cylinder.ad.sources.some(s=>s.url.includes('2026-19374')));
  assert.match(verificationMarkup('auto-suspension'),/HL만도를 조사 대상으로 확정하지/);
});
test('OCTG final margins remain separate from ambiguous cash instructions, other steel cases and firm selection', () => {
  const r=productVerification('octg'); assert.equal(r.ad.status,'official_case_confirmed_deposit_unresolved');
  assert.equal(r.ad.document_id,'2026-19529'); assert.equal(r.ad.por_start,'2023-09-01');
  assert.equal(r.ad.margins.find(m=>m.official_name==='SeAH Steel Corporation').margin_pct,'9.80');
  assert.equal(r.ad.rate_pct,null); assert.equal(companyADLink('ad-seah','octg'),null);
  assert.equal(productVerification('welded-pipe'),null); assert.ok(!verificationMarkup('octg','CHN').includes('9.80'));
});

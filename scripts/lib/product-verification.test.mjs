import test from 'node:test';
import assert from 'node:assert/strict';
import { KOREA_AD_REVIEW, PRODUCT_VERIFICATIONS, productVerification, verificationMarkup, adCoverageStatus, coverageStatusMarkup } from '../../New for anti/policy-simulator/product-verification.mjs';
import { PRODUCTS, policyOptions, initialDraft, newRow, tariffPair, modelInput } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { simulate } from '../../New for anti/policy-simulator/country-model.mjs';
import { companyADLink } from '../../New for anti/policy-simulator/company-profiles.mjs';

test('bounded Korean roster review is auditable, never a no-duty determination or another-origin result', () => {
  assert.equal(new Set(KOREA_AD_REVIEW.case_ids).size,51); assert.equal(KOREA_AD_REVIEW.pages_reviewed,6);
  assert.ok(KOREA_AD_REVIEW.case_ids.includes('A-580-870')); assert.ok(KOREA_AD_REVIEW.case_ids.includes('C-580-913'));
  for (const [product, row] of Object.entries(PRODUCT_VERIFICATIONS)) {
    assert.equal(productVerification(product).ad.rate_pct,null);
    assert.equal(productVerification(product,'DEU').ad.status,'origin_not_reviewed');
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

test('advanced material research preserves mismatches and historical revocation without creating applicable cases', () => {
  for (const product of ['fiber','carbon-fiber','aramid']) {
    const r=productVerification(product), html=verificationMarkup(product);
    assert.equal(r.checked_on,'2026-10-14'); assert.equal(r.ad.review.checked_on,'2026-10-12');
    assert.equal(r.ad.status,'bounded_search_no_confirmed_case'); assert.equal(r.ad.rate_pct,null);
    assert.deepEqual(r.ad.case_ids,[]); assert.ok(r.ad.research.terms.length>=2);
    assert.match(html,/품목별 조사 근거/); assert.match(html,/면제나 0% 판정이 아닙니다/);
    assert.match(html,/전수 재조회는 미실행/); assert.equal(companyADLink('hs-materials',product),null);
    for (const origin of ['NLD','DEU','CAN','',null]) {
      const other=productVerification(product,origin);
      assert.equal(other.ad.status,'origin_not_reviewed'); assert.equal(other.ad.research,undefined);
      assert.ok(!verificationMarkup(product,origin).includes('data-material-research'));
    }
  }
  const aramid=productVerification('aramid').ad.research.findings[0];
  assert.equal(aramid.country,'NLD'); assert.equal(aramid.case_id,'A-421-805');
  assert.equal(aramid.disposition,'historical_other_origin_revoked');
  assert.equal(aramid.published,'2001-03-13'); assert.equal(aramid.revoked_effective_date,'2000-01-01');
  assert.equal(productVerification('fiber').ad.research.findings[0].disposition,'different_product');
  assert.equal(productVerification('carbon-fiber').ad.research.findings.length,0);
  const copy=productVerification('aramid'); copy.ad.research.findings[0].country='KOR';
  assert.equal(productVerification('aramid').ad.research.findings[0].country,'NLD');
});

test('coverage separates our investigation and integration gaps from official decisions without inventing pending proceedings', () => {
  const unreviewed=adCoverageStatus('aramid','DEU');
  assert.equal(unreviewed.research.state,'not_recorded'); assert.equal(unreviewed.checked_on,null);
  assert.equal(adCoverageStatus('not-in-catalog').research.state,'not_recorded');
  const roster=adCoverageStatus('switchgear'), materials=adCoverageStatus('aramid');
  assert.equal(roster.research.state,'roster_reviewed'); assert.equal(roster.checked_on,'2026-10-12');
  assert.equal(materials.research.state,'product_search_reviewed'); assert.equal(materials.checked_on,'2026-10-14');
  for (const r of [roster,materials]) {
    assert.equal(r.procedure.state,'case_unconfirmed'); assert.equal(r.integration.state,'not_ready');
    assert.match(r.procedure.note,/판정 대기로 확인된 상태가 아닙니다/);
  }
  const related=adCoverageStatus('auto-suspension');
  assert.equal(related.procedure.state,'related_case_scope_unresolved');
  const octg=productVerification('octg');
  assert.equal(octg.coverage.procedure.state,'final_published');
  assert.equal(octg.coverage.integration.state,'deposit_interpretation_pending'); assert.equal(octg.ad.rate_pct,null);
  const html=coverageStatusMarkup('octg');
  assert.match(html,/data-coverage-procedure="final_published"/); assert.match(html,/정부의 최종결과 대기가 아닙니다/);
  assert.match(verificationMarkup('aramid','DEU'),/조사 기록 없음/);
  assert.ok(!verificationMarkup('aramid','DEU').includes('자료 확인 2026-10-14'));
});

test('Vietnam review separates CVD sunset, historical AD termination and annual review schedule without rates', () => {
  const r=productVerification('tire','VNM');
  assert.equal(r.ad.country,'VNM');assert.equal(r.ad.review,undefined);assert.equal(r.ad.rate_pct,null);
  assert.deepEqual(r.ad.case_ids,['C-552-829']);assert.equal(r.coverage.procedure.state,'official_schedule_recorded');
  assert.equal(r.ad.official_schedule.por_start,'2024-01-01');assert.equal(r.ad.official_schedule.announced_for,'2026-10-22');
  assert.equal(r.ad.research.findings.find(f=>f.disposition==='cvd_sunset').published,'2026-10-05');
  assert.equal(r.ad.research.findings.find(f=>f.disposition==='historical_ad_terminated').published,'2021-06-23');
  assert.equal(productVerification('fiber','VNM').ad.research.findings[0].case_id,'A-552-832');
  assert.equal(productVerification('fiber','VNM').ad.research.findings[0].disposition,'different_product');
  for(const product of ['fiber','carbon-fiber','aramid']) {
    const v=productVerification(product,'VNM');assert.equal(v.coverage.procedure.state,'case_unconfirmed');
    assert.equal(v.checked_on,'2026-10-15');assert.deepEqual(v.ad.case_ids,[]);assert.equal(v.ad.rate_pct,null);
    assert.ok(!verificationMarkup(product,'VNM').includes('A-421-805'));
  }
  assert.equal(adCoverageStatus('truck-tire','VNM').research.state,'not_recorded');
});

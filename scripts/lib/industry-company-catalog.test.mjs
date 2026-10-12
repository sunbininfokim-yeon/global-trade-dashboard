import test from 'node:test';
import assert from 'node:assert/strict';
import { AD_CATALOG } from '../../New for anti/policy-simulator/antidumping-catalog.mjs';
import { COMPANY_INDUSTRIES, COMPANY_PROFILES, INDUSTRY_FAMILIES, companyADLink, companyCalibration } from '../../New for anti/policy-simulator/company-profiles.mjs';
import { PRODUCTS, policyOptions, initialDraft, elasticityCalibration } from '../../New for anti/policy-simulator/policy-catalog.mjs';
import { lookupAD, simulateDeposit } from '../../New for anti/policy-simulator/antidumping-model.mjs';
import { reviewRecords, reviewProgress, createADExample } from '../../New for anti/policy-simulator/antidumping-guide.mjs';

const pipe = AD_CATALOG.cases.find(c => c.case_id === 'A-580-897');
const lookup = company_id => lookupAD({ case_id: pipe.case_id, company_id, entry_date: AD_CATALOG.checked_on });
test('official pipe appendix retains 21 nonselected identities without limiting by size or merging affiliates', () => {
  const names = ['AJU Besteel Co., Ltd.', 'Chang Won Bending Co., Ltd.', 'Daiduck Piping Co., Ltd.', 'Dong Yang Steel Pipe Co., Ltd.', 'Dongbu Incheon Steel Co., Ltd.', 'EEW KHPC Co., Ltd.', 'EEW Korea Co., Ltd.', 'Geumok Tech. Co. Ltd.', 'Hansol Metal Co. Ltd.', 'HiSteel Co., Ltd.', 'Husteel Co., Ltd.', 'Hyundai RB Co., Ltd.', 'Il Jin Nts Co. Ltd.', 'Kiduck Industries Co., Ltd.', 'Kum Kang Kind. Co., Ltd.', 'Kumsoo Connecting Co., Ltd.', 'Nexteel Co., Ltd.', 'Seonghwa Industrial Co., Ltd.', 'SIN-E B&P Co., Ltd.', 'Steel Flower Co., Ltd.', 'WELTECH Co., Ltd.'];
  assert.deepEqual(pipe.companies.slice(2).map(c => c.official_name), names);
  assert.equal(pipe.companies.length, 23);
  assert.equal(new Set(pipe.companies.map(c => c.id)).size, 23);
  assert.equal(lookup('Hyundai RB Co., Ltd.').company.id, 'hyundai-rb');
  assert.equal(lookup('Hyundai Steel Company').status, 'unresolved');
});
test('assigned historical margins never become an unverified cash deposit or a fabricated zero', () => {
  for (const c of pipe.companies.slice(2)) {
    const r = lookup(c.id);
    assert.equal(r.margin_pct, '0.80'); assert.equal(r.rate_pct, null); assert.equal(r.status, 'unresolved');
    assert.equal(r.document.document_id, '2026-08489'); assert.equal(r.effective, undefined);
    const result = simulateDeposit({ case_id: pipe.case_id, company_id: c.id, entry_date: AD_CATALOG.checked_on, scope_confirmed: true, identity_confirmed: true });
    assert.equal(result.reference_deposit_usd, null);
    assert.equal(createADExample({ case_id: pipe.case_id, company_id: c.id, entry_date: AD_CATALOG.checked_on }).values.scenario_rate_pct, '');
  }
  assert.equal(lookup('hyundai-pipe').rate_pct, '0'); assert.equal(lookup('seah').rate_pct, '0.80');
});
test('next pipe POR partitions 15 rescissions and 6 continuing nonselected firms; neither shares respondent selection', () => {
  let rescinded = 0, continuing = 0;
  for (const c of pipe.companies.slice(2)) {
    const [current, latest, historical] = reviewRecords(pipe.case_id, c.id), p = reviewProgress(pipe.case_id, latest.id);
    assert.equal(current.por_start, '2025-05-01'); assert.equal(reviewProgress(pipe.case_id, current.id).latest_stage, 'initiation');
    assert.equal(latest.por_start, '2024-05-01'); assert.equal(historical.por_start, '2023-05-01');
    assert.equal(p.stages.find(s => s.id === 'selection').state, 'unknown');
    assert.equal(p.stages.find(s => s.id === 'final').state, 'unknown');
    assert.equal(p.deposit, undefined);
    if (p.status === 'rescinded') {
      rescinded++; assert.equal(p.latest_stage, 'rescinded'); assert.equal(p.stages.find(s => s.id === 'preliminary').state, 'unknown');
      assert.equal(p.status_event.source, '2026-15399');
      assert.match(p.status_event.note, /0%判定|0% 판정/);
    } else {
      continuing++; assert.equal(p.latest_stage, 'preliminary'); assert.match(p.stages.find(s => s.id === 'preliminary').event.note, /0.80%/);
    }
    assert.equal(reviewProgress(pipe.case_id, historical.id).deposit, undefined);
  }
  assert.equal(rescinded, 15); assert.equal(continuing, 6);
});
test('LG Chem SAP official zero begins at the final effective date and does not cover other chemicals or firms', () => {
  const ctx = { case_id: 'A-580-914', company_id: 'lg-chem' };
  assert.equal(lookupAD({ ...ctx, entry_date: '2026-09-24' }).rate_pct, null);
  const r = lookupAD({ ...ctx, entry_date: '2026-09-25' });
  assert.equal(r.rate_pct, '0'); assert.equal(r.document.document_id, '2026-19625'); assert.equal(r.por_start, '2023-12-01');
  assert.equal(lookupAD({ ...ctx, company_id: 'another', entry_date: '2026-10-11' }).rate_pct, null);
  assert.equal(companyADLink('ad-lg-chem', 'aramid'), null);
});
test('six core industrial families plus existing autos preserve distinct products and evidence gaps', () => {
  assert.equal(INDUSTRY_FAMILIES.length, 7); assert.equal(COMPANY_INDUSTRIES.length, 22);
  for (const industry of COMPANY_INDUSTRIES) {
    assert.ok(PRODUCTS[industry.product]); assert.ok(INDUSTRY_FAMILIES.some(f => f.id === industry.family));
    assert.ok(industry.profiles.length); assert.ok(industry.profiles.every(id => COMPANY_PROFILES[id]));
  }
  for (const product of ['power-cable', 'submarine-cable', 'industrial-cable', 'carbon-fiber', 'aramid', 'sap', 'octg', 'truck-tire', 'hot-rolled', 'welded-pipe']) {
    assert.equal(PRODUCTS[product].hts, ''); assert.equal(PRODUCTS[product].elasticity, undefined); assert.deepEqual(policyOptions(product, 'KOR'), []);
    assert.equal(elasticityCalibration(initialDraft(product)).sigma.kind, 'user_assumption');
  }
  assert.equal(companyADLink('ad-seah', 'octg'), null);
  assert.equal(companyADLink('hankook', 'truck-tire'), null);
  assert.equal(companyADLink('hyosung', 'switchgear'), null);
  assert.equal(companyADLink('ad-seah', 'welded-pipe').company_id, 'seah');
  assert.equal(companyCalibration('ad-seah', 'octg').selected_product_source.url, 'https://www.seahsteel.co.kr/eng/application/oil-gas.asp');
});
test('all curated notice entities have selectable profiles with source provenance and no invented financials', () => {
  for (const c of AD_CATALOG.cases) {
    const industry = COMPANY_INDUSTRIES.find(x => x.case_id === c.case_id);
    assert.equal(industry.profiles.length, c.companies.length);
    for (const entity of c.companies) {
      const p = Object.values(COMPANY_PROFILES).find(p => p.ad?.case_id === c.case_id && p.ad?.company_id === entity.id);
      assert.ok(p); assert.ok(industry.profiles.includes(p.id));
      assert.equal(p.product_price, null); assert.equal(p.product_origin, null);
      if (p.financial === null) {
        assert.match(p.source.url, /^https:\/\/www.govinfo.gov\//); assert.equal(p.official_name, entity.official_name);
        const cloned = companyCalibration(p.id).public_company_context; cloned.source.title = 'modified'; assert.notEqual(p.source.title, cloned.source.title);
      }
    }
  }
  assert.ok(pipe.featured_company_ids.length <= 8);
  assert.ok(Object.values(COMPANY_PROFILES).every(p => p.market_share == null && p.domestic_rank == null));
});

test('automotive company and product boundaries do not inherit unrelated AD cases or fabricated input data', () => {
  const auto = COMPANY_INDUSTRIES.filter(x => x.family === 'auto');
  assert.equal(auto.length, 8);
  assert.deepEqual(auto.filter(x => x.profiles.includes('hyundai-motor')).map(x => x.product), ['vehicle','vehicle-hev','vehicle-phev','vehicle-ev']);
  for (const group of auto) for (const id of group.profiles) {
    assert.equal(group.case_id, null); assert.equal(companyADLink(id, group.product), null);
    assert.equal(COMPANY_PROFILES[id].product_origin, null); assert.equal(COMPANY_PROFILES[id].product_price, null);
    if (id !== 'kia') assert.equal(COMPANY_PROFILES[id].financial, null);
  }
  assert.match(companyCalibration('hyundai-motor','vehicle-phev').selected_product_source.url, /hyundai\.com/);
  assert.match(companyCalibration('hl-mando','auto-steering').selected_product_source.url, /hlmando\.com/);
  for (const p of ['auto-brake','auto-steering','auto-suspension','auto-electric-drive']) {
    if (p === 'auto-electric-drive') { assert.equal(PRODUCTS[p].hts, ''); assert.deepEqual(policyOptions(p,'KOR'), []); }
    else { assert.ok(PRODUCTS[p].hts); assert.equal(policyOptions(p,'KOR')[0].rate, 15); }
    assert.equal(elasticityCalibration(initialDraft(p)).sigma.kind,'user_assumption');
  }
});

const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.SIMULATOR_PREVIEW_URL || 'http://127.0.0.1:8773';
if (new URL(base).hostname !== '127.0.0.1') throw new Error('Only loopback preview may be tested.');
(async () => {
  const { COMPANY_PROFILES, COMPANY_INDUSTRIES } = await import('../../New for anti/policy-simulator/company-profiles.mjs');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message)); page.on('request', r => requests.push(r.url()));
    const field = name => page.getByLabel(name, { exact: true });
    const click = name => page.getByRole('button', { name, exact: true }).click();
    await page.goto(`${base}/policy/us/simulator`); await click('기업');
    assert.equal(await field('실제 기업 선택').locator('option').count(), 38);
    for (const p of Object.values(COMPANY_PROFILES)) {
      await field('실제 기업 선택').selectOption(p.id);
      const context = await page.locator('[data-company-public]').innerText();
      assert.ok(context.includes(p.name));
      if (!p.financial) { assert.match(context, /재무 미수록/); assert.ok(!context.includes('2025 매출')); }
      assert.equal(await field('기업 기준 통관 단가').inputValue(), '');
      assert.equal(await field('기업 단위 변동원가').inputValue(), '');
      assert.equal(await field('기업 제품 원산지').inputValue(), '');
      assert.equal(await field('기업 분석 품목').inputValue(), p.product);
    }
    await field('기업 목록 검색').fill('LG Chem');
    assert.equal(await field('실제 기업 선택').locator('option[value="ad-lg-chem"]').count(), 1);
    await field('실제 기업 선택').selectOption('ad-lg-chem');
    assert.equal(await field('기업 분석 품목').inputValue(), 'sap');
    await click('이 기업의 반덤핑 사건 보기 →');
    assert.equal(await field('반덤핑 기업').inputValue(), 'lg-chem');
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '0%');
    for (const industry of COMPANY_INDUSTRIES) {
      if (await field('산업 분야').inputValue() !== industry.family) await field('산업 분야').selectOption(industry.family);
      await click(industry.label);
      assert.ok(await page.locator(`.ts-ad-selection button[aria-label="${industry.label}"][aria-pressed="true"]`).isVisible());
      if (!industry.case_id) assert.equal(await page.locator('[data-ad-reference], [data-ad-stage]').count(), 0);
    }
    await field('산업 분야').selectOption('steel'); await click('강관 · 대구경 용접강관');
    await page.locator('[data-ad-all]>summary').click();
    await field('반덤핑 전체 기업 검색').fill('AJU'); await click('AJU Besteel Co., Ltd.');
    assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), 'welded-pipe-2025-26');
    assert.equal(await page.locator('[data-ad-stage=initiation]').getAttribute('data-state'), 'latest');
    await field('진행을 볼 재심 대상 기간').selectOption('welded-pipe-rescinded-2024-25');
    assert.ok(await page.locator('[data-ad-rescinded]').isVisible());
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-industries-desktop.png' });
    await page.setViewportSize({ width: 360, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-industries-mobile.png' });
    await field('반덤핑 전체 기업 검색').fill('');
    assert.equal(await page.locator('[data-ad-company]:visible').count(), 23);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await click('기업');
    await field('기업 목록 검색').fill(''); await field('실제 기업 선택').selectOption('ad-seah');
    await field('기업 분석 품목').selectOption('octg');
    assert.equal(await page.locator('[data-company-ad]').count(), 0);
    assert.match(await page.locator('[data-company-public]').innerText(), /선택 품목의 별도 근거/);
    await field('기업 제품 원산지').selectOption('KOR');
    assert.match(await page.locator('[data-company-rate]').innerText(), /확인 필요/);
    assert.equal(await field('기업 현행 관세 조합').inputValue(), 'unresolved');
    await field('기업 목록 검색').fill('<img src=x>'); assert.equal(await page.locator('[data-company-simulator] img').count(), 0);
    await click('국가'); await field('분석 품목').selectOption('carbon-fiber');
    assert.equal(await field('한국 현행 관세 조합').inputValue(), 'unresolved');
    assert.equal(await field('대체탄력성').inputValue(), '4');
    assert.equal(await field('시장 수요탄력성').inputValue(), '-1');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []); assert.ok(requests.every(u => new URL(u).hostname === '127.0.0.1'));
    console.log('PASS: all 37 official company/group profiles; financial null and blank private inputs; English company search; SAP company→AD link; all 15 product selectors; source-only product gaps; OCTG not inheriting pipe AD/tariff; appendix search/15-firm rescission; 360px and escaped searches; no external calls.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

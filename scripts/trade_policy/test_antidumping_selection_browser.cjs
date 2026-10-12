const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.SIMULATOR_PREVIEW_URL || 'http://127.0.0.1:8773';
if (new URL(base).hostname !== '127.0.0.1') throw new Error('Only the loopback preview may be tested.');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [], requests = [];
    page.on('pageerror', e => errors.push(e.message)); page.on('request', r => requests.push(r.url()));
    const field = name => page.getByLabel(name, { exact: true });
    const families = { '변압기': 'power', '차단기·배전기기': 'power', '전력 케이블': 'cables', '해저 케이블': 'cables', '산업용 전선': 'cables', '철강 · 열연강판': 'steel', '강관 · 대구경 용접강관': 'steel', '유정용 강관 · OCTG': 'steel', '타이어': 'tires', '트럭·버스 타이어': 'tires', '산업용 섬유': 'materials', '탄소섬유': 'materials', '아라미드': 'materials', '고흡수성 수지 · SAP': 'chemicals', '자동차': 'other' };
    const click = async name => {
      if (families[name] && await field('산업 분야').inputValue() !== families[name]) await field('산업 분야').selectOption(families[name]);
      await page.getByRole('button', { name, exact: true }).click();
    };
    const picker = page.locator('.ts-ad-selection');
    const company = id => picker.locator(`[data-ad-company="${id}"]:visible`);
    await page.goto(`${base}/policy/us/simulator`); await click('반덤핑');
    assert.equal(await picker.locator('[data-ad-case], [data-ad-industry]').count(), 2);
    assert.equal(await field('산업 분야').locator('option').count(), 7);
    assert.equal(await picker.locator('[data-ad-company]').count(), 4);
    assert.ok(await picker.evaluate(el => el.compareDocumentPosition(document.querySelector('[data-ad-editor]')) & Node.DOCUMENT_POSITION_FOLLOWING));
    for (const [id, name, rate] of [['hyundai', 'HD현대일렉트릭', '0%'], ['iljin', '일진전기', '0%'], ['ls', 'LS일렉트릭', '4.32%'], ['hyosung', '효성중공업', '4.32%']]) {
      await click(name);
      assert.equal(await field('반덤핑 기업').inputValue(), id);
      assert.equal(await company(id).getAttribute('aria-pressed'), 'true');
      assert.equal(await picker.locator('[data-ad-company][aria-pressed="true"]').count(), 1);
      assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), rate);
      assert.match(await picker.locator('.ts-ad-selection-context').innerText(), new RegExp(name));
      assert.ok(await company(id).evaluate(el => document.activeElement === el));
    }
    await field('진행을 볼 재심 대상 기간').selectOption('lpt-2023-24');
    await click('AD 예치 부담 계산');
    assert.ok(await field('AD 제품 범위 확인').evaluate(el => document.activeElement === el));
    assert.match(await page.locator('[data-ad-error]').innerText(), /AD 제품 범위 확인/);
    await field('AD 제품 범위 확인').check(); await click('AD 예치 부담 계산');
    assert.ok(await field('AD 법인 적용 조건 확인').evaluate(el => document.activeElement === el));
    assert.match(await page.locator('[data-ad-error]').innerText(), /AD 법인 적용 조건 확인/);
    await field('AD 법인 적용 조건 확인').check();
    await click('AD 예치 부담 계산');
    assert.ok(await page.getByRole('button', { name: '반덤핑 JSON 저장', exact: true }).isEnabled());
    await click('효성중공업'); // Selecting the active company must not invalidate a result.
    assert.ok(await page.getByRole('button', { name: '반덤핑 JSON 저장', exact: true }).isEnabled());
    await field('대상 수입 신고가격 · USD').fill('2500000');
    await field('가정 AD 예치율 %').fill('12');
    await click('LS일렉트릭');
    assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), 'lpt-2023-24');
    assert.equal(await field('대상 수입 신고가격 · USD').inputValue(), '2500000');
    assert.equal(await field('가정 AD 예치율 %').inputValue(), '12');
    assert.ok(!(await field('AD 법인 적용 조건 확인').isChecked()));
    assert.ok(await page.getByRole('button', { name: '반덤핑 JSON 저장', exact: true }).isDisabled());
    await click('타이어');
    assert.equal(await field('반덤핑 사건').inputValue(), 'A-580-908');
    assert.equal(await picker.locator('[data-ad-company]').count(), 3);
    assert.equal(await picker.locator('[data-ad-company="hyosung"]').count(), 0);
    assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), 'tires-2025-26');
    await click('넥센타이어'); assert.equal(await field('반덤핑 기업').inputValue(), 'nexen');
    await field('반덤핑 기업').selectOption('kumho');
    assert.equal(await company('kumho').getAttribute('aria-pressed'), 'true');
    await field('반덤핑 사건').selectOption('A-580-867');
    assert.equal(await picker.locator('[data-ad-case="A-580-867"]').getAttribute('aria-pressed'), 'true');
    assert.equal(await picker.locator('[data-ad-company]').count(), 4);
    await field('예치율 근거').selectOption('manual');
    assert.equal(await picker.locator('[data-ad-company][aria-pressed="true"]').count(), 0);
    await click('효성중공업');
    assert.equal(await field('예치율 근거').inputValue(), 'published');
    await field('통관일').fill(''); await click('일진전기');
    assert.equal(await field('통관일').inputValue(), '');
    assert.match(await company('iljin').innerText(), /미확인/);
    await click('이 품목의 예시값 채우기'); await click('효성중공업');
    // Newly sourced cases must work through the actual selector/calculation path.
    for (const [industry, caseId, recordId, companies] of [
      ['철강 · 열연강판', 'A-580-883', 'hot-rolled-2023-24', [['현대제철', 'hyundai-steel', '1.49%'], ['포스코·포스코인터내셔널', 'posco-pic', '1.22%']]],
      ['강관 · 대구경 용접강관', 'A-580-897', 'welded-pipe-2024-25', [['현대스틸파이프', 'hyundai-pipe', '0%'], ['세아제강', 'seah', '0.8%']]],
    ]) {
      await click(industry);
      assert.equal(await field('반덤핑 사건').inputValue(), caseId);
      assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), caseId === 'A-580-897' ? 'welded-pipe-2025-26' : 'hot-rolled-2024-25');
      assert.equal(await page.locator('[data-ad-stage=initiation]').getAttribute('data-state'), 'latest');
      assert.equal(await picker.locator('[data-ad-company]').count(), caseId === 'A-580-897' ? 23 : 2);
      assert.equal(await picker.locator('[data-ad-company]:visible').count(), caseId === 'A-580-897' ? 5 : 2);
      for (const [name, id, rate] of companies) {
        await click(name);
        assert.equal(await field('반덤핑 기업').inputValue(), id);
        assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), rate);
        assert.ok(await company(id).evaluate(el => document.activeElement === el));
      }
      await click('이 품목의 예시값 채우기');
      await field('AD 제품 범위 확인').check(); await field('AD 법인 적용 조건 확인').check();
      await click('AD 예치 부담 계산');
      assert.ok(await page.getByRole('button', { name: '반덤핑 JSON 저장', exact: true }).isEnabled());
    }
    await field('진행을 볼 재심 대상 기간').selectOption('welded-pipe-2024-25');
    assert.equal(await page.locator('[data-ad-stage="preliminary"]').getAttribute('data-state'), 'latest');
    assert.equal(await page.locator('[data-ad-stage="final"]').getAttribute('data-state'), 'unknown');
    assert.match(await page.locator('[data-ad-calculated]').innerText(), /800\.00/);
    await field('진행을 볼 재심 대상 기간').selectOption('welded-pipe-2023-24');
    assert.equal(await page.locator('[data-ad-stage="final"]').getAttribute('data-state'), 'latest');
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '0.8%');
    // Full appendix lookup preserves assigned margin and company-specific rescission.
    await picker.locator('[data-ad-all]>summary').click();
    await field('반덤핑 전체 기업 검색').fill('AJU Besteel');
    assert.equal(await picker.locator('[data-ad-company]:visible').count(), 1);
    await click('AJU Besteel Co., Ltd.');
    assert.equal(await field('반덤핑 기업').inputValue(), 'aju');
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '미확인');
    assert.match(await page.locator('[data-ad-reference]').innerText(), /배정 마진 0.8%/);
    assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), 'welded-pipe-2025-26');
    await field('진행을 볼 재심 대상 기간').selectOption('welded-pipe-rescinded-2024-25');
    assert.ok(await page.locator('[data-ad-rescinded]').isVisible());
    assert.equal(await page.locator('[data-ad-stage="preliminary"]').getAttribute('data-state'), 'unknown');
    assert.equal(await page.locator('[data-ad-stage="final"]').getAttribute('data-state'), 'unknown');
    assert.equal(await page.locator('[data-ad-calculated]').count(), 0);
    await field('반덤핑 전체 기업 검색').fill('<img src=x>');
    assert.equal(await picker.locator('[data-ad-company]:visible').count(), 0);
    assert.equal(await picker.locator('img').count(), 0);
    await field('반덤핑 전체 기업 검색').fill('하이스틸'); await click('하이스틸');
    assert.equal(await page.locator('[data-ad-rescinded]').count(), 0);
    await field('진행을 볼 재심 대상 기간').selectOption('welded-pipe-nonselected-2024-25');
    assert.equal(await page.locator('[data-ad-stage="preliminary"]').getAttribute('data-state'), 'latest');
    assert.equal(await page.locator('[data-ad-stage="selection"]').getAttribute('data-state'), 'unknown');
    await field('반덤핑 전체 기업 검색').fill('');
    assert.equal(await picker.locator('[data-ad-company]:visible').count(), 23);
    await picker.locator('[data-ad-all]>summary').click();
    assert.equal(await picker.locator('[data-ad-company]:visible').count(), 5);
    await click('고흡수성 수지 · SAP'); await click('LG화학');
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '0%');
    assert.equal(await page.locator('[data-ad-stage="initiation"]').getAttribute('data-state'), 'latest');
    await field('진행을 볼 재심 대상 기간').selectOption('sap-2023-24');
    assert.equal(await page.locator('[data-ad-stage="final"]').getAttribute('data-state'), 'latest');
    await click('강관 · 대구경 용접강관');
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-steel-desktop.png' });
    await page.setViewportSize({ width: 360, height: 844 });
    for (const industry of ['철강 · 열연강판', '강관 · 대구경 용접강관']) {
      await click(industry); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-steel-mobile.png' });
    await page.setViewportSize({ width: 1440, height: 1080 });
    // An expanded industry is not a new verified AD case. No inherited rate,
    // history, process lamps or calculated result may survive that boundary.
    for (const [industry, names] of [
      ['전력 케이블', ['LS전선', '대한전선']],
      ['차단기·배전기기', ['LS일렉트릭', '효성중공업']],
      ['자동차', ['기아']],
      ['산업용 섬유', ['HS효성첨단소재']],
      ['해저 케이블', ['LS전선', '대한전선']], ['산업용 전선', ['LS전선', '대한전선']],
      ['유정용 강관 · OCTG', ['세아제강']], ['트럭·버스 타이어', ['한국타이어앤테크놀로지']],
      ['탄소섬유', ['HS효성첨단소재']], ['아라미드', ['HS효성첨단소재']],
    ]) {
      await click(industry);
      assert.equal(await picker.locator('[data-ad-profile]').count(), names.length);
      for (const name of names) {
        await click(name);
        assert.match(await picker.locator('.ts-ad-selection-context').innerText(), new RegExp(name));
        assert.match(await page.locator('[data-ad-gap]').innerText(), /공고와 예치율은 아직 연결하지 않았습니다/);
        assert.equal(await page.locator('[data-ad-reference], [data-ad-calculated], [data-ad-stage], [data-ad-method-form]').count(), 0);
        assert.equal(await page.getByRole('button', { name: 'AD 예치 부담 계산', exact: true }).count(), 0);
      }
    }
    for (const [industry, companyName, companyId, product] of [
      ['전력 케이블', '대한전선', 'taihan', 'power-cable'],
      ['차단기·배전기기', 'LS일렉트릭', 'ls-electric', 'switchgear'],
      ['자동차', '기아', 'kia', 'vehicle'],
      ['산업용 섬유', 'HS효성첨단소재', 'hs-materials', 'fiber'],
      ['탄소섬유', 'HS효성첨단소재', 'hs-materials', 'carbon-fiber'],
      ['유정용 강관 · OCTG', '세아제강', 'ad-seah', 'octg'],
    ]) {
      await click(industry); await click(companyName); await click('이 기업·품목의 손익 시나리오 보기 →');
      assert.equal(await field('실제 기업 선택').inputValue(), companyId);
      assert.equal(await field('기업 분석 품목').inputValue(), product);
      assert.equal(await field('기업 제품 원산지').inputValue(), '');
      assert.equal(await field('기업 기준 통관 단가').inputValue(), '');
      assert.equal(await page.getByRole('button', { name: '이 기업의 반덤핑 사건 보기 →', exact: true }).count(), 0);
      if (product === 'switchgear') {
        await field('기업 분석 품목').selectOption('transformer');
        assert.ok(await page.getByRole('button', { name: '이 기업의 반덤핑 사건 보기 →', exact: true }).isVisible());
        await field('기업 분석 품목').selectOption('switchgear');
        assert.equal(await page.getByRole('button', { name: '이 기업의 반덤핑 사건 보기 →', exact: true }).count(), 0);
      }
      await click('반덤핑');
      assert.equal(await picker.locator('[data-ad-profile][aria-pressed="true"]').count(), 1);
      assert.equal(await page.locator('[data-ad-reference], [data-ad-calculated]').count(), 0);
    }
    await click('변압기'); await click('효성중공업');
    assert.equal(await field('반덤핑 사건').inputValue(), 'A-580-867');
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '4.32%');
    assert.equal(await page.locator('[data-ad-calculated]').count(), 0);
    assert.ok(!(await field('AD 제품 범위 확인').isChecked()));
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-selection-desktop.png' });
    await click('전력 케이블'); await click('대한전선');
    await page.locator('[data-ad-simulator]').screenshot({ path: '/tmp/antidumping-industry-gap-desktop.png' });
    await page.setViewportSize({ width: 360, height: 844 });
    assert.equal(await picker.locator('.ts-ad-industries').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 2);
    for (const industry of ['전력 케이블', '차단기·배전기기', '자동차', '산업용 섬유']) {
      await click(industry); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    await page.locator('[data-ad-simulator]').screenshot({ path: '/tmp/antidumping-industry-gap-mobile.png' });
    await click('타이어'); await click('금호타이어'); await click('변압기'); await click('효성중공업');
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.equal(await field('반덤핑 기업').inputValue(), 'hyosung');
    assert.ok(await company('hyosung').evaluate(el => document.activeElement === el));
    await page.locator('[data-ad-process]').screenshot({ path: '/tmp/antidumping-selection-mobile.png' });
    assert.deepEqual(errors, []); assert.ok(requests.every(u => new URL(u).hostname === '127.0.0.1'));
    console.log('PASS: six core families/15 products; five official cases/33 entities; 23 pipe entities; featured/full Korean-English search; 15 rescissions/6 continuing nonselected firms; SAP zero; no unverified deposits; official final/preliminary separation and new calculations; expanded company discovery without inherited AD rates, history or stages; company/product handoff and cable HTS isolation; bidirectional selectors; POR isolation; preserved edits and stale results; manual and empty-date recovery; focus; 360px; no external calls.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

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
    const click = name => page.getByRole('button', { name, exact: true }).click();
    const picker = page.locator('.ts-ad-selection');
    const company = id => picker.locator(`[data-ad-company="${id}"]`);
    await page.goto(`${base}/policy/us/simulator`); await click('반덤핑');
    assert.equal(await picker.locator('[data-ad-case], [data-ad-industry]').count(), 6);
    assert.equal(await picker.locator('[data-ad-company]').count(), 4);
    assert.ok(await picker.evaluate(el => el.compareDocumentPosition(document.querySelector('[data-ad-editor]')) & Node.DOCUMENT_POSITION_FOLLOWING));
    for (const [id, name, rate] of [['hyundai', 'HD현대일렉트릭', '0%'], ['iljin', '일진전기', '0%'], ['ls', 'LS일렉트릭', '4.32%'], ['hyosung', '효성중공업', '4.32%']]) {
      await click(name);
      assert.equal(await field('반덤핑 기업').inputValue(), id);
      assert.equal(await company(id).getAttribute('aria-pressed'), 'true');
      assert.equal(await picker.locator('[data-ad-company][aria-pressed="true"]').count(), 1);
      assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), rate);
      assert.match(await picker.locator('[role="status"]').innerText(), new RegExp(name));
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
    assert.equal(await field('진행을 볼 재심 대상 기간').inputValue(), 'tires-2023-24');
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
    // An expanded industry is not a new verified AD case. No inherited rate,
    // history, process lamps or calculated result may survive that boundary.
    for (const [industry, names] of [
      ['전력 케이블', ['LS전선', '대한전선']],
      ['차단기·배전기기', ['LS일렉트릭', '효성중공업']],
      ['자동차', ['기아']],
      ['산업용 섬유', ['HS효성첨단소재']],
    ]) {
      await click(industry);
      assert.equal(await picker.locator('[data-ad-profile]').count(), names.length);
      for (const name of names) {
        await click(name);
        assert.match(await picker.locator('[role="status"]').innerText(), new RegExp(name));
        assert.match(await page.locator('[data-ad-gap]').innerText(), /공고와 예치율은 아직 연결하지 않았습니다/);
        assert.equal(await page.locator('[data-ad-reference], [data-ad-calculated], [data-ad-stage], [data-ad-method-form]').count(), 0);
        assert.equal(await page.getByRole('button', { name: 'AD 예치 부담 계산', exact: true }).count(), 0);
      }
    }
    for (const [industry, companyName, companyId, product] of [
      ['전력 케이블', '대한전선', 'taihan', 'custom'],
      ['차단기·배전기기', 'LS일렉트릭', 'ls-electric', 'switchgear'],
      ['자동차', '기아', 'kia', 'vehicle'],
      ['산업용 섬유', 'HS효성첨단소재', 'hs-materials', 'fiber'],
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
    console.log('PASS: six industry groups; four transformer/three tire companies; expanded company discovery without inherited AD rates, history or stages; company/product handoff and cable HTS isolation; bidirectional selectors; POR isolation; preserved edits and stale results; manual and empty-date recovery; focus; 360px; no external calls.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });

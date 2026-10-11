const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.SIMULATOR_PREVIEW_URL || 'http://127.0.0.1:8773';
if (new URL(base).hostname !== '127.0.0.1') throw new Error('Only the loopback preview may be tested.');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 360, height: 844 } });
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto(`${base}/policy/us/simulator`);
    await page.getByLabel('분석 품목', { exact: true }).waitFor();
    const calculate = () => page.getByRole('button', { name: '시나리오 계산', exact: false }).first().click();
    const field = label => page.getByLabel(label, { exact: true });
    const assertTarget = async label => {
      const state = await field(label).evaluate(el => {
        const r = el.getBoundingClientRect();
        return { focused: document.activeElement === el, invalid: el.getAttribute('aria-invalid'), top: r.top, bottom: r.bottom, left: r.left, right: r.right,
          height: innerHeight, width: innerWidth, described: (el.getAttribute('aria-describedby') || '').split(/\s+/).some(id => document.getElementById(id)?.matches('[data-ts-field-error]')) };
      });
      assert.ok(state.focused && state.invalid === 'true' && state.described, JSON.stringify(state));
      assert.ok(state.top > 0 && state.bottom < state.height && state.left >= 0 && state.right <= state.width, JSON.stringify(state));
      assert.equal(await page.locator('[data-ts-field-error]').count(), 1);
      const width = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
      assert.ok(width[0] <= width[1], JSON.stringify(width));
    };
    // Each supported product fills its own starting points and preserves actual provenance.
    const values = { transformer: ['3.5', '-0.15'], tire: ['4.5', '-0.375'], vehicle: ['7.58', '-0.82'], switchgear: ['3', '-1'], fiber: ['3.5', '-1'], semiconductor: ['3.32', '-1'], cable: ['4', '-1'], custom: ['4', '-1'] };
    for (const [product, [sigma, eta]] of Object.entries(values)) {
      await field('분석 품목').selectOption(product);
      assert.equal(await field('대체탄력성').inputValue(), sigma);
      assert.equal(await field('시장 수요탄력성').inputValue(), eta);
      if (['cable', 'custom'].includes(product)) assert.match(await page.locator('[data-sigma-basis]').innerText(), /사용자 가정/);
    }
    await field('분석 품목').selectOption('vehicle');
    assert.match(await page.locator('[data-eta-basis] a').getAttribute('href'), /epa.gov/);
    await field('시장 수요탄력성').fill('-0.6');
    assert.match(await page.locator('[data-eta-basis]').innerText(), /사용자 가정/);
    assert.match(await page.locator('[data-sigma-basis]').innerText(), /문헌 기반/);
    await page.getByRole('button', { name: '문헌 기본값 적용' }).click();
    assert.equal(await field('시장 수요탄력성').inputValue(), '-0.82');
    assert.match(await page.locator('[data-eta-basis]').innerText(), /문헌 검토/);
    await field('분석 품목').selectOption('transformer');
    await field('구매액 기준 연도·기간').fill('  ');
    await calculate(); await assertTarget('구매액 기준 연도·기간');
    await field('구매액 기준 연도·기간').fill('2025 · 테스트 가정');
    assert.equal(await field('구매액 기준 연도·기간').getAttribute('aria-invalid'), null);

    await page.locator('[data-supplier="MEX"]').click();
    await calculate(); await assertTarget('멕시코 기준 구매액');
    await field('멕시코 기준 구매액').fill('10');
    // Non-empty unresolved dropdowns also navigate to the correct control.
    await calculate(); await assertTarget('멕시코 현행 관세 조합');
    await field('멕시코 현행 관세 조합').selectOption('manual');
    await calculate(); await assertTarget('멕시코 확인한 현행 관세');
    await field('멕시코 확인한 현행 관세').fill('20');
    await field('멕시코 현행 관세 출처').fill(' ');
    await calculate(); await assertTarget('멕시코 현행 관세 출처');
    await field('멕시코 현행 관세 출처').fill('공식 관세 직접 검토 · 테스트');
    await field('멕시코 비교할 관세').selectOption('manual');
    await calculate(); await assertTarget('멕시코 가정 관세');
    await field('멕시코 가정 관세').fill('25');

    const extra = field('한국 별도 추가세');
    await extra.evaluate(el => { el.closest('details').open = true; });
    await extra.fill('');
    await extra.evaluate(el => { el.closest('details').open = false; });
    await calculate(); await assertTarget('한국 별도 추가세');
    assert.ok(await extra.evaluate(el => el.closest('details').open));
    await extra.fill('-1');
    await extra.evaluate(el => { el.closest('details').open = false; });
    await calculate(); await assertTarget('한국 별도 추가세');
    await extra.fill('290'); // Valid individual number, invalid combined rate 15+290.
    await extra.evaluate(el => { el.closest('details').open = false; });
    await calculate(); await assertTarget('한국 별도 추가세');
    assert.match(await page.locator('[data-sim-error]').innerText(), /합산 관세/);
    await extra.fill('0');
    await calculate(); await assertTarget('관세 적용 조건 확인');
    await field('관세 적용 조건 확인').check(); await calculate();
    await page.getByRole('heading', { name: '한국 공급에 미치는 영향' }).waitFor();
    assert.ok(await page.getByRole('button', { name: '결과 JSON 저장', exact: true }).isEnabled());
    await field('구매액 기준 연도·기간').fill('');
    await calculate(); await assertTarget('구매액 기준 연도·기간');
    assert.ok(await page.getByRole('button', { name: '결과 JSON 저장', exact: true }).isDisabled());
    assert.ok(await page.locator('[data-stale]').isVisible());
    await page.screenshot({ path: '/tmp/country-tariff-validation-mobile.png', fullPage: false });

    await page.getByRole('button', { name: '기업', exact: true }).click();
    await field('실제 기업 선택').selectOption('manual');
    await field('기업 이름').fill('가상 수출기업');
    await field('기업 분석 품목').selectOption('transformer');
    await field('기업 제품 원산지').selectOption('KOR');
    for (const [label, value] of [['기업 분석 기간', '테스트 입력 · 연간'], ['기업 기준 판매량', '10000'], ['기업 단위 변동원가', '70'], ['기업 기간 고정비', '100000']]) await field(label).fill(value);
    await field('기업 기준 통관 단가').fill('');
    await calculate(); await assertTarget('기업 기준 통관 단가');
    await field('기업 기준 통관 단가').fill('100');
    await field('기업 최대 공급 가능 물량').fill('1');
    await calculate(); await assertTarget('기업 최대 공급 가능 물량');
    await field('기업 최대 공급 가능 물량').fill(''); // Optional means optional.
    const companyExtra = field('기업 별도 추가세');
    await companyExtra.evaluate(el => { el.closest('details').open = true; });
    await companyExtra.fill('');
    await companyExtra.evaluate(el => { el.closest('details').open = false; });
    await calculate(); await assertTarget('기업 별도 추가세');
    await companyExtra.fill('0');
    await calculate(); await assertTarget('기업 관세 적용 조건 확인');
    await field('기업 관세 적용 조건 확인').check(); await calculate();
    await page.getByRole('heading', { name: '가상 수출기업 · 제품 손익' }).waitFor();
    await field('기업 반응 방식').selectOption('country');
    await calculate();
    assert.ok(await page.locator('[data-company-link]').evaluate(el => document.activeElement === el));
    assert.match(await page.locator('[data-company-error]').innerText(), /먼저 연결/);
    assert.deepEqual(errors, []);
    console.log('PASS: all product defaults; independent parameter sources/restore; 360px focus + scroll + inline errors; whitespace/missing/range/unresolved policy/source/total rate; closed details; checkbox; optional inputs; previous result/export protection; country and company; missing proxy link.');
  } finally { await browser.close(); }
})().catch(err => { console.error(err); process.exitCode = 1; });

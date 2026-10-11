// Run the loopback preview first. Set PLAYWRIGHT_MODULE if not installed locally.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const base = process.env.SIMULATOR_PREVIEW_URL || 'http://127.0.0.1:8773';
if (new URL(base).hostname !== '127.0.0.1') throw new Error('Only the loopback preview may be tested.');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [], requests = [];
    page.on('pageerror', err => errors.push(err.message));
    page.on('request', request => requests.push(new URL(request.url()).pathname));
    await page.goto(`${base}/policy/us/simulator`);
    await page.getByRole('heading', { name: '한국 공급에 미치는 영향' }).waitFor();
    assert.match(await page.locator('.ts-kpis').innerText(), /-27\.99/);
    assert.equal(requests.filter(p => p.startsWith('/api/')).length, 0);
    assert.ok(await page.getByRole('button', { name: '기업 준비 중' }).isDisabled());

    await page.getByLabel('한국 가정 관세', { exact: true }).fill('40');
    assert.ok(await page.locator('[data-stale]').isVisible());
    assert.ok(await page.getByRole('button', { name: '결과 JSON 저장' }).isDisabled());
    await page.getByRole('button', { name: '시나리오 계산' }).click();
    await page.getByText('관세 0.0% → 40.0%', { exact: false }).waitFor();
    assert.ok(await page.locator('[data-stale]').isHidden());

    await page.getByRole('button', { name: '+ 공급국 추가' }).click();
    await page.getByLabel('중국 기준 구매액', { exact: true }).fill('10');
    await page.getByLabel('기타국 합계 기준 구매액', { exact: true }).fill('15');
    await page.getByLabel('중국 기존 관세', { exact: true }).fill('10');
    await page.getByLabel('중국 가정 관세', { exact: true }).fill('30');
    await page.getByLabel('관심 공급국', { exact: true }).selectOption('CHN');
    await page.getByRole('button', { name: '시나리오 계산' }).click();
    await page.getByRole('heading', { name: '중국 공급에 미치는 영향' }).waitFor();
    assert.equal(await page.locator('.ts-bar-row').count(), 4);
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '결과 JSON 저장' }).click();
    const download = await downloadPromise;
    const json = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
    assert.equal(json.inputs.focus, 'CHN'); assert.equal(json.rows.length, 4);
    assert.equal(json.model_version, 'country-ces-1'); assert.ok(json.checks.max_log_residual < 1e-8);
    assert.equal(requests.filter(p => p.startsWith('/api/')).length, 0);

    await page.getByLabel('중국 제거', { exact: true }).click();
    await page.getByRole('button', { name: '시나리오 계산' }).click();
    await page.getByRole('heading', { name: '한국 공급에 미치는 영향' }).waitFor();
    await page.getByRole('button', { name: '가상 예시로 초기화' }).click();
    await page.getByLabel('공급국 2', { exact: true }).selectOption('CAN');
    await page.getByLabel('기준 기간', { exact: true }).fill('<img src=x onerror=alert(1)>');
    await page.getByRole('button', { name: '시나리오 계산' }).click();
    await page.getByRole('heading', { name: '캐나다 공급에 미치는 영향' }).waitFor();
    assert.equal(await page.locator('.ts-result-heading img').count(), 0);
    assert.match(await page.locator('.ts-result-heading').innerText(), /<img src=x/);

    await page.getByRole('button', { name: '의회', exact: true }).click();
    await page.getByRole('heading', { name: '상임위 (하원)', exact: true }).waitFor();
    assert.equal(new URL(page.url()).pathname, '/policy/us');
    await page.getByRole('button', { name: '행정부', exact: true }).click();
    await page.getByRole('button', { name: '관세 시뮬레이터', exact: true }).click();
    await page.getByRole('heading', { name: '캐나다 공급에 미치는 영향' }).waitFor();
    assert.equal(await page.locator('[data-sim-form]').count(), 1);
    assert.equal(new URL(page.url()).pathname, '/policy/us/simulator');
    await page.goBack();
    await page.waitForURL('**/policy/us/executive');
    await page.goForward();
    await page.getByRole('heading', { name: '캐나다 공급에 미치는 영향' }).waitFor();
    await page.getByRole('button', { name: '가상 예시로 초기화' }).click();
    await page.screenshot({ path: '/tmp/country-tariff-desktop.png', fullPage: true });
    for (const width of [390, 360]) {
      await page.setViewportSize({ width, height: 844 });
      const dimensions = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }));
      assert.ok(dimensions.page <= dimensions.viewport, JSON.stringify(dimensions));
    }
    await page.screenshot({ path: '/tmp/country-tariff-mobile.png', fullPage: true });
    await page.reload();
    await page.getByRole('heading', { name: '한국 공급에 미치는 영향' }).waitFor();

    const offline = await browser.newPage();
    await offline.route('**/api/us/overview', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"DB unavailable"}' }));
    await offline.goto(`${base}/policy/us`);
    await offline.getByText('정책 데이터를 불러오지 못했습니다', { exact: true }).waitFor();
    await offline.getByRole('button', { name: '관세 시뮬레이터', exact: true }).click();
    await offline.getByRole('heading', { name: '한국 공급에 미치는 영향' }).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: render; tariff recalculation; stale/export guard; country add/remove/focus; JSON download; escaped input; Congress/executive/back/forward/reload; 390/360px; DB outage independence; no calculation API calls.');
  } finally { await browser.close(); }
})().catch(err => { console.error(err); process.exitCode = 1; });

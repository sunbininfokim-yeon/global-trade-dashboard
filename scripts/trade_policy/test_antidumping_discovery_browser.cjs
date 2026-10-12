const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.SIMULATOR_PREVIEW_URL || 'http://127.0.0.1:8773';
if (new URL(base).hostname !== '127.0.0.1') throw new Error('Only loopback preview');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [], requests = []; page.on('pageerror', e => errors.push(e.message)); page.on('request', r => requests.push(r.url()));
    await page.goto(`${base}/policy/us/simulator`); await page.getByRole('button', { name: '반덤핑', exact: true }).click();
    const notices = page.locator('[data-ad-notices]');
    assert.match(await notices.locator('summary').first().innerText(), /A-580-867/);
    await notices.locator('summary').first().click();
    assert.match(await notices.innerText(), /2026-10-12/); assert.match(await notices.innerText(), /검증하기 전에는/);
    assert.equal(await page.locator('[data-ad-reference]>strong').innerText(), '4.32%');
    await page.getByLabel('산업 분야', { exact: true }).selectOption('steel');
    await page.getByRole('button', { name: '강관 · 대구경 용접강관', exact: true }).click();
    assert.match(await notices.locator('summary').first().innerText(), /A-580-897/);
    await notices.locator('summary').first().click();
    assert.match(await notices.innerText(), /2026-13892/); // Newly discovered initiation; never auto-promoted to a rate.
    const before = await page.locator('[data-ad-reference]>strong').innerText();
    assert.match(before, /0%|0.8%/);
    const bounds = await notices.evaluate(el => el.getBoundingClientRect()); assert.ok(bounds.width > 0);
    await notices.screenshot({ path: '/tmp/antidumping-notice-review-desktop.png' });
    await page.setViewportSize({ width: 360, height: 800 });
    await notices.scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await notices.screenshot({ path: '/tmp/antidumping-notice-review-mobile.png' });
    await page.getByLabel('산업 분야', { exact: true }).selectOption('cables');
    await page.getByRole('button', { name: '전력 케이블', exact: true }).click();
    assert.equal(await page.locator('[data-ad-notices]').count(), 0);
    assert.match(await page.locator('[data-ad-notice-review]').innerText(), /まだ|아직/);
    assert.deepEqual(errors, []); assert.ok(requests.every(url => new URL(url).hostname === '127.0.0.1'));
    console.log('PASS discovery UI: case isolation, unactivated candidates, preserved rates, no external calls, 360px');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });

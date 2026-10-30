// Optional smoke: NODE_PATH pointing at a Playwright installation.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const p = require('../New for anti/policy-evidence.js');
const bill = require('./fixtures/clarity-119-hr-3633.json');
bill.lifecycle = p.buildLifecycle(bill);
bill.committees = bill.bill_committees.map(c => ({ ...c.committees, committee_id: c.committee_id }));
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('https://policy.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/us/overview') return route.fulfill({ json: { congress_overview: { committees: [] }, executive_overview: { agencies: [] } } });
      if (url.pathname === '/api/us/congress/bills/119-hr-3633') return route.fulfill({ json: bill });
      if (url.pathname === '/api/us/search') return route.fulfill({ json: { query: 'HR 3633', items: [{ type: 'bill', id: bill.bill_id, title: bill.title, match_type: 'exact_bill_number', bill_type: 'hr', bill_number: 3633, congress_number: 119 }] } });
      if (['/policy-evidence.js', '/policy.js', '/style.css'].includes(url.pathname)) return route.fulfill({ body: fs.readFileSync(path.join(root, 'New for anti', url.pathname.slice(1))), contentType: url.pathname.endsWith('.css') ? 'text/css' : 'application/javascript' });
      if (url.pathname.startsWith('/api/')) throw Error('Unexpected request '+url.pathname);
      return route.fulfill({ contentType: 'text/html', body: '<html lang="ko"><head><meta charset="utf-8"><link rel="stylesheet" href="/style.css"></head><body><main id="policy"></main><script src="/policy-evidence.js"></script><script src="/policy.js"></script></body></html>' });
    });
    await page.goto('https://policy.test/policy/us/bill/119-hr-3633');
    await page.evaluate(() => window.USPolicy.render('us-congress-overview', document.querySelector('#policy')));
    assert.match(await page.locator('#policy').innerText(), /상원 토론 종결 표결 부결/);
    const house = page.locator('.policy-stage-step').filter({ hasText: /^하원 본회의 통과/ });
    assert.match(await house.getAttribute('class'), /is-done/);
    const senate = page.locator('.policy-stage-step').filter({ hasText: /^상원 본회의 통과/ });
    assert.doesNotMatch(await senate.getAttribute('class'), /is-done|is-current/);
    assert.match(await page.locator('.policy-stage-step.is-current').innerText(), /상원 상임위 보고/);
    await page.locator('[data-search-input]').fill('HR 3633');
    await page.locator('.policy-search-result').waitFor();
    assert.match(await page.locator('.policy-search-result').innerText(), /Digital Asset Market Clarity Act.*HR 3633 \(119대\)/s);
    await page.locator('.policy-search-result').click();
    assert.deepEqual(errors, []);
    await page.screenshot({ path: '/private/tmp/clarity-policy-smoke.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile page must not overflow');
    await page.screenshot({ path: '/private/tmp/clarity-policy-mobile.png', fullPage: true });
    console.log('PASS: real fixture rendered; House passed, Senate report, failed cloture, grouped exact-search navigation, mobile width');
  } finally { await browser.close(); }
})().catch(e => { console.error(e.message); process.exitCode = 1; });

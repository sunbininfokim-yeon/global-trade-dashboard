// Optional real Chromium ESM smoke. No HTTP server or live site is needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {analyzeRisk} from '../../New for anti/portfolio-engine/index.mjs';

function compare(actual, expected) {
  if (typeof expected === 'number') {
    assert.ok(Number.isFinite(actual));
    assert.ok(Math.abs(actual - expected) <= Math.max(1e-11, Math.abs(expected) * 1e-9));
  } else if (expected && typeof expected === 'object') {
    assert.deepEqual(Object.keys(actual), Object.keys(expected));
    Object.entries(expected).forEach(([key, value]) => compare(actual[key], value));
  } else assert.equal(actual, expected);
}

test('Chromium native module matches Node; calculation has no outbound requests/storage',
  {skip: !process.env.PORTFOLIO_PLAYWRIGHT}, async () => {
    const {chromium} = await import(pathToFileURL(process.env.PORTFOLIO_PLAYWRIGHT).href);
    const browser = await chromium.launch({headless: true,
      ...(process.env.PORTFOLIO_CHROMIUM ? {executablePath: process.env.PORTFOLIO_CHROMIUM} : {})});
    try {
      const page = await browser.newPage(), requests = [];
      const files = new Map(['index.mjs', 'math.mjs'].map(name => [
        `https://portfolio-engine.test/${name}`,
        readFileSync(new URL(`../../New for anti/portfolio-engine/${name}`, import.meta.url), 'utf8')]));
      await page.route('**/*', async route => {
        const url = route.request().url(); requests.push(url);
        if (url === 'https://portfolio-engine.test/')
          return route.fulfill({contentType: 'text/html', body: '<!doctype html><title>Engine test</title>'});
        if (files.has(url)) return route.fulfill({contentType: 'text/javascript', body: files.get(url)});
        return route.abort();
      });
      await page.goto('https://portfolio-engine.test/');
      await page.evaluate(async () => {
        window.engine = await import('/index.mjs');
        const fail = () => { throw new Error('forbidden host operation'); };
        window.fetch = fail; window.XMLHttpRequest = fail; window.WebSocket = fail;
        navigator.sendBeacon = fail; Storage.prototype.setItem = fail;
        indexedDB.open = fail;
      });
      const f = JSON.parse(readFileSync(new URL('./golden/numerical.json', import.meta.url)))[0];
      const before = requests.length;
      const actual = await page.evaluate(input => window.engine.analyzeRisk(input), f.input);
      compare(actual, analyzeRisk(f.input));
      assert.equal(requests.length, before, 'calculation made a request');
      assert.deepEqual(requests.sort(), ['https://portfolio-engine.test/', ...files.keys()].sort());
    } finally { await browser.close(); }
  });

// Exercise the production reader and renderer against real committed gzip data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../New for anti');
const board = JSON.parse(fs.readFileSync(path.join(root, 'public/data/overseas_letf_board_v1.json')));
// Independent display contract: the product's current data chooses the label.
const structureLabels = { swap: '스왑', futures: '선물', physical_margin: '현물·차입', derivatives_and_collateral: '파생·담보', mixed: '혼합' };
(async () => {
    const browser = await chromium.launch({ headless: true });
    try {
        const page = await browser.newPage();
        const checkSelectedProduct = async (product) => {
            assert.equal(typeof product.structure, 'string');
            assert(product.structure.length > 0, 'product structure must be present');
            assert.equal(await page.locator('[data-ms-overseas-product]').inputValue(), product.product_id);
            assert.equal(await page.locator('[data-ms-overseas] > h3').first().innerText(), product.name);
            const label = structureLabels[product.structure] || product.structure;
            const note = await page.locator('[data-ms-overseas] > h3 + p').first().innerText();
            assert(note.includes(`구조 ${label} (`), 'selected product structure must match its data');
            if (label !== product.structure) assert(!note.includes(product.structure), 'use the translated structure label');
        };
        const errors = [];
        page.on('pageerror', (e) => errors.push(e.message));
        await page.route('http://letf.test/**', async (route) => {
            const name = decodeURIComponent(new URL(route.request().url()).pathname);
            if (name === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/style.css"><main id="test-host"></main>' });
            const file = path.join(root, name);
            if (!fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
            return route.fulfill({ body: fs.readFileSync(file), contentType: name.endsWith('.css') ? 'text/css' : name.endsWith('.gz') ? 'application/gzip' : 'application/json' });
        });
        await page.goto('http://letf.test/');
        // Only app-level plumbing is supplied; chart and domain code are real.
        await page.addScriptTag({ content: `
            const finEsc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
            const finPct = v => Number.isFinite(v) ? (v*100).toFixed(2)+'%' : '—';
            const finDataPaths = name => ['/public/data/'+name];
            const loadFirstJson = async paths => { for (const p of paths) { try { const r=await fetch(p); if(r.ok)return await r.json(); }catch(_){} } return null; };
        ` });
        await page.addScriptTag({ path: path.join(root, 'macro.js') });
        await page.addScriptTag({ path: path.join(root, 'market-microstructure.js') });
        await page.evaluate(async () => { MS_TAB='overseas'; await renderMicrostructure(document.getElementById('test-host')); });
        assert.equal(await page.locator('[data-ms-overseas-product] option').count(), 2);
        const counts = await page.evaluate(() => ({ n: MS_HIST.overseas.length, ids: new Set(MS_HIST.overseas.map(r => r.product_id)).size }));
        assert(counts.n > 500 && counts.ids === 15, 'gzip reader must preserve different products on the same date');
        await page.selectOption('[data-ms-overseas-group]', 'samsung');
        await page.selectOption('[data-ms-overseas-product]', 'XS3388190301');
        // Check the selected product's own detail, not another row in the panel.
        const samsungProduct = board.products.find(p => p.product_id === 'XS3388190301');
        await checkSelectedProduct(samsungProduct);
        await page.selectOption('[data-ms-overseas-group]', 'adr');
        await page.selectOption('[data-ms-overseas-product]', 'SKHQ');
        assert.match(await page.locator('[data-ms-overseas]').innerText(), /축적 중/);
        await page.selectOption('[data-ms-overseas-group]', 'global');
        await page.selectOption('[data-ms-overseas-product]', 'TQQQ');
        const tqqq = board.products.find(p => p.product_id === 'TQQQ');
        await checkSelectedProduct(tqqq);
        assert(await page.locator('.mm-chart path.mm-line').count() >= 3);
        for (const width of [736, 360]) {
            await page.setViewportSize({ width, height: 1000 });
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'page must fit viewport');
        }
        // Already decompressed HTTP responses must work as well as .gz bytes.
        await page.route('http://letf.test/public/data/plain.jsonl.gz', route => route.fulfill({body:'{"date":"2026-09-04","product_id":"a"}\n{"date":"2026-09-04","product_id":"b"}\n'}));
        assert.equal(await page.evaluate(async () => (await msGetJsonl('plain.jsonl.gz')).length), 2);
        // A legitimate future structure change must not require a new product
        // assertion. This is synthetic test data, never a published observation.
        const changed = { ...samsungProduct, structure: samsungProduct.structure === 'swap' ? 'futures' : 'swap' };
        await page.evaluate(async ({ product_id, structure }) => {
            MS_DATA.overseas.products.find(p => p.product_id === product_id).structure = structure;
            MS_OVERSEAS_GROUP = 'samsung';
            MS_OVERSEAS_PRODUCT = product_id;
            await renderMicrostructure(document.getElementById('test-host'));
        }, changed);
        await checkSelectedProduct(changed);
        assert.deepEqual(errors, []);
        console.log('Overseas LETF browser integration passed:', counts);
    } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });

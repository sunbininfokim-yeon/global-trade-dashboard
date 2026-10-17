// Regression tests for the trade-aggregation audit, issue #602 (A01-A13).
//
//   node --test tests/comtrade/aggregation-602.test.mjs
//
// Every fixture value is synthetic. The real data.js / trade-monthly.js /
// trade.js are loaded into a vm, as the other tests in this folder do.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const src = (f) => fs.readFileSync(path.join(repo, 'New for anti', f), 'utf8');
const host = (v) => JSON.parse(JSON.stringify(v));
const quiet = { log() {}, warn() {}, error() {} };

// data.js with /api/comtrade answering `body`.
function annual(body, headers = { 'X-Comtrade-Period': '2025' }) {
    const document = new Proxy({}, { get: () => () => null });
    const window = { document, addEventListener() {}, CountryCoords: () => [10, 10] };
    const fetch = async (url) => (String(url).startsWith('/api/comtrade?')
        ? new Response(JSON.stringify(body), { headers })
        : new Response('{}', { status: 404 }));
    vm.runInNewContext(src('data.js'), { window, document, fetch, URLSearchParams, Response,
        console: quiet, setTimeout, clearTimeout });
    return window;
}
function monthly(fetch = async () => new Response('{}', { status: 404 })) {
    const window = { ComtradeM49Names: { 156: 'China', 392: 'Japan' } };
    vm.runInNewContext(src('trade-monthly.js'), { window, console: quiet, Date, fetch, URLSearchParams });
    return window.TradeMonthly._internal;
}
const row = { reporterCode: 124, partnerCode: 156, flowCode: 'X', period: '2025', primaryValue: 1e7, netWgt: 100 };

// ---- A01: a multi-HS basket is summed, mirrors are not -------------------

test('A01: every HS line of a basket is trade; mirror reports of one line are not added', async () => {
    const baskets = { cobalt: ['8105', '2822', '283329'], lithium: ['283691', '2530', '282520'],
        graphite: ['2504', '3801'], chromium: ['2610', '720241', '720249'], tin: ['8001', '2609'] };
    for (const [cid, hs] of Object.entries(baskets)) {
        const rows = hs.map((cmdCode, i) => ({ ...row, cmdCode, primaryValue: (i + 1) * 1e7 }));
        const arcs = await annual({ data: rows }).fetchComtradeArcs(cid);
        assert.equal(arcs.length, 1, cid);
        assert.equal(arcs[0].usdValue, rows.reduce((s, r) => s + r.primaryValue, 0), cid);
    }
    // Same line, exporter's X and importer's M mirror: the larger, not the sum.
    const mirror = await annual({ data: [{ ...row, cmdCode: '2606' },
        { ...row, reporterCode: 156, partnerCode: 124, flowCode: 'M', cmdCode: '2606', primaryValue: 11e6 }] })
        .fetchComtradeArcs('bauxite');
    assert.equal(mirror[0].usdValue, 11e6);
});

test('A01: a basket keeps ore and metal tonnes apart instead of adding them', async () => {
    const arcs = await annual({ data: [{ ...row, cmdCode: '8001', netWgt: 1e6 }, { ...row, cmdCode: '2609', netWgt: 5e6 }] })
        .fetchComtradeArcs('tin');
    assert.equal(arcs[0].netWeightMt, null);
    assert.deepEqual(host(arcs[0].weightByHs), { 8001: 1e6, 2609: 5e6 });
});

test('A05 (annual): a child line under a basket heading is the same trade', async () => {
    // oil's basket is 2709; a 270900 row of the same route is not added to it.
    const arcs = await annual({ data: [{ ...row, cmdCode: '2709', primaryValue: 100e6 },
        { ...row, cmdCode: '270900', primaryValue: 100e6 }] }).fetchComtradeArcs('oil');
    assert.equal(arcs[0].usdValue, 100e6);
    // A code outside the basket is not this commodity.
    const alien = await annual({ data: [{ ...row, cmdCode: '2710' }] }).fetchComtradeArcs('oil');
    assert.equal(alien.length, 0);
});

// ---- A02 / A03: raw precision, null weight ------------------------------

test('A02: a small route keeps its value; rounding is display-only', async () => {
    const [a] = await annual({ data: [{ ...row, cmdCode: '2606', primaryValue: 400000, netWgt: 4500 }] })
        .fetchComtradeArcs('bauxite');
    assert.equal(a.usdValue, 400000);
    assert.equal(a.volume, 0.4);
    assert.equal(a.netWeightKg, 4500);
    assert.ok(a.netWeightMt > 0);
    assert.equal(a.percentage, 100);
});

test('A03: an unreported weight is null, not 0; a reported 0 stays 0', async () => {
    const [missing] = await annual({ data: [{ ...row, cmdCode: '2606', netWgt: null }] }).fetchComtradeArcs('bauxite');
    assert.equal(missing.netWeightMt, null);
    assert.equal(missing.weightPartial, true);
    const [zero] = await annual({ data: [{ ...row, cmdCode: '2606', netWgt: 0 }] }).fetchComtradeArcs('bauxite');
    assert.equal(zero.netWeightMt, 0);
});

test('A12 (annual): a partial body is flagged on every arc', async () => {
    const arcs = await annual({ partial: true, missing_chunks: 2, data: [{ ...row, cmdCode: '2606' }] })
        .fetchComtradeArcs('bauxite');
    assert.equal(arcs[0].partial, true);
    assert.match(src('app.js'), /first\.partial \? ' · 일부 자료 누락'/);
});

test('A02: trade.js formats small positives instead of printing 0', () => {
    const start = src('trade.js').indexOf('const fmtTradeAmount');
    const code = src('trade.js').slice(start, src('trade.js').indexOf('};', start) + 2);
    const ctx = {};
    vm.runInNewContext(`${code}; this.f = fmtTradeAmount;`, ctx);
    assert.equal(ctx.f(0.004), '<0.1');
    assert.equal(ctx.f(0.4), '0.4');
    assert.equal(ctx.f(0), '0');
    assert.equal(ctx.f(null), '—');
    assert.equal(ctx.f(0.004, 2), '<0.01');
});

// ---- A04 / A05: live monthly aggregation -------------------------------

const zero = { period: '202606', flowCode: 'X', partnerCode: 0, primaryValue: 0, netWgt: 0 };

test('A04: an explicit zero month is kept for every product, missing is not zero', () => {
    const t = monthly();
    assert.deepEqual(host(t.aggregateComtradeMonthly([{ ...zero, cmdCode: '2606' }], '2606').X),
        [{ month: '2026-06', usd: 0, kg: 0, kgKnown: true }]);
    // Weight known, value not: kept as a weight-only month.
    const kgOnly = host(t.aggregateComtradeMonthly([{ ...zero, cmdCode: '2606', primaryValue: null, netWgt: 7 }], '2606').X);
    assert.equal(kgOnly[0].usd, null);
    assert.equal(kgOnly[0].kg, 7);
    // Neither: nothing observed.
    assert.equal(t.aggregateComtradeMonthly([{ ...zero, cmdCode: '2606', primaryValue: null, netWgt: null }], '2606').X.length, 0);
});

test('A05: parent and child lines in one live response are not added', () => {
    const t = monthly();
    const got = host(t.aggregateComtradeMonthly(['2709', '270900'].map((cmdCode) => ({ ...zero, cmdCode, primaryValue: 100, netWgt: 1 })), '2709'));
    assert.equal(got.X[0].usd, 100);
    // Basket lines are summed in USD; their kg are not one quantity.
    const basket = host(t.aggregateComtradeMonthly([{ ...zero, cmdCode: '8105', primaryValue: 10, netWgt: 1 },
        { ...zero, cmdCode: '2822', primaryValue: 20, netWgt: 2 }, { ...zero, cmdCode: '9999', primaryValue: 99 }], '8105,2822,283329'));
    assert.equal(basket.X[0].usd, 30);
    assert.equal(basket.X[0].kgKnown, false);
    assert.equal(basket.X[0].kgMixed, true);
});

// ---- A11 / A12: live hold policy and partial bodies ---------------------

const lastMonths = () => {
    const now = new Date();
    const out = [];
    for (let i = 36; i >= 1; i--) {
        const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
        out.push(`${d.getUTCFullYear()}${String(d.getUTCMonth() + 1).padStart(2, '0')}`);
    }
    return out;
};

test('A11/A12: a collapsed month is held and a partial block is marked, on the live card too', async () => {
    const months = lastMonths();
    const last = months.at(-1);
    const t = monthly(async (url) => {
        const per = new URL(`http://x${url}`).searchParams.get('period').split(',');
        const data = per.map((p) => ({ period: p, flowCode: 'X', partnerCode: 0, cmdCode: '1201',
            primaryValue: p === last ? 2312 : 6e9, netWgt: 1e9 }));
        return new Response(JSON.stringify(per.includes(last) ? { partial: true, missing_chunks: 1, data } : { data }));
    });
    const d = await t.loadComtradeSeries('1201', '76');
    assert.equal(d.incomplete, 1);
    const lp = d.X.at(-1);
    assert.equal(lp.partial, true);
    assert.equal(lp.held, true);
    const html = t.liveCardHtml(d, 36, 'Brazil');
    assert.doesNotMatch(html, /<strong>0\.0023<\/strong>/);   // not the headline
    assert.match(html, /보류: /);                              // but kept on record
    assert.match(html, /일부 자료만 받았습니다/);
    assert.match(html, /부분 응답 구간/);
});

test('A11: the live hold rule matches the pipeline (1% of the median of earlier accepted months)', () => {
    const t = monthly();
    const pts = [100, 100, 100, 0.5, 0].map((usd, i) => ({ month: `2026-0${i + 1}`, usd, kg: 1, kgKnown: true }));
    t.applyPreviewHold(pts);
    assert.deepEqual(pts.map((p) => !!p.held), [false, false, false, true, true]);
    // Zero against no baseline is a value, not a hold.
    const first = [{ month: '2026-01', usd: 0, kg: 0, kgKnown: true }];
    t.applyPreviewHold(first);
    assert.equal(first[0].held, undefined);
});

// ---- A06 / A07 / A07b: bilateral table uses the backend analysis --------

test('A06/A07: a held share stays held and tied partners share a rank', () => {
    const t = monthly();
    const part = { meta: { value_basis: 'FOB' }, flows: { X: { metrics: { trade_value_usd: { world_total: 100 } }, rows: [
        { partner: '156', metrics: { trade_value_usd: 120, net_weight_kg: null },
            analysis: { trade_value_usd: { share_pct: null, share_reason: 'partner_exceeds_world', rank: 1 } } },
        { partner: '392', metrics: { trade_value_usd: 120, net_weight_kg: null },
            analysis: { trade_value_usd: { share_pct: null, share_reason: 'partner_exceeds_world', rank: 1 } } },
    ] } } };
    const html = t.bilateralHtml(part, { period: '202606', hs: '2709' });
    assert.doesNotMatch(html, /120\.0%/);
    assert.match(html, /세계합계 초과 · 보류/);
    assert.deepEqual([...html.matchAll(/class="tr-i">(\d+)/g)].map((m) => Number(m[1])), [1, 1]);
    assert.match(html, /금액\(FOB\)/);
});

test('A07b: a partner with weight but no USD is shown in the weight table', () => {
    const t = monthly();
    const part = { meta: {}, flows: { X: { metrics: {}, rows: [
        { partner: '156', metrics: { trade_value_usd: 50, net_weight_kg: 5e6 },
            analysis: { trade_value_usd: { share_pct: 50, rank: 1 }, net_weight_kg: { share_pct: 50, rank: 1 } } },
        { partner: '392', metrics: { trade_value_usd: null, net_weight_kg: 7e6 },
            analysis: { trade_value_usd: { share_pct: null, share_reason: 'measurement_missing', rank: null },
                net_weight_kg: { share_pct: 70, rank: 1 } } },
    ] } } };
    const html = t.bilateralHtml(part, { period: '202606', hs: '2602' });
    assert.match(html, /중량 기준 순위/);
    assert.match(html, /title="수출 · Japan · 7 천 톤"/);
    // Weight-only flow: the weight table is the one shown.
    const only = t.bilateralHtml({ meta: {}, flows: { X: { metrics: {}, rows: [part.flows.X.rows[1]] } } },
        { period: '202606', hs: '2602' });
    assert.match(only, /수출 상대국 · 중량/);
});

// ---- A08: comparability needs the same HS scope ------------------------

test('A08: same unit, different products are not compared', () => {
    const t = monthly();
    const points = [{ month: '2026-05', value: 10 }, { month: '2026-06', value: 10 }];
    const got = t.compareSources([{ source: 'ore', hs: '2603', flow: 'X', unit: 'kt', points },
        { source: 'refined', hs: '7403', flow: 'X', unit: 'kt', points }]);
    assert.equal(got[0].kind, 'scope');
    assert.match(t.comparisonHtml(got), /비교하지 않습니다/);
    // Same HS still compares (JODI vs GASTAT crude).
    const same = t.compareSources([{ source: 'a', hs: '2709', flow: 'X', unit: 'kt', points },
        { source: 'b', hs: '2709', flow: 'X', unit: 'kt', points }]);
    assert.equal(same[0].kind, 'overlap');
});

// ---- A09: every file of the newest period ------------------------------

test('A09: FOB export and CIF import files of one period are both selected', () => {
    const t = monthly();
    const p = (c) => `parts/${c.repeat(64)}.json`;
    const index = { entries: [
        { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: '202606', value_basis: 'FOB', flows: ['X'], path: p('a') },
        { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: '202607', value_basis: 'FOB', flows: ['X'], path: p('b') },
        { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: '202607', value_basis: 'CIF', flows: ['M'], path: p('c') },
        { frequency: 'M', reporter_iso3: 'CHL', hs: '7403', period: '202605', value_basis: 'FOB', flows: ['X'], path: p('d') },
    ] };
    const got = host(t.bilateralEntries(index, new Set(['2603', '7403']), 'CHL'));
    assert.deepEqual(got.map((e) => [e.hs, e.period, e.value_basis]),
        [['2603', '202607', 'FOB'], ['2603', '202607', 'CIF'], ['7403', '202605', 'FOB']]);
});

// ---- A10 / A13: no invented numbers, honest labels ---------------------

test('A13: the country stat names its real denominator and keeps directions apart', () => {
    const trade = src('trade.js');
    assert.doesNotMatch(trade, /'글로벌 비중'/);
    assert.match(trade, /확보 노선 내 금액 비중/);
    assert.match(trade, /확보 노선 내 금액 비중 \(수출 · 수입\)/);
    assert.match(trade, /`\$\{pct\(exportVol\)\} · \$\{pct\(importVol\)\}`/);
    assert.doesNotMatch(trade, /물동량/);
    assert.doesNotMatch(src('index.html'), /<span class="to-label">물동량<\/span>/);
});

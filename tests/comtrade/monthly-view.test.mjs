// Country-card 연간 / 월별 toggle: which commodity x country gets monthly
// data, and how each source's series is cleaned before it is shown.
//
//   node --test tests/comtrade/monthly-view.test.mjs
//
// Loads the real New for anti/trade-monthly.js with small inline fixtures
// shaped like the commodity_trade pipeline's public files.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function load() {
    const window = { ComtradeM49Names: { 156: 'China', 392: 'Japan' } };
    const ctx = vm.createContext({ window, console, Date });
    vm.runInContext(fs.readFileSync(path.join(repo, 'New for anti/trade-monthly.js'), 'utf8'), ctx);
    return window.TradeMonthly._internal;
}
const T = load();
// Arrays built inside the vm context have that realm's prototype; copy them
// into this realm before deepStrictEqual compares them.
const host = (v) => JSON.parse(JSON.stringify(v));

// Months relative to now, so the "dormant for 2+ years" rule never ages the fixtures.
const now = new Date();
const ym = (back) => {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - back, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
const compact = (m) => m.replace('-', '');

// `hold` mirrors what scripts/commodity_trade/preview_quality.py writes.
const comtradePt = (month, usd, flow = 'X', hold = null) => ({
    month, value: usd / 3, unit: 'kg', source: 'comtrade_preview', hs: '1201', flow, primary_value_usd: usd,
    publication: hold
        ? { policy: 'comtrade-preview-publication-v1', status: 'hold', eligible_for_display: false,
            flags: ['suspected_partial_month'], evidence: { ratio: hold } }
        : { policy: 'comtrade-preview-publication-v1', status: 'eligible', eligible_for_display: true, flags: [] },
});

function docs() {
    return {
        comtrade: { reporters: {
            BRA: { flows: {
                // May is real, the newest month is a partial count ($2,312).
                exports: { commodities: { soybeans: { hs: '1201', points: [comtradePt(ym(4), 6.29e9), comtradePt(ym(3), 2312, 'X', 3.7e-7)] } } },
                imports: { commodities: { soybeans: { hs: '1201', points: [comtradePt(ym(4), 34.9e6, 'M'), comtradePt(ym(3), 23.8e6, 'M')] } } },
            } },
        } },
        national: { reporters: {
            SAU: { flows: { exports: { commodities: { crude_oil: { hs: '2709', points: [
                { month: ym(12), value: 26355192, unit: 'metric_tons', source: 'saudi_gastat_tableau_monthly' },
                { month: ym(11), value: 24117778, unit: 'metric_tons', source: 'saudi_gastat_tableau_monthly' },
            ] } } } } },
        } },
        monthly: { sectors: {
            energy: { commodities: {
                crude_oil: { hs_stems: ['2709'], countries: {
                    // JODI publishes real zeros; they must stay.
                    THA: { points: [
                        { month: ym(5), value: 37, unit: 'KTONS', source: 'jodi_oil' },
                        { month: ym(4), value: 0, unit: 'KTONS', source: 'jodi_oil' },
                        { month: ym(3), value: 56, unit: 'KTONS', source: 'jodi_oil' },
                    ] },
                } },
                lng: { hs_stems: ['271111'], countries: {
                    // Stopped a decade ago.
                    ARE: { points: [
                        { month: '2016-04', value: 683, unit: 'M3', source: 'jodi_gas' },
                        { month: '2016-05', value: 751, unit: 'M3', source: 'jodi_gas' },
                    ] },
                } },
            } },
        } },
        bilateralIndex: { entries: [
            { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: compact(ym(4)), path: `parts/${'a'.repeat(64)}.json` },
            { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: compact(ym(2)), path: `parts/${'b'.repeat(64)}.json` },
            { frequency: 'M', reporter_iso3: 'CHL', hs: '9999', period: compact(ym(1)), path: `parts/${'c'.repeat(64)}.json` },
            { frequency: 'M', reporter_iso3: 'CHL', hs: '2603', period: compact(ym(1)), path: '../../escape.json' },
        ] },
        saudi: { points: [{ month: ym(3), value: 63176.98, unit: 'SAR_million', share_of_total_goods_export_value: 0.72 }] },
    };
}
// copper's HS comes from the priority panels; give it one.
function withCopper(d) {
    d.comtrade.reporters.CHL = { flows: { exports: { commodities: { copper: { hs: '2603', points: [
        { month: ym(3), value: 1, unit: 'kg', source: 'comtrade_preview', primary_value_usd: 3.86e9 },
    ] } } } } };
    return d;
}

test('no toggle where there is no monthly data', () => {
    const d = docs();
    assert.equal(T.buildView(d, 'platinum', 'USA'), null);   // not tracked monthly
    assert.equal(T.buildView(d, 'soybeans', 'USA'), null);   // tracked, but not for this country
    assert.equal(T.buildView(d, 'gas', 'ARE'), null);        // only a series that ended in 2016
    assert.equal(T.buildView({}, 'oil', 'SAU'), null);       // monthly files not deployed yet
});

test('a month the pipeline held is cut from the headline but kept on record', () => {
    const v = T.buildView(docs(), 'soybeans', 'BRA');
    const x = v.series.find((s) => s.flow === 'X');
    assert.equal(v.series[0].flow, 'X');                     // exports first
    assert.equal(x.unit, 'usd_m');
    assert.deepEqual(host(x.points.map((p) => p.month)), [ym(4)]);
    assert.equal(x.latest, ym(4));
    assert.equal(x.held.length, 1);
    assert.equal(x.held[0].month, ym(3));
    const html = T.seriesCardHtml(x, v.latest);
    assert.match(html, /보류/);
    assert.match(html, /0\.0023 M USD/);                    // never rounded to "0"
    assert.match(html, /직전 중앙값의 0\.1% 미만/);           // the pipeline's own ratio
    // Imports carry no hold: both months stay.
    assert.equal(v.series.find((s) => s.flow === 'M').points.length, 2);
});

test('the UI never holds a month on its own', () => {
    // Same collapse, but the pipeline marked it eligible: shown as published.
    const d = docs();
    d.comtrade.reporters.BRA.flows.exports.commodities.soybeans.points[1] = comtradePt(ym(3), 2312);
    const x = T.buildView(d, 'soybeans', 'BRA').series.find((s) => s.flow === 'X');
    assert.equal(x.held.length, 0);
    assert.equal(x.latest, ym(3));
});

test('zeros from JODI are data, not partial counts', () => {
    const v = T.buildView(docs(), 'oil', 'THA');
    const s = v.series[0];
    assert.deepEqual(host(s.points.map((p) => p.value)), [37, 0, 56]);
    assert.equal(s.held.length, 0);
    assert.equal(s.unitLabel, '천 톤');
});

test('Saudi: bulletin value is a separate reference card, tonnes become 천 톤', () => {
    const v = T.buildView(docs(), 'oil', 'SAU');
    assert.ok(v.saudi);
    const gastat = v.series.find((s) => s.source === 'saudi_gastat_tableau_monthly');
    assert.equal(gastat.unit, 'kt');
    assert.equal(Math.round(gastat.points[0].value), 26355);
    // Crude on any other country never gets the Saudi bulletin.
    assert.equal(T.buildView(docs(), 'oil', 'THA').saudi, null);
});

test('bilateral: newest part for the commodity HS, safe paths only', () => {
    const v = T.buildView(withCopper(docs()), 'copper', 'CHL');
    assert.equal(v.bilateral.period, compact(ym(2)));
    assert.match(v.bilateral.path, /^parts\/b{64}\.json$/);
    assert.equal(v.latest, ym(2));
});

test('partner codes: dashboard names, ISO3 fallback, Comtrade residual', () => {
    assert.deepEqual(host(T.partnerLabel(752)), ['SWE', 'SWE']);
    assert.equal(T.partnerLabel('899')[0], '기타');
    assert.deepEqual(host(T.partnerLabel(12345)), ['12345', 'M49 12345']);
});

test('trailing window is the latest month back 12, inclusive', () => {
    const pts = Array.from({ length: 15 }, (_, i) => ({ month: ym(15 - i), value: i + 1 }));
    const w = T.trailing12(pts);
    assert.equal(w.length, 12);
    assert.equal(w[w.length - 1].month, ym(1));
});

test('palm oil: country card reads the pipeline commodity palm_oil (HS 1511)', () => {
    assert.equal(T.MONTHLY_ID.palm_oil, 'palm_oil');
    const d = { comtrade: { reporters: { MYS: { flows: { exports: { commodities: { palm_oil: { hs: '1511', points: [
        { month: ym(3), value: 1, unit: 'kg', source: 'comtrade_preview', primary_value_usd: 17.3e6 },
    ] } } } } } } } };
    const v = T.buildView(d, 'palm_oil', 'MYS');
    assert.equal(v.series[0].hs, '1511');
    // One Comtrade preview month has nothing to be compared against.
    assert.match(T.seriesCardHtml(v.series[0], v.latest), /부분 집계인지 확인되지 않은/);
});

test('national units in single currency units are shown in millions, FOB and CIF apart', () => {
    const pts = [
        { month: ym(4), value: 1936186680, unit: 'THB_FOB', source: 'thailand_customs_statistics_report' },
        { month: ym(4), value: 3542423, unit: 'THB_CIF', source: 'thailand_customs_statistics_report' },
    ];
    const series = T.seriesFromPoints(pts, { flow: 'X', hs: '1511' });
    assert.equal(series.length, 2);
    const fob = series.find((s) => s.unit === 'thb_m_fob');
    assert.equal(fob.unitLabel, '백만 바트 (FOB)');
    assert.equal(Math.round(fob.points[0].value), 1936);
});

test('Comtrade monthly: breakdown rows collapse to the total, HS codes sum, months sort', () => {
    const rows = [
        // Same month/flow/HS: total plus a mode-of-transport breakdown row.
        { period: '202605', flowCode: 'X', partnerCode: 0, cmdCode: '2822', primaryValue: 100e6, netWgt: 10e6 },
        { period: '202605', flowCode: 'X', partnerCode: 0, cmdCode: '2822', primaryValue: 60e6, netWgt: 6e6 },
        // Second HS code of the same commodity, same month: summed.
        { period: '202605', flowCode: 'X', partnerCode: 0, cmdCode: '8105', primaryValue: 20e6, netWgt: null },
        { period: '202604', flowCode: 'X', partnerCode: 0, cmdCode: '2822', primaryValue: 90e6, netWgt: 9e6 },
        { period: '202605', flowCode: 'M', partnerCode: 0, cmdCode: '2822', primaryValue: 5e6, netWgt: 1e6 },
        // Re-exports and non-World partners are not part of the series.
        { period: '202605', flowCode: 'RX', partnerCode: 0, cmdCode: '2822', primaryValue: 7e6 },
        { period: '202605', flowCode: 'X', partnerCode: 156, cmdCode: '2822', primaryValue: 50e6 },
    ];
    const s = host(T.aggregateComtradeMonthly(rows));
    assert.deepEqual(s.X.map((p) => p.month), ['2026-04', '2026-05']);
    assert.equal(s.X[1].usd, 120e6);
    assert.equal(s.X[1].kgKnown, false);    // one HS code had no weight
    assert.equal(s.M[0].usd, 5e6);
});

test('Comtrade monthly: 36 complete months in three blocks of 12', () => {
    const blocks = host(T.monthBlocks(new Date(Date.UTC(2026, 8, 24))));
    assert.equal(blocks.length, 3);
    assert.deepEqual(blocks.map((b) => b.length), [12, 12, 12]);
    assert.equal(blocks[0][0], '202309');
    assert.equal(blocks[2][11], '202608');
});

test('Comtrade monthly: reporter codes use Comtrade\'s own where they differ', () => {
    assert.equal(T.reporterCodeFor('USA'), 842);
    assert.equal(T.reporterCodeFor('IND'), 699);
    assert.equal(T.reporterCodeFor(null), null);
});

test('Comtrade monthly card: range, YoY, and missing months are stated', () => {
    const X = Array.from({ length: 36 }, (_, i) => {
        const d = new Date(Date.UTC(2023, 8 + i, 1));
        return { month: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`, usd: (100 + i) * 1e6, kg: 1e9, kgKnown: true };
    }).filter((_, i) => i !== 30);   // one unreported month
    const html = T.liveCardHtml({ X, M: [], hs: '2709', failures: 0 }, 12, 'Saudi Arabia');
    assert.match(html, /12개월 중 11개월 보고/);
    assert.match(html, /전년 동월 \+9\.8%/);   // 2026-08 135 vs 2025-08 123
    assert.match(html, /최근 36개월 보고 없음/); // imports
    assert.match(html, /data-range="36"/);
});

test('fetchComtradeArcs: a blended year keeps one year per route and marks older routes', async () => {
    let payload = null;
    const fetchStub = async (url) => {
        if (!String(url).startsWith('/api/comtrade')) return new Response('{}', { status: 404 });
        return new Response(JSON.stringify(payload.body), { status: 200, headers: payload.headers });
    };
    const document = new Proxy({}, { get: () => () => null });
    const win = { fetch: fetchStub, document, addEventListener() {} };
    win.window = win;
    const ctx = vm.createContext({ ...win, console: { log() {}, warn() {}, error() {} }, URLSearchParams, Response, setTimeout, clearTimeout });
    vm.runInContext(fs.readFileSync(path.join(repo, 'New for anti/data.js'), 'utf8'), ctx);
    payload = {
        headers: { 'X-Comtrade-Period': '2025', 'X-Comtrade-Blend': '2024' },
        body: { data: [
            { reporterCode: 76, partnerCode: 156, flowCode: 'X', primaryValue: 33e9, netWgt: 1, period: '2025' },
            // Stray older row of the same route must not be added.
            { reporterCode: 156, partnerCode: 76, flowCode: 'M', primaryValue: 31e9, netWgt: 1, period: '2024' },
            { reporterCode: 682, partnerCode: 156, flowCode: 'X', primaryValue: 40e9, netWgt: 1, period: '2024' },
        ] },
    };
    const arcs = host((await ctx.window.fetchComtradeArcs('oil')).map((a) =>
        ({ s: a.sourceName, v: a.volume, y: a.dataYear, b: a.blendFrom, p: a.period })));
    const bra = arcs.find((a) => a.s === 'Brazil');
    assert.equal(bra.v, 33000);
    assert.equal(bra.y, '2025');
    const sau = arcs.find((a) => a.v === 40000);
    assert.equal(sau.y, '2024');
    assert.equal(sau.b, '2024');
    assert.equal(sau.p, '2025');
});

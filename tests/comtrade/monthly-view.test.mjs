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

const comtradePt = (month, usd, flow = 'X') => ({
    month, value: usd / 3, unit: 'kg', source: 'comtrade_preview', hs: '1201', flow, primary_value_usd: usd,
});

function docs() {
    return {
        comtrade: { reporters: {
            BRA: { flows: {
                // May is real, the newest month is a partial count ($2,312).
                exports: { commodities: { soybeans: { hs: '1201', points: [comtradePt(ym(4), 6.29e9), comtradePt(ym(3), 2312)] } } },
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

test('a partial Comtrade month is cut from the headline but kept on record', () => {
    const v = T.buildView(docs(), 'soybeans', 'BRA');
    const x = v.series.find((s) => s.flow === 'X');
    assert.equal(v.series[0].flow, 'X');                     // exports first
    assert.equal(x.unit, 'usd_m');
    assert.deepEqual(host(x.points.map((p) => p.month)), [ym(4)]);
    assert.equal(x.latest, ym(4));
    assert.equal(x.partial.length, 1);
    assert.equal(x.partial[0].month, ym(3));
    const html = T.seriesCardHtml(x, v.latest);
    assert.match(html, /0\.0023 M USD/);                     // never rounded to "0"
    assert.match(html, /부분 집계/);
    // Imports are not partial: both months stay.
    assert.equal(v.series.find((s) => s.flow === 'M').points.length, 2);
});

test('zeros from JODI are data, not partial counts', () => {
    const v = T.buildView(docs(), 'oil', 'THA');
    const s = v.series[0];
    assert.deepEqual(host(s.points.map((p) => p.value)), [37, 0, 56]);
    assert.equal(s.partial.length, 0);
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

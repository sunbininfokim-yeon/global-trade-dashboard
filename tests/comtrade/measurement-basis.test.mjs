// A point's measurement basis (#614): contained metal and declared goods
// weight can both end up on the same normalised unit ("kt"), so the monthly
// view must never merge them into one series or set them against each other.
//
//   node --test tests/comtrade/measurement-basis.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function load() {
    const window = { ComtradeM49Names: {} };
    const ctx = vm.createContext({ window, console, Date });
    vm.runInContext(fs.readFileSync(path.join(repo, 'New for anti/trade-monthly.js'), 'utf8'), ctx);
    return window.TradeMonthly._internal;
}
const T = load();
const host = (v) => JSON.parse(JSON.stringify(v));

const now = new Date();
const ym = (back) => {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - back, 1));
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
// kg points, the way the national/priority files carry them.
const pt = (month, kg, basis, where = 'normalized') => ({
    month, value: kg, unit: 'kg', source: 'nat_office',
    ...(basis ? (where === 'normalized' ? { normalized: { measurement_basis: basis } } : { measurement_basis: basis }) : {}),
});

test('goods weight and the unknown default read as one basis', () => {
    for (const b of [undefined, '', 'unknown', 'goods_net_mass']) {
        assert.equal(T.basisOf(b ? { normalized: { measurement_basis: b } } : {}), '', String(b));
    }
    assert.equal(T.basisOf({ normalized: { measurement_basis: 'contained_copper_mass' } }), 'contained_copper_mass');
    // The top-level field counts too (monthly points carry both).
    assert.equal(T.basisOf({ measurement_basis: 'contained_copper_mass' }), 'contained_copper_mass');
});

test('same source, unit and month with different bases stay two series', () => {
    const pts = [
        pt(ym(1), 5e9, 'goods_net_mass'), pt(ym(0), 6e9, 'goods_net_mass'),
        pt(ym(1), 2e9, 'contained_copper_mass'), pt(ym(0), 3e9, 'contained_copper_mass', 'top'),
    ];
    const series = host(T.seriesFromPoints(pts, { flow: 'X', hs: '2603' }));
    assert.equal(series.length, 2);
    const goods = series.find((s) => !s.basis);
    const contained = series.find((s) => s.basis === 'contained_copper_mass');
    assert.deepEqual(goods.points.map((p) => p.value), [5e3, 6e3]);
    assert.deepEqual(contained.points.map((p) => p.value), [2e3, 3e3]);
    // Nothing was overwritten: each month kept its own value.
    assert.match(contained.unitLabel, /구리 함량/);
    assert.doesNotMatch(goods.unitLabel, /구리 함량/);
});

test('a series without a basis behaves exactly as before', () => {
    const series = host(T.seriesFromPoints([pt(ym(1), 1e9), pt(ym(0), 2e9, 'unknown')], { flow: 'X', hs: '2603' }));
    assert.equal(series.length, 1);
    assert.equal(series[0].basis, '');
    assert.equal(series[0].unitLabel, '천 톤');
});

test('same unit and scope but different basis is not compared numerically', () => {
    const points = [{ month: ym(1), value: 10 }, { month: ym(0), value: 10 }];
    const got = host(T.compareSources([
        { source: 'customs', hs: '2603', flow: 'X', unit: 'kt', basis: '', points },
        { source: 'cochilco', hs: '2603', flow: 'X', unit: 'kt', basis: 'contained_copper_mass', points },
    ]));
    assert.equal(got.length, 1);
    assert.equal(got[0].kind, 'basis');
    const html = T.comparisonHtml(got);
    assert.match(html, /측정 기준이 다릅니다/);
    assert.match(html, /신고 상품 중량/);
    assert.match(html, /구리 함량 기준/);
    assert.doesNotMatch(html, /평균 차이/);
});

test('the same basis on both sides still compares as before', () => {
    const points = [{ month: ym(1), value: 10 }, { month: ym(0), value: 10 }];
    const got = host(T.compareSources([
        { source: 'a', hs: '2603', flow: 'X', unit: 'kt', basis: 'contained_copper_mass', points },
        { source: 'b', hs: '2603', flow: 'X', unit: 'kt', basis: 'contained_copper_mass', points },
    ]));
    assert.equal(got[0].kind, 'overlap');
    // And series with no basis field at all (older callers) still compare.
    const legacy = host(T.compareSources([
        { source: 'a', hs: '2603', flow: 'X', unit: 'kt', points },
        { source: 'b', hs: '2603', flow: 'X', unit: 'kt', points },
    ]));
    assert.equal(legacy[0].kind, 'overlap');
});

test('a different unit still reports the unit note, not the basis note', () => {
    // Chile today: Cochilco's own unit string already separates the series.
    const points = [{ month: ym(1), value: 10 }, { month: ym(0), value: 10 }];
    const got = host(T.compareSources([
        { source: 'customs', hs: '2603', flow: 'X', unit: 'kt', basis: '', points },
        { source: 'cochilco', hs: '2603', flow: 'X', unit: 'kMT_cu_content', basis: 'contained_copper_mass', points },
    ]));
    assert.equal(got[0].kind, 'units');
});

test('every measurement basis in the published monthly file is covered', () => {
    // A new basis would silently read as "other"; make that a visible choice.
    const doc = JSON.parse(fs.readFileSync(path.join(repo, 'New for anti/public/data/commodity_trade_monthly_v1.json'), 'utf8'));
    const seen = new Set();
    const walk = (o) => {
        if (Array.isArray(o)) o.forEach(walk);
        else if (o && typeof o === 'object') {
            if (typeof o.measurement_basis === 'string') seen.add(o.measurement_basis);
            Object.values(o).forEach(walk);
        }
    };
    walk(doc);
    const known = new Set(['goods_net_mass', 'unknown', 'contained_copper_mass']);
    for (const b of seen) assert.ok(known.has(b), `new measurement_basis "${b}": add a label in trade-monthly.js BASIS_LABEL`);
});

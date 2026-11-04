import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dividedAuthorityHtml, isDivided, dividedAuthorityKeys } from '../country-explorer/special/divided-authority.js';
import { conflictCrosses, isConflictCountry } from '../country-explorer/world-map.js';

const board = JSON.parse(readFileSync(new URL('../../../public/data/elections_board_v1.json', import.meta.url)));
const personnel = (iso) => JSON.parse(readFileSync(new URL(`../../../public/data/personnel/${iso}.json`, import.meta.url)));
const row = (iso) => ({ ...board.countries.find((c) => c.iso3 === iso), personnel: personnel(iso) });

test('the 14 roster countries are on the board, so the world map opens them', () => {
    const iso = new Set(board.countries.map((c) => c.iso3));
    for (const code of ['ARM', 'AZE', 'EGY', 'ESP', 'GEO', 'GRC', 'IRQ', 'KWT', 'LBN', 'LBY', 'MAR', 'PAN', 'QAT', 'YEM']) {
        assert.ok(iso.has(code), `${code} missing from the board`);
    }
});

test('Libya and Yemen draw each side as its own numbered tier group', () => {
    const lby = row('LBY');
    assert.ok(isDivided(lby));
    const html = dividedAuthorityHtml(lby);
    assert.match(html, /트리폴리\(서부\)/);
    assert.match(html, /대표원\(동부\)/);
    assert.match(html, /elections-org-box/);
    assert.match(html, /어느 쪽이 정통인지 판정하지 않습니다/);
    assert.ok(dividedAuthorityKeys(lby).has('tripoli'));
    const yem = dividedAuthorityHtml(row('YEM'));
    assert.match(yem, /대통령지도위원회/);
    assert.match(yem, /사나\(후티\)/);
    assert.equal(dividedAuthorityHtml(row('GRC')), null);
});

test('conflict countries get an X built from GeoJSON lines', () => {
    assert.ok(isConflictCountry(row('LBY')) && !isConflictCountry(row('GRC')));
    const square = { type: 'Feature', properties: { iso: 'X' }, geometry: { type: 'Polygon', coordinates: [[[10, 20], [20, 20], [20, 30], [10, 30], [10, 20]]] } };
    const out = conflictCrosses([square, { ...square, properties: { iso: 'Y' } }], (f) => f.properties.iso === 'X');
    assert.equal(out.features.length, 1);
    const [a, b] = out.features[0].geometry.coordinates;
    assert.deepEqual(a[0], [11.8, 21.8]);
    assert.ok(a.length > 10 && b.length > 10, 'lines are densified to follow the globe');
});

import { campTabs, campHtml, controlColor, controlCamp, controlMapSummaryHtml } from '../country-explorer/special/divided-authority.js';

test('each side of a divided country gets its own structured dashboard', () => {
    const lby = row('LBY');
    assert.deepEqual(campTabs(lby).map(([, key]) => key), ['camp_government', 'camp_opposition']);
    const opp = campHtml(lby, 'camp_opposition');
    for (const label of ['위상', '근거지', '무장 세력', '대외 후원', '정통성 주장', '통제 지역', '지도부']) assert.match(opp, new RegExp(label));
    assert.match(opp, /벵가지/);
    assert.match(opp, /검증 전/, 'background facts are labelled as unverified');
    assert.match(campHtml(row('YEM'), 'camp_opposition'), /후티/);
    assert.equal(campHtml(row('GRC'), 'camp_government'), null);
});

test('every admin1 region of Libya and Yemen is assigned to a side, contested ones dimmed', () => {
    for (const iso of ['LBY', 'YEM']) {
        const country = row(iso);
        const geo = JSON.parse(readFileSync(new URL(`../../../public/data/admin1/${iso}.json`, import.meta.url)));
        for (const f of geo.features) {
            assert.ok(controlCamp(country, f.properties.code), `${iso} ${f.properties.code} has no side`);
            assert.equal(controlColor(country, f.properties.code).length, 4);
        }
        assert.match(controlMapSummaryHtml(country), /지역을 누르면/);
    }
    assert.equal(controlCamp(row('YEM'), 'YE-SA'), 'opposition');
    assert.ok(controlColor(row('YEM'), 'YE-TA')[3] < controlColor(row('YEM'), 'YE-AD')[3]);
});

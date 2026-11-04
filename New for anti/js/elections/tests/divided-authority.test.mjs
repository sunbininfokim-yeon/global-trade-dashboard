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

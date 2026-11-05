import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { regionLeaderIndex, regionCardHtml } from '../country-explorer/special/region-leaders.js';

const root = new URL('../../../public/data/', import.meta.url);
const read = (p) => JSON.parse(readFileSync(new URL(p, root)));
const country = (iso3) => ({ iso3, personnel: read(`personnel/${iso3}.json`) });
const features = (iso3) => read(`admin1/${iso3}.json`).features;

test('region heads are matched to admin1 shapes for the countries whose rosters name them', () => {
    const cases = { KOR: 17, JPN: 47, DEU: 16, CAN: 13, SAU: 12 };
    for (const [iso3, expected] of Object.entries(cases)) {
        const index = regionLeaderIndex(country(iso3), features(iso3));
        const covered = features(iso3).filter((f) => index.has(f.properties.code)).length;
        assert.equal(covered, expected, `${iso3} covered ${covered}`);
    }
    const kor = regionLeaderIndex(country('KOR'), features('KOR'));
    assert.match(kor.get('KR-11')[0].name, /오세훈/);
    assert.equal(kor.get('KR-29')[0].name, kor.get('KR-46')[0].name, 'merged Jeonnam-Gwangju covers both shapes');
});

test('legislators with a constituency are not shown as region heads', () => {
    const index = regionLeaderIndex(country('TUR'), features('TUR'));
    assert.equal(index.size, 0, 'Turkey roster has no governors yet');
});

test('a region card shows the head as an org box, or says the roster is not collected', () => {
    const kor = features('KOR').find((f) => f.properties.code === 'KR-11');
    const html = regionCardHtml(country('KOR'), kor, regionLeaderIndex(country('KOR'), features('KOR')).get('KR-11'));
    assert.match(html, /elections-org-box/);
    assert.match(html, /광역단체장/);
    const tur = features('TUR').find((f) => f.properties.code === 'TR-34');
    assert.match(regionCardHtml(country('TUR'), tur, []), /아직 수집되지 않았습니다/);
});

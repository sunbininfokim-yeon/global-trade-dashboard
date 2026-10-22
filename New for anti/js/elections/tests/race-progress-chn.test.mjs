import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { raceProgressContent } from '../country-explorer/special/race-progress.js';

const data = JSON.parse(readFileSync(new URL('../../../public/data/race_progress_chn_v1.json', import.meta.url)));
const at = (iso) => Date.parse(`${iso}T04:00:00Z`); // noon in Beijing
const render = (iso, race = data) => raceProgressContent({ iso3: 'CHN', race_progress: race }, at(iso));

test('published CHN plenum file renders every plenum with its year', () => {
    assert.equal(data.schema, 'race_progress_v1');
    assert.equal(data.mode, 'party_plenum_cycle');
    const html = render('2026-10-22');
    for (const p of data.plenums) assert.match(html, new RegExp(p.label_ko));
    assert.match(html, /2022\.10\.23/);
    assert.match(html, /2026\.10\.26~29/);
    assert.match(html, /4회 완료/);
    assert.match(html, /追认/);
});

test('5th plenum phase follows the Beijing date, never a stored status', () => {
    assert.match(render('2026-10-25'), /5중전회[\s\S]*?예정/);
    assert.match(render('2026-10-27'), /5중전회[\s\S]*?진행 중/);
    const closed = render('2026-10-30');
    assert.match(closed, /폐막 · 공보 반영 대기/);
    assert.doesNotMatch(closed, /5회 완료/);
});

test('a filled-in communique outcome marks the plenum completed', () => {
    const race = structuredClone(data);
    race.plenums.at(-1).outcome_ko = '결정 통과';
    const html = render('2026-10-30', race);
    assert.match(html, /5회 완료/);
    assert.doesNotMatch(html, /공보 반영 대기/);
});

test('non-https source links are dropped', () => {
    const race = structuredClone(data);
    race.politburo_meetings[0].source_url = 'javascript:alert(1)';
    assert.doesNotMatch(render('2026-10-22', race), /javascript:/);
});

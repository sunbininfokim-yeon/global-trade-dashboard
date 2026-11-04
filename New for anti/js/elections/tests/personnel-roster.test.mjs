import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { personnelRosterHtml } from '../country-explorer/special/personnel-roster.js';

const dir = new URL('../../../public/data/personnel/', import.meta.url);
const index = JSON.parse(readFileSync(new URL('index.json', dir)));
const load = (iso) => JSON.parse(readFileSync(new URL(`${iso}.json`, dir)));

test('every published country renders without throwing and shows its as_of', () => {
    const countries = Object.keys(index.countries);
    assert.ok(countries.length >= 30);
    for (const iso of countries) {
        const data = load(iso);
        const html = personnelRosterHtml(data);
        assert.ok(html && html.length > 500, `${iso} rendered too little`);
        assert.match(html, new RegExp(`기준일 ${data.as_of}`));
        assert.doesNotMatch(html, /\[object Object\]|undefined/, `${iso} leaked a raw value`);
    }
});

test('people link to their source and seat tables become bars', () => {
    const gbr = personnelRosterHtml(load('GBR'));
    assert.match(gbr, /Andy Burnham/);
    assert.match(gbr, /pr-group/);
    assert.match(gbr, /Labour/);
    assert.match(gbr, /href="https:\/\/www\.gov\.uk/);
    assert.match(gbr, /이 명단에 없는 것/);
});

test('internal ids stay hidden and unsafe urls never become links', () => {
    const jpn = personnelRosterHtml(load('JPN'));
    assert.doesNotMatch(jpn, /mona_cd|hr_cmt_id/);
    const html = personnelRosterHtml({ schema: 'x_personnel_v1', as_of: '2026-11-04', president: { name: 'X', source_url: 'javascript:alert(1)' } });
    assert.doesNotMatch(html, /javascript:/);
    assert.equal(personnelRosterHtml(null), null);
});

import { personnelCategory } from '../country-explorer/special/personnel-roster.js';

test('roster splits into 국가원수·대통령실 / 행정부 / 의회 / 지방 tabs', () => {
    const kor = personnelRosterHtml(load('KOR'));
    for (const tab of ['국가원수·대통령실', '의회', '지방']) assert.match(kor, new RegExp(`>${tab}<`));
    assert.equal((kor.match(/type="radio"/g) || []).length, (kor.match(/data-pr-pane=/g) || []).length);
    assert.equal(personnelCategory('president'), 'head');
    assert.equal(personnelCategory('prime_minister'), 'executive');
    assert.equal(personnelCategory('knesset_27'), 'legislature');
    assert.equal(personnelCategory('governors'), 'local');
    assert.equal(personnelCategory('orientation'), 'other');
});

test('every top-level section of every country lands in exactly one tab', () => {
    for (const iso of Object.keys(index.countries)) {
        const html = personnelRosterHtml(load(iso));
        const panes = (html.match(/data-pr-pane=/g) || []).length;
        assert.ok(panes >= 1, `${iso} has no tabs`);
        assert.equal((html.match(/ checked/g) || []).length, 1, `${iso} should open one tab`);
    }
});

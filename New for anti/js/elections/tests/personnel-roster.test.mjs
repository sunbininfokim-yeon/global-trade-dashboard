import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { personnelCategories, personnelPartHtml, personnelCategory } from '../country-explorer/special/personnel-roster.js';

const dir = new URL('../../../public/data/personnel/', import.meta.url);
const index = JSON.parse(readFileSync(new URL('index.json', dir)));
const load = (iso) => JSON.parse(readFileSync(new URL(`${iso}.json`, dir)));
const cats = (iso) => [...personnelCategories(load(iso)).keys()];

test('every published country renders its categories without leaking raw values', () => {
    const countries = Object.keys(index.countries);
    assert.ok(countries.length >= 30);
    for (const iso of countries) {
        const data = load(iso);
        const all = personnelPartHtml(data, [...personnelCategories(data).keys()]);
        assert.ok(all.length > 500, `${iso} rendered too little`);
        assert.match(all, new RegExp(`기준일 ${data.as_of}`));
        assert.doesNotMatch(all, /\[object Object\]|undefined/, `${iso} leaked a raw value`);
    }
});

test('offices follow each country: 대통령실, 총리실, both for semi-presidential systems', () => {
    assert.ok(cats('FRA').includes('president') && cats('FRA').includes('pm'));
    assert.ok(cats('KOR').includes('president') && !cats('KOR').includes('pm'));
    assert.ok(cats('GBR').includes('pm') && !cats('GBR').includes('president'), 'UK PM is hoisted out of executive');
    assert.ok(cats('DEU').includes('pm') && cats('DEU').includes('executive'), 'chancellor goes to 총리실');
    assert.ok(cats('SAU').includes('monarch'));
    assert.ok(cats('IRN').includes('leader'));
    assert.equal(personnelCategory('prime_minister'), 'pm');
    assert.equal(personnelCategory('knesset_27'), 'legislature');
    assert.equal(personnelCategory('governors'), 'local');
    assert.equal(personnelCategory('orientation'), 'orientation');
});

test('a part only holds the categories asked for, and nothing for an absent category', () => {
    const gbr = load('GBR');
    const pm = personnelPartHtml(gbr, ['pm']);
    assert.match(pm, /Andy Burnham/);
    assert.doesNotMatch(pm, /Labour/);
    assert.match(personnelPartHtml(gbr, ['legislature']), /pr-group/);
    assert.equal(personnelPartHtml(gbr, ['monarch']), '');
    assert.equal(personnelPartHtml(null, ['pm']), '');
});

test('internal ids stay hidden and unsafe urls never become links', () => {
    const jpn = load('JPN');
    assert.doesNotMatch(personnelPartHtml(jpn, [...personnelCategories(jpn).keys()]), /mona_cd|hr_cmt_id/);
    const html = personnelPartHtml({ as_of: '2026-11-04', president: { name: 'X', source_url: 'javascript:alert(1)' } }, ['president']);
    assert.match(html, /X/);
    assert.doesNotMatch(html, /javascript:/);
});

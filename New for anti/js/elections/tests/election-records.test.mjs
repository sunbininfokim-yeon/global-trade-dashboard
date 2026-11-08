import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { electionRecordsHtml } from '../country-explorer/special/election-records.js';

const dir = new URL('../../../public/data/election_records/', import.meta.url);
const index = JSON.parse(readFileSync(new URL('index.json', dir)));
const load = (iso) => JSON.parse(readFileSync(new URL(`${iso}.json`, dir)));
const card = (iso) => electionRecordsHtml({ iso3: iso, election_records: load(iso) });

test('every published country renders offices in executive → legislature → local order', () => {
    const countries = Object.keys(index.countries);
    assert.ok(countries.length >= 50);
    for (const iso of countries) {
        const html = card(iso);
        if (!html) continue;
        assert.doesNotMatch(html, /\[object Object\]|undefined|NaN/, `${iso} leaked a raw value`);
        const at = (label) => html.indexOf(label);
        const order = ['· 행정수반', '· 의회', '· 지방선거'].map(at).filter((i) => i >= 0);
        assert.deepEqual(order, [...order].sort((a, b) => a - b), `${iso} office order`);
    }
});

test('a runoff shows the first round and the runoff separately (Brazil)', () => {
    const html = card('BRA');
    assert.match(html, /1차 · /);
    assert.match(html, /결선 · /);
    assert.match(html, /Lula/);
    assert.match(html, /득표율은 표에 있는 후보 득표의 합/);
});

test('a parliamentary executive points at the chamber that produces it (Germany)', () => {
    const html = card('DEU');
    assert.match(html, /의회에서 선출/);
    assert.match(html, /근거 선거/);
    assert.match(html, /직전 선거 기록이 아직 수집되지 않았습니다/); // Bundestag row not collected yet
});

test('countries due for issue research say so until issues arrive', () => {
    const html = card('KOR');
    assert.match(html, /쟁점/);
});

test('researched input overrides derived fields and shows candidates and turnout', () => {
    const data = {
        country: 'XXX', issues_expected: true,
        offices: [{ key: 'executive', system_id: 'x-president', title_ko: '대통령', term_years: 5, records: [{
            election_id: 'x-2025', date: '2025-06-03', turnout_pct: 79.4, term_start: '2025-06-04', term_end: '2030-06-03', origin: 'researched',
            candidates: [{ name: 'A', party: 'P1', votes: 100, vote_pct: 49.42, elected: true }, { name: 'B', party: 'P2', votes: 80, vote_pct: 41.15 }],
        }], next: { date: '2030-06-05', date_status: 'scheduled' } }],
        issues: [{ title_ko: '경제', summary_ko: '물가', positions: [{ actor_ko: 'A', stance_ko: '감세' }] }],
    };
    const html = electionRecordsHtml({ iso3: 'XXX', election_records: data });
    assert.match(html, /투표율<\/span><strong>79\.4%/);
    assert.match(html, /49\.42%/);
    assert.match(html, /임기<\/span><strong>/);
    assert.match(html, /감세/);
    assert.doesNotMatch(html, /선거 일정판에서 옮긴 기록/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { officialResult, officialLine } from '../data/official-results.js';

const race = {
    race_id: 'USA:GA:senate', state: 'GA', precincts_reporting: 1200, precincts_total: 2600, authority_ko: '조지아 국무장관실',
    candidates: [{ name: 'Jon Ossoff', party: 'DEM', votes: 2100530, pct: 59.01 }, { name: 'Mike Collins', party: 'REP', votes: 1459087, pct: 40.99 }],
    leader: { name: 'Jon Ossoff', party: 'DEM', margin_pct: 18.02 }, status: 'unofficial_count', fetched_at: '2026-11-04T06:00:00Z',
};

test('official count line names the state source, both leaders and precincts, and never a winner', () => {
    const html = officialLine(race);
    assert.match(html, /주정부 개표\(비공식\)/);
    assert.match(html, /Ossoff D 59\.0% · Collins R 41\.0%/);
    assert.match(html, /투표구 1200\/2600/);
    assert.match(html, /is-dem/);
    assert.doesNotMatch(html, /당선/);
    assert.match(officialLine({ ...race, stale: true }), /갱신 지연/);
    assert.equal(officialLine(null), '');
});

test('the board carries official results only by race id', () => {
    const board = { officialResults: { races: { 'USA:GA:senate': race } } };
    assert.equal(officialResult(board, 'USA:GA:senate'), race);
    assert.equal(officialResult(board, 'USA:GA:governor'), null);
    assert.equal(officialResult({}, 'USA:GA:senate'), null);
});

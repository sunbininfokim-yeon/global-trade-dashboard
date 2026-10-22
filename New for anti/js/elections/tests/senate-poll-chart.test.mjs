import test from 'node:test';
import assert from 'node:assert/strict';
import { senatePollChartHtml } from '../country-explorer/special/usa-senate-poll-chart.js';

const now = Date.parse('2026-10-22T12:00:00Z');
const obs = (id, pollster, end, answers, population = 'lv') => ({ id, pollster, pollster_group: pollster, field_end: end, population, answers });
const race = (state, observations, window = {}) => ({ race_id: `USA:${state}:senate`, state, office: 'senate', observations, windows: { '14': window } });
const two = (d, r) => [{ name: 'Dem Name', pct: d, party: 'DEM' }, { name: 'Rep Name', pct: r, party: 'REP' }];

test('chart draws only the pipeline verdict and pollster dots, never an average', () => {
    const races = [
        race('TX', [obs('a', 'A', '2026-10-19', two(48, 50)), obs('b', 'B', '2026-10-18', two(50, 49))], { status: 'tie', included_ids: ['a', 'b'] }),
        race('OH', [obs('c', 'C', '2026-10-19', two(52, 46))], { status: 'poll_lead', party: 'DEM', included_ids: ['c'] }),
        race('MI', [obs('d', 'D', '2026-10-08', two(47, 45))], { status: 'no_recent_poll' }),
    ];
    const html = senatePollChartHtml(races, { now });
    assert.match(html, /상원 여론조사 한눈에/);
    assert.match(html, /동률·엇갈림/); assert.match(html, /D 우세 \(복수 기관\)/); assert.match(html, /14일 집계 없음 · 최근 10\/08/);
    assert.equal((html.match(/elections-senate-dot /g) || []).length, 4);
    assert.equal((html.match(/is-counted/g) || []).length, 3);
    assert.doesNotMatch(html, /평균 [+-]?\d/);
    assert.ok(html.indexOf('>TX<') < html.indexOf('>MI<'), 'closest counted race first');
});

test('older than 30 days is not drawn; fewer than three Senate races renders nothing', () => {
    const races = [race('AL', [obs('x', 'X', '2026-08-01', two(40, 55))]), race('SC', [obs('y', 'Y', '2026-10-20', two(40, 55))]), race('NM', [obs('z', 'Z', '2026-10-20', two(55, 40))])];
    const html = senatePollChartHtml(races, { now });
    assert.equal((html.match(/elections-senate-dot /g) || []).length, 2);
    assert.equal(senatePollChartHtml(races.slice(0, 2), { now }), '');
});

test('Alaska ranked-choice: first-preference rows yield to final-round rows from the same wave', () => {
    const first = [{ name: 'Mary Peltola', pct: 47, party: 'DEM' }, { name: 'Dan S. Sullivan', pct: 44, party: 'REP' }, { name: 'Other', pct: 4, party: 'OTH' }, { name: 'Heikes', pct: 1, party: 'REP' }];
    const races = [
        race('AK', [obs('q15', 'DFP', '2026-10-16', first), obs('q18', 'DFP', '2026-10-16', [{ name: 'Mary Peltola', pct: 51, party: 'DEM' }, { name: 'Dan S. Sullivan', pct: 49, party: 'REP' }])]),
        race('TX', [obs('a', 'A', '2026-10-19', two(48, 50))]), race('OH', [obs('c', 'C', '2026-10-19', two(52, 46))]),
    ];
    const html = senatePollChartHtml(races, { now });
    const ak = html.slice(html.indexOf('>AK<'), html.indexOf('</button>', html.indexOf('>AK<')));
    assert.equal((ak.match(/elections-senate-dot /g) || []).length, 1);
    assert.match(ak, /Peltola 51/);
    assert.match(html, /순위선택투표/);
});

test('independent challenger is drawn on the left in its own colour', () => {
    const ne = race('NE', [obs('n', 'N', '2026-10-05', [{ name: 'Dan Osborn', pct: 46, party: 'IND' }, { name: 'Pete Ricketts', pct: 48, party: 'REP' }]), obs('m', 'M', '2026-10-06', [{ name: 'Dan Osborn', pct: 49, party: 'IND' }, { name: 'Pete Ricketts', pct: 45, party: 'REP' }])]);
    const html = senatePollChartHtml([ne, race('TX', [obs('a', 'A', '2026-10-19', two(48, 50))]), race('OH', [obs('c', 'C', '2026-10-19', two(52, 46))])], { now });
    assert.match(html, /is-ind/); assert.match(html, /\(무소속\)/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { pollSignal } from '../data/usa-election-context.js';
import { pollEvidenceHtml } from '../country-explorer/special/usa-election-evidence.js';

test('an outdated pre-election board cannot keep a poll colour after election day', () => {
    const board = { schema: 'usa_live_polls_v1', source_status: 'ok',
        fetched_at: '2026-11-03T16:00:00Z', stale_after_hours: 48 };
    const health = { status: 'ok' };
    const race = { phase: 'pre_election', election_date: '2026-11-03',
        windows: { '7': { status: 'poll_lead', party: 'REP', leader: 'Candidate', pollster_count: 2 } } };
    assert.equal(pollSignal(race, board, health, 7, Date.parse('2026-11-03T20:00:00Z')).party, 'REP');
    assert.equal(pollSignal(race, board, health, 7, Date.parse('2026-11-04T00:00:00Z')).party, 'REP');
    assert.deepEqual(pollSignal(race, board, health, 7, Date.parse('2026-11-04T12:00:00Z')),
        { status: 'awaiting_certified_result', party: null });
    race.phase = 'certified_result';
    race.result = { status: 'certified', party: 'DEM', winner: 'Winner' };
    assert.equal(pollSignal(race, board, health, 7, Date.parse('2026-11-04T12:00:00Z')).party, 'DEM');
});

test('a delayed live-board refresh does not expose accumulated polls after the date cutoff', () => {
    const priorDate = new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10);
    const race = { phase: 'pre_election', election_date: priorDate,
        observations: [{ pollster: 'Example', field_end: priorDate, answers: [] }] };
    const html = pollEvidenceHtml(race, null, null);
    assert.match(html, /선거 종료 · 공식 결과 대기/);
    assert.doesNotMatch(html, /누적 조사 1건 보기/);
});

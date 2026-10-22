import test from 'node:test';
import assert from 'node:assert/strict';
import { readIsraelFixture } from './fixtures/israel-snapshot.mjs';
import { weeklySeatRows } from '../data/israel-trend.js';
import { israelAnalysisHtml } from '../country-explorer/special/israel-analysis.js';
const original = JSON.parse(readIsraelFixture('israel_election_analysis_v1.json'));
const makeBoard = () => {
    const board = structuredClone(original);
    const poll = board.observations.find(r => r.question_id === 'reported_seats' && r.review_status === 'accepted');
    poll.poll_id = 'sample'; poll.published_at = '2026-10-19T18:00:00Z'; poll.field_end = '2026-10-18';
    board.observations = [poll];
    return board;
};
test('publication window includes exactly seven days, newest publication first, not field date', () => {
    const b=makeBoard(), sample=b.observations[0];
    b.observations=[['old','2026-10-14'],['boundary','2026-10-15'],['latest','2026-10-21'],['future','2026-10-22']].map(([id,day])=>({...structuredClone(sample),poll_id:id,published_at:day+'T12:00:00Z',field_end:'2026-10-12'}));
    assert.deepEqual(weeklySeatRows(b,'2026-10-21').map(r=>r.poll.poll_id),['latest','boundary']);
});
test('Israeli publication day handles UTC midnight boundaries and missing dates stay missing', () => {
    const b=makeBoard();b.observations[0].published_at='2026-10-14T22:30:00Z';
    assert.equal(weeklySeatRows(b,'2026-10-21')[0].publishedDay,'2026-10-15');
    for(const value of [null,'bad date']) {b.observations[0].published_at=value;assert.deepEqual(weeklySeatRows(b,'2026-10-21'),[]);}
});
test('partial, held, hypothetical, invalid and future fieldwork polls are excluded', () => {
    for(const patch of [{review_status:'partial'},{review_status:'held'},{scenario:'hypothetical'},{field_end:null},{field_end:'2026-10-22'},{seat_sum:119}]) {
        const b=makeBoard();Object.assign(b.observations[0],patch);assert.deepEqual(weeklySeatRows(b,'2026-10-21'),[]);
    }
});
test('four disjoint cooperation categories preserve every reported seat without mutating inputs', () => {
    const b=makeBoard(), before=structuredClone(b);const row=weeklySeatRows(b,'2026-10-21')[0];
    assert.deepEqual(row.groups.map(g=>g.id),['likud','change','arab','independent']);
    assert.equal(row.groups.reduce((s,g)=>s+(g.total??0),0),120);
    const ids=row.groups.flatMap(g=>g.values.map(v=>v.list_id));
    assert.equal(new Set(ids).size,ids.length);assert.equal(ids.length,row.poll.values.length);assert.deepEqual(b,before);
});
test('absent category remains null and is labelled unpublished rather than zero', () => {
    const b=makeBoard();const poll=original.observations.find(r=>r.poll_id==='midgam-n12-2026-10-19'&&r.question_id==='reported_seats');
    b.observations=[structuredClone(poll)];const groups=weeklySeatRows(b,'2026-10-21')[0].groups;
    assert.equal(groups.find(g=>g.id==='independent').total,null);
    const html=israelAnalysisHtml(b,{today:'2026-10-21'});assert.match(html,/그외 미발표/);assert.doesNotMatch(html,/그외 0석/);
});
test('trend sits above existing controls, stays seven-day based, and has no invented empty-day rows', () => {
    const b=makeBoard();const html=israelAnalysisHtml(b,{today:'2026-10-21',days:14,grouping:'ideology'});
    assert(html.indexOf('israel-weekly')<html.indexOf('israel-section-nav'));
    assert.equal((html.match(/data-israel-weekly-poll=/g)||[]).length,1);
    assert.match(html,/발표일 기준/);assert.match(html,/정부 구성 확정이 아닙니다/);
    const empty=israelAnalysisHtml(b,{today:'2026-11-10'});assert.match(empty,/최근 7일에 발표된 채택 조사가 없습니다/);
    assert.doesNotMatch(empty,/data-israel-weekly-poll=/);
});
test('publisher strings are escaped and unsafe source links cannot enter the trend', () => {
    const b=makeBoard();b.observations[0].publisher='<script>alert(1)</script>';
    b.localization.translations.push({source:b.observations[0].publisher,ko:'<script>alert(1)</script>'});
    const html=israelAnalysisHtml(b,{today:'2026-10-21'});assert(!html.includes('<script>alert(1)</script>'));
    b.observations[0].source_url='javascript:alert(1)';assert.deepEqual(weeklySeatRows(b,'2026-10-21'),[]);
});
test('multiple polls published on the same day remain separate rows', () => {
    const b=makeBoard();const second=structuredClone(b.observations[0]);second.poll_id='second';second.published_at='2026-10-19T19:00:00Z';b.observations.push(second);
    assert.deepEqual(weeklySeatRows(b,'2026-10-21').map(r=>r.poll.poll_id),['second','sample']);
});

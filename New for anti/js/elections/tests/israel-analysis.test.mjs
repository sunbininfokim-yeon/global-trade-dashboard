import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { koreaToday, dayAge, listSeats, seatPolls, selectedSeatSum, sourceHref, validateIsraelBoard } from '../data/israel-analysis.js';
import { israelAnalysisHtml } from '../country-explorer/special/israel-analysis.js';
const data = new URL('../../../public/data/', import.meta.url);
const board = JSON.parse(readFileSync(new URL('israel_election_analysis_v1.json', data)));
const health = JSON.parse(readFileSync(new URL('israel_election_analysis_status_v1.json', data)));
const today = '2026-10-20';
const latest = seatPolls(board, { today }).find(r => r.review_status === 'accepted');

test('research snapshot keeps counts, accepted rows, partial and held separate', () => {
    assert.equal(validateIsraelBoard(board, health, today), board);
    assert.equal(seatPolls(board, { today }).length, 12);
    assert.equal(latest.poll_id, 'midgam-n12-2026-10-19');
    assert.equal(board.current_seats, null);
    assert.equal(board.automatic_refresh, false);
});
test('missing list seats remain null; explicit zero and arithmetic empty selection are distinct', () => {
    assert.equal(listSeats(latest, 'k26:ך'), null);
    assert.equal(listSeats({ values: [{ list_id: 'zero', seats: 0 }] }, 'zero'), 0);
    assert.equal(selectedSeatSum(latest, [], board).total, 0);
    assert.equal(selectedSeatSum(latest, ['k26:ך'], board).total, null);
});
test('same-poll arithmetic deduplicates selection and exposes 61 as arithmetic only', () => {
    const selected = latest.values.map(r => r.list_id);
    assert.equal(selectedSeatSum(latest, [...selected, selected[0]], board).total, 120);
    assert.equal(selectedSeatSum(latest, selected, board).gap, 0);
    assert.equal(selectedSeatSum(latest, selected, board).status, 'arithmetic_only');
    assert.equal(selectedSeatSum(latest, ['k26:דרך', 'k26:מחל'], board).total, 45);
    const partial = seatPolls(board, { today }).find(r => r.review_status === 'partial');
    assert.equal(selectedSeatSum(partial, selected, board).status, 'held');
});
test('recent windows use fieldwork, exclude unknown field dates and cannot revive future rows', () => {
    const recent = seatPolls(board, { today, days: 7 });
    assert(!recent.some(r => r.poll_id === 'channel13-2026-10-07'));
    assert(!recent.some(r => r.poll_id === 'midgam-n12-2026-10-12'));
    assert(seatPolls(board, { today, days: 14 }).some(r => r.poll_id === 'midgam-n12-2026-10-12'));
    assert.equal(seatPolls(board, { today: '2026-11-14', days: 14 }).length, 0);
    assert.equal(dayAge('2026-02-30', today), null);
    assert.equal(koreaToday(Date.parse('2026-10-13T16:00:00Z')), '2026-10-14');
});
test('bad schema, mismatched health and future research are unavailable', () => {
    assert.throws(() => validateIsraelBoard(board, { ...health, evidence_as_of: '2026-10-13' }, today));
    assert.throws(() => validateIsraelBoard({ ...board, iso3: 'USA' }, health, today));
    assert.throws(() => validateIsraelBoard(board, health, '2026-10-13'));
    const bad = structuredClone(board); bad.observations[0].values[0].seats = null;
    assert.throws(() => validateIsraelBoard(bad, health, today));
});
test('safe links reject script and credential URLs; source labels and quotes escape HTML', () => {
    assert.equal(sourceHref('javascript:alert(1)'), null);
    assert.equal(sourceHref('https://user:pass@example.org'), null);
    const bad = structuredClone(board);bad.observations[0].publisher = '<script>alert(1)</script>';
    const html = israelAnalysisHtml(bad, { today });
    assert(!html.includes('<script>alert(1)</script>'));
    assert(html.includes('&lt;script&gt;'));
});
test('view discloses methodology, original error sign, missing values, partial and no automatic collection', () => {
    const html = israelAnalysisHtml(board, { today });
    assert.match(html, /자동 갱신 미설치/); assert.match(html, /공식 후보 순위 보류/);
    assert.match(html, /연정 합의나 정부 구성 확정은 아닙니다/);
    assert.match(html, /표본오차 ±4.4%p/); assert.match(html, /현직 의석/);
    const hayom = israelAnalysisHtml(board, { today, pollId: 'kantar-israelhayom-2026-10-07' });
    assert.match(hayom, /4.2%\+/); assert.doesNotMatch(hayom, /±4.2/);
    const partial = israelAnalysisHtml(board, { today, pollId: 'channel13-2026-10-07' });
    assert.match(partial, /부분 자료는 의석 조합 계산을 보류/);
    assert.match(israelAnalysisHtml(null), /불러오지 못했습니다/);
});
test('empty recent windows and old evidence remain explicitly empty or dated', () => {
    const html = israelAnalysisHtml(board, { today: '2026-11-14', days: 7 });
    assert.match(html, /선택 기간에 검토한 조사가 없습니다/);
    assert.match(html, /25일 경과/);
    assert.doesNotMatch(html, /data-israel-list=/);
});

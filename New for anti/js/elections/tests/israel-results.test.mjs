import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { readIsraelFixture } from './fixtures/israel-snapshot.mjs';
import { validateIsraelBoard, seatPolls, canCalculate } from '../data/israel-analysis.js';
import { israelAnalysisHtml } from '../country-explorer/special/israel-analysis.js';

const board=JSON.parse(readIsraelFixture('israel_election_analysis_v1.json'));
const status=JSON.parse(readIsraelFixture('israel_election_analysis_status_v1.json'));
board.post_election=JSON.parse(readFileSync(new URL('../../../scripts/election_watch/tests/fixtures/israel/2026-10-31/post_election.json',import.meta.url),'utf8'));
const today='2026-10-31';

test('reported election results lead; pre-election UI is inside a closed disclosure',()=>{
    validateIsraelBoard(board,status,today);
    const html=israelAnalysisHtml(board,{today});
    assert(html.indexOf('id="israel-results"')<html.indexOf('id="israel-next-steps"'));
    assert(html.indexOf('id="israel-next-steps"')<html.indexOf('id="israel-history"'));
    assert.match(html,/<details id="israel-history"[^>]*><summary>/);
    assert(html.indexOf('id="israel-history"')<html.indexOf('israel-weekly-title'));
    assert.match(html,/공식 표 확인 보류/);
    assert.match(html,/지명일 미확인으로 종료일은 계산하지 않습니다/);
    assert.match(html,/11월 4일 예정/);
    assert.match(html,/11월 10일 예상/);
    assert.match(html,/2016년/);
});
test('count never enters poll selection or accepted-poll coalition arithmetic',()=>{
    assert(!seatPolls(board,{today}).some((r)=>r.question_id==='official_results'));
    assert.equal(canCalculate(board.post_election.result_record,board),false);
    assert.equal(board.evidence_as_of,'2026-10-20');
    assert.equal(board.post_election.evidence_as_of,today);
});
test('corrupt count, completed events and unreviewed sources fail closed',()=>{
    const mutations=[
        d=>d.result_record.values[0].seats++,
        d=>d.result_record.values.push(d.result_record.values[0]),
        d=>d.result_record.review_status='accepted',
        d=>d.official_table_verified=true,
        d=>d.government_formed=true,
        d=>d.mandate_date='2026-10-31',
        d=>d.steps[1].date='2026-11-11',
        d=>d.steps[0].source_ids=['cec-table'],
        d=>d.result_record.bloc_as_published.arab=18,
        d=>d.evidence_as_of='2026-11-01',
    ];
    for(const change of mutations){const b=structuredClone(board);change(b.post_election);assert.throws(()=>validateIsraelBoard(b,status,today));}
});
test('new descriptions are escaped and unsafe source URLs cannot become links',()=>{
    const b=structuredClone(board);
    b.post_election.steps[0].description_ko='<img src=x onerror=alert(1)>';
    b.post_election.sources[0].url='javascript:alert(1)';
    const html=israelAnalysisHtml(b,{today});
    assert.match(html,/&lt;img/);
    assert.doesNotMatch(html,/<img src=x|href="javascript:/);
});

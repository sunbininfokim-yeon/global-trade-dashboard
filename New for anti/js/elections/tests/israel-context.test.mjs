import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { koreanText, partyProfile, personProfile, groupingGroups, groupSeatSummary, presetSeatSum, selectionRelationships } from '../data/israel-context.js';
import { seatPolls } from '../data/israel-analysis.js';
import { israelAnalysisHtml } from '../country-explorer/special/israel-analysis.js';
const board = JSON.parse(readFileSync(new URL('../../../public/data/israel_election_analysis_v1.json', import.meta.url)));
const latest = seatPolls(board, {today:'2026-10-15'}).find(r=>r.review_status==='accepted');

test('four stable colors separate reported blocs from unknown alignment',()=>{
    const likud=partyProfile(board,'k26:מחל');
    assert.equal(likud.color,partyProfile(board,'k26:ג').color);
    assert.notEqual(likud.color,partyProfile(board,'k26:ך').color);
    assert.equal(partyProfile(board,'k26:כן').group,'independent');
    assert.equal(partyProfile(board,'k26:עם').group,'arab');
    assert.deepEqual(board.coalition_context.groups.map(g=>groupSeatSummary(board,latest,g.id).total),[49,54,13,4]);
});
test('presets add only this accepted poll and preserve unavailable values',()=>{
    assert.equal(presetSeatSum(board,latest,'likud').total,49);
    assert.equal(presetSeatSum(board,latest,'change').total,54);
    assert.equal(presetSeatSum(board,latest,'change-external').total,62);
    const missing=structuredClone(latest);missing.values=missing.values.filter(v=>v.list_id!=='k26:ג');
    assert.equal(presetSeatSum(board,missing,'likud').total,null);
    const partial=seatPolls(board,{today:'2026-10-15'}).find(r=>r.review_status==='partial');
    assert.equal(presetSeatSum(board,partial,'likud').total,null);
});
test('personal refusal appears only for the selected counterpart and retains conditions',()=>{
    assert(!selectionRelationships(board,['k26:דרך','k26:רק']).some(r=>r.kind==='refusal'));
    const refusal=selectionRelationships(board,['k26:מחל','k26:דרך']).find(r=>r.kind==='refusal');
    assert.equal(refusal.target_person,'Benjamin Netanyahu');
    const conditional=selectionRelationships(board,['k26:מחל','k26:ג']);
    assert(conditional.some(r=>r.kind==='conditional'));
});
test('Joint List external proposal is not inherited by Raam or treated as cabinet membership',()=>{
    assert(!selectionRelationships(board,['k26:דרך','k26:עם']).some(r=>r.kind==='external_support'));
    assert(selectionRelationships(board,['k26:דרך','k26:ודם']).some(r=>r.kind==='external_support'));
    assert(!selectionRelationships(board,['k26:ודם']).some(r=>r.kind==='external_support'));
    const html=israelAnalysisHtml(board,{today:'2026-10-15',selected:board.coalition_context.presets[2].list_ids,presetId:'change-external'});
    assert.match(html,/62<small>석/);assert.match(html,/상대 정당 수용 미확인/);
});
test('Korean identity labels use saved Gemini text and keep missing identities unknown',()=>{
    assert.match(partyProfile(board,'k26:ך').leader,/오페르 윈터/);
    assert.match(personProfile(board,'בנימין נתניהו').role,/리쿠드.*현직 총리/);
    assert.equal(koreanText(board,'unknown text'),'한국어 설명 미확인');
    assert(!/[\u0590-\u05ff]/u.test(partyProfile(board,'k26:ך').description));
});
test('main rendered labels do not expose Hebrew or untranslated English identities',()=>{
    const html=israelAnalysisHtml(board,{today:'2026-10-15'});
    const primary=html.replace(/<details><summary>원문 표기<\/summary>[\s\S]*?<\/details>/g,'')
        .replace(/<[^>]+>/g,'');
    assert(!/[\u0590-\u05ff]/u.test(primary));
    assert.match(primary,/오페르 윈터/);assert.match(primary,/베니 간츠/);
    assert.match(primary,/Gemini API 사전 번역/);
    assert.doesNotMatch(primary,/추론하지 마십시오|전환하지 마십시오/);
});
test('Likud relationship filter keeps conditions and refusal but removes unrelated platforms',()=>{
    const html=israelAnalysisHtml(board,{today:'2026-10-15',relationFilter:'likud'});
    const section=html.split('id="israel-relations"')[1].split('id="israel-threshold"')[0];
    assert.match(section,/추천·참여 조건부/);assert.match(section,/네타냐후와 참여 거부/);
    assert.doesNotMatch(section,/공동 정부 구성 추진/);
});

test('refusal diagram shows one anchor versus counterparts, rather than a chain of opposition refusals',()=>{
    const html=israelAnalysisHtml(board,{today:'2026-10-15'});
    const refusal=html.split('israel-relation-refusal')[1].split('</article>')[0];
    assert.match(refusal,/함께 참여 거부/);assert.match(refusal,/israel-relation-targets/);
    assert.doesNotMatch(refusal,/↔/);
});


test('ideology and cooperation remain independent, including secular right and mixed lists',()=>{
    const likud=partyProfile(board,'k26:מחל'), yb=partyProfile(board,'k26:ל');
    assert.equal(likud.ideologyGroup,yb.ideologyGroup);
    assert.notEqual(likud.group,yb.group);
    assert.equal(partyProfile(board,'k26:רק').ideologyGroup,'mixed');
    assert.notEqual(partyProfile(board,'k26:ודם').ideologyGroup,partyProfile(board,'k26:עם').ideologyGroup);
    assert.equal(partyProfile(board,'k26:זך').ideologyGroup,partyProfile(board,'k26:ג').ideologyGroup);
    assert.notEqual(partyProfile(board,'k26:זך').group,partyProfile(board,'k26:ג').group);
});
test('each grouping partitions the same published seats once, and unpublished seats remain unknown',()=>{
    for(const grouping of ['cooperation','ideology']) {
        for(const poll of seatPolls(board,{today:'2026-10-15'})) {
            const summaries=groupingGroups(board,grouping).map(g=>groupSeatSummary(board,poll,g.id,grouping));
            assert.equal(summaries.reduce((sum,s)=>sum+(s.total??0),0),120);
            const ids=summaries.flatMap(s=>s.values.map(v=>v.list_id));
            assert.equal(ids.length,new Set(ids).size);
            assert.equal(ids.length,poll.values.length);
        }
    }
    const blank={...latest,values:[]};
    assert.equal(groupSeatSummary(board,blank,'haredi','ideology').total,null);
    assert(groupSeatSummary(board,latest,'right','ideology').missing.includes('k26:ך'));
});
test('switching classification retains selected parties and personal refusal conditions',()=>{
    const state={today:'2026-10-15',selected:['k26:מחל','k26:ל'],presetId:null};
    for(const grouping of ['cooperation','ideology']) {
        const html=israelAnalysisHtml(board,{...state,grouping});
        assert.match(html,/29<small>석/);
        assert.match(html,/네타냐후와 참여 거부/);
        for(const id of state.selected) assert(html.includes(`data-israel-list="${id}" aria-label=`));
        assert.equal((html.match(/ 선택" checked/g)||[]).length,2);
    }
    const html=israelAnalysisHtml(board,{today:'2026-10-15',grouping:'ideology'});
    assert.match(html,/성향 설명·근거/);assert.match(html,/의석 미발표 명부/);
    assert.match(html,/같은 성향도 서로 다른 협력 진영/);
});
test('cooperation pairs are five reported surplus agreements, not coalition membership',()=>{
    const pairs=board.coalition_context.cooperation_pairs;
    assert.equal(pairs.length,5);
    assert(pairs.some(p=>p.parties.includes('k26:ודם')&&p.parties.includes('k26:עם')));
    assert(pairs.every(p=>p.source_ids.length&&p.event_date&&p.parties.length===2));
    const html=israelAnalysisHtml(board,{today:'2026-10-15'});
    assert.match(html,/위원회 접수 원문은 보류/);
});

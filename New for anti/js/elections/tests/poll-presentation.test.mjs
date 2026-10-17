import test from 'node:test';
import assert from 'node:assert/strict';
import { pollPresentationContext, pollRaceAssessment, pollPrecision, pollRowAssessment, summarizePollPresentation } from '../data/poll-presentation.js';
import { pollSignal } from '../data/usa-election-context.js';
import { pollAnswersHtml, pollEvidenceHtml } from '../country-explorer/special/usa-election-evidence.js';
import { pollOfficePanelsHtml } from '../country-explorer/special/usa-poll-panels.js';
import { senateCurrentHtml } from '../country-explorer/special/usa-senate-current.js';
import { candidateMatchupHtml } from '../country-explorer/special/usa-candidate-matchup.js';
import { candidatePartyOrder } from '../data/election-matchups.js';
import { statePollEvidenceHtml } from '../country-explorer/usa-state-dashboard.js';
import { renderUsaElectionNational } from '../country-explorer/special/usa-election-national.js';

const now = Date.parse('2026-10-14T12:00:00Z');
const board = { schema:'usa_live_polls_v1', source_status:'ok', as_of:'2026-10-14', fetched_at:'2026-10-14T01:00:00Z', stale_after_hours:48 };
const health = {status:'ok',as_of:board.as_of};
const observation = (id, d = 51, r = 45, extra = {}) => ({id, field_end:'2026-10-12', pollster_group:id, population:'lv', sample_n:800,
    contest_id:'general',display_group:'general',aggregation_eligibility:{eligible:true},
    source_quality:{verification_level:'primary_toplines_checked'},answers:[{name:'D',party:'DEM',pct:d},{name:'R',party:'REP',pct:r}], ...extra});
const race = (observations, extra = {}) => ({race_id:'USA:NY:house:17',state:'NY',office:'house',district:'17',
    phase:'pre_election',election_date:'2026-11-03',schedule_status:'reported_general_matchup',contest_id:'general',required_candidates:['D','R'],observations,...extra});
const context = pollPresentationContext(board,health,now);
const quality = (changes = {}) => ({verification_level:'primary_toplines_checked',question_sample_n:800,
    reported_precision:{kind:'margin_of_error',half_width_pp:3,scope:'800_LV',...changes}});

test('single-source numeric leads are counted, with uncertainty missing and single-source flags', () => {
    const s = summarizePollPresentation([race([observation('a')])],board,health,7,now);
    assert.equal(s.dem,1);assert.equal(s.single,1);assert.equal(s.precisionUnknown,1);assert.equal(s.within,0);
    assert.equal(s.recent,1);assert.equal(s.states,1);
});

test('reviewed MN01 legal-name and poll-name aliases count in both the card and summary', () => {
    const legal = 'Jacob "Jake" Johnson';
    const row = observation('mn01',46,44,{answers:[{name:'Jake Johnson',party:'DEM',pct:46},
        {name:'Brad Finstad',party:'REP',pct:44}]});
    const r = race([row],{race_id:'USA:MN:house:01',state:'MN',district:'01',
        required_candidates:[legal,'Brad Finstad'],candidates:{
            [legal]:{party:'DEM',canonical_name:legal},
            'Jake Johnson':{party:'DEM',canonical_name:legal},
            'Brad Finstad':{party:'REP',canonical_name:'Brad Finstad'}}});
    assert.equal(summarizePollPresentation([r],board,health,14,now).recent,1);
    assert.equal(summarizePollPresentation([r],board,health,14,now).dem,1);
    assert.match(pollEvidenceHtml(r,board,health,14,{now}),/최근 14일 요약: DEM 수치상 우세/);
    assert.match(pollEvidenceHtml(r,board,health,14,{now}),/Jake Johnson/);
    assert.equal(r.observations[0].answers[0].name,'Jake Johnson');
});

test('similar spellings without reviewed aliases and duplicate aliases cannot count', () => {
    const legal = 'Jacob "Jake" Johnson';
    const row = observation('mn01',46,44,{answers:[{name:'Jake Johnson',party:'DEM',pct:46},
        {name:'Brad Finstad',party:'REP',pct:44}]});
    const r = race([row],{required_candidates:[legal,'Brad Finstad'],candidates:{
        [legal]:{canonical_name:legal},'Brad Finstad':{canonical_name:'Brad Finstad'}}});
    assert.equal(pollRaceAssessment(r,context,14).status,'missing');
    r.candidates['Jake Johnson']={canonical_name:legal};
    r.observations[0].answers.push({name:legal,party:'DEM',pct:1});
    assert.equal(pollRaceAssessment(r,context,14).status,'missing');
    assert.equal(summarizePollPresentation([r],board,health,14,now).recent,0);
});

test('candidate interval overlap uses twice reviewed same-sample MOE, including its boundary', () => {
    assert.equal(pollRowAssessment(observation('a',51,45,{source_quality:quality()})).status,'within');
    assert.equal(pollRowAssessment(observation('a',52,45,{source_quality:quality()})).status,'dem');
    assert.equal(pollRowAssessment(observation('a',45,52,{source_quality:quality()})).status,'rep');
    for (const precision of [{kind:'credibility_interval'},{kind:'modeled_margin_of_error'},
        {scope:'800_RV'},{scope:'whole_survey'},{half_width_pp:NaN}]) {
        assert.equal(pollPrecision(observation('a',51,45,{source_quality:quality(precision)})),null);
    }
    assert.equal(pollPrecision(observation('a',51,45,{source_quality:{...quality(),question_sample_n:400}})),null);
});

test('stale snapshot remains dated historical evidence and cannot revive forecast/map signals', () => {
    const b = {...board,as_of:'2026-10-11',fetched_at:'2026-10-11T01:00:00Z'};
    const h = {...health,as_of:b.as_of};
    const r = race([observation('a',51,45,{field_end:'2026-10-09'})]);
    const s = summarizePollPresentation([r],b,h,7,now);
    assert.equal(s.context.stale,true);assert.equal(s.context.collectedOn,'2026-10-11');assert.equal(s.dem,1);
    assert.equal(pollSignal(r,b,h,7,now).status,'stale');
    const html = pollOfficePanelsHtml([r],b,h,7,()=>'',{now});
    assert.match(html,/마지막 정상 수집 2026-10-11 기준/);assert.match(html,/현재 우세 판정은 중단/);
});

test('inconsistent or future snapshot cannot produce a lead; missing values are not zero leads', () => {
    const rows = [race([observation('a')])];
    assert.equal(summarizePollPresentation(rows,board,{...health,as_of:'2026-10-13'},7,now).unavailable,1);
    assert.equal(pollPresentationContext({...board,as_of:'2026-10-15'},health,now).available,false);
    assert.equal(pollPresentationContext({...board,as_of:'2026-99-99'},null,now).available,false);
    const s=summarizePollPresentation(rows,null,null,7,now);assert.equal(s.dem,0);assert.equal(s.unavailable,1);
});

test('same-wave duplicates, conflicts, LV/RV and 7/14-day boundaries retain admission rules', () => {
    const old=observation('old',51,45,{field_end:'2026-10-02'});
    assert.equal(pollRaceAssessment(race([old]),context,7).status,'missing');
    assert.equal(pollRaceAssessment(race([old]),context,14).status,'dem');
    const a=observation('a');const duplicate={...a,id:'duplicate'};
    const x=pollRaceAssessment(race([a,duplicate,observation('rv',42,54,{population:'rv'})]),context,7);
    assert.equal(x.rows.length,1);assert.equal(x.status,'dem');
    const conflicting={...a,id:'conflict',answers:observation('x',42,54).answers};
    assert.equal(pollRaceAssessment(race([a,conflicting]),context,7).status,'conflict');
});

test('CA48 historical numerical DEM lead and CA22 internal reference explain zero recent seats', () => {
    // Fixed incident fixtures: never depend on an evolving live JSON date.
    const ca48=race([observation('ca48',45,42,{field_end:'2026-09-01'})],
        {race_id:'USA:CA:house:48',state:'CA',district:'48'});
    const ca22=race([observation('ca22',48,44,{field_end:'2026-06-21',
        aggregation_eligibility:{eligible:false,reasons:['methodology_incomplete_reference','party_commissioned_reference','party_internal_reference']}})],
        {race_id:'USA:CA:house:22',state:'CA',district:'22'});
    for (const days of [7,14]) {
        const summary=summarizePollPresentation([ca48,ca22],board,health,days,now);
        assert.equal(summary.dem,0);assert.equal(summary.missing,2);
        const first=pollEvidenceHtml(ca48,board,health,days,{now});
        assert.match(first,new RegExp(`최근 ${days}일 요약: 기간 내 채택 조사 없음`));
        assert.match(first,/2026-09-01/);assert.match(first,/선택 기간 밖/);assert.match(first,/45%/);
        const second=pollEvidenceHtml(ca22,board,health,days,{now});
        assert.match(second,/2026-06-21/);assert.match(second,/방법론 미확인/);assert.match(second,/정파 의뢰·내부 조사/);
        assert.match(second,/누적 조사 1건 보기/);
    }
});

test('the same poll card explains a 7-day exclusion and a 14-day counted lead without changing totals', () => {
    const r=race([observation('older',51,45,{field_end:'2026-10-02'})]);
    assert.match(pollEvidenceHtml(r,board,health,7,{now}),/최근 7일 요약: 기간 내 채택 조사 없음/);
    assert.match(pollEvidenceHtml(r,board,health,14,{now}),/최근 14일 요약: DEM 수치상 우세/);
    const html=pollOfficePanelsHtml([r],board,health,14,()=>'',{now});
    assert.match(html,/최근 14일 DEM 수치상 우세<strong>1석/);
});

test('a current numerical lead inside overlapping precision intervals identifies the actual summary category', () => {
    const r=race([observation('close',51,45,{source_quality:quality()})]);
    const html=pollEvidenceHtml(r,board,health,7,{now});
    assert.match(html,/최근 7일 요약: 오차구간 겹침/);
    assert.match(html,/지지율 차이가 있어도/);
    assert.equal(summarizePollPresentation([r],board,health,7,now).dem,0);
});

test('references and wrong contests cannot enter counts; opposing institutions remain mixed', () => {
    const ref=observation('ref',51,45,{aggregation_eligibility:{eligible:false}});
    assert.equal(pollRaceAssessment(race([ref]),context).status,'reference');
    assert.equal(pollRaceAssessment(race([observation('wrong',51,45,{contest_id:'primary'})]),context).status,'missing');
    assert.equal(pollRaceAssessment(race([observation('a'),observation('b',42,54)]),context).status,'mixed');
});

test('third-party leads and single candidate ballots do not become DEM/GOP wins', () => {
    const r=race([observation('a',42,35,{answers:[{name:'D',party:'DEM',pct:30},{name:'R',party:'REP',pct:25},{name:'I',party:'IND',pct:45}]})]);
    assert.equal(pollRaceAssessment(r,context).status,'other');
    assert.equal(pollRaceAssessment({...r,schedule_status:'single_candidate_ballot_listing'},context).status,'singleCandidate');
});

test('after election, stale snapshot never resurrects polls; certified results stay separate', () => {
    const r=race([observation('a')]);const later=pollPresentationContext(board,health,Date.parse('2026-11-05'));
    assert.equal(pollRaceAssessment(r,later).status,'closed');
    const html=pollEvidenceHtml(r,board,health,7,{now:later.actualNow});assert.doesNotMatch(html,/누적 조사|51%/);
    const s=summarizePollPresentation([{...r,phase:'certified_result',result:{status:'certified',party:'DEM'}}],board,health,7,later.actualNow);
    assert.equal(s.certified,1);assert.equal(s.dem,0);
});

test('scoreboard emphasizes names and percentages, preserves other answers and escapes content', () => {
    const row=observation('a');row.answers.push({name:'<script>other</script>',party:'IND',pct:null});
    const html=pollAnswersHtml(row);assert.match(html,/<strong>D<\/strong><b>51%<\/b>/);
    assert.match(html,/>GOP<\/small>/);assert.match(html,/수치 미확인/);assert.doesNotMatch(html,/<script>/);
    const pollHtml=pollEvidenceHtml(race([observation('a')]),board,health,7,{now});
    assert.match(pollHtml,/elections-poll-scoreboard/);assert.match(pollHtml,/누적 조사 1건/);
});

test('office disclosure boxes cover all watched races and remember the selected office', () => {
    const races=[race([observation('h')]),race([observation('s')],{office:'senate',race_id:'USA:NY:senate'}),
        race([],{office:'governor',race_id:'USA:NY:governor'})];
    const html=pollOfficePanelsHtml(races,board,health,7,()=>'<p>race</p>',{now,open:{'poll-senate':true}});
    assert.equal((html.match(/class="elections-poll-office"/g)||[]).length,3);
    assert.match(html,/data-evidence-section="poll-senate" open/);assert.match(html,/최근 조사 없음 1곳/);
    const stateHtml=statePollEvidenceHtml('NY',{...board,races:Object.fromEntries(races.map(r=>[r.race_id,r]))},health,7,null,{now,open:{'poll-house':true}});
    assert.match(stateHtml,/data-evidence-section="poll-house" open/);
});

test('national poll coverage includes races outside the old watch-state and 18-card shortlist', () => {
    const races = Array.from({length:20}, (_,n) => race([observation(String(n))], {
        state:'CA',district:String(n+1).padStart(2,'0'),race_id:`USA:CA:house:${String(n+1).padStart(2,'0')}`}));
    const root={innerHTML:'',querySelector:()=>null,querySelectorAll:()=>[]};
    renderUsaElectionNational(root,{country:null,board:{...board,races:Object.fromEntries(races.map(r=>[r.race_id,r]))},health});
    assert.match(root.innerHTML,/20개 선거 · 누적 20건/);
    assert.match(root.innerHTML,/감시 20석/);
    assert.match(root.innerHTML,/CA · 하원 20구/);
});

test('both incumbent Senators are separate from nominees, and incumbent independent party sorts first', () => {
    const incumbents=[{name:'Current D',abbr:'DEM',up_in_2026:false,senate_class:1},
        {name:'Current I',abbr:'IND',up_in_2026:true,senate_class:2}];
    const html=senateCurrentHtml({federal_delegation:{senators:incumbents}});
    assert.ok(html.indexOf('Current I') < html.indexOf('Current D'));
    assert.match(html,/이번 선거 없음/);assert.match(html,/이번 선거 대상/);assert.match(html,/상원 2석/);
    const candidates=[{name:'New D',party:'DEM'},{name:'New R',party:'REP'},{name:'Current I',party:'IND'},{name:'Another I',party:'IND'}];
    assert.deepEqual(candidatePartyOrder(candidates,incumbents),['IND','DEM','REP']);
    const field=candidateMatchupHtml(null,null,null,null,null,7,{showPolls:false,now,incumbents,matchup:{candidates,coverage:'complete_ballot'}});
    assert.ok(field.indexOf('<h4>IND</h4>') < field.indexOf('<h4>DEM</h4>'));
    assert.match(field,/Another I/);assert.doesNotMatch(field,/Current D/);
});

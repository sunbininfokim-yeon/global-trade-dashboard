import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { originLink, governorContextHtml, governorElectionSummaryHtml, campaignFundraisingHtml, candidateBiographyHtml } from '../country-explorer/special/usa-candidate-context.js';
import { observationHtml } from '../country-explorer/special/usa-election-evidence.js';
import { candidateMatchupHtml } from '../country-explorer/special/usa-candidate-matchup.js';
import { usaStateSuperPac } from '../country-explorer/special/usa-state-superpac.js';
const now = Date.parse('2026-10-19T12:00:00Z');
const source = 'https://www.fec.gov/data/candidate/S6OH00163/?cycle=2026';
const moneyRow = () => ({candidate_id:'S6OH00163',race_id:'USA:OH:senate',state:'OH',office:'senate',election_year:2026,
    status:'reported_campaign_summary_ballot_unverified',currency:'USD',amount_unit:'cents',includes_outside_spending:false,
    coverage_end:'2026-09-30',snapshot_as_of:'2026-10-19',source_url:source,
    source_receipts:{summary:{url:'https://www.fec.gov/files/bulk-downloads/2026/weball26.zip'}},
    amounts:{individual_contributions_cents:100001,receipts_cents:400002,cash_on_hand_cents:0,disbursements_cents:200003,candidate_loans_cents:100000,debts_owed_cents:null}});
const person = () => ({candidate_id:'S6OH00163',name:'Sherrod Brown',reported_names:['Sherrod Brown'],reported_parties:['DEM'],campaign_fundraising:moneyRow(),election_types:{G2026:{totals_by_category:{super_pac:{support_cents:900,oppose_cents:100}}}}});
const race = {cycle:2026,race_id:'USA:OH:senate',office:'senate',state_id:'OH',district:null};
const governor = () => ({state:'OH',cycle:2026,election_in_cycle:true,race_id:'USA:OH:governor',election_date:'2026-11-03',incumbent:{name:'Mike DeWine'},incumbent_ballot_status:'term_limited_reported',reviewed_on:'2026-10-19',source:{url:'https://www.nga.org/governors/elections/'},legal_rule_review:{url:'https://codes.ohio.gov/ohio-constitution/section-3.2'}});

test('source anchors reject script/http/credential URLs and escape labels and attributes', () => {
    for (const url of ['javascript:alert(1)','data:text/html,bad','http://bad.example/','https://user:password@bad.example/']) assert.equal(originLink(url),'');
    const html=originLink('https://example.org/?x=%22','<img onerror=bad>');assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);assert.match(html,/noopener noreferrer/);
});
test('governor context keeps election presence, term limits, retirement and legal sources distinct', () => {
    let html=governorContextHtml({id:'OH',governor_election:governor()},now);assert.match(html,/현직 연임 제한/);assert.match(html,/ohio-constitution/);assert.match(html,/2026-11-03/);
    const r={...governor(),incumbent_ballot_status:'not_seeking_reelection_reported',source:{source_url:'https://www.270towin.com/2026-governor-election/',source_grade:'secondary_explicit_note'}};
    html=governorContextHtml({id:'OH',governor_election:r},now);assert.match(html,/현직 불출마/);assert.match(html,/2차 출처/);
    html=governorContextHtml({id:'OH',governor_election:{...governor(),election_in_cycle:false,race_id:null,election_date:null,incumbent_ballot_status:'not_on_cycle_ballot'}},now);assert.match(html,/2026 주지사 선거 없음/);
    for (const patch of [{state:'NY'},{reviewed_on:'2026-10-20'},{reviewed_on:'2026-02-31'}]) assert.match(governorContextHtml({id:'OH',governor_election:{...governor(),...patch}},now),/정보 연결 대기/);
});
test('national governor list uses all fifty reviewed rows and exposes 36 election links without claiming missing governors', () => {
    const inputs=JSON.parse(fs.readFileSync(new URL('../../../scripts/election_watch/config/usa_polls/governor_context_2026.json',import.meta.url)));
    const catalog=JSON.parse(fs.readFileSync(new URL('../../../scripts/election_watch/config/usa_polls/targets_2026.json',import.meta.url)));
    const states=Object.fromEntries(Object.keys(catalog.states).map((st)=>[st,{...governor(),state:st,election_in_cycle:!!inputs.contests[st],race_id:inputs.contests[st]?`USA:${st}:governor`:null,election_date:inputs.contests[st]?'2026-11-03':null}]));
    const country={ui_ready:{state_drilldown:{governor_elections:{schema:'usa_governor_election_context_v1',states}}}};
    const html=governorElectionSummaryHtml(country,now);assert.match(html,/36주/);assert.match(html,/14주/);assert.equal((html.match(/data-overview-state=/g)||[]).length,50);
    delete states.WA;assert.equal(governorElectionSummaryHtml(country,now),'');
});
test('campaign money renders individual giving, gross receipts, cash, original report date and original FEC links separately', () => {
    const html=campaignFundraisingHtml(person(),race,null,now);assert.match(html,/\$1,000.01/);assert.match(html,/\$4,000.02/);assert.match(html,/\$0/);assert.match(html,/공시 기준 2026-09-30/);assert.match(html,/수집 2026-10-19/);assert.match(html,/S6OH00163/);assert.match(html,/weball26.zip/);assert.match(html,/슈퍼팩.*합산하지 않습니다/);
});
test('scope conflicts, future dates and unsupported governors never borrow federal or outside-spending amounts', () => {
    for (const patch of [{candidate_id:'S6NY00001'},{race_id:'USA:NY:senate'},{office:'house'},{state:'NY'},{coverage_end:'2026-10-20'},{currency:'KRW'},{includes_outside_spending:true}]) {
        const p=person();p.campaign_fundraising={...moneyRow(),...patch};const html=campaignFundraisingHtml(p,race,null,now);assert.match(html,/금액 보류/);assert.doesNotMatch(html,/\$/);
    }
    assert.match(campaignFundraisingHtml(person(),{...race,office:'governor'},null,now),/주별 캠프 공시 미연결/);
    assert.doesNotMatch(campaignFundraisingHtml(person(),{...race,office:'governor'},null,now),/\$/);
    assert.match(campaignFundraisingHtml(null,race,null,now),/0달러가 아닙니다/);
});
test('last-good fundraising reports retain their own dates and flag transfers rather than inventing net fundraising', () => {
    const p=person();p.campaign_fundraising.carried_forward_reason='missing_in_new_bulk';p.campaign_fundraising.transfer_double_count_risk=true;
    const html=campaignFundraisingHtml(p,race,{source_status:{candidate_fundraising:{status:'failed_last_good_preserved'}}},now);assert.match(html,/이전 유효 공시 보존/);assert.match(html,/2026-09-30/);assert.match(html,/중복 위험/);assert.match(html,/임의 순모금을 계산하지 않습니다/);
});
test('candidate cards show campaign money and general independent support/opposition as separate blocks', () => {
    const p=person();const matchup={candidates:[{name:p.name,party:'DEM',candidate_id:p.candidate_id}],reviewed_on:'2026-10-19'};
    const html=candidateMatchupHtml(null,{...race,candidates:[p]},null,null,null,7,{now,showPolls:false,matchup});assert.match(html,/개인 기부/);assert.match(html,/\$1,000.01/);assert.match(html,/지지 지출/);assert.match(html,/\$9/);assert.match(html,/반대 지출/);assert.match(html,/FEC 독립지출 공시 조회/);
});
test('governor nominees are visible from reviewed state roster even without any poll API observations', () => {
    const id='USA:OH:governor';const state={id:'OH',governor_election:governor(),election_matchups:{[id]:{race_id:id,state:'OH',office:'governor',status:'reported_general_matchup',reviewed_on:'2026-10-19',election_date:'2026-11-03',candidates:[{name:'Amy Acton',party:'DEM'},{name:'Vivek Ramaswamy',party:'REP'}]}}};
    const html=usaStateSuperPac(state,[],null,null,null,null,7,{showPolls:false});assert.match(html,/Amy Acton/);assert.match(html,/Vivek Ramaswamy/);assert.match(html,/주별 캠프 공시 미연결/);
});
test('biographies compute birthday age and keep unknown service/ethnicity, self-report attribution and per-field originals', () => {
    const missing={value:null,status:'not_verified'};const c={name:'Sherrod Brown',party:'DEM'};c.biography={...c,birth_date:{value:'1952-11-09',precision:'day',status:'verified',source_url:'https://history.house.gov/People/Detail/9996',reviewed_on:'2026-10-19',evidence_locator:'Concise Biography'},career:{value:[{role_ko:'의사·공중보건'}],status:'self_reported',source_url:'https://example.org/biography',reviewed_on:'2026-10-19',evidence_locator:'Career'},military_service:missing,race_ethnicity:missing};
    const html=candidateBiographyHtml(c,now);assert.match(html,/73세/);assert.match(html,/캠프·본인 서술/);assert.match(html,/history.house.gov/);assert.doesNotMatch(html,/무복무|군 복무 없음/);assert.match(candidateBiographyHtml(c,Date.parse('2026-11-09T12:00:00Z')),/74세/);
    assert.equal(candidateBiographyHtml({...c,name:'Another Candidate'},now),'');
});
test('poll sources include the checked university release beside provider PDF and flag unverified minor toplines', () => {
    const row={pollster:'BGSU',answers:[{name:'Sherrod Brown',party:'DEM',pct:48},{name:'Jon Husted',party:'REP',pct:42},{name:'Minor candidate',pct:3}],source_url:'https://scholarworks.bgsu.edu/cgi/viewcontent.cgi?article=1030',source_quality:{verification_level:'primary_toplines_checked',reviewed_on:'2026-10-19',primary_toplines:{'Sherrod Brown':48,'Jon Husted':42},review_sources:['https://www.bgsu.edu/poll.html','javascript:bad()'],limitations_ko:'주요 후보만 원문 대조 · PDF 접근 장애'}};
    const html=observationHtml(row);assert.match(html,/href="https:\/\/www.bgsu.edu\/poll.html"/);assert.match(html,/검토 원문/);assert.match(html,/수집에 기록된 출처/);assert.equal((html.match(/API 전달값 · 원문 수치 미대조/g)||[]).length,1);assert.match(html,/검토 2026-10-19/);assert.doesNotMatch(html,/javascript:/);
});
test('latest support comes before finance, other nominees are collapsed, and independent incumbents keep first billing',()=>{
    const nominees=[{name:'Dem Candidate',party:'DEM'},{name:'Rep Candidate',party:'REP'},{name:'Independent Incumbent',party:'IND'},{name:'Write-in Candidate',party:'WRI'}];
    const poll={race_id:race.race_id,phase:'pre_election',schedule_status:'reported_general_matchup',contest_id:'general',election_date:'2026-11-03',required_candidates:nominees.slice(0,2).map(c=>c.name),candidates:Object.fromEntries(nominees.map(c=>[c.name,{party:c.party}])),observations:[{id:'fixture',contest_id:'general',display_group:'general',field_end:'2026-10-18',pollster_group:'fixture',answers:[{name:'Dem Candidate',party:'DEM',pct:48},{name:'Rep Candidate',party:'REP',pct:42}],aggregation_eligibility:{eligible:true},source_quality:{verification_level:'primary_toplines_checked'}}]};
    const html=candidateMatchupHtml(poll,{...race,candidates:[]},null,null,null,7,{now,matchup:{candidates:nominees},incumbents:[{party:'IND'}]});
    assert.ok(html.indexOf('48%')<html.indexOf('후보 캠프 모금'));
    assert.match(html,/Independent Incumbent <span>vs<\/span> Dem Candidate/);
    assert.match(html,/<details class="elections-disclosure elections-other-nominees"><summary>나머지 정당·무소속·기명투표 후보 1명/);
    assert.match(html,/Write-in Candidate/);
});

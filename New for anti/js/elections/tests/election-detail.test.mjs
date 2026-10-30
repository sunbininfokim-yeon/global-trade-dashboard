import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { electionRatingSummary, electionOutlook } from '../data/election-overview.js';
import { electionOverviewHtml } from '../country-explorer/special/usa-election-overview.js';
import { candidateGeneralMoney, matchFinanceCandidate, candidateMatchupHtml, spendingHistoryHtml } from '../country-explorer/special/usa-candidate-matchup.js';
import { latestAdmittedPoll } from '../country-explorer/special/usa-election-evidence.js';
import { districtElectionColor, renderUsaDistrictMap } from '../country-explorer/usa-district-map.js';
import { districtFocusHtml } from '../country-explorer/usa-state-dashboard.js';
const read = f => JSON.parse(fs.readFileSync(new URL('../../../public/data/'+f,import.meta.url)));
const country = read('elections_board_v1.json').countries.find(c=>c.iso3==='USA');
const ratings = read('usa_election_ratings_review_v1.json');
const now = Date.parse('2026-10-07T00:00:00Z');
const contract = {federal_superpac_categories:['super_pac']};
const node = (support,oppose) => ({totals_by_category:{super_pac:{support_cents:support,oppose_cents:oppose}}});
const candidate = {candidate_id:'H123',name:'DOE, JANE',reported_parties:['DEM'],election_types:{G2026:node(10000,2300),P2026:node(50000,100),G2024:node(900000,700)}};
const finance = {office:'house',candidates:[candidate]};
const race = {race_id:'USA:NY:house:17',phase:'pre_election',schedule_status:'reported_general_matchup',contest_id:'general',election_date:'2026-11-03',required_candidates:['Jane Doe','Sam Smith'],candidates:{'Jane Doe':{party:'DEM'},'Sam Smith':{party:'REP'}},observations:[]};
const poll = (id,date,eligible=true,level='primary_toplines_checked') => ({id,field_end:date,pollster_group:id,population:'lv',sample_n:400,contest_id:'general',display_group:'general',aggregation_eligibility:{eligible},source_quality:{verification_level:level},answers:[{name:'Jane Doe',pct:48,party:'DEM'},{name:'Sam Smith',pct:46,party:'REP'}]});

test('100-seat Senate retains exactly 65 seats and exposes only 35 contests including both special elections',()=>{
 const r=electionRatingSummary(ratings,'senate',country,null,now);
 const o=electionOutlook(country,'senate',r,{now});
 assert.equal(o.retained,65);assert.deepEqual(o.retainedCounts,{DEM:32,GOP:31,IND:2,unknown:0});
 const html=electionOverviewHtml(country,ratings,{now});
 const senate=html.split('data-office="senate"')[1].split('data-office="house"')[0];
 assert.match(senate,/이번 선거 35석/);assert.match(senate.replace(/<[^>]*>/g,''),/비선거 유지 65석/);
 const list=senate.split('class="elections-disclosure elections-senate-contests"')[1].split('</details>')[0];
 assert.equal((list.match(/data-overview-state=/g)||[]).length,35);
 assert.equal((list.match(/특별선거/g)||[]).length,2);
 assert.match(senate,/DEM<\/span>/);assert.match(senate,/GOP<\/span>/);
});
test('candidate matchup matches unique verified name/party and separates general spending from primary and historical amounts',()=>{
 const c=matchFinanceCandidate('Jane Doe',{party:'DEM'},finance);
 assert.equal(c,candidate);
 assert.deepEqual(candidateGeneralMoney(c,finance,contract),{support:10000,oppose:2300});
 assert.equal(matchFinanceCandidate('Jane Doe',{party:'REP'},finance),null);
 assert.equal(matchFinanceCandidate('Jane Doe',{party:'DEM'},{candidates:[candidate,candidate]}),null);
 const html=candidateMatchupHtml(race,finance,contract,null,null,7,{now,showPolls:false});
 assert.match(html,/Jane Doe/);assert.match(html,/Sam Smith/);assert.match(html,/\$100/);assert.match(html,/\$23/);
 assert.doesNotMatch(html,/\$500|\$9,000/);
 const history=spendingHistoryHtml(finance,contract);assert.match(history,/2026 경선/);assert.match(history,/2024 과거 본선/);
});
test('unknown ballot phase remains missing in general matchup, rather than zero or a cycle-wide sum',()=>{
 const c={name:'Jane Doe',totals_by_category:node(99999,50).totals_by_category};
 assert.deepEqual(candidateGeneralMoney(c,finance,contract),{support:null,oppose:null});
 assert.match(spendingHistoryHtml({office:'house',candidates:[c]},contract),/선거 구분 미확인/);
 assert.doesNotMatch(candidateMatchupHtml({...race,required_candidates:[]},{...finance,candidates:[c]},contract,null,null,7,{now}),/Jane Doe vs/);
});
test('latest admitted poll excludes newer reference, unverified, future, primary and conflicting records',()=>{
 const rows=[poll('old','2026-09-20'),poll('latest','2026-10-01'),poll('reference','2026-10-02',false),poll('unverified','2026-10-03',true,'unverified'),poll('future','2026-10-08'),{...poll('primary','2026-10-04'),display_group:'primary'}];
 assert.equal(latestAdmittedPoll({...race,observations:rows},now).id,'latest');
 const a=poll('conflict','2026-10-05'),b=structuredClone(a);b.id='conflict-2';b.answers[0].pct=50;
 assert.equal(latestAdmittedPoll({...race,observations:[...rows,a,b]},now).id,'latest');
 assert.equal(latestAdmittedPoll({...race,observations:rows},Date.parse('2026-11-05')),null);
});
test('map paints stable Cook seats lightly, preserves added caution, and removes old assumptions after election',()=>{
 const r={races:[{race_id:'D',effective_rating:'solid_dem'},{race_id:'R',effective_rating:'likely_rep'},{race_id:'T',rating:'solid_rep',effective_rating:'toss_up'}]};
 assert.deepEqual(districtElectionColor('D',r,null,null,7,now),[96,165,250,115]);
 assert.deepEqual(districtElectionColor('R',r,null,null,7,now),[248,113,113,115]);
 assert.deepEqual(districtElectionColor('T',r,null,null,7,now),[71,85,105,230]);
 assert.deepEqual(districtElectionColor('D',r,null,null,7,Date.parse('2026-11-05')),[71,85,105,230]);
 const board={races:{D:{phase:'certified_result',result:{status:'certified',party:'REP'}}}};
 assert.deepEqual(districtElectionColor('D',r,board,null,7,Date.parse('2026-11-05')),[220,38,38,225]);
});
test('district map click callback selects a real district and ignores base geography',async()=>{
 let click,selected=null;
 const host={layers:{GeoJsonLayer:class {constructor(props){this.props=props;}}},worldBaseLayers:()=>[],setElectionMap:(layers,callback)=>{click=callback;}};
 const geo={features:[{properties:{district:'00'},geometry:{coordinates:[[[0,0],[1,1]]]}}]};
 await renderUsaDistrictMap({host,stateId:'AK',geo,onDistrictSelect:(id)=>{selected=id;}});
 click({object:{properties:{district:'00'}}});assert.equal(selected,'00');
 click({object:{properties:{district:'99'}}});assert.equal(selected,'00');
});
test('selected district card combines current member/party, matchup, polls and clearly labelled accumulated spending',()=>{
 const state={...country.ui_ready.state_drilldown.states.find(s=>s.id==='NY'),election_matchups:{}};
 const html=districtFocusHtml(state,'17',[],contract,{races:{'USA:NY:house:17':race}},null);
 assert.match(html,/Lawler, Michael/);assert.match(html,/공화당/);assert.match(html,/Jane Doe/);assert.match(html,/여론조사/);assert.match(html,/공시 누적 합계/);
 assert.equal(districtFocusHtml(state,null,[],contract,null,null),'');
});

test('legacy midterms brief also includes 33 regular plus two special seats',async()=>{
 const {usaMidtermsModel}=await import('../data/usa-midterms-model.js');
 const model=usaMidtermsModel(country);
 const senate=model.columns.find(c=>c.key==='senate');
 assert.match(senate.contestedKo,/35석 선거/);assert.match(senate.contestedKo,/정기 33 \+ 특별 2/);
 const {usaStateSuperPac}=await import('../country-explorer/special/usa-state-superpac.js');
 const state=country.ui_ready.state_drilldown.states.find(s=>s.id==='GA');
 const html=usaStateSuperPac(state,null,null,contract,null,null,7,{contestIds:new Set(['USA:GA:governor','USA:GA:senate'])});
 assert.match(html,/자금 자료 연결 대기/);assert.doesNotMatch(html,/해당 선거 없음/);
});

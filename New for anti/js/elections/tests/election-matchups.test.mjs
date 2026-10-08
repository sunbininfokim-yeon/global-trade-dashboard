import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { electionMatchup, senateTenureLabel, pollMatchesMatchup } from '../data/election-matchups.js';
import { districtFocusHtml } from '../country-explorer/usa-state-dashboard.js';
import { candidateMatchupHtml } from '../country-explorer/special/usa-candidate-matchup.js';
import { electionOverviewHtml } from '../country-explorer/special/usa-election-overview.js';
import { electionOutlook, electionRatingSummary } from '../data/election-overview.js';
const read = (name) => JSON.parse(fs.readFileSync(new URL('../../../public/data/'+name,import.meta.url)));
const country=read('elections_board_v1.json').countries.find((c)=>c.iso3==='USA');
const ratings=read('usa_election_ratings_review_v1.json');
const now=Date.parse('2026-10-07T12:00:00Z');
const state=(id)=>country.ui_ready.state_drilldown.states.find((s)=>s.id===id);

test('CA01 shows current member and certified nominees without any poll feed',()=>{
 const html=districtFocusHtml(state('CA'),'01',[],null,null,null);
 assert.match(html,/현재 의원/);assert.match(html,/Gallagher/);
 assert.match(html,/이번 선거 구도/);assert.match(html,/DEM/);assert.match(html,/Mike McGuire/);
 assert.match(html,/GOP/);assert.match(html,/James Gallagher/);assert.match(html,/공식 인증 본선 명부/);
 assert.match(html,/여론조사 감시 미연결/);assert.doesNotMatch(html,/후보 미확정|경선 미완료/);
});

test('same-party and independent finalists are preserved rather than inventing a GOP nominee',()=>{
 const ca=state('CA');
 const same=candidateMatchupHtml(null,null,null,null,null,7,{now,matchup:electionMatchup(ca,'USA:CA:house:04',null,now)});
 assert.equal((same.match(/<span>DEM<\/span>/g)||[]).length,2);assert.match(same,/GOP<\/span><strong>본선 후보 없음/);
 const independent=candidateMatchupHtml(null,null,null,null,null,7,{now,matchup:electionMatchup(ca,'USA:CA:house:06',null,now)});
 assert.match(independent,/Kevin Kiley/);assert.match(independent,/>IND</);assert.match(independent,/본선 후보 없음/);
});

test('future roster is not accepted and missing nominee data is not called an unfinished primary',()=>{
 const original=state('CA'),rid='USA:CA:house:01';
 const future={...original,election_matchups:{[rid]:{...original.election_matchups[rid],reviewed_on:'2027-01-01'}}};
 assert.equal(electionMatchup(future,rid,null,now),null);
 const empty=candidateMatchupHtml(null,null,null,null,null,7,{now});
 assert.match(empty,/명부 확인 필요/);assert.doesNotMatch(empty,/후보 미확정|경선 미완료/);
});

test('reviewed display roster suppresses a poll for a different candidate field',()=>{
 const rid='USA:NY:house:17',ny=state('NY');
 const matchup=electionMatchup(ny,rid,null,now);
 const wrong={schedule_status:'reported_general_matchup',required_candidates:['Old Democrat','Mike Lawler'],candidates:{'Old Democrat':{party:'DEM'},'Mike Lawler':{party:'REP'}}};
 assert.equal(pollMatchesMatchup(wrong,matchup),false);
 const html=candidateMatchupHtml(wrong,null,null,null,null,7,{now,matchup});
 assert.match(html,/Cait Conley/);assert.doesNotMatch(html,/Old Democrat/);assert.match(html,/조사 우세 표시 보류/);
 const correct={...wrong,required_candidates:['Cait Conley','Mike Lawler'],candidates:{'Cait Conley':{party:'DEM'},'Mike Lawler':{party:'REP'}}};
 assert.equal(pollMatchesMatchup(correct,matchup),true);
});

test('100 senators reconcile retained and contested current party counts; non-election NY is not a contest',()=>{
 const r=electionRatingSummary(ratings,'senate',country,null,now);
 const tally=electionOutlook(country,'senate',r,{now});
 assert.deepEqual(tally.contestedCurrentCounts,{DEM:13,GOP:22,IND:0,unknown:0});
 assert.equal(tally.retained+ r.contested,100);
 const ny=state('NY');const nr=electionRatingSummary(ratings,'senate',country,'NY',now);
 const nt=electionOutlook(country,'senate',nr,{state:ny,now});
 assert.equal(nr.contested,0);assert.equal(nt.retained,2);assert.equal(nt.contestedCurrentCounts.DEM,0);
});

test('a poll for the wrong nominee cannot resolve a Lean/Toss-up seat in the outlook',()=>{
 const rid='USA:NY:house:17';
 const rating=electionRatingSummary(ratings,'house',country,null,now);
 const poll={race_id:rid,election_date:'2026-11-03',schedule_status:'reported_general_matchup',
   required_candidates:['Cait Conley','Mike Lawler'],candidates:{'Cait Conley':{party:'DEM'},'Mike Lawler':{party:'REP'}},
   observations:[{id:'sample',field_end:'2026-10-05',pollster_group:'Independent',population:'lv',answers:[{name:'Cait Conley',party:'DEM',pct:51},{name:'Mike Lawler',party:'REP',pct:44}]}]};
 const board={schema:'usa_live_polls_v1',source_status:'ok',as_of:'2026-10-07',fetched_at:'2026-10-07T00:00:00Z',races:{[rid]:poll}};
 const health={status:'ok',as_of:'2026-10-07'};
 assert.equal(electionOutlook(country,'house',rating,{board,health,now}).pollResolved,1);
 poll.required_candidates[0]='Old Democrat';poll.candidates['Old Democrat']={party:'DEM'};
 assert.equal(electionOutlook(country,'house',rating,{board,health,now}).pollResolved,0);
});

test('35-seat list has one-line state/office/rating and bold incumbent tenure plus real opponent',()=>{
 const html=electionOverviewHtml(country,ratings,{now});
 const list=html.split('class="elections-disclosure elections-senate-contests"')[1].split('</details>')[0];
 assert.equal((list.match(/data-overview-state=/g)||[]).length,35);
 const ak=list.split('data-overview-state="AK"')[1].split('</button>')[0];
 assert.match(ak,/알래스카 · 상원/);assert.match(ak,/Toss-Up/);
 assert.match(ak.replace(/<[^>]*>/g,''),/GOP Dan Sullivan \(2선\)/);assert.match(ak,/<strong>DEM Mary Peltola<\/strong>/);
 const senators=state('ME').federal_delegation.senators;
 assert.equal(senateTenureLabel(senators.find((s)=>s.bioguideId==='C001035')),'5선');
 assert.equal(senateTenureLabel(state('FL').federal_delegation.senators.find((s)=>s.bioguideId==='M001244')),'임명');
});

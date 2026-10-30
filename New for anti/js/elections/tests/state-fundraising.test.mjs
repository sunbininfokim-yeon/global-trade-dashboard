import test from 'node:test';
import assert from 'node:assert/strict';
import { stateFundraisingSummary, stateFundraisingHtml } from '../country-explorer/special/usa-state-fundraising.js';
import { electionOverviewHtml } from '../country-explorer/special/usa-election-overview.js';
import fs from 'node:fs';
const now=Date.parse('2026-10-19T12:00:00Z');
const rid=(office,district)=>`USA:OH:${office}`+(district?`:${district}`:'');
const nominee=(id,name,party)=>({candidate_id:id,name,party});
const ballot=(office,nominees,district=null)=>({race_id:rid(office,district),state:'OH',office,district,election_date:'2026-11-03',reviewed_on:'2026-10-19',status:'certified_ballot',candidates:nominees});
const state=(...ballots)=>({id:'OH',election_matchups:Object.fromEntries(ballots.map(b=>[b.race_id,b]))});
const candidate=(id,name,party,value,office='house',district='01')=>({candidate_id:id,name,reported_names:[name],reported_parties:[party],
    campaign_fundraising:{candidate_id:id,name,reported_party:party,state:'OH',office,district,race_id:rid(office,district),election_year:2026,
        status:'reported_campaign_summary_ballot_unverified',currency:'USD',amount_unit:'cents',includes_outside_spending:false,
        coverage_end:'2026-09-30',snapshot_as_of:'2026-10-19',amounts:{receipts_cents:value},source_url:`https://www.fec.gov/data/candidate/${id}/?cycle=2026`,source_receipts:{summary:{url:'https://www.fec.gov/files/bulk-downloads/2026/weball26.zip'}}}});
const finance=(office,candidates,district=null)=>({cycle:2026,race_id:rid(office,district),state_id:'OH',office,district,candidates});
const dem=nominee('H6OH01001','DEM nominee','DEM'),rep=nominee('H6OH01002','GOP nominee','REP');
const d=candidate(dem.candidate_id,dem.name,dem.party,100001),r=candidate(rep.candidate_id,rep.name,rep.party,250002);

test('state House totals add only current reviewed nominees, split parties, and exclude former primary candidates',()=>{
    const s=state(ballot('house',[dem,rep],'01'));
    const old=candidate('H6OH01999','Primary loser','DEM',99999999);
    const data=stateFundraisingSummary(s,'house',[finance('house',[d,r,old],'01')],null,now);
    assert.equal(data.parties.DEM.amount,100001);assert.equal(data.parties.REP.amount,250002);assert.equal(data.total.amount,350003);
    assert.equal(data.total.nominees,2);assert.equal(data.total.observed,2);assert.equal(data.status,'reviewed_roster_connected');
});
test('House and Senate amounts stay separate and another state/cycle never enters the sum',()=>{
    const senator=nominee('S6OH00001','Senate nominee','DEM');
    const s=state(ballot('house',[dem,rep],'01'),ballot('senate',[senator]));
    const sr=finance('senate',[candidate(senator.candidate_id,senator.name,'DEM',700000,'senate',null)]);
    const wrong={...finance('house',[d],'01'),state_id:'NY'};
    const old={...finance('house',[d],'01'),cycle:2024};
    const files=[finance('house',[d,r],'01'),sr,wrong,old];
    assert.equal(stateFundraisingSummary(s,'house',files,null,now).total.amount,350003);
    assert.equal(stateFundraisingSummary(s,'senate',files,null,now).total.amount,700000);
});
test('identical race/candidate/nominee repetitions count once; conflicting same-ID reports are held',()=>{
    const s=state(ballot('house',[dem,dem,rep],'01'));const file=finance('house',[d,d,r],'01');
    let data=stateFundraisingSummary(s,'house',[file,structuredClone(file)],null,now);
    assert.equal(data.total.amount,350003);assert.equal(data.total.nominees,2);assert.ok(data.duplicatesRemoved>=2);
    const changed=structuredClone(file);changed.candidates[0].campaign_fundraising.amounts.receipts_cents=400001;
    data=stateFundraisingSummary(s,'house',[file,changed],null,now);assert.equal(data.total.amount,null);assert.ok(data.identityConflicts>0);
});
test('missing summaries remain partial, genuine reported zero stays zero, and no party data is not zero-filled',()=>{
    const s=state(ballot('house',[dem,rep],'01'));const zero=structuredClone(d);zero.campaign_fundraising.amounts.receipts_cents=0;
    const data=stateFundraisingSummary(s,'house',[finance('house',[zero],'01')],null,now);
    assert.equal(data.parties.DEM.amount,0);assert.equal(data.parties.REP.amount,null);assert.equal(data.total.amount,0);assert.equal(data.status,'partial');
    const html=stateFundraisingHtml(s,'house',[finance('house',[zero],'01')],null,null,now);assert.match(html,/일부 집계/);assert.match(html,/미연결/);assert.match(html,/1\/2명 금액 연결/);
});
test('third-party nominees are separate from DEM/GOP while included in the observed overall total',()=>{
    const ind=nominee('H6OH01003','Independent nominee','IND');const s=state(ballot('house',[dem,rep,ind],'01'));
    const data=stateFundraisingSummary(s,'house',[finance('house',[d,r,candidate(ind.candidate_id,ind.name,'IND',80000)],'01')],null,now);
    assert.equal(data.parties.OTHER.amount,80000);assert.equal(data.total.amount,430003);
    assert.equal(data.parties.DEM.amount,100001);assert.equal(data.parties.REP.amount,250002);
});
test('future, wrong-district and unsafe amounts cannot create state fundraising totals',()=>{
    const s=state(ballot('house',[dem],'01'));
    for(const patch of [{coverage_end:'2026-10-20'},{race_id:'USA:OH:house:02'},{district:'02'},{coverage_end:'2026-09-30',snapshot_as_of:'2026-06-30'},{amounts:{receipts_cents:1.25}},{currency:'KRW'}]){
        const c=structuredClone(d);Object.assign(c.campaign_fundraising,patch);
        assert.equal(stateFundraisingSummary(s,'house',[finance('house',[c],'01')],null,now).total.amount,null);
    }
});
test('no 2026 Senate/governor election and unconnected governor state disclosure remain explicit',()=>{
    const s={id:'OH',governor_election:{cycle:2026,election_in_cycle:false,reviewed_on:'2026-10-19'},federal_delegation:{senators:[{up_in_2026:false},{up_in_2026:false}]}};
    assert.equal(stateFundraisingSummary(s,'governor',[],null,now).status,'not_scheduled');assert.equal(stateFundraisingSummary(s,'senate',[],null,now).status,'not_scheduled');
    s.governor_election.election_in_cycle=true;
    const html=stateFundraisingHtml(s,'governor',[],null,null,now);assert.match(html,/주별 공시 미연결/);assert.doesNotMatch(html,/\$/);
});
test('unreviewed race coverage is marked missing; retained original dates and original sources are visible',()=>{
    const s=state(ballot('house',[dem],'01'));const missing={...ballot('house',[],'02'),schedule_status:'scheduled_general_unreviewed'};delete missing.status;
    const old=structuredClone(d);old.campaign_fundraising.coverage_end='2026-06-30';old.campaign_fundraising.snapshot_as_of='2026-10-18';old.campaign_fundraising.carried_forward_reason='missing_in_new_bulk';
    const board={races:{[missing.race_id]:missing}};
    const data=stateFundraisingSummary(s,'house',[finance('house',[old],'01')],board,now);assert.equal(data.targetRaces,2);assert.equal(data.reviewedRaces,1);assert.equal(data.status,'partial');
    const html=stateFundraisingHtml(s,'house',[finance('house',[old],'01')],board,null,now);assert.match(html,/공시 기준 2026-06-30/);assert.match(html,/수집 2026-10-18/);assert.match(html,/이전 유효 공시 보존/);assert.match(html,/H6OH01001/);assert.match(html,/weball26.zip/);
});
test('safe integer overflow is held instead of rounding a financial sum',()=>{
    const s=state(ballot('house',[dem,rep],'01'));const large=structuredClone(d);large.campaign_fundraising.amounts.receipts_cents=Number.MAX_SAFE_INTEGER;
    const data=stateFundraisingSummary(s,'house',[finance('house',[large,r],'01')],null,now);assert.equal(data.total.amount,null);assert.equal(data.total.overflow,true);
});
test('each state office card places fundraising just under current party boxes and before outlook; poll windows do not change it',()=>{
    const board=JSON.parse(fs.readFileSync(new URL('../../../public/data/elections_board_v1.json',import.meta.url)));
    const country=board.countries.find(c=>c.iso3==='USA');const original=country.ui_ready.state_drilldown.states.find(s=>s.id==='OH');
    const s={...original,election_matchups:{[rid('house','01')]:ballot('house',[dem,rep],'01')}};
    const render=(days)=>electionOverviewHtml(country,null,{state:s,financeRaces:[finance('house',[d,r],'01')],days,now});
    const a=render(7),b=render(14);const house=a.split('data-office="house"')[1];
    assert.ok(house.indexOf('elections-current-parties')<house.indexOf('data-fundraising-office="house"'));
    assert.ok(house.indexOf('data-fundraising-office="house"')<house.indexOf('elections-outlook-parties'));
    assert.match(house,/\$3,500.03/);assert.match(b,/\$3,500.03/);
});

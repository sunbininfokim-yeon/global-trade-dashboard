import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { currentElectionSeats, electionRatingSummary, classifyElectionRace, electionOutlook } from '../data/election-overview.js';
import { electionOverviewHtml, evidenceSectionHtml } from '../country-explorer/special/usa-election-overview.js';
const base = new URL('../../../public/data/', import.meta.url);
const read = f => JSON.parse(fs.readFileSync(new URL(f, base)));
const country = read('elections_board_v1.json').countries.find(c => c.iso3 === 'USA');
const ratings = read('usa_election_ratings_review_v1.json');
const board = read('usa_election_live_polls_v1.json'), health = read('usa_election_live_polls_status_v1.json');
const states = country.ui_ready.state_drilldown.states;
const now = Date.parse('2026-10-07T00:00:00Z');
const sum = c => c.DEM + c.GOP + c.IND + (c.unknown || 0);
const summary = (office, state = null, data = ratings, c = country, time = now) => electionRatingSummary(data, office, c, state, time);

test('current national holders reconcile independently, preserving independents and vacancies', () => {
    const rows = currentElectionSeats(country);
    assert.equal(sum(rows.governor.counts), 50);
    assert.equal(sum(rows.senate.counts), 100);
    assert.equal(rows.senate.counts.IND, 2);
    assert.equal(sum(rows.house.counts) + rows.house.vacancies, 435);
    assert.deepEqual(rows.house.counts, { ...country.ui_ready.congress.summary.house_by_party, unknown: 0 });
    const aggregated = states.reduce((a,s) => {
        const row = currentElectionSeats(country,s).house;
        for (const key of ['DEM','GOP','IND']) a[key] += row.counts[key];
        a.vacancies += row.vacancies; return a;
    }, { DEM:0,GOP:0,IND:0,vacancies:0 });
    assert.deepEqual(aggregated, {DEM:rows.house.counts.DEM,GOP:rows.house.counts.GOP,IND:rows.house.counts.IND,vacancies:rows.house.vacancies});
});

test('complete original Cook categories reconcile all contests and all 50 House states', () => {
    for (const [office, expected] of Object.entries({ house: [197,195,21,22,435], senate: [12,15,1,7,35], governor: [13,11,7,5,36] })) {
        const r = summary(office, null, ratings, null);
        assert.deepEqual([r.cookBlue,r.cookRed,r.lean,r.cookToss,r.contested], expected);
        assert.equal(r.blue + r.red + r.lean + r.toss, r.contested);
    }
    for (const state of states) {
        const r = summary('house', state.id);
        assert.equal(r.contested, currentElectionSeats(country, state).house.total, state.id);
        assert.equal(r.blue + r.red + r.lean + r.toss, r.contested, state.id);
    }
});

test('NY splits House ratings by district, with extra cautions instead of assigning all seats to state color', () => {
    const state = states.find(s => s.id === 'NY');
    const r = summary('house', 'NY');
    assert.equal(r.contested, 26);
    assert.equal(r.toss, r.cookToss + r.additional.length);
    assert(r.additional.some(x => x.district === '21' && x.rating === 'likely_rep' && x.effective_rating === 'toss_up'));
    assert(r.blue < 26);
    const senate = summary('senate', 'NY');
    assert.equal(senate.contested, 0);
    const outlook = electionOutlook(country, 'senate', senate, { state, now });
    assert.deepEqual(outlook.counts, { DEM: 2, GOP: 0, IND: 0 });
    assert.equal(outlook.retained, 2);
});

test('user cautions preserve Cook and distinguish statewide mismatch from a verified district crossover', () => {
    const ny21 = ratings.offices.house.races.find(r => r.race_id === 'USA:NY:house:21');
    const original = structuredClone(ny21);
    const changed = classifyElectionRace(ny21, country);
    assert.deepEqual(ny21, original);
    assert.equal(changed.reasons[0].criterion, 'state_presidential_held_party_mismatch');
    const fl22 = ratings.offices.house.races.find(r => r.race_id === 'USA:FL:house:22');
    assert.equal(classifyElectionRace(fl22, country).additional, false);
    assert.equal(classifyElectionRace(fl22, country).rating, 'toss_up');
    const ak = summary('house').additional.find(r => r.state === 'AK');
    assert.equal(ak.reasons[0].criterion, 'two_party_changes_last_three_general_elections');
    const example = {race_id:'USA:PA:house:01',state:'PA',district:'01',rating:'likely_rep',cook_held_party:'GOP'};
    const split = {chamber:'house',state:'PA',district:'01',criterion:'presidential_congressional_split_ticket',basis_ko:'verified boundary',
        evidence:[{year:2024,party_abbr:'GOP',presidential_party_abbr:'DEM',source_url:'https://example.org/results'}]};
    const c = {ui_ready:{congress:{swing_seats:[split]}}};
    assert.equal(classifyElectionRace(example,c).additional,false, 'number match alone must not reuse old boundaries');
    split.boundary_lineage_verified = true;
    assert.equal(classifyElectionRace(example,c).additional,true);
});

test('outlook reconciles 435/100/50, accounts for special Senate races and does not call unpolled Lean/Toss-up seats', () => {
    for (const [office,total] of [['house',435],['senate',100],['governor',50]]) {
        const r = summary(office);
        const o = electionOutlook(country, office, r, {now});
        assert.equal(sum(o.counts) + o.pending,total);
        assert.equal(o.pending,r.lean + r.toss);
        assert.equal(o.total,total);
    }
    assert.equal(electionOutlook(country,'senate',summary('senate'),{now}).counts.IND,2);
    for(const id of ['FL','OH']) {
        const state=states.find(s=>s.id===id);
        const o=electionOutlook(country,'senate',summary('senate',id),{state,now});
        assert.equal(o.retained,1,`${id} special election must remove class III incumbent from retained`);
        assert.equal(o.total,2);
    }
});

test('7/14-day selections use live windows and separate single-source references; stale polls cannot call a contest', () => {
    const r = summary('house');
    const opts = {board,health,now};
    const seven = electionOutlook(country,'house',r,{...opts,days:7});
    const fourteen = electionOutlook(country,'house',r,{...opts,days:14});
    assert.equal(seven.pollResolved,0);
    assert.equal(fourteen.pollResolved,2);
    assert.equal(fourteen.single,2);
    assert.equal(seven.pending - fourteen.pending,2);
    const stale = {...board,fetched_at:'2026-09-01T00:00:00Z'};
    assert.equal(electionOutlook(country,'house',r,{...opts,board:stale,days:14}).pollResolved,0);
});

test('state totals preserve vacancies and delegates; missing or malformed inputs remain unavailable', () => {
    const state={id:'TX',governor:{abbr:'GOP'},federal_delegation:{senators:[{abbr:'GOP'},{abbr:'IND'}],house_members:[{abbr:'DEM'},{abbr:'GOP'},{abbr:'GOP',is_delegate:true}]}};
    const rows=currentElectionSeats({ui_ready:{congress:{vacancies:[{state:'TX',chamber:'house'}]}}},state);
    assert.equal(rows.house.total,3);assert.equal(rows.house.vacancies,1);
    assert.equal(currentElectionSeats(null).house.counts,null);
    assert.equal(currentElectionSeats(null,{id:'XX',federal_delegation:{house_members:[]}}).house.total,null);
    assert.equal(summary('house',null,ratings,country,Date.parse('2026-11-01')),null);
    assert.equal(summary('governor',null,null),null);
    const incomplete=structuredClone(ratings);incomplete.offices.house.races.pop();
    assert.equal(summary('house',null,incomplete),null);
    const duplicate=structuredClone(ratings);duplicate.offices.house.races[0]=duplicate.offices.house.races[1];
    assert.equal(summary('house',null,duplicate),null);
    const oldGov=structuredClone(country);oldGov.ui_ready.state_drilldown.states.pop();
    assert.equal(electionOutlook(oldGov,'governor',summary('governor'),{now}),null);
});

test('after the election, expired Cook assumptions stop and only certified winners resolve contests', () => {
    const after=Date.parse('2026-11-05T00:00:00Z');
    assert.equal(summary('house',null,ratings,country,after),null);
    const r=electionRatingSummary(ratings,'house',country,null,after,{resultsOnly:true});
    const certifiedBoard={races:{'USA:NY:house:17':{phase:'certified_result',result:{status:'certified',party:'DEM',winner:'Verified winner'}}}};
    const o=electionOutlook(country,'house',r,{board:certifiedBoard,now:after});
    assert.equal(o.counts.DEM,1);assert.equal(o.counts.GOP,0);assert.equal(o.pending,434);assert.equal(o.certified,1);
    const html=electionOverviewHtml(country,ratings,{board:certifiedBoard,now:after});
    assert.match(html,/선거 후 · 공식 결과/);assert.match(html,/지난 Cook 등급의 우세 가정은 중단/);
});

test('overview separates current holders, outlook, ratings and collapsed evidence', () => {
    const html=electionOverviewHtml(country,ratings,{now});
    assert.equal((html.match(/class="elections-seat-card"/g)||[]).length,3);
    assert.match(html,/현재 보유/);assert.match(html,/전망 · 최근 7일/);assert.match(html,/2026 선거 분류/);
    assert.match(html,/무소속 2/);assert.match(html,/추가 경합/);
    assert.doesNotMatch(evidenceSectionHtml('poll','여론조사','', '<p>data</p>'),/ open>/);
    assert.match(evidenceSectionHtml('poll','여론조사','', '<p>data</p>',true),/ open>/);
});

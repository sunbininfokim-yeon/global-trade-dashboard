import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { currentPollWindow } from '../data/poll-window.js';
import { pollSignal, pollSourceReady } from '../data/usa-election-context.js';
import { selectNationalRaces, summarizeNationalRaces, nationalMonitoringStates } from '../country-explorer/special/usa-election-national.js';
import { pollEvidenceHtml } from '../country-explorer/special/usa-election-evidence.js';
import { usaStateSuperPac } from '../country-explorer/special/usa-state-superpac.js';

const now = Date.parse('2026-10-06T12:00:00Z');
const board = { schema: 'usa_live_polls_v1', source_status: 'ok', as_of: '2026-10-06', fetched_at: '2026-10-06T01:00:00Z', stale_after_hours: 192 };
const observation = (id, date, group = id, changes = {}) => ({ id, field_end: date, pollster_group: group,
    pollster: group, population: 'lv', aggregation_eligibility: { eligible: true, reasons: [] },
    answers: [{ name: 'D', pct: 51, party: 'DEM' }, { name: 'R', pct: 45, party: 'REP' }], ...changes });
const race = (rows) => ({ phase: 'pre_election', election_date: '2026-11-03', observations: rows,
    office: 'house', state: 'NY', district: '17', race_id: 'USA:NY:house:17', required_candidates: ['D','R'], schedule_status: 'reported_general_matchup' });

test('weekly snapshot stays usable for seven days but its seven-day poll ages out', () => {
    const r = race([observation('a','2026-10-01')]);
    assert.equal(pollSignal(r, board, { status:'ok' }, 7, now).status, 'single_poll_lead');
    assert.equal(pollSignal(r, board, { status:'ok' }, 7, Date.parse('2026-10-08T12:00:00Z')).status, 'no_recent_poll');
    assert.equal(pollSourceReady(board,{status:'ok'},Date.parse('2026-10-12T12:00:00Z')),true);
    assert.equal(pollSourceReady(board,{status:'ok'},Date.parse('2026-10-15T12:00:00Z')),false);
});

test('references cannot count as an institution or displace eligible observations', () => {
    const r=race([observation('a','2026-10-01','same'), observation('ref','2026-10-06','same',
        { aggregation_eligibility:{eligible:false,reasons:['reference_only']} })]);
    const w=currentPollWindow(r,7,now);
    assert.deepEqual(w.included_ids,['a']); assert.deepEqual(w.reference_ids,['ref']);
    assert.equal(w.pollster_count,1);
});

test('latest institution waves and LV/RV populations remain separate', () => {
    const r=race([observation('old','2026-10-01','same'),observation('new','2026-10-02','same'),
        observation('rv','2026-10-06','other',{population:'rv'})]);
    assert.deepEqual(currentPollWindow(r,7,now).included_ids,['new']);
    r.observations.push(observation('conflict','2026-10-02','same',{
        answers:[{name:'D',pct:44,party:'DEM'},{name:'R',pct:52,party:'REP'}]}));
    const w=currentPollWindow(r,7,now);assert.equal(w.status,'no_recent_poll');
    assert.deepEqual(w.conflicting_pollsters,['same']);
});

test('single poll leads are displayed and separately counted; Cook direction supplies no winner', () => {
    const r=race([observation('a','2026-10-01')]);r.state='WA';r.race_id='USA:WA:house:03';
    r.monitor_priority={tier:'toss_up'};
    const b={...board,races:{[r.race_id]:r}};
    assert.equal(pollSignal(r,b,{status:'ok'},7,now).party,'DEM');
    assert.equal(summarizeNationalRaces(b,{status:'ok'},7,now).total.singleDem,1);
    assert.equal(summarizeNationalRaces(b,{status:'ok'},7,now).total.dem,0);
    r.state='IA';assert.equal(selectNationalRaces(b,7,{status:'ok'},now).length,1);
    assert.ok(nationalMonitoringStates(b).includes('IA'));
    r.observations=[];assert.equal(pollSignal(r,b,{status:'ok'},7,now).party,null);
});

test('reference quality and rejected matchup labels reach HTML without becoming an accuracy grade', () => {
    const r=race([observation('reference','2026-10-01','example',{
        aggregation_eligibility:{eligible:false,reasons:['party_commissioned_reference']},
        source_quality:{verification_level:'primary_toplines_checked',methodological_quality:'unrated'},
        commissioning:{sponsors:['Fixture sponsor']}})]);
    const b={...board,monitoring:{race_coverage:{[r.race_id]:{matchup_reviewed:false}}}};
    const html=pollEvidenceHtml(r,b,{status:'ok'},7);
    assert.match(html,/참고 전용/);assert.match(html,/정확도 미등급/);assert.match(html,/Fixture sponsor/);
    assert.match(html,/본선 후보 대진 검토 대기/);
});

test('polls remain visible when state finance assets are unavailable', () => {
    const r=race([observation('a','2026-10-01')]);const b={...board,races:{[r.race_id]:r}};
    const html=usaStateSuperPac({id:'NY'},null,new Set(['17']),null,b,{status:'ok'},7);
    assert.match(html,/여론조사/);assert.match(html,/자료 연결 대기/);assert.match(html,/하원 17구/);
});

test('mixed snapshot health is not accepted', () => {
    assert.equal(pollSourceReady(board,{status:'ok',as_of:'2026-10-05'},now),false);
});

test('browser window calculation agrees with all published backend race windows', () => {
    const b=JSON.parse(fs.readFileSync(new URL('../../../public/data/usa_election_live_polls_v1.json',import.meta.url)));
    const at=Date.parse(`${b.as_of}T12:00:00Z`);
    for (const r of Object.values(b.races)) for (const days of [7,14]) {
        if(r.phase!=='pre_election')continue;
        const computed=currentPollWindow(r,days,at),published=r.windows[String(days)];
        for(const key of ['from','through','population','status','party','leader','pollster_count','lead_counts','tie_count','included_ids','conflicting_pollsters','reference_ids','reference_poll_count','latest_field_end']) {
            assert.deepEqual(computed[key],published[key],`${r.race_id}/${days}/${key}`);
        }
    }
});

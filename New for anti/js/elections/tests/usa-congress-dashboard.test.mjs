import assert from 'node:assert/strict';
import test from 'node:test';

import { usaLegislature } from '../country-explorer/special/usa-legislature.js';
import { usaSections } from '../country-explorer/special/usa.js';

const member = (bioguideId, name, abbr, state, district) => ({
    bioguideId, name, abbr, state, state_abbr: state, district,
});
const country = {
    ui_ready: { congress: {
        summary: { house_by_party: { DEM: 2, GOP: 1 }, house_vacancies: 2, senate_by_party: { GOP: 4, DEM: 1 } },
        house_members: [member('H000001', 'One, House', 'DEM', 'CA', 1),
            member('H000002', 'Two, House', 'DEM', 'TX', 2), member('H000003', 'Three, House', 'GOP', 'TX', 3)],
        senate_members: [member('S000001', 'One, Senator', 'DEM', 'CA', null)],
        floor_leadership: [
            { chamber: 'house', office: 'speaker', name: 'Rep. House One', bioguide_id: 'H000001' },
            { chamber: 'senate', office: 'senate_minority_leader', name: 'Sen. Senator One', bioguide_id: 'S000001' },
        ],
    }},
    us_congress_dashboard: {
        rosters: {
            congress: 119,
            people: { H000001: { name: 'House One', official_url: 'https://official.house.gov/' } },
            chambers: {
                house: { factions: { DEM: [
                    { name_ko: 'Group A', kind: 'public_membership', member_ids: ['H000001', 'H000001', 'S000001'] },
                    { name_ko: 'Group B', kind: 'public_membership', member_ids: ['H000001'] },
                ] } },
                senate: { factions: { DEM: [
                    { name_ko: 'Voting segment', kind: 'voting_profile', member_ids: ['S000001'] },
                ] } },
            },
        },
        agenda: { milestones: [
            { title_ko: '예산기한', chambers: ['house'], date: '2026-12-11', url: 'https://www.govinfo.gov/' },
            { title_ko: '지난 일정', chambers: ['house'], date: '2026-11-20' },
            { title_ko: '상원 일정', chambers: ['senate'], date: '2026-12-01' },
        ] },
    },
};

test('USA political dashboard has separate chambers', () => {
    assert.deepEqual(usaSections.filter(([, id]) => ['senate', 'house'].includes(id)), [['상원', 'senate'], ['하원', 'house']]);
    assert.ok(!usaSections.some(([, id]) => ['legislature', 'factions'].includes(id)));
});

test('House shows both rows, official office links, overlapping factions and unmatched members', () => {
    const html = usaLegislature(country, 'house', { today: '2026-11-26' });
    assert.match(html, /원내 지도부[\s\S]*의석 분포[\s\S]*상임위[\s\S]*공석 · 주요 일정/);
    assert.match(html, /grid-template-columns:minmax\(0,1fr\)/);
    assert.match(html, /민주당<\/h3>[\s\S]*주별 분포[\s\S]*주요 당직자[\s\S]*계파 분류[\s\S]*공화당<\/h3>/);
    assert.match(html, /href="https:\/\/official\.house\.gov\/"[^>]*>House One/);
    assert.match(html, /Group A · 1명[\s\S]*House One[\s\S]*Group B · 1명[\s\S]*House One/);
    assert.match(html, /계파 미확인 · 1명[\s\S]*House Two/);
    assert.match(html, /예산기한/);
    assert.doesNotMatch(html, /상원 일정|지난 일정|Senator One/);
});

test('Senate voting groups do not count as documented affiliations', () => {
    const html = usaLegislature(country, 'senate', { today: '2026-11-26' });
    assert.match(html, /Voting segment · 1명[\s\S]*공개 계파·연대 미확인 · 1명/);
    assert.match(html, /상원 일정/);
    assert.doesNotMatch(html, /Group A|예산기한/);
});

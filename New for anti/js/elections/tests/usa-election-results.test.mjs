import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { usaSections } from '../country-explorer/special/usa.js';
import { mountUsaElectionResults, usaElectionResults } from '../country-explorer/special/usa-election-results.js';

const asset = (name) => JSON.parse(readFileSync(new URL(`../../../public/data/${name}.json`, import.meta.url)));
const results = asset('usa_state_executive_results_v1');
const governors = asset('usa_governors_dashboard_v1');

test('the USA results block retains its route and separates the three national contest totals', () => {
    assert.deepEqual(usaSections.at(-1), ['선거 결과', 'race_progress']);
    const html = usaElectionResults(results, governors);
    assert.match(html, /연방상원 · 선거 35석[\s\S]*?민주당 22석[\s\S]*?공화당 13석/);
    assert.match(html, /비선거 65석[\s\S]*?선거 후 전체 100석/);
    assert.match(html, /연방하원 · 선거 435석[\s\S]*?민주당 259석[\s\S]*?공화당 173석[\s\S]*?승자 미발표 3석/);
    assert.match(html, /주지사 · 선거 36곳[\s\S]*?민주당 24석[\s\S]*?공화당 12석/);
    assert.match(html, /취임 후 예상 · 50개 주[\s\S]*?민주당 30석[\s\S]*?공화당 20석/);
    assert.equal((html.match(/<option /g) || []).length, 50);
    assert.match(html, /43개 주 · 행정부·위원회 296석 · 승자 확인 296석/);
});

test('Texas results carry the independently elected finance officer and distinguish calls from a count lead', () => {
    const html = usaElectionResults(results, governors);
    assert.match(html, /<option value="TX" selected>/);
    assert.match(html, /주 재정감독관[\s\S]*?Sarah Eckhardt[\s\S]*?Comptroller of Public Accounts[\s\S]*?5,014,496표/);
    assert.match(html, /주 검찰총장[\s\S]*?Nathan Johnson/);
    assert.match(html, /주 위원회·교육기관 9석/);
    assert.match(html, /8 선거구[\s\S]*?Dana Van De Walker[\s\S]*?tpr\.org[\s\S]*?공개 출처 승자 발표/);
    const counting = structuredClone(results);
    counting.states.TX.offices.find((row) => row.name === 'Dana Van De Walker').result_status = 'count_leader';
    const provisional = usaElectionResults(counting, governors);
    assert.match(provisional, /승자 확인 295석/);
    assert.match(provisional, /8 선거구[\s\S]*?Dana Van De Walker[\s\S]*?주정부 개표 선두/);
    assert.match(html, /주 최고법원·형사항소법원 7석/);
    assert.match(html, /국무장관은 주지사가 임명/);
    assert.match(html, /인종·민족 <a[^>]+>라티나<\/a>/);
    assert.match(html, /인종·민족 미확인/);
});

test('state selector renders joint-ticket affiliation and state scope independently of governor party', () => {
    const select = { value: 'AZ', addEventListener(_name, callback) { this.change = callback; } };
    const panel = { innerHTML: '' };
    const root = {
        ownerDocument: { querySelector: () => ({}) },
        querySelector: (selector) => selector.includes('select') ? select : panel,
    };
    mountUsaElectionResults(root, results, governors);
    select.change();
    assert.match(panel.innerHTML, /John Giles[\s\S]*?정당 선호 없음[\s\S]*?주지사와 공동 후보/);
    select.value = 'WA';
    select.change();
    assert.match(panel.innerHTML, /2026년 주지사 선거 없음/);
    assert.match(panel.innerHTML, /전국 집계에 이 주의 2026년 주 행정부 선출직 선거가 없습니다/);
});

test('the state executive snapshot carries one sourced record per seat and sourced demographic fields', () => {
    const counts = new Map();
    for (const [state, result] of Object.entries(results.states)) {
        assert.ok(governors.states.some((row) => row.state === state));
        const seats = new Set();
        for (const row of result.offices) {
            const key = [row.office, row.district, row.seat_key].join(':');
            assert.ok(!seats.has(key), `${state} ${key}`);
            seats.add(key);
            assert.ok(results.offices[row.office], `${state} ${row.office}`);
            assert.match(row.result_url, /^https:\/\//);
            if (row.votes !== undefined) {
                assert.ok(Number.isInteger(row.votes));
                assert.match(row.vote_url, /^https:\/\//);
                assert.match(row.vote_as_of, /^2026-\d{2}-\d{2}$/);
            }
            for (const field of [row.profile?.gender, row.profile?.race_ethnicity].filter(Boolean)) {
                assert.ok(field.value);
                assert.match(field.source_url, /^https:\/\//);
            }
            counts.set(row.office, (counts.get(row.office) || 0) + 1);
        }
    }
    assert.equal(counts.get('attorney-general'), 30);
    assert.equal(counts.get('lieutenant-governor'), 31);
    assert.equal(counts.get('secretary-of-state'), 26);
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { usaExecutivePanels, usaGovernorDashboard } from '../country-explorer/special/usa-governors.js';

const data = JSON.parse(readFileSync(new URL('../../../public/data/usa_governors_dashboard_v1.json', import.meta.url)));

test('governor dashboard presents the 50-state roster and the 36 election results separately', () => {
    const html = usaGovernorDashboard(data, { today: '2026-11-26' });
    assert.equal(new Set(data.states.map((row) => row.state)).size, 50);
    assert.equal(data.states.filter((row) => row.transition).length, 36);
    assert.match(html, /현직 · 명부 기준[\s\S]*민주당 24석[\s\S]*공화당 26석/);
    assert.match(html, /선거 36곳 · 비선거 14곳[\s\S]*민주당 24석[\s\S]*공화당 12석/);
    assert.match(html, /취임 후 예상 구성[\s\S]*민주당 30석[\s\S]*공화당 20석/);
    assert.match(html, /정당 교체 예정 6곳/);
    assert.match(html, /현직 주지사 26명[\s\S]*href="https:\/\/gov\.alaska\.gov\/"[^>]*>Mike Dunleavy/);
    assert.match(html, /전체 취임 일정 36개 주/);
    assert.match(html, /사우스다코타 · 날짜 미확인/);
    assert.match(html, /추가 협의체 소속 미확인/);
});

test('a passed inauguration date does not promote a reported winner into the incumbent roster', () => {
    const html = usaGovernorDashboard(data, { today: '2026-12-09' });
    assert.match(html, />Mike Dunleavy<\/a>/);
    assert.match(html, /Jonathan Kreiss-Tomkins<\/a> · <a[^>]*>예정일 경과 · 취임 확인 대기/);
    assert.match(html, /주 인증 확인/);
    assert.match(html, /승자 발표/);
});

test('the executive options preserve the federal default and provide a labeled governor panel', () => {
    const html = usaExecutivePanels('<p>Federal dashboard</p>', data);
    assert.match(html, /id="elections-chamber-1"[^>]*checked/);
    assert.match(html, /for="elections-chamber-2"[^>]*>주지사/);
    assert.match(html, /data-chamber-slot="1"[\s\S]*Federal dashboard/);
    assert.match(html, /data-chamber-slot="2"[\s\S]*data-usa-governors/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chnLeadersToggle, provincesHtml, enterprisesHtml, centralEvidenceHtml, evidence } from '../country-explorer/special/chn-leaders.js';

const data = JSON.parse(readFileSync(new URL('../../../public/data/elections_cn_leaders_v1.json', import.meta.url)));

test('toggle keeps the central chart and adds provinces and enterprises', () => {
    const html = chnLeadersToggle('<p>CENTRAL</p>', data);
    assert.match(html, /CENTRAL/);
    assert.match(html, /중앙 인사/);
    assert.match(html, /지방 지도부 31/);
    assert.match(html, /기업·기타/);
    assert.equal((html.match(/type="radio"/g) || []).length, 3);
    assert.equal((html.match(/ checked/g) || []).length, 1, 'only the central tab starts open');
});

test('missing leaders file leaves the central chart untouched', () => {
    assert.equal(chnLeadersToggle('<p>CENTRAL</p>', null), '<p>CENTRAL</p>');
});

test('every province gets its own collapsible card, plus XPCC', () => {
    const html = provincesHtml(data);
    assert.equal((html.match(/class="cn-lead-province"/g) || []).length, 32);
    for (const sec of data.provincial_secretaries) assert.match(html, new RegExp(`data-region="${sec.region_ko.replace(/[()]/g, '\\$&')}"`));
    assert.match(html, /신장생산건설병단/);
});

test('acting, vacant and concurrent heads are labelled, not shown as elected', () => {
    const html = provincesHtml(data);
    const card = (region) => html.split('<details').find((part) => part.includes(`data-region="${region}"`));
    assert.match(card('장시'), /수반 공석/);
    assert.match(card('푸젠'), /서기 겸임/);
    assert.match(card('허베이'), /대리/);
    assert.doesNotMatch(card('허베이'), /인대 선출/);
    assert.match(card('허베이'), /낡은 페이지 주의/);
});

test('dates carry their source, and missing sources are said out loud', () => {
    assert.match(evidence({ date: '2026-10-25', url: 'https://www.news.cn/x', search_only: false }), /2026-10-25 · <a [^>]*>원문<\/a>/);
    assert.match(evidence({ date: '2026-10-25', url: 'https://www.news.cn/x', search_only: true }), /검색 본문/);
    assert.match(evidence({ date: '2021-10-22', url: null }), /원문 미확인/);
    assert.match(evidence(null), /미확인/);
    assert.doesNotMatch(evidence({ date: '2026-01-01', url: 'javascript:alert(1)' }), /href/);
});

test('enterprise and central evidence render from the published file', () => {
    assert.match(enterprisesHtml(data), /중국다탕그룹/);
    assert.match(enterprisesHtml(data), /중국공상은행/);
    const central = centralEvidenceHtml(data);
    assert.match(central, new RegExp(`정치국 ${data.politburo.length}인`));
    assert.match(central, /장성민/);
    assert.match(central, /중앙위원 보충 10인/);
});

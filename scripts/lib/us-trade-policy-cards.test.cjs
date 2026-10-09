'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'New for anti/public/data/trade_policy/us_tariffs_v1.json')));
const source = fs.readFileSync(path.join(root, 'New for anti/export-controls.js'), 'utf8');
function renderer(input = data) {
    const window = {};
    const exposed = source.replace('    window.ExportControls = {', `
    usTariffs = input;
    window.testTradeCards = { partnerHtml, tariffPhase, usTariffSectionHtml };
    window.ExportControls = {`);
    vm.runInNewContext(exposed, { window, input, Intl, console });
    return window.testTradeCards;
}

test('country cards connect new partners to existing measures and conditional tools', () => {
    const ids = new Set(data.measures.map(m => m.id));
    const tools = new Set(data.legal_tools.map(t => t.id));
    assert.equal(ids.size, data.measures.length);
    assert.equal(tools.size, data.legal_tools.length);
    for (const [iso, p] of Object.entries(data.partners)) {
        for (const id of p.legal_tool_ids) assert.ok(tools.has(id), `${iso}: ${id}`);
        for (const l of p.lines) for (const id of l.measure_ids || []) assert.ok(ids.has(id), `${iso}: ${id}`);
    }
    for (const iso of ['VNM', 'MEX', 'CAN']) {
        const html = renderer().partnerHtml(iso, data.partners[iso]);
        assert.ok(html.includes(data.partners[iso].name_ko));
        assert.match(html, /법적 요건을 충족하면 검토할 수 있는 수단/);
        assert.match(html, /모두 적용 중이거나/);
        assert.match(renderer().usTariffSectionHtml(), new RegExp(`data-ec-iso="${iso}"`));
    }
});

test('Canada duty changes, exclusion and USMCA exemption stay distinct', () => {
    const duty = data.measures.find(m => m.id === 'sec338-canada-motor-retaliation');
    const ban = data.measures.find(m => m.id === 'sec338-canada-motor-import-ban');
    assert.equal(duty.started, '2026-08-22');
    assert.equal(ban.started, '2026-09-29');
    assert.equal(ban.action_type, 'import_ban');
    assert.equal(ban.calculation_ready, false);
    const html = renderer().partnerHtml('CAN', data.partners.CAN);
    assert.match(html, /무관세로 신고/);
    assert.match(html, /전체 면제는 아님/);
    assert.match(html, /수입금지/);
    assert.match(html, /09-15/);
});

test('investigations and unverified mixed measures are not ended or effective tariffs', () => {
    const r = renderer();
    const investigation = data.measures.find(m => m.id === 'sec301-vietnam-ip-investigation');
    const mixed = data.measures.find(m => m.id === 'sec232-other');
    assert.equal(r.tariffPhase(investigation), 'pending');
    assert.equal(r.tariffPhase(mixed), 'pending');
    assert.equal(r.tariffPhase({ status: 'active', started: '2027-01-01' }), 'pending');
    assert.equal(r.tariffPhase({ status: 'active', ended: '2026-09-01' }), 'history');
    assert.equal(r.tariffPhase({ status: 'unknown' }), 'pending');
    const html = r.usTariffSectionHtml();
    const live = html.split('시행 중인 제도')[1].split('조사·시행 예정·재확인')[0];
    assert.ok(!live.includes(investigation.name_ko));
    for (const m of data.measures.filter(m => m.authority === 'IEEPA')) assert.equal(r.tariffPhase(m), 'history');
});

test('base-rate floor rule is not a cap reducing a higher tariff', () => {
    for (const iso of ['KOR', 'JPN', 'TWN', 'DEU']) {
        const first = data.partners[iso].lines[0];
        assert.match(first.rate_ko, /추가 0/);
        assert.ok(!first.rate_ko.includes('상한'));
    }
    assert.match(data.measures.find(m => m.id === 'sec232-metals').rate_ko, /최소 15%/);
});

test('legal powers and display prose cannot silently supply model rates', () => {
    for (const t of data.legal_tools) {
        assert.equal(t.availability, 'conditional');
        assert.equal(t.assumed_rate, null);
        assert.equal(t.calculation_ready, false);
        assert.ok(t.legal_basis && t.trigger_ko && t.procedure_ko && t.sources.length);
    }
    for (const m of data.measures) assert.equal(m.calculation_ready, false);
    assert.equal(data.audit.status, 'partial');
});

test('country text is escaped and source URLs cannot inject executable links', () => {
    const p = structuredClone(data.partners.VNM);
    p.name_ko = '<img src=x onerror=alert(1)>';
    p.lines[0].rate_ko = '<script>alert(1)</script>';
    p.lines[0].sources = [{ label: '<img>', url: 'javascript:alert(1)' }];
    p.sources = [{ label: '<img>', url: 'data:text/html,evil' }];
    const html = renderer().partnerHtml('VNM', p);
    assert.ok(!html.includes('<script>'));
    assert.ok(!html.includes('<img'));
    assert.ok(!html.includes('href="javascript:'));
    assert.ok(!html.includes('href="data:'));
    assert.match(html, /&lt;script&gt;/);
});

test('each checked line has provenance and unresolved legacy claims remain visible', () => {
    const render = renderer();
    for (const [iso, p] of Object.entries(data.partners)) {
        for (const l of p.lines) if (l.verification === 'primary_text_checked') assert.ok(l.sources?.length, iso);
    }
    assert.match(render.partnerHtml('KOR', data.partners.KOR), /기존 자료 · 재확인 필요/);
    assert.match(render.usTariffSectionHtml(), /모든 현행 HTS/);
});

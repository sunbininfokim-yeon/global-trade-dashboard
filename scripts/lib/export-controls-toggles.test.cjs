'use strict';
// Toggles in the export-control monitor: US panel (관세 정책 | 제재·제한 | 수출통제·최근 공고),
// the tariff sub-toggle (국가별 | 시행 | 가능 | 완료) and 수출 통제 | 미국 對○ 제재 on a country.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const pub = (f) => JSON.parse(fs.readFileSync(path.join(root, 'New for anti/public/data', f)));
const tariffs = pub('trade_policy/us_tariffs_v1.json');
const sanc = pub('trade_policy/us_sanctions_v1.json');
const manifest = pub('export_controls/manifest.json');
const modules = manifest.modules.map((m) => pub(`export_controls/${m.file}`));
const doc = { ...manifest, modules: manifest.modules.map((m, i) => ({ ...m, ...modules[i], controls: undefined })), controls: modules.flatMap((m) => m.controls) };
const source = fs.readFileSync(path.join(root, 'New for anti/export-controls.js'), 'utf8');

function harness({ sanctionsInput = sanc, docInput = doc } = {}) {
    const window = {};
    const code = source.replace('    window.ExportControls = {', `
    usTariffs = tariffs; sanctions = sanctionsInput; doc = docInput;
    window.t = { ui, usToggleHtml, usTariffSectionHtml, usSanctionsOverviewHtml, renderCountryPanel, onPanelClick, renderPanel };
    window.ExportControls = {`);
    class Element {
        constructor(attrs) { this.attrs = attrs; }
        closest(sel) { return sel.startsWith('[') && Object.hasOwn(this.attrs, sel.slice(1, -1)) ? this : null; }
        getAttribute(a) { return this.attrs[a] ?? null; }
        matches() { return false; }
    }
    vm.runInNewContext(code, { window, tariffs, sanctionsInput, docInput, console, Intl, URL, Element, CSS: { escape: (s) => s } });
    const h = window.t;
    h.Element = Element;
    h.ui.panel = { innerHTML: '', scrollTop: 0 };
    h.click = (attrs) => h.onPanelClick({ target: new Element(attrs) });
    return h;
}
const buttons = (html, attr) => [...html.matchAll(new RegExp(`${attr}="([^"]+)"[^>]*>([^<]*(?:<span>[^<]*</span>)?)`, 'g'))].map((m) => [m[1], m[2].replace(/<[^>]+>/g, '').trim()]);

test('US panel has three toggles in order: 관세 정책, 제재·제한, 수출통제·최근 공고', () => {
    const h = harness();
    const html = h.usToggleHtml();
    assert.deepEqual(buttons(html, 'data-ec-usview').map(([k]) => k), ['tariffs', 'sanctions', 'controls']);
    const labels = buttons(html, 'data-ec-usview').map(([, l]) => l);
    assert.match(labels[0], /^관세 정책/);
    assert.match(labels[1], /^제재·제한/);
    assert.match(labels[2], /^수출통제·최근 공고/);
    assert.match(html, /aria-pressed="true"[^>]*>관세 정책/); // tariffs is the default view
});

test('US panel toggle switches the whole view; unknown values are ignored', () => {
    const h = harness();
    h.ui.iso = 'USA';
    h.click({ 'data-ec-usview': 'sanctions' });
    assert.equal(h.ui.usView, 'sanctions');
    assert.match(h.ui.panel.innerHTML, /미국 제재·거래 제한/);
    assert.doesNotMatch(h.ui.panel.innerHTML, /국가별 미국 통상 조치/); // tariff section is gone
    h.click({ 'data-ec-usview': 'bogus' });
    assert.equal(h.ui.usView, 'sanctions');
    h.click({ 'data-ec-usview': 'controls' });
    assert.doesNotMatch(h.ui.panel.innerHTML, /미국 제재·거래 제한|국가별 미국 통상 조치/);
    h.click({ 'data-ec-usview': 'tariffs' });
    assert.match(h.ui.panel.innerHTML, /data-ec-tariffview/);
});

test('US sanctions overview links the four countries to their sanctions view and states its limits', () => {
    const h = harness();
    const html = h.usSanctionsOverviewHtml();
    for (const iso of ['RUS', 'CHN', 'KOR', 'JPN']) assert.match(html, new RegExp(`data-ec-iso="${iso}" data-ec-cview="sanctions"`));
    assert.match(html, /4개국 시범/);
    assert.match(html, /조회되지 않아도 ‘제재 없음’으로 판정하지 않습니다/);
    assert.match(html, /SDN · 자산동결/);
    // clicking a card opens that country already on its sanctions view
    h.ui.iso = 'USA';
    h.click({ 'data-ec-iso': 'RUS', 'data-ec-cview': 'sanctions' });
    assert.equal(h.ui.iso, 'RUS');
    assert.equal(h.ui.countryViews.RUS, 'sanctions');
    assert.match(h.ui.panel.innerHTML, /uss-tabs/);
});

test('US sanctions overview warns instead of concluding anything when the snapshot failed', () => {
    for (const bad of [{ error: true }, { countries: { RUS: {} } }]) {
        assert.match(harness({ sanctionsInput: bad }).usSanctionsOverviewHtml(), /불러오지 못/);
    }
});

test('tariff sub-toggle: 국가별 | 시행 제도 | 가능 제도 | 완료 제도, with matching counts', () => {
    const h = harness();
    const html = h.usTariffSectionHtml();
    const b = buttons(html, 'data-ec-tariffview');
    assert.deepEqual(b.map(([k]) => k), ['partners', 'live', 'possible', 'done']);
    assert.deepEqual(b.map(([, l]) => l.replace(/\s*\d+$/, '')), ['국가별', '시행 제도', '가능 제도', '완료 제도']);
    // toggle sits right under the 트럼프 2기 title, above the lead text
    assert.ok(html.indexOf('ec-sect') < html.indexOf('ust-subtoggle'));
    assert.ok(html.indexOf('ust-subtoggle') < html.indexOf('ust-lead'));
    const n = Object.fromEntries(b.map(([k, l]) => [k, Number(l.match(/(\d+)$/)[1])]));
    assert.equal(n.partners, Object.keys(tariffs.partners).length);
    assert.equal(n.possible, tariffs.measures.filter((m) => !['active', 'truce', 'expired', 'struck_down', 'ended'].includes(m.status) ||
        (['active', 'truce'].includes(m.status) && m.started > tariffs.as_of)).length + tariffs.legal_tools.length);
});

test('each tariff view shows only its own content', () => {
    const h = harness();
    const inv = tariffs.measures.find((m) => m.id === 'sec301-vietnam-ip-investigation');
    const ended = tariffs.measures.find((m) => m.how_ended_ko);
    const only = (view) => { h.ui.tariffView = view; return h.usTariffSectionHtml(); };
    const partners = only('partners');
    assert.match(partners, /data-ec-iso="VNM"/);
    assert.doesNotMatch(partners, /시행 중인 제도|가능 제도 — |완료 제도 — /);
    const live = only('live');
    assert.match(live, /시행 중인 제도/);
    assert.doesNotMatch(live, /data-ec-iso="VNM"/);
    assert.ok(!live.includes(inv.name_ko));
    const possible = only('possible');
    assert.ok(possible.includes(inv.name_ko)); // 조사 중 lives here
    assert.match(possible, /<details class="ust-tools" open>/); // conditional legal tools, expanded
    assert.match(possible, /발동을 예고하거나 확률을 말하는 것이 아닙니다/);
    assert.ok(!possible.includes('시행 중인 제도'));
    const done = only('done');
    assert.ok(done.includes(ended.name_ko) && done.includes('어떻게 끝났나'));
    assert.ok(!done.includes(inv.name_ko));
    h.ui.tariffView = 'nonsense';
    assert.match(h.usTariffSectionHtml(), /data-ec-iso="VNM"/); // falls back to 국가별
});

test('clicking the sub-toggle re-renders in place and keeps the scroll position', () => {
    const h = harness();
    h.ui.iso = 'USA';
    h.ui.panel.scrollTop = 120;
    h.click({ 'data-ec-tariffview': 'possible' });
    assert.equal(h.ui.tariffView, 'possible');
    assert.equal(h.ui.panel.scrollTop, 120);
    assert.match(h.ui.panel.innerHTML, /data-ec-tariffview="possible"\s+aria-pressed="true"/);
    h.click({ 'data-ec-tariffview': 'bogus' });
    assert.equal(h.ui.tariffView, 'possible');
});

test('RUS/CHN/KOR/JPN get 수출 통제 | 미국 對○ 제재 and each shows alone', () => {
    const h = harness();
    for (const [iso, short] of [['RUS', '러'], ['CHN', '중'], ['KOR', '한'], ['JPN', '일']]) {
        h.ui.countryViews = {};
        h.renderCountryPanel(iso);
        const html = h.ui.panel.innerHTML;
        const b = buttons(html, 'data-ec-cview');
        assert.deepEqual(b.map(([k]) => k), ['controls', 'sanctions'], iso);
        assert.match(b[0][1], /^수출 통제/);
        assert.ok(b[1][1].startsWith(`미국 對${short} 제재`), `${iso}: ${b[1][1]}`);
        // exactly one of the two bodies is rendered
        assert.equal(/class="uss-section"/.test(html) && /class="ec-items"/.test(html), false, iso);
    }
});

test('Russia opens on 수출 통제; switching shows sanctions only and back again', () => {
    const h = harness();
    h.ui.iso = 'RUS';
    h.renderCountryPanel('RUS');
    assert.match(h.ui.panel.innerHTML, /class="ec-items"/); // curated control rows
    assert.doesNotMatch(h.ui.panel.innerHTML, /class="uss-section"/);
    h.click({ 'data-ec-cview': 'sanctions' });
    assert.equal(h.ui.countryViews.RUS, 'sanctions');
    assert.match(h.ui.panel.innerHTML, /class="uss-section"/);
    assert.doesNotMatch(h.ui.panel.innerHTML, /class="ec-items"|규제 기관이 낸 공고|을\(를\) 겨냥한 공고/);
    h.click({ 'data-ec-cview': 'controls' });
    assert.match(h.ui.panel.innerHTML, /class="ec-items"/);
    assert.doesNotMatch(h.ui.panel.innerHTML, /class="uss-section"/);
    h.click({ 'data-ec-cview': 'bogus' });
    assert.equal(h.ui.countryViews.RUS, 'controls');
});

test('each country keeps its own choice, sanctions sub-tabs still work inside the sanctions view', () => {
    const h = harness();
    h.ui.iso = 'RUS'; h.renderCountryPanel('RUS'); h.click({ 'data-ec-cview': 'sanctions' });
    h.click({ 'data-ec-sanctions-view': 'companies' });
    assert.match(h.ui.panel.innerHTML, /1–5 \/ 10/);
    h.ui.iso = 'CHN'; h.renderCountryPanel('CHN');
    assert.equal(h.ui.countryViews.CHN, undefined);
    assert.match(h.ui.panel.innerHTML, /data-ec-cview="controls"\s+aria-pressed="true"/);
    assert.equal(h.ui.countryViews.RUS, 'sanctions');
});

test('countries without sanctions data keep the old layout, no toggle', () => {
    const h = harness();
    for (const iso of ['VNM', 'MEX', 'DEU']) {
        h.renderCountryPanel(iso);
        assert.doesNotMatch(h.ui.panel.innerHTML, /data-ec-cview/, iso);
    }
});

test('if the sanctions snapshot failed, no toggle is offered and the failure message stays visible', () => {
    const h = harness({ sanctionsInput: { error: true } });
    h.renderCountryPanel('RUS');
    assert.doesNotMatch(h.ui.panel.innerHTML, /data-ec-cview/);
    assert.match(h.ui.panel.innerHTML, /불러오지 못/);
});

test('a country with sanctions data but no export-control rows opens on sanctions and says so on the other tab', () => {
    const h = harness({ docInput: { ...doc, controls: doc.controls.filter((c) => c.iso !== 'JPN') } });
    h.renderCountryPanel('JPN');
    assert.match(h.ui.panel.innerHTML, /class="uss-section"/);
    h.ui.countryViews.JPN = 'controls';
    h.renderCountryPanel('JPN');
    assert.match(h.ui.panel.innerHTML, /정리된 수출통제 조치도, 최근 공고도 없습니다/);
});

test('opening a country fresh starts on 수출 통제; only a card that names a view opens on sanctions', () => {
    const h = harness();
    h.ui.iso = 'USA';
    h.click({ 'data-ec-iso': 'RUS', 'data-ec-cview': 'sanctions' });
    assert.equal(h.ui.countryViews.RUS, 'sanctions');
    assert.match(h.ui.panel.innerHTML, /class="uss-section"/);
    // back to the list, then the plain country button (no view named) -> default view again
    h.click({ 'data-ec-back': '' });
    h.click({ 'data-ec-iso': 'RUS' });
    assert.equal(h.ui.countryViews.RUS, undefined);
    assert.match(h.ui.panel.innerHTML, /class="ec-items"/);
    assert.doesNotMatch(h.ui.panel.innerHTML, /class="uss-section"/);
});

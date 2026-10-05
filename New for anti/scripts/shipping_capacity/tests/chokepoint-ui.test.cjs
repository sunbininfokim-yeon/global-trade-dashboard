// Presentation regression tests. Public JSON is the source of every displayed
// production value; synthetic cases below only exercise missing-data handling.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const assetRoot = path.resolve(__dirname, '../../..');
const source = fs.readFileSync(path.join(assetRoot, 'shipping.js'), 'utf8');
const snapshot = JSON.parse(fs.readFileSync(path.join(assetRoot, 'public/data/shipping_capacity_v1.json'), 'utf8'));
let fetches = 0;
const context = vm.createContext({
  window: {},
  document: { querySelector: () => null, addEventListener() {} },
  console,
  fetch() { fetches++; throw new Error('Unit render must not fetch a scenario grid or external data'); }
});
const marker = 'window.ShippingDashboard = { render, unmount, loadData: loadShippingData };';
assert.ok(source.includes(marker));
vm.runInContext(source.replace(marker, `${marker}
  window.__chokeTest = {normalizeSnapshot, latestOfficialCargo, officialVolumeChartData, publishedOfficialRows, publicationPeriod, renderChokepoints, renderObservedTypeComparison, scenarioPresetControls, trafficSummaryOf, renderTrafficComparisons, renderTrafficComposition};`), context);
const api = context.window.__chokeTest;
const normalized = api.normalizeSnapshot(snapshot);
const point = id => normalized.ui.chokepoints.find(row => row.id === id);
const rows = id => api.publishedOfficialRows(point(id).officialCargo);
const plain = value => JSON.parse(JSON.stringify(value));
const renderList = () => {
  const root = { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
  api.renderChokepoints(normalized, root);
  return root.innerHTML;
};
const card = (html, id) => html.match(new RegExp(`<article[^>]*data-chokepoint="${id}"[\\s\\S]*?<\\/article>`))[0];

test('Hormuz main value is the latest official oil average, not a big -99% headline', () => {
  const html = card(renderList(), 'hormuz');
  const latest = api.latestOfficialCargo(point('hormuz'));
  assert.equal(latest.publisher, 'IEA');
  assert.equal(latest.value, 7600000);
  assert.match(html, /760만 배럴\/일/);
  assert.match(html, /2026-08/);
  assert.match(html, /전체 AIS 포착량 변화/);
  assert.match(html, /전년 같은 요일 7일/);
  assert.doesNotMatch(html, /<strong class="shipping-change[^>]*>-99%/);
});

test('Suez headline is all-ship AIS tonnes; SUMED oil is only a separate reference', () => {
  const html = card(renderList(), 'suez');
  assert.match(html, /<strong class="shipping-change[^>]*>1\.53M t\/일/);
  assert.doesNotMatch(html, /<strong class="shipping-change[^>]*>580만 배럴\/일/);
  assert.match(html, /석유 참고 580만 배럴\/일/);
  assert.match(html, /SUMED 포함/);
  assert.ok(html.indexOf('유조선') < html.indexOf('벌크선'));
  assert.ok(html.indexOf('벌크선') < html.indexOf('컨테이너선'));
  assert.match(html, /41\.8%/);
  assert.match(html, /29\.6%/);
  assert.match(html, /27\.0%/);
  assert.doesNotMatch(html, /TEU/);
});

test('small comparisons render engine values without treating prior 28 days as a month', () => {
  const summary = api.trafficSummaryOf(point('suez'));
  const html = api.renderTrafficComparisons(summary);
  assert.match(html, /전주 <b>-6\.8%/);
  assert.match(html, /전월 <b>\+5\.6%/);
  assert.match(html, /전년 <b>\+0\.7%/);
  assert.match(html, /2026-08-21~2026-08-27/);
  const mutated = plain(summary);
  mutated.comparisons.week.change_pct = 123.4;
  assert.match(api.renderTrafficComparisons(mutated), /전주 <b>\+123\.4%/);
  assert.match(renderList(), /전월은 달 전체 평균이 아닙니다/);
});

test('unavailable comparisons and weights do not become synthetic zero percentages', () => {
  const summary = plain(api.trafficSummaryOf(point('suez')));
  summary.comparisons.week.status = 'zero_baseline';
  summary.comparisons.week.change_pct = null;
  assert.match(api.renderTrafficComparisons(summary), /전주 <b>—/);
  summary.ship_types.forEach(row => { row.share_pct = null; });
  summary.remaining_types_share_pct = null;
  assert.match(api.renderTrafficComposition(summary), /선종 비중 미산출/);
  assert.doesNotMatch(api.renderTrafficComposition(summary), /width:|0\.0%/);
  assert.equal(api.trafficSummaryOf({live: {}}), null);
});

test('list is compact and the AIS overview is initially closed', () => {
  const html = renderList();
  assert.match(html, /<details id="shipping-ais-overview"/);
  assert.doesNotMatch(html, /<details id="shipping-ais-overview"[^>]*\bopen\b/);
  assert.doesNotMatch(html, /최대 위축 통로|위험 · 전년 대비|정상 범위/);
  assert.match(html, /실제 석유 감소율·봉쇄율이 아닙니다/);
  assert.equal(fetches, 0);
});

test('official chart uses published period values and separates EIA from IEA', () => {
  const config = api.officialVolumeChartData(rows('hormuz'), 'total_oil');
  const eia = config.datasets.find(row => row.label.startsWith('EIA'));
  const iea = config.datasets.find(row => row.label.startsWith('IEA'));
  assert.equal(config.unit, 'barrels_per_day');
  assert.deepEqual(plain(eia.data), [2090, 2100, 2130, 2160, 1490, 490, null]);
  assert.deepEqual(plain(iea.data), [null, null, null, null, null, null, 760]);
  assert.equal(iea.showLine, false);
  assert.equal(eia.tension, 0);
  assert.equal(eia.spanGaps, false);
  assert.equal(config.labels.length, 7); // Not a fabricated 500-day official series.
});

test('crude selection cannot reuse the IEA total-oil reference', () => {
  const latest = api.latestOfficialCargo(point('hormuz'), 'crude_condensate');
  assert.equal(latest.publisher, 'EIA');
  assert.equal(latest.value, 3700000);
  const config = api.officialVolumeChartData(rows('hormuz'), 'crude_condensate');
  assert.equal(config.datasets.length, 1);
  assert.deepEqual(plain(config.datasets[0].data), [1480, 1490, 1500, 1590, 1090, 370]);
});

test('LNG retains its native unit and is never put on the oil axis', () => {
  const config = api.officialVolumeChartData(rows('hormuz'), 'lng');
  assert.equal(config.unit, 'billion_cubic_feet_per_day');
  assert.deepEqual(plain(config.datasets[0].data), [11.7, 11, 10.9, 10.5, 7.4, 0.8]);
});

test('missing publication is a gap, not zero or an interpolated daily value', () => {
  const input = [{publisher: 'EIA', frequency: 'quarterly', geography_scope: 'strait_of_hormuz', cargo_category: 'total_oil', unit: 'barrels_per_day', period: '1Q26', period_start: '2026-01-01', value: null}];
  const config = api.officialVolumeChartData(input, 'total_oil');
  assert.deepEqual(plain(config.datasets[0].data), [null]);
  assert.equal(config.datasets[0].showLine, false);
});

test('geography and publication frequency are separate dataset identities', () => {
  const base = rows('hormuz').find(row => row.cargo_category === 'total_oil');
  const config = api.officialVolumeChartData([
    base,
    {...base, geography_scope: 'outside_hormuz'},
    {...base, frequency: 'monthly'}
  ], 'total_oil');
  assert.equal(config.datasets.length, 3);
});

test('Suez main card explicitly includes SUMED; tanker default matches Hormuz', () => {
  assert.match(card(renderList(), 'suez'), /SUMED 포함/);
  const comparison = api.renderObservedTypeComparison(point('hormuz'));
  assert.match(comparison, /data-chokepoint-metric="tanker"[^>]*aria-selected="true"/);
  assert.match(comparison, /data-chokepoint-metric="all"[^>]*aria-selected="false"/);
});

test('UI does not mutate the engine snapshot or send it to an AI service', () => {
  const before = JSON.stringify(snapshot);
  renderList();
  api.officialVolumeChartData(rows('hormuz'), 'total_oil');
  assert.equal(JSON.stringify(snapshot), before);
  assert.equal(fetches, 0);
});

test('detail uses four separate panes and keeps research behind a native disclosure', () => {
  assert.match(source, /\['official', '공식 물량'\].*\['ais', 'AIS 통항'\].*\['conditions', '통항 여건'\].*\['simulator', '시뮬레이션'\]/);
  assert.match(source, /<details id="shipping-choke-appendix"/);
  assert.match(source, /await loadScenarioGrid\(data\)/);
  assert.match(source, /if \(activeTab !== key\)/);
  assert.match(source, /!pane\.isConnected/);
});

test('simulator inputs match the selected preset rather than using Hormuz 80% everywhere', () => {
  const grid = JSON.parse(fs.readFileSync(path.join(assetRoot, 'public/data/shipping_capacity_scenario_grid_v1.json'), 'utf8')).ui_scenario_grid;
  for (const id of ['suez_50pct_28d', 'suez_100pct_28d', 'hormuz_effective_80pct_28d']) {
    const preset = normalized.ui.baseScenarios.find(row => row.id === id);
    assert.ok(preset, id);
    const controls = api.scenarioPresetControls(preset, grid.closure_pct_options, grid.duration_day_options);
    assert.equal(controls.closure, Math.round(preset.closure_fraction * 100));
    assert.equal(controls.duration, preset.duration_days);
  }
});

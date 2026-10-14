const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../../New for anti/policy.js'), 'utf8');

function harness(pathname = '/policy/us/simulator', failOverview = false) {
  const calls = [], listeners = new Map(); let mounts = 0, cleanups = 0;
  const fakeSimulator = { markup: () => '<div>COUNTRY SIMULATOR</div>', mount: () => { mounts++; return () => { cleanups++; }; } };
  const surface = { dataset: {}, classList: { add() {}, remove() {} }, innerHTML: '',
    querySelector: () => ({}), addEventListener: (type, fn) => listeners.set(type, fn), removeEventListener: type => listeners.delete(type) };
  const window = { location: { pathname }, history: { pushState(_s, _t, url) { window.location.pathname = url; }, replaceState(_s, _t, url) { window.location.pathname = url; } } };
  const code = source.replace('  window.USPolicy = {', `
    simulatorPromise = Promise.resolve(fakeSimulator);
    window.navTest = {go, parseLeafFromPath, pathForLeaf};
    window.USPolicy = {`);
  vm.runInNewContext(code, { window, fakeSimulator, URLSearchParams, clearTimeout, console: { error() {} }, fetch: async url => {
    calls.push(url);
    return { ok: !failOverview, status: failOverview ? 503 : 200, json: async () => failOverview ? { error: 'DB unavailable' } :
      { congress_overview: { committees: [] }, executive_overview: { agencies: [] }, policy_areas: [], cfr_titles: [] } };
  } });
  return { window, surface, calls, listeners, get mounts() { return mounts; }, get cleanups() { return cleanups; } };
}
test('simulator direct link/reload mounts without a DB request and is cleaned up on exit', async () => {
  const h = harness(); await h.window.USPolicy.render('us-policy-hub', h.surface);
  assert.match(h.surface.innerHTML, /의회/); assert.match(h.surface.innerHTML, /행정부/); assert.match(h.surface.innerHTML, /COUNTRY SIMULATOR/);
  assert.equal(h.calls.length, 0); assert.equal(h.mounts, 1);
  assert.equal(h.window.navTest.pathForLeaf('simulator'), '/policy/us/simulator');
  assert.equal(h.window.navTest.parseLeafFromPath('/policy/us/simulator').view, 'simulator');
  h.window.USPolicy.unmount(h.surface); assert.equal(h.cleanups, 1); assert.equal(h.listeners.size, 0);
});
test('switching from simulator to Congress lazily loads overview and retains navigation', async () => {
  const h = harness(); await h.window.USPolicy.render('us-policy-hub', h.surface);
  await h.window.navTest.go('congress');
  assert.deepEqual(h.calls, ['/api/us/overview']); assert.equal(h.window.location.pathname, '/policy/us');
  assert.equal(h.cleanups, 1); assert.match(h.surface.innerHTML, /CRS 정책분야/);
  await h.window.navTest.go('simulator'); assert.equal(h.mounts, 2); assert.equal(h.calls.length, 1);
});
test('DB outage retains branch buttons; calculator can still be entered', async () => {
  const h = harness('/policy/us', true); await h.window.USPolicy.render('us-policy-hub', h.surface);
  assert.match(h.surface.innerHTML, /정책 데이터를 불러오지 못했습니다/);
  assert.match(h.surface.innerHTML, /data-view="simulator"/); assert.ok(h.listeners.has('click'));
  await h.window.navTest.go('simulator'); assert.match(h.surface.innerHTML, /COUNTRY SIMULATOR/); assert.equal(h.calls.length, 1);
});
test('a slow navigation cannot repaint after a later navigation', async () => {
  const h = harness(); await h.window.USPolicy.render('us-policy-hub', h.surface);
  const congress = h.window.navTest.go('congress');
  const simulator = h.window.navTest.go('simulator');
  await Promise.all([congress, simulator]);
  assert.match(h.surface.innerHTML, /COUNTRY SIMULATOR/); assert.equal(h.window.location.pathname, '/policy/us/simulator');
});

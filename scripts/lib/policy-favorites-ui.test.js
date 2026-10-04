'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const evidence = require('../../New for anti/policy-evidence.js');
const fixture = require('../fixtures/clarity-119-hr-3633.json');
const source = file => fs.readFileSync(require.resolve(`../../New for anti/${file}`), 'utf8');
function policy(Auth = {}) {
  const alerts = [];
  const context = vm.createContext({ window: { PolicyEvidence: evidence, Auth, alert: msg => alerts.push(msg) }, console: { error() {} }, URLSearchParams });
  vm.runInContext(source('policy.js').replace('window.USPolicy = {', 'window.USPolicy = { stageRail, toggleFavorite,'), context);
  return { ...context.window.USPolicy, alerts };
}
test('Clarity shows a red Senate floor marker with procedural-defeat wording; no terminal rejection', () => {
  const ui = policy();
  const html = ui.stageRail(fixture);
  assert.equal((html.match(/class="policy-stage-step is-failed"/g) || []).length, 1);
  assert.match(html, /class="policy-stage-step is-failed" title="상원 본회의 통과/);
  assert.match(html, /심의 개시 토론종결 부결/);
  assert.match(html, /법안 최종 통과 표결의 부결과는 다릅니다/);
  assert.match(ui.favoriteBillCardHtml(fixture), /상원 심의 개시 토론종결 부결/);
  assert.equal(evidence.buildLifecycle(fixture).current.stage, 'second_chamber');
});
test('successful later Senate passage removes the red marker; House-origin and Senate-origin failures target their own chamber', () => {
  const success = structuredClone(fixture);
  success.bill_votes.push({ chamber: 'senate', question: 'On Passage', result: 'Passed', vote_date: '2026-09-20' });
  assert.doesNotMatch(policy().stageRail(success), /policy-stage-step is-failed/);
  const failed = { bill_type: 's', bill_votes: [{ chamber: 'house', question: 'On Passage', result: 'Failed', vote_date: '2026-09-20' }] };
  const setback = evidence.floorSetback(evidence.buildLifecycle(failed));
  assert.equal(setback.step_id, 'house_passage');
  assert.equal(setback.label, '본회의 통과 표결 부결');
  assert.doesNotMatch(setback.note, /절차/);
});
test('favorite write errors are visible, never paint success, and release the button for retry', async () => {
  const ui = policy({ currentUser: () => ({ id: 'test-user' }), addFavorite: async () => { throw Error('RLS denied'); } });
  const button = { dataset: { favKind: 'bill', favId: '119-hr-3633' }, disabled: false, classList: { toggle() { assert.fail('must not paint success'); } } };
  await ui.toggleFavorite(button);
  assert.equal(button.disabled, false);
  assert.equal(ui.alerts.length, 1);
  assert.match(ui.alerts[0], /저장하지 못했습니다/);
});
test('Auth listeners that fetch favorites run outside the auth callback; upsert uses the composite key', async () => {
  let callback, inside = false, queriedInside = false, options;
  const deferred = [];
  const client = {
    auth: { onAuthStateChange(fn) { callback = fn; }, getSession: async () => ({ data: { session: null } }) },
    from(table) {
      assert.equal(table, 'user_favorites');
      queriedInside ||= inside;
      return { select() { return { order: async () => ({ data: [], error: null }) }; }, upsert: async (_row, opts) => { options = opts; return { error: null }; } };
    },
  };
  const context = vm.createContext({ window: { supabase: { createClient: () => client } }, document: { getElementById: () => null }, setTimeout: fn => deferred.push(fn) });
  vm.runInContext(source('auth.js'), context);
  await Promise.resolve();
  const auth = context.window.Auth;
  let listenerCalled = false;
  auth.onChange(() => { listenerCalled = true; return auth.listFavorites(); });
  inside = true; callback('SIGNED_IN', { user: { id: 'test-user' } }); inside = false;
  assert.equal(listenerCalled, false);
  deferred.splice(0).forEach(fn => fn());
  assert.equal(listenerCalled, true);
  assert.equal(queriedInside, false);
  await auth.addFavorite('bill', '119-hr-3633', 'Clarity');
  assert.equal(options.onConflict, 'user_id,item_kind,item_id');
});
function mypage(Auth, loadBillById) {
  const context = vm.createContext({ window: { Auth, USPolicy: { loadBillById } }, CSS: { escape: s => s }, console });
  vm.runInContext(source('mypage.js').replace('window.MyPage = { render, unmount }', 'window.MyPage = { render, unmount, renderFavoriteBillCards }'), context);
  return context.window.MyPage;
}
test('saved title stays visible while details load or fail; stale request cannot overwrite an unmounted page', async () => {
  let reject;
  const ui = mypage({}, () => new Promise((_resolve, fail) => { reject = fail; }));
  const card = { innerHTML: '' };
  const container = { innerHTML: '', querySelector: () => card, addEventListener() {} };
  ui.renderFavoriteBillCards(container, [{ item_id: '119-hr-3633', title: 'Clarity <test>' }], 0);
  assert.match(container.innerHTML, /Clarity &lt;test&gt;/);
  assert.match(container.innerHTML, /저장됨/);
  reject(Error('network failed')); await new Promise(setImmediate);
  assert.match(card.innerHTML, /즐겨찾기는 저장돼 있습니다/);
  ui.renderFavoriteBillCards(container, [{ item_id: '119-hr-3633', title: 'Clarity' }], 0);
  ui.unmount({ innerHTML: '' });
  card.innerHTML = 'new view';
  reject(Error('old request')); await new Promise(setImmediate);
  assert.equal(card.innerHTML, 'new view');
});
test('My Page opened before session recovery subscribes and refreshes after login', async () => {
  let user = null, listener, reads = 0;
  const ui = mypage({ currentUser: () => user, onChange: fn => { listener = fn; }, listFavorites: async () => { reads++; return []; } });
  const element = () => ({ innerHTML: '', textContent: '', classList: { remove() {}, toggle() {} }, addEventListener() {} });
  const identity = element(), panel = element(), login = element();
  const surface = { ...element(), querySelector: selector => selector === '#mypage-identity' ? identity : selector === '#mypage-login-btn' ? login : panel, querySelectorAll: () => [] };
  ui.render('mypage', surface);
  assert.equal(typeof listener, 'function');
  user = { email: 'test@example.com' }; listener(); await Promise.resolve();
  assert.equal(identity.textContent, 'test@example.com');
  assert.equal(reads, 1);
});

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const PolicyEvidence = require('../../New for anti/policy-evidence.js');
const fixture = require('../fixtures/clarity-119-hr-3633.json');
const source = fs.readFileSync(require.resolve('../../_worker.js'), 'utf8').replace(/^import PolicyEvidence[^\n]*\n/, '').replace('export default {', 'globalThis.worker = {');
function worker(fetch) {
  const context = vm.createContext({ PolicyEvidence, fetch, Request, Response, URL, URLSearchParams, Headers, console, setTimeout, clearTimeout });
  vm.runInContext(source, context);
  return context.worker;
}
const env = { SUPABASE_URL: 'https://example.supabase.co', SUPABASE_SERVICE_ROLE_KEY: 'sb_secret_test' };
test('exact number route bypasses embedding provider, sorts Congress and preserves result contract', async () => {
  let count = 0;
  const w = worker(async (url, options) => {
    count++;
    const u = new URL(url);
    assert.equal(u.pathname, '/rest/v1/bills');
    assert.equal(u.searchParams.get('bill_type'), 'eq.hr');
    assert.equal(u.searchParams.get('bill_number'), 'eq.3633');
    assert.equal(u.searchParams.get('order'), 'congress_number.desc');
    assert.equal(options.headers.Authorization, undefined);
    return Response.json([fixture]);
  });
  const response = await w.fetch(new Request('https://test/api/us/search?q=Hr%203633'), env, {});
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.items[0].id, '119-hr-3633');
  assert.equal(data.items[0].title, 'Digital Asset Market Clarity Act');
  assert.equal(data.search_mode, 'bill_number');
  assert.equal(count, 1);
});
test('explicit Congress scopes lookup and no exact hit never returns an unrelated semantic bill', async () => {
  const w = worker(async url => {
    assert.equal(new URL(url).searchParams.get('congress_number'), 'eq.119');
    return Response.json([]);
  });
  const response = await w.fetch(new Request('https://test/api/us/search?q=119-hr-99999'), env, {});
  assert.deepEqual((await response.json()).items, []);
});
test('bill detail sends lifecycle, committee dates and sources, without raw payload or embedding', async () => {
  const w = worker(async url => Response.json(new URL(url).pathname.endsWith('/bill_relations') ? [] : [{ ...structuredClone(fixture), embedding: [1], raw_source: { private: 'hidden' } }]));
  const response = await w.fetch(new Request('https://test/api/us/congress/bills/119-hr-3633'), env, {});
  assert.equal(response.status, 200);
  const b = await response.json();
  assert.equal(b.lifecycle.current.step_id, 'senate_reported');
  assert.ok(b.committees[0].activities.length);
  assert.equal(b.embedding, undefined);
  assert.equal(b.raw_source, undefined);
  assert.equal(b.bill_committees, undefined);
});
test('semantic search keeps grouped bill metadata and regulation links after exact-search integration', async () => {
  const w = worker(async (url, options) => {
    const u = new URL(url);
    if (u.hostname === 'embedding.test') return Response.json({ values: [1, ...Array(1535).fill(0)] });
    if (u.pathname.includes('/rpc/')) {
      const body = JSON.parse(options.body);
      assert.equal(body.p_embedding_model, 'gemini-embedding-001');
      return Response.json([{ source_type: 'bill', source_id: fixture.bill_id, title: fixture.title, similarity_score: 0.9 }, { source_type: 'regulation', source_id: 'reg-test', title: 'Test regulation', similarity_score: 0.8 }]);
    }
    if (u.pathname.endsWith('/regulations')) return Response.json([{ regulation_id: 'reg-test', federal_register_url: 'https://www.federalregister.gov/test' }]);
    if (u.pathname.endsWith('/bills')) return Response.json([{ ...fixture, law_type: 'public', law_number: '119-1', current_stage: 'enacted' }]);
    throw Error('Unexpected path');
  });
  const response = await w.fetch(new Request('https://test/api/us/search?q=export%20controls'), { ...env, POLICY_EMBEDDING_PROXY_URL: 'https://embedding.test', POLICY_EMBEDDING_PROXY_TOKEN: 'test' }, {});
  assert.equal(response.status, 200);
  const b = await response.json();
  assert.equal(b.items[0].current_stage, 'enacted');
  assert.equal(b.items[0].law_number, '119-1');
  assert.equal(b.items[1].source_url, 'https://www.federalregister.gov/test');
});

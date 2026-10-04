'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const PolicySearchTerms = require('./policy-search-terms.js');
const PolicyEvidence = require('../../New for anti/policy-evidence.js');
const fixture = require('../fixtures/clarity-119-hr-3633.json');
const source = fs.readFileSync(require.resolve('../../_worker.js'), 'utf8').replace(/^import [^\n]*\n/gm, '').replace('export default {', 'globalThis.worker = {');
function worker(fetch) {
  const context = vm.createContext({ PolicyEvidence, PolicySearchTerms, fetch, Request, Response, URL, URLSearchParams, Headers, console, setTimeout, clearTimeout });
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
test('generic titles and short titles survive provider failure; unrelated substring titles are excluded',async()=>{
 const w=worker(async url=>{
  const u=new URL(url);
  if(u.hostname==='embedding.test')return new Response('unavailable',{status:503});
  if(!u.pathname.endsWith('/bills'))return Response.json([]);
  return Response.json([
   {bill_id:'119-s-100',title:'GENIUS Act',summary:'Stablecoin rules',congress_number:119},
   {bill_id:'119-hr-101',title:'Payment Stablecoin Framework',summary:'This bill is known as the GENIUS Act.',congress_number:119},
   {bill_id:'119-hr-102',title:'STABLE GENIUS Act',summary:'Tax matters'},
   {bill_id:'119-hr-103',title:'STABLEGENIUS Act',summary:'Schools'},
   {bill_id:'119-hr-104',title:'Digital Payment Market Framework',summary:'<p><strong>Digital Payment Market Framework or the GENIUS Act of 2026</strong></p><p>Payment rules.</p>'},
  ]);
 });
 const r=await w.fetch(new Request('https://test/api/us/search?q=GENIUS%20Act'),{...env,POLICY_EMBEDDING_PROXY_URL:'https://embedding.test',POLICY_EMBEDDING_PROXY_TOKEN:'test'},{});
 const data=await r.json();assert.equal(r.status,200);assert.equal(data.semantic_available,false);
 assert.equal(data.items[0].id,'119-s-100');assert.equal(data.items[0].match_type,'exact_title');
 assert.ok(data.items.some(x=>x.id==='119-hr-101'&&x.match_type==='summary_phrase'));
 assert.ok(data.items.some(x=>x.id==='119-hr-104'&&x.relevance_rank===4&&x.match_type==='exact_summary_title'));
 assert.ok(!data.items.some(x=>x.id==='119-hr-103'));
 assert.ok(data.items.every(x=>x.summary===undefined));
});
test('single Korean topics use documented English aliases and include historical public laws',async()=>{
 const w=worker(async url=>{
  const u=new URL(url);assert.ok(!u.searchParams.toString().includes('embedding'));
  if(u.pathname.endsWith('/bills'))return Response.json([{bill_id:'119-s-1',title:'Digital Asset Consumer Protection',summary:'Cryptocurrency trading'}]);
  if(u.pathname.endsWith('/public_laws'))return Response.json([{public_law_id:'118-2',law_title:'Cryptocurrency Reporting Act',enacted_date:'2024-01-01'}]);
  return Response.json([]);
 });
 const r=await w.fetch(new Request('https://test/api/us/search?q='+encodeURIComponent('암호화폐')),env,{});
 const data=await r.json();assert.equal(r.status,200);assert.ok(data.items.some(x=>x.type==='public_law'));assert.ok(data.items.some(x=>x.type==='bill'));
});
test('no lexical evidence during provider outage reports unavailable rather than a false empty result',async()=>{
 const w=worker(async()=>Response.json([]));
 const r=await w.fetch(new Request('https://test/api/us/search?q=unknown'),env,{});
 assert.equal(r.status,503);
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
      return Response.json([{ source_type: 'bill', source_id: fixture.bill_id, title: fixture.title, similarity_score: 0.9 }, { source_type: 'regulation', source_id: 'reg-test', title: 'Test regulation', similarity_score: 0.8 },{source_type:'executive_order',source_id:'12345',title:'Test EO',similarity_score:0.7},{source_type:'public_law',source_id:'PLAW-test',title:'Test law',similarity_score:0.6}]);
    }
    if (u.pathname.endsWith('/regulations')) return Response.json([{ regulation_id: 'reg-test', federal_register_url: 'https://www.federalregister.gov/test',publication_date:'2026-09-01' }]);
    if (u.pathname.endsWith('/executive_orders')) return Response.json([{eo_number:12345,publication_date:'2026-09-02',signed_date:'2026-09-01'}]);
    if (u.pathname.endsWith('/public_laws')) return Response.json([{public_law_id:'PLAW-test',enacted_date:'2026-09-03'}]);
    if (u.pathname.endsWith('/bills')) return Response.json([{ ...fixture, law_type: 'public', law_number: '119-1', current_stage: 'enacted' }]);
    throw Error('Unexpected path');
  });
  const response = await w.fetch(new Request('https://test/api/us/search?q=export%20controls'), { ...env, POLICY_EMBEDDING_PROXY_URL: 'https://embedding.test', POLICY_EMBEDDING_PROXY_TOKEN: 'test' }, {});
  assert.equal(response.status, 200);
  const b = await response.json();
  assert.equal(b.items[0].current_stage, 'enacted');
  assert.equal(b.items[0].law_number, '119-1');
  assert.equal(b.items[1].source_url, 'https://www.federalregister.gov/test');
  assert.equal(b.items[1].publication_date,'2026-09-01');
  assert.equal(b.items[2].publication_date,'2026-09-02');
  assert.equal(b.items[3].enacted_date,'2026-09-03');
});
test('usOverview reads committee_directory and uses canonical_bill_count, not three JEC rows', async () => {
  const paths = [];
  const w = worker(async url => {
    const u = new URL(url);
    paths.push(u.pathname);
    if (u.pathname === '/rest/v1/committee_directory') {
      return Response.json([
        { committee_id: '119-joint-jjec00', name: 'Joint Economic Committee', chamber: 'joint', committee_type: 'joint', official_url: null, jurisdiction_summary: null, display_order: null, canonical_bill_count: 7, source_committee_ids: ['119-joint-jhje00', '119-joint-jjec00', '119-joint-jsec00'] },
        { committee_id: '119-house-hsag00', name: 'Committee on Agriculture', chamber: 'house', committee_type: 'standing', official_url: null, jurisdiction_summary: null, display_order: null, canonical_bill_count: 42, source_committee_ids: ['119-house-hsag00'] },
      ]);
    }
    if (['/rest/v1/agencies', '/rest/v1/policy_areas', '/rest/v1/cfr_titles', '/rest/v1/bills', '/rest/v1/executive_order_agencies', '/rest/v1/regulation_cfr_references', '/rest/v1/committee_agency_jurisdictions'].includes(u.pathname)) return Response.json([]);
    throw new Error(`Unexpected path ${u.pathname}`);
  });
  const response = await w.fetch(new Request('https://test/api/us/overview'), env, {});
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.congress_overview.committees.length, 2, 'exactly one JEC row, not three');
  const jec = body.congress_overview.committees.find(c => c.committee_id === '119-joint-jjec00');
  assert.equal(jec.bill_count, 7, 'bill_count comes from canonical_bill_count');
  assert.ok(!paths.includes('/rest/v1/committees'), 'must not query the raw committees table any more');
  assert.ok(!paths.includes('/rest/v1/bill_committees'), 'must not run the old per-committee bill count aggregation');
});
test('usCommitteeDetail resolves a JEC alias id to its canonical id before querying subcommittees', async () => {
  const w = worker(async url => {
    const u = new URL(url);
    if (u.pathname === '/rest/v1/committee_identity') {
      assert.equal(u.searchParams.get('source_committee_id'), 'eq.119-joint-jhje00');
      return Response.json([{ canonical_committee_id: '119-joint-jjec00' }]);
    }
    if (u.pathname === '/rest/v1/committee_directory') {
      assert.equal(u.searchParams.get('canonical_parent_committee_id'), 'eq.119-joint-jjec00', 'subcommittee lookup must use the canonical id, not the alias requested');
      return Response.json([]);
    }
    throw new Error(`Unexpected path ${u.pathname}`);
  });
  const response = await w.fetch(new Request('https://test/api/us/congress/committees?committee_id=119-joint-jhje00'), env, {});
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.committee_id, '119-joint-jjec00', 'response reports the canonical id');
  assert.equal(body.requested_committee_id, '119-joint-jhje00');
});
test('usBillList filters bills by every JEC source id, not just the requested one', async () => {
  const w = worker(async url => {
    const u = new URL(url);
    if (u.pathname === '/rest/v1/committee_identity') return Response.json([{ canonical_committee_id: '119-joint-jjec00' }]);
    if (u.pathname === '/rest/v1/committee_directory') return Response.json([{ source_committee_ids: ['119-joint-jhje00', '119-joint-jjec00', '119-joint-jsec00'] }]);
    if (u.pathname === '/rest/v1/bills') {
      const filter = u.searchParams.get('bill_committees.committee_id');
      assert.ok(filter, 'bill query must carry a committee_id filter');
      assert.match(filter, /^in\.\(.*jhje00.*jjec00.*jsec00.*\)$/, `expected all three source ids in the filter, got: ${filter}`);
      return Response.json([]);
    }
    throw new Error(`Unexpected path ${u.pathname}`);
  });
  const response = await w.fetch(new Request('https://test/api/us/congress/bills?committee_id=119-joint-jsec00'), env, {});
  assert.equal(response.status, 200);
});

test('condition search includes full and partial matches across types, with no embedding dependency', async()=>{
 const calls=[];
 const w=worker(async url=>{
  const u=new URL(url);calls.push(u);
  assert.ok(u.searchParams.get('and').startsWith('(or('));
  if(u.pathname.endsWith('/bills'))return Response.json([
   {bill_id:'119-hr-1',title:'Nickel batteries',summary:'Export controls apply',current_stage:'introduced'},
   {bill_id:'119-hr-2',title:'Nickel battery production',summary:'Domestic subsidies'},
   {bill_id:'119-hr-3',title:'Unrelated legislation',summary:'Schools'},
  ]);
  if(u.pathname.endsWith('/public_laws'))return Response.json([{public_law_id:'118-1',law_title:'Nickel batteries and export restrictions',govinfo_url:'https://www.govinfo.gov/test'}]);
  return Response.json([]);
 });
 const response=await w.fetch(new Request('https://test/api/us/search?q='+encodeURIComponent('니켈, 수출통제, 배터리')),env,{});
 assert.equal(response.status,200);const data=await response.json();
 assert.equal(data.search_mode,'conditions');assert.equal(data.semantic_available,false);
 assert.deepEqual(data.items.map(i=>i.matched_condition_count),[3,3,2]);
 assert.equal(data.items[2].condition_matches.find(m=>m.term==='수출통제').matched,false);
 assert.ok(data.items.some(i=>i.type==='public_law'));
 assert.equal(calls.length,16);assert.ok(calls.some(u=>u.searchParams.get('and').includes('),or(')));
});
test('too many conditions return an actionable 400 without API calls',async()=>{
 const w=worker(async()=>{throw Error('must not call');});
 const r=await w.fetch(new Request('https://test/api/us/search?q=a,b,c,d,e,f'),env,{});
 assert.equal(r.status,400);assert.match((await r.json()).error,/5개/);
});
test('source failure is not misrepresented as no matches',async()=>{
 const w=worker(async()=>new Response('failed',{status:500}));
 const r=await w.fetch(new Request('https://test/api/us/search?q=nickel,battery'),env,{});
 assert.equal(r.status,503);
});
test('semantic provider failure preserves evidence-based results and marks degraded mode',async()=>{
 const w=worker(async url=>{
  if(new URL(url).hostname==='embedding.test')return new Response('failed',{status:503});
  return Response.json(new URL(url).pathname.endsWith('/bills')?[{bill_id:'119-hr-1',title:'Nickel batteries'}]:[]);
 });
 const r=await w.fetch(new Request('https://test/api/us/search?q=nickel,battery'),{...env,POLICY_EMBEDDING_PROXY_URL:'https://embedding.test',POLICY_EMBEDDING_PROXY_TOKEN:'test'},{});
 const data=await r.json();assert.equal(data.items[0].matched_condition_count,2);assert.equal(data.semantic_available,false);
});

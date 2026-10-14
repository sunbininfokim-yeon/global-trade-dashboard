import test from 'node:test';
import assert from 'node:assert/strict';
import { discoverNotices, queryURL } from '../trade_policy/discover_antidumping_notices.mjs';

const now = () => '2026-10-12T12:00:00.000Z';
const caseId = 'A-580-897';
const catalog = { cases: [{ case_id: caseId, product: 'pipe' }], documents: { '2026-08489': {} } };
const meta = (id = '2026-08489', title = 'Final Results') => ({ document_number: id, title, publication_date: '2026-05-01', docket_ids: [caseId] });
const source = id => `<pre>Federal Register [${caseId}] [FR Doc No: ${id}] verified source</pre>`;
const options = { now, catalog, through: '2026-10-12', minIntervalMs: 0, wait: async () => {} };
const fixtureFetch = (records, text = source) => async url => url.includes('/api/')
  ? Response.json({ results: records, count: records.length, total_pages: records.length ? 1 : 0 })
  : new Response(text(url.split('/').at(-1).replace('.htm', '')));

test('search is bounded to an exact case, official agency, fixed date window and stable page order', () => {
  const u = new URL(queryURL(caseId, '2026-01-01', '2026-10-12', 2));
  assert.equal(u.hostname, 'www.federalregister.gov'); assert.equal(u.searchParams.get('conditions[term]'), `"${caseId}"`);
  assert.equal(u.searchParams.get('conditions[publication_date][lte]'), '2026-10-12'); assert.equal(u.searchParams.get('page'), '2');
});
test('new final/correction discovery cannot activate cash rates or stage lamps; replay is idempotent', async () => {
  const fetchImpl = fixtureFetch([meta(), meta('2026-12345', 'Amended Final Results; Correction')]);
  const first = await discoverNotices({ ...options, fetchImpl });
  const second = await discoverNotices({ ...options, previous: first, fetchImpl });
  assert.equal(second.status, 'complete'); const notices = second.cases[caseId].notices;
  assert.equal(notices.length, 2);
  assert.equal(notices.find(n => n.document_id === '2026-12345').review_status, 'needs_review');
  assert.equal(notices.find(n => n.document_id === '2026-08489').review_status, 'catalogued_not_reconciled');
  for (const n of notices) {
    assert.equal(n.rate_activation_allowed, false); assert.equal(n.legal_effect_verified, false);
    assert.equal(n.margin_pct, undefined); assert.equal(n.deposit_rate_pct, undefined); assert.equal(n.stage, undefined);
  }
});
test('same document body changes invalidate the discovery baseline even for catalogued documents', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([meta()]) });
  const next = await discoverNotices({ ...options, previous: first, fetchImpl: fixtureFetch([meta()], id => source(id) + 'corrected') });
  const n = next.cases[caseId].notices[0]; assert.equal(n.review_status, 'changed_needs_review');
  assert.equal(n.previous_content_hash, first.cases[caseId].notices[0].content_hash); assert.notEqual(n.content_hash, n.previous_content_hash);
});
test('nested correction changes also invalidate metadata baseline without making a rate', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([{ ...meta(), corrections: [{ document_number: '2026-11111' }] }]) });
  const next = await discoverNotices({ ...options, previous: first, fetchImpl: fixtureFetch([{ ...meta(), corrections: [{ document_number: '2026-22222' }] }]) });
  assert.equal(next.cases[caseId].notices[0].review_status, 'changed_needs_review');
});
test('a missing old record is retained and flagged, not deleted or treated as revoked', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([meta()]) });
  const next = await discoverNotices({ ...options, previous: first, fetchImpl: fixtureFetch([]) });
  assert.equal(next.cases[caseId].notices.length, 1); assert.equal(next.cases[caseId].notices[0].review_status, 'missing_from_search_needs_review');
});
test('blocked body request preserves all previous notices/watermark and stops other case traffic', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([meta()]) });
  let calls = 0; const saves = [];
  const next = await discoverNotices({ ...options, previous: first, through: '2026-10-13', now: () => '2026-10-13T00:00:00Z',
    catalog: { ...catalog, cases: [...catalog.cases, { case_id: 'A-580-914', product: 'SAP' }] }, persist: async s => saves.push(structuredClone(s)),
    fetchImpl: async url => { calls++; return url.includes('/api/') ? Response.json({ results: [meta(), meta('2026-12345')], count: 2, total_pages: 1 }) : new Response('', { status: 429, headers: { 'retry-after': '18000' } }); } });
  assert.equal(calls, 2); assert.equal(next.status, 'partial'); assert.equal(next.cases[caseId].status, 'failed_preserved');
  assert.equal(next.cases[caseId].searched_through, '2026-10-12'); assert.equal(next.cases[caseId].last_success_at, first.cases[caseId].last_success_at);
  assert.deepEqual(next.cases[caseId].notices, first.cases[caseId].notices); assert.equal(next.blocked_until, '2026-10-13T05:00:00.000Z');
  assert.ok(saves.length); await assert.rejects(discoverNotices({ ...options, previous: next, now: () => '2026-10-13T01:00:00Z' }), /cooldown/);
});
test('partial pages/source errors never advance the case watermark or replace prior good data', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([meta()]) });
  for (const fetchImpl of [async () => Response.json({ results: [meta()], count: 2, total_pages: 1 }), fixtureFetch([meta()], () => '<html>Sign in</html>'), async () => { throw new Error('timeout'); }]) {
    const next = await discoverNotices({ ...options, previous: first, fetchImpl });
    assert.equal(next.status, 'partial'); assert.equal(next.cases[caseId].last_success_at, first.cases[caseId].last_success_at);
    assert.deepEqual(next.cases[caseId].notices, first.cases[caseId].notices);
  }
});
test('unrelated country docket mentioning this case only as a citation is not linked', async () => {
  const next = await discoverNotices({ ...options, fetchImpl: fixtureFetch([{ ...meta(), docket_ids: ['A-489-833'] }], id => `Federal Register [A-489-833] ${id} footnote cites ${caseId}`) });
  assert.equal(next.cases[caseId].notices.length, 0);
});
test('GovInfo line-wrapped case numbers remain discoverable in collective initiation tables', async () => {
  for (const table of ['A-\n 580-897.... 5/1/25', 'A-           5/1/25-4/30/26\n 580-897...........................', 'A-580-     5/1/25-4/30/26\n 897........................', 'A-580-  Walter Ankner (202) 482-8374.\n 897 (1st Review).']) {
    const next = await discoverNotices({ ...options, fetchImpl: fixtureFetch([{ ...meta(), title: 'Initiation of Antidumping and Countervailing Duty Administrative Reviews', docket_ids: [] }], id => `Federal Register ${id} Korea pipe, ${table}`) });
    assert.equal(next.status, 'complete'); assert.equal(next.cases[caseId].notices.length, 1);
    assert.equal(next.cases[caseId].notices[0].rate_activation_allowed, false);
  }
});
test('explicit resume skips completed cases only for the same window; normal reruns still detect changed sources', async () => {
  const first = await discoverNotices({ ...options, fetchImpl: fixtureFetch([meta()]) });
  const resumed = await discoverNotices({ ...options, previous: first, resumeIncomplete: true, fetchImpl: () => { throw new Error('must not fetch completed case'); } });
  assert.equal(resumed.status, 'complete'); assert.equal(resumed.requests_this_run, 0);
  assert.equal(resumed.cases[caseId].last_success_at, first.cases[caseId].last_success_at);
  const normal = await discoverNotices({ ...options, previous: first, fetchImpl: fixtureFetch([meta()], id => source(id) + 'revision') });
  assert.equal(normal.cases[caseId].notices[0].review_status, 'changed_needs_review');
});
test('request cap and date/checkpoint guards stop unbounded or regressed runs', async () => {
  let calls = 0;
  const next = await discoverNotices({ ...options, maxRequests: 1, fetchImpl: async url => { calls++; return fixtureFetch([meta()])(url); } });
  assert.equal(calls, 1); assert.equal(next.status, 'partial'); assert.equal(next.cases[caseId].searched_through, null);
  await assert.rejects(discoverNotices({ ...options, from: '2026-12-01' }), /window/);
  await assert.rejects(discoverNotices({ ...options, previous: { schema_version: 1, from: '2026-01-01', cases: { [caseId]: { searched_through: '2026-10-13' } } } }), /backwards/);
});

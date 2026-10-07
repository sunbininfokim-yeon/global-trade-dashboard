const { test } = require('node:test');
const assert = require('node:assert/strict');
const { archiveReports, githubSnapshot } = require('../archive-mailing-reports');
const report = id => ({ id, source_id: 'eia', title: { original: 'Official report' }, published_at: '2026-10-01T10:00:00Z', url: 'https://www.eia.gov/report', commodities: ['crude_oil'] });
test('only verified undated items may be explicitly skipped; dates are never invented', async () => {
  const undated = report('unknown'); delete undated.published_at;
  let saved;
  const result = await archiveReports({ document: { items: [report('dated'), undated] }, skipUndated: true, upsert: async (_table, rows, key) => { saved = rows; assert.equal(key, 'report_id'); } });
  assert.equal(result.reports, 1); assert.equal(result.skipped_undated, 1); assert.equal(result.partial, true);
  assert.equal(saved[0].report_id, 'dated'); assert.equal(saved[0].published_at, '2026-10-01T10:00:00.000Z');
});
test('missing date policy does not permit malformed dated items or unsafe URLs', async () => {
  for (const bad of [null, { ...report('bad'), published_at: 'invalid' }, { ...report('bad'), published_at: null, url: 'javascript:alert(1)' }]) {
    let writes = 0;
    await assert.rejects(archiveReports({ document: { items: [report('good'), bad] }, skipUndated: true, upsert: async () => writes++ }), /invalid_report_rows/);
    assert.equal(writes, 0);
  }
});
test('unclassified policy notices do not block classified reports, but require an explicit skip policy', async () => {
  const unclassified = { ...report('policy'), commodities: [] };
  await assert.rejects(archiveReports({ document: { items: [unclassified] }, skipUndated: true, upsert: async () => {} }), /invalid_report_rows/);
  let saved;
  const result = await archiveReports({ document: { items: [report('classified'), { ...unclassified, published_at: null }] }, skipUndated: true, skipUnclassified: true, upsert: async (_table, rows) => saved = rows });
  assert.equal(result.reports, 1); assert.equal(result.skipped, 1); assert.equal(result.skipped_unclassified, 1); assert.equal(result.skipped_undated, 1);
  assert.equal(saved[0].report_id, 'classified');
});
test('preview never writes and failed later batches safely replay by report ID', async () => {
  const document = { items: Array.from({ length: 51 }, (_, i) => report(String(i))) };
  await archiveReports({ document, dryRun: true, upsert: () => { throw Error('must not write'); } });
  const saved = new Map(); let calls = 0;
  const upsert = async (_table, rows) => { if (++calls === 2) throw Error('timeout'); for (const row of rows) saved.set(row.report_id, row); };
  await assert.rejects(archiveReports({ document, upsert }), /timeout/); assert.equal(saved.size, 50);
  calls = 2; await archiveReports({ document, upsert }); assert.equal(saved.size, 51);
});
test('GitHub snapshot pins the blob identity and fails closed on source failure', () => {
  const document = { items: [report('one')] };
  const run = (_exe, args) => { assert.match(args[1], /contents\/New%20for%20anti/); return { status: 0, stdout: JSON.stringify({ sha: 'blob-id', encoding: 'base64', content: Buffer.from(JSON.stringify(document)).toString('base64') }) }; };
  assert.deepEqual(githubSnapshot({ run }), { document, sha: 'blob-id' });
  assert.throws(() => githubSnapshot({ run: () => ({ status: 1 }) }), /report_snapshot_unavailable/);
});

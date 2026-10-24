const { test } = require('node:test');
const assert = require('node:assert/strict');
const { archiveReports, githubSnapshot, assertArchiveExecutionContext } = require('../archive-mailing-reports');
const { spawnSync } = require('node:child_process');
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
test('duplicate stable IDs keep the newest official edition in either feed order', async () => {
  const older = { ...report('permanent'), published_at: '2026-10-01T10:00:00Z', title: { original: 'Old release' } };
  const newer = { ...report('permanent'), published_at: '2026-10-08T10:00:00Z', title: { original: 'New release' } };
  for (const items of [[newer, older], [older, newer]]) {
    let saved;
    await archiveReports({ document: { items }, upsert: async (_table, rows) => saved = rows });
    assert.equal(saved.length, 1);
    assert.equal(saved[0].title, 'New release');
    assert.equal(saved[0].published_at, '2026-10-08T10:00:00.000Z');
  }
});
test('news headlines are never archived for mailing, only official reports', async () => {
  let saved = [];
  const headline = { ...report('news-1'), source_id: 'gn_idn_nickel_coal_en', publisher_type: 'news', summary: null, url: 'https://www.reuters.com/a' };
  const result = await archiveReports({ document: { items: [report('official'), headline] }, upsert: async (_table, rows) => saved = rows });
  assert.deepEqual(saved.map(r => r.report_id), ['official']);
  assert.equal(result.reports, 1); assert.equal(result.skipped_news, 1);
});
test('a malformed news item never blocks the official archive', async () => {
  let saved = [];
  const bare = { id: 'bare-news', publisher_type: 'news' };
  const result = await archiveReports({ document: { items: [report('official'), bare] }, upsert: async (_table, rows) => saved = rows });
  assert.deepEqual(saved.map(r => r.report_id), ['official']);
  assert.equal(result.skipped_news, 1); assert.equal(result.partial, false);
});
test('catalog news is excluded from old or incorrectly labelled snapshots', async () => {
  const items = [report('official'),
    { ...report('old-news'), source_id: 'gn_idn_nickel_coal_en' },
    { ...report('wrong-type'), source_id: 'gn_idn_nickel_coal_en', publisher_type: 'official' },
    { ...report('case'), publisher_type: ' News ' },
    { ...report('institution'), source_id: 'my_mpoc_news' }];
  let saved;
  const result = await archiveReports({ document: { items }, upsert: async (_table, rows) => saved = rows });
  assert.deepEqual(saved.map(r => r.report_id), ['official', 'institution']);
  assert.equal(result.skipped_news, 3);
});
test('only main schedule/manual Actions writes are accepted; local recovery is allowed', () => {
  const main = { GITHUB_ACTIONS: 'true', GITHUB_REPOSITORY: 'sunbininfokim-yeon/global-trade-dashboard', GITHUB_REF: 'refs/heads/main', GITHUB_EVENT_NAME: 'schedule' };
  assert.doesNotThrow(() => assertArchiveExecutionContext({}));
  assert.doesNotThrow(() => assertArchiveExecutionContext(main));
  assert.doesNotThrow(() => assertArchiveExecutionContext({ ...main, GITHUB_EVENT_NAME: 'workflow_dispatch' }));
  for (const overrides of [{ GITHUB_REF: 'refs/heads/work' }, { GITHUB_REF: 'refs/pull/1/merge' },
    { GITHUB_REF: 'refs/tags/main' }, { GITHUB_REF: '' }, { GITHUB_REPOSITORY: 'fork/repo' },
    { GITHUB_EVENT_NAME: 'pull_request_target' }, { GITHUB_EVENT_NAME: undefined }]) {
    assert.throws(() => assertArchiveExecutionContext({ ...main, ...overrides }), /mailing_archive_untrusted_execution/);
  }
});
test('default DB adapter rejects a branch before reading a snapshot; preview remains usable', () => {
  const script = `const {archiveReports}=require(${JSON.stringify(require.resolve('../archive-mailing-reports'))});
    (async()=>{
      try { await archiveReports({file:'/missing-archive-snapshot.json'}); process.exitCode=2; }
      catch(e) { if(e.message!=='mailing_archive_untrusted_execution') throw e; }
      const result=await archiveReports({document:{items:[]},dryRun:true});
      if(result.mode!=='preview') process.exitCode=3;
    })().catch(()=>{process.exitCode=4});`;
  const result = spawnSync(process.execPath, ['-e', script], { encoding: 'utf8',
    env: { ...process.env, GITHUB_ACTIONS: 'true', GITHUB_REF: 'refs/heads/work', GITHUB_EVENT_NAME: 'workflow_dispatch' } });
  assert.equal(result.status, 0, result.stderr);
});

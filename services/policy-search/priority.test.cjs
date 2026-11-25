'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { PGlite } = require('@electric-sql/pglite');
const { buildPrioritySql } = require('../../scripts/policy-search-priority-sql');

test('queue priority preview is read-only and promotion preserves active work and vectors', async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      create table bills (
        bill_id text primary key, congress_number int, latest_action_date date,
        embedding int, embedding_model text
      );
      create table public_laws (public_law_id text primary key, congress_number int, enacted_date date);
      create table policy_search_passages (document_id text, embedding int, embedding_model text);
      create table policy_search_jobs (
        document_id text primary key, source_type text, source_id text,
        status text, claim_token text, attempts int, retry_at timestamptz, revision int, priority int
      );
      insert into bills values
        ('missing',119,current_date-1,null,null),
        ('legacy-only',119,current_date-2,1,'gemini-embedding-001'),
        ('passage-only',119,current_date-3,null,null),
        ('wrong-model',119,current_date-4,1,'old-model'),
        ('processing',119,current_date-5,null,null),
        ('deferred',119,current_date-6,null,null),
        ('urgent',119,current_date-7,null,null),
        ('historical',118,current_date-8,null,null);
      insert into public_laws values
        ('recent',119,current_date-15),('old',119,current_date-91),('with-passage',119,current_date-1);
      insert into policy_search_passages values
        ('bill:passage-only',1,'gemini-embedding-001'),
        ('public_law:with-passage',1,'gemini-embedding-001');
      insert into policy_search_jobs
        select 'bill:'||bill_id,'bill',bill_id,'queued',null,0,now(),3,20 from bills
        union all select 'public_law:'||public_law_id,'public_law',public_law_id,'queued',null,0,now(),4,20 from public_laws;
      update policy_search_jobs set status='processing',claim_token='claimed',attempts=2 where source_id='processing';
      update policy_search_jobs set retry_at=now()+interval '1 day' where source_id='deferred';
      update policy_search_jobs set priority=45 where source_id='urgent';
    `);

    const queue = async () => (await db.query('select * from policy_search_jobs order by document_id')).rows;
    const initial = await queue();
    await db.exec('begin read only');
    const preview = (await db.query(buildPrioritySql({ limit: 2 }))).rows[0];
    await db.exec('commit');
    assert.equal(preview.eligible_bills, 2);
    assert.equal(preview.eligible_recent_public_laws, 1);
    assert.equal(preview.promoted, null);
    assert.deepEqual(preview.documents.map(item => item.document_id), ['public_law:recent', 'bill:missing']);
    assert.deepEqual(await queue(), initial);

    const applied = (await db.query(buildPrioritySql({ limit: 2, apply: true }))).rows[0];
    assert.equal(applied.promoted, 2);
    assert.ok(applied.documents.every(item => item.promoted));
    assert.deepEqual(await queue(), initial.map(job => ({
      ...job,
      priority: job.source_id === 'recent' ? 31 : job.source_id === 'missing' ? 30 : job.priority,
    })));
    const next = (await db.query(buildPrioritySql())).rows[0];
    assert.deepEqual(next.documents.map(item => item.document_id), ['bill:wrong-model']);
    assert.equal((await db.query('select count(*) n from policy_search_passages')).rows[0].n, 2);
  } finally {
    await db.close();
  }
});

test('batch bounds reject invalid values before generating SQL', () => {
  for (const limit of [0, -1, 101, 1.5, NaN, '2; delete']) {
    assert.throws(() => buildPrioritySql({ limit }), /--limit/);
  }
});
